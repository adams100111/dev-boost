from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from devboost.core import osinfo
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules import _credentials as creds
from devboost.modules import secrets
from devboost.modules.secrets import Secrets

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
_JSON = json.dumps({"GIT_USER": "alice", "GIT_EMAIL": "a@x", "GITHUB_PAT": "ghp_x"})
_GH_USER = json.dumps({"login": "alice", "email": "a@x"})
#: `-c core.askPass=` — no GUI prompt even when the user configured an askpass helper.
FILL = ("git", "-c", "core.askPass=", "credential", "fill")


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")
    monkeypatch.setenv("DEVBOOST_BOOTSTRAP_DIR", str(tmp_path / "boot"))
    monkeypatch.delenv("DEVBOOST_SECRETS", raising=False)
    monkeypatch.delenv("DEVBOOST_SECRETS_KEY", raising=False)
    return tmp_path


class _GhEx(FakeExecutor):
    """gh authenticated as alice; no bundle."""

    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        interactive: bool = False,
        timeout: float | None = None,
    ) -> Result:
        super().run(
            argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive,
            timeout=timeout,
        )
        if list(argv[:3]) == ["gh", "api", "user"]:
            return Result(0, stdout=_GH_USER)
        if list(argv[:3]) == ["gh", "auth", "token"]:
            return Result(0, stdout="gho_tok\n")
        return Result(0)


def test_macos_gh_source_uses_gh_setup_git_and_no_plaintext(home: Path) -> None:
    ex = _GhEx(present={"gh"})
    Secrets().install(Ctx(os=MAC, ex=ex))
    assert ["gh", "auth", "setup-git"] in ex.calls
    assert ["git", "config", "--global", "credential.helper", "store"] not in ex.calls
    assert not (home / ".git-credentials").exists()


def test_macos_bundle_source_uses_osxkeychain(home: Path) -> None:
    boot = home / "boot"
    boot.mkdir()
    (boot / "secrets.age").write_text("cipher", encoding="utf-8")
    (boot / "age-key.txt").write_text("AGE-SECRET-KEY-1X", encoding="utf-8")
    stdins: list[str | None] = []

    class _Ex(FakeExecutor):
        def run(
            self,
            argv: Sequence[str],
            *,
            sudo: bool = False,
            stdin: str | None = None,
            env: Mapping[str, str] | None = None,
            cwd: Path | None = None,
            interactive: bool = False,
            timeout: float | None = None,
        ) -> Result:
            super().run(
                argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive,
                timeout=timeout,
            )
            stdins.append(stdin)
            return Result(0, stdout=_JSON) if argv[0] == "age" else Result(0)

    ex = _Ex(present={"age"})
    Secrets().install(Ctx(os=MAC, ex=ex))
    assert ["git", "config", "--global", "credential.helper", "osxkeychain"] in ex.calls
    i = ex.calls.index(["git", "credential", "approve"])
    assert stdins[i] == "protocol=https\nhost=github.com\nusername=alice\npassword=ghp_x\n\n"
    # The token travels on stdin only — never in any argv.
    assert not any("ghp_x" in " ".join(c) for c in ex.calls)
    assert not (home / ".git-credentials").exists()


def test_linux_still_writes_git_credentials(home: Path) -> None:
    ex = _GhEx(present={"gh"})
    Secrets().install(Ctx(os=FEDORA, ex=ex))
    assert (home / ".git-credentials").read_text(encoding="utf-8").strip() == (
        "https://alice:gho_tok@github.com"
    )


def test_age_key_from_keychain_is_a_temp_0600_file_removed_after(home: Path) -> None:
    ex = FakeExecutor(scripts={"security": Result(0, stdout="AGE-SECRET-KEY-1Z\n")})
    with secrets.age_key(Ctx(os=MAC, ex=ex)) as key:
        assert key is not None
        assert key.read_text(encoding="utf-8").strip() == "AGE-SECRET-KEY-1Z"
        assert (key.stat().st_mode & 0o777) == 0o600
        kept = key
    assert not kept.exists()
    assert [
        "security", "find-generic-password", "-a", "devboost", "-s", "devboost-age", "-w",
    ] in ex.calls


