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
    ) -> Result:
        super().run(argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive)
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
        ) -> Result:
            super().run(argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive)
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


def test_import_key_sends_key_on_stdin_never_argv(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from devboost.cli import secrets_cmd
    from devboost.cli.app import app

    keyfile = home / "age-key.txt"
    keyfile.write_text("AGE-SECRET-KEY-1SECRET\n", encoding="utf-8")
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
        ) -> Result:
            stdins.append(stdin)
            return super().run(
                argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive
            )

    ex = _Ex()
    monkeypatch.setattr(secrets_cmd, "RealExecutor", lambda: ex)
    monkeypatch.setattr(osinfo, "detect", lambda: MAC)
    res = CliRunner().invoke(app, ["secrets", "import-key", str(keyfile)])
    assert res.exit_code == 0, res.output
    assert ex.calls == [["security", "-i"]]
    assert stdins == [
        "add-generic-password -U -a devboost -s devboost-age -w AGE-SECRET-KEY-1SECRET\n"
    ]
    assert "AGE-SECRET-KEY-1SECRET" not in res.output


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