def test_age_key_none_when_nothing_available(home: Path) -> None:
    ex = FakeExecutor(scripts={"security": Result(44)})
    with secrets.age_key(Ctx(os=MAC, ex=ex)) as key:
        assert key is None


def test_github_credentials_order_gh_then_git_credentials(home: Path) -> None:
    assert creds.github_credentials(Ctx(os=MAC, ex=_GhEx(present={"gh"}))) == {
        "GIT_USER": "alice", "GIT_EMAIL": "a@x", "GITHUB_PAT": "gho_tok",
    }
    (home / ".git-credentials").write_text("https://bob:ghp_b@github.com\n", encoding="utf-8")
    no_gh = Ctx(os=FEDORA, ex=FakeExecutor())
    assert creds.github_credentials(no_gh) == {
        "GIT_USER": "bob", "GIT_EMAIL": "", "GITHUB_PAT": "ghp_b",
    }


def test_github_credentials_none(home: Path) -> None:
    assert creds.github_credentials(Ctx(os=FEDORA, ex=FakeExecutor())) is None


class _StdinEx(FakeExecutor):
    """Records stdin alongside argv; answers from ``replies`` (argv prefix → Result)."""

    def __init__(self, replies: dict[tuple[str, ...], Result] | None = None) -> None:
        super().__init__()
        self.stdins: list[str | None] = []
        self.envs: list[Mapping[str, str] | None] = []
        self.replies = replies or {}

    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        interactive: bool = False,
        timeout: float | None = None,
    ) -> Result:
        super().run(
            argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive,
            timeout=timeout,
        )
        self.stdins.append(stdin)
        self.envs.append(env)
        for prefix, res in self.replies.items():
            if tuple(argv[: len(prefix)]) == prefix:
                return res
        return Result(0)


_AGE_KEYGEN_FILE = (
    "# created: 2026-09-19T10:00:00+02:00\n"
    "# public key: age1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq\n"
    "AGE-SECRET-KEY-1SECRET\n"
)


def _import_key(
    monkeypatch: pytest.MonkeyPatch, keyfile: Path, os_info: OsInfo = MAC
) -> tuple[_StdinEx, object]:
    from typer.testing import CliRunner

    from devboost.cli import secrets_cmd
    from devboost.cli.app import app

    ex = _StdinEx()
    monkeypatch.setattr(secrets_cmd, "RealExecutor", lambda: ex)
    monkeypatch.setattr(osinfo, "detect", lambda: os_info)
    return ex, CliRunner().invoke(app, ["secrets", "import-key", str(keyfile)])


def test_import_key_accepts_age_keygen_file_and_sends_only_key_on_stdin(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    keyfile = home / "age-key.txt"
    keyfile.write_text(_AGE_KEYGEN_FILE, encoding="utf-8")
    ex, res = _import_key(monkeypatch, keyfile)
    assert res.exit_code == 0, res.output  # type: ignore[attr-defined]
    assert ex.calls == [["security", "-i"]]
    assert ex.stdins == [
        "add-generic-password -U -a devboost -s devboost-age -w AGE-SECRET-KEY-1SECRET\n"
    ]
    assert "AGE-SECRET-KEY-1SECRET" not in res.output  # type: ignore[attr-defined]


def test_import_key_rejects_file_without_key(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    keyfile = home / "age-key.txt"
    keyfile.write_text("# created: x\n# public key: age1qqq\n\n", encoding="utf-8")
    ex, res = _import_key(monkeypatch, keyfile)
    assert res.exit_code != 0  # type: ignore[attr-defined]
    assert ex.calls == []


def test_import_key_rejects_file_with_two_keys(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    keyfile = home / "age-key.txt"
    keyfile.write_text("AGE-SECRET-KEY-1A\nAGE-SECRET-KEY-1B\n", encoding="utf-8")
    ex, res = _import_key(monkeypatch, keyfile)
    assert res.exit_code != 0  # type: ignore[attr-defined]
    assert ex.calls == []


def test_import_key_is_macos_only(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    keyfile = home / "age-key.txt"
    keyfile.write_text(_AGE_KEYGEN_FILE, encoding="utf-8")
    ex, res = _import_key(monkeypatch, keyfile, os_info=FEDORA)
    assert res.exit_code != 0  # type: ignore[attr-defined]
    assert ex.calls == []


def test_github_credentials_falls_back_to_git_credential_fill(home: Path) -> None:
    ex = _StdinEx({FILL: Result(0, stdout="protocol=https\nhost=github.com\n"
                                           "username=carol\npassword=ghp_kc\n")})
    assert creds.github_credentials(Ctx(os=MAC, ex=ex)) == {
        "GIT_USER": "carol", "GIT_EMAIL": "", "GITHUB_PAT": "ghp_kc",
    }
    i = ex.calls.index(list(FILL))
    assert ex.stdins[i] == "protocol=https\nhost=github.com\n\n"
    # No terminal prompt and no GUI askpass pop-up in an unattended run.
    assert ex.envs[i] == {"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "", "SSH_ASKPASS": ""}


def test_git_credential_fill_without_password_is_none(home: Path) -> None:
    ex = _StdinEx({FILL: Result(0, stdout="username=carol\n")})
    assert creds.github_credentials(Ctx(os=MAC, ex=ex)) is None


def test_github_credentials_skips_incomplete_bundle(home: Path) -> None:
    boot = home / "boot"
    boot.mkdir()
    (boot / "secrets.age").write_text("cipher", encoding="utf-8")
    (boot / "age-key.txt").write_text("AGE-SECRET-KEY-1X", encoding="utf-8")
    partial = json.dumps({"GIT_USER": "alice", "GIT_EMAIL": "a@x"})  # no GITHUB_PAT
    ex = _StdinEx({
        ("age",): Result(0, stdout=partial),
        ("gh", "api", "user"): Result(0, stdout=_GH_USER),
        ("gh", "auth", "token"): Result(0, stdout="gho_tok\n"),
    })
    ex.present = {"gh", "age"}
    assert creds.github_credentials(Ctx(os=MAC, ex=ex)) == {
        "GIT_USER": "alice", "GIT_EMAIL": "a@x", "GITHUB_PAT": "gho_tok",
    }
    assert ["age", "-d"] in [c[:2] for c in ex.calls]  # the bundle was really tried


def test_github_credentials_reads_bundle_with_keychain_key(home: Path) -> None:
    boot = home / "boot"
    boot.mkdir()
    (boot / "secrets.age").write_text("cipher", encoding="utf-8")  # no age-key.txt
    seen: dict[str, str] = {}

    class _Ex(_StdinEx):
        def run(
            self,
            argv: Sequence[str],
            *,
            sudo: bool = False,
            stdin: str | None = None,
            env: Mapping[str, str] | None = None,
            cwd: Path | None = None,
            interactive: bool = False,
            timeout: float | None = None,
        ) -> Result:
            if argv[0] == "age":
                key = Path(argv[argv.index("-i") + 1])
                seen["path"] = str(key)
                seen["key"] = key.read_text(encoding="utf-8").strip()
            return super().run(
                argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive
            )

    ex = _Ex({
        ("security",): Result(0, stdout="AGE-SECRET-KEY-1KC\n"),
        ("age",): Result(0, stdout=_JSON),
    })
    ex.present = {"age"}
    assert creds.github_credentials(Ctx(os=MAC, ex=ex)) == json.loads(_JSON)
    assert seen["key"] == "AGE-SECRET-KEY-1KC"
    assert seen["path"] != str(boot / "age-key.txt")
    assert not Path(seen["path"]).exists()  # temp key removed after decrypt


def test_ssh_setup_without_credentials_is_non_blocking(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from devboost.exec.primitives import github
    from devboost.modules.ssh_setup import SshSetup

    monkeypatch.setenv("XDG_STATE_HOME", str(home / "state"))
    ssh = home / ".ssh"
    ssh.mkdir(mode=0o700)
    (ssh / "id_ed25519").write_text("priv", encoding="utf-8")
    (ssh / "id_ed25519.pub").write_text("ssh-ed25519 AAA", encoding="utf-8")

    def _never(*a: object, **k: object) -> bool:
        raise AssertionError("must not upload without credentials")

    monkeypatch.setattr(github, "upload_ssh_key", _never)
    ctx = Ctx(os=MAC, ex=FakeExecutor(scripts={"security": Result(44)}))
    SshSetup().install(ctx)  # no bundle, no gh, no key: warns, does not raise
    assert SshSetup().verify(ctx) is False


def test_macos_bundle_source_approve_failure_raises_without_token(home: Path) -> None:
    from devboost.core.errors import InstallError

    boot = home / "boot"
    boot.mkdir()
    (boot / "secrets.age").write_text("cipher", encoding="utf-8")
    (boot / "age-key.txt").write_text("AGE-SECRET-KEY-1X", encoding="utf-8")
    ex = _StdinEx({
        ("age",): Result(0, stdout=_JSON),
        ("git", "credential", "approve"): Result(1, stderr="keychain locked"),
    })
    ex.present = {"age"}
    with pytest.raises(InstallError) as exc:
        Secrets().install(Ctx(os=MAC, ex=ex))
    assert "ghp_x" not in str(exc.value)
    assert "git credential approve" in str(exc.value)


def test_macos_verify_true_when_keychain_yields_token(home: Path) -> None:
    ex = _StdinEx({
        FILL: Result(
            0, stdout="protocol=https\nhost=github.com\nusername=carol\npassword=ghp_kc\n"
        ),
    })
    assert Secrets().verify(Ctx(os=MAC, ex=ex)) is True


def test_macos_verify_false_when_helper_set_but_no_token(home: Path) -> None:
    # credential.helper=osxkeychain alone proves nothing: the keychain may be empty.
    ex = _StdinEx({
        ("git", "config", "--global", "credential.helper"): Result(0, stdout="osxkeychain\n"),
        FILL: Result(128, stderr="terminal prompts disabled"),
    })
    assert Secrets().verify(Ctx(os=MAC, ex=ex)) is False


def test_git_credentials_line_is_url_decoded(home: Path) -> None:
    # git's store helper percent-encodes; an email-style username arrives as %40.
    (home / ".git-credentials").write_text(
        "https://bob%40corp.com:ghp%2Fb@github.com\n", encoding="utf-8"
    )
    assert creds.github_credentials(Ctx(os=FEDORA, ex=FakeExecutor())) == {
        "GIT_USER": "bob@corp.com", "GIT_EMAIL": "", "GITHUB_PAT": "ghp/b",
    }


def test_github_credentials_skips_bundle_when_age_missing(home: Path) -> None:
    # A lookup is read-only: no `age` on PATH means skip the bundle, never install age.
    boot = home / "boot"
    boot.mkdir()
    (boot / "secrets.age").write_text("cipher", encoding="utf-8")
    (boot / "age-key.txt").write_text("AGE-SECRET-KEY-1X", encoding="utf-8")
    ex = _StdinEx({
        ("gh", "api", "user"): Result(0, stdout=_GH_USER),
        ("gh", "auth", "token"): Result(0, stdout="gho_tok\n"),
    })
    ex.present = {"gh"}
    assert creds.github_credentials(Ctx(os=MAC, ex=ex)) == {
        "GIT_USER": "alice", "GIT_EMAIL": "a@x", "GITHUB_PAT": "gho_tok",
    }
    assert not any(c[0] in ("age", "brew", "dnf", "pacman", "sudo") for c in ex.calls)
