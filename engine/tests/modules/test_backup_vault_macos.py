from __future__ import annotations

import plistlib
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from devboost.core.errors import GithubError, NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import age, github
from devboost.model import Ctx
from devboost.modules import _credentials, server
from devboost.modules.apps import ObsidianSync
from devboost.modules.server import B2_MAC_SCRIPT, ResticB2
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
SECRETS = {
    "B2_ACCOUNT_ID": "id",
    "B2_ACCOUNT_KEY": "key",
    "RESTIC_REPOSITORY": "b2:bucket:path",
    "RESTIC_PASSWORD": "p w$1",
}


def _plist(home: Path, name: str) -> dict[str, object]:
    path = home / "Library" / "LaunchAgents" / f"dev.devboost.{name}.plist"
    return plistlib.loads(path.read_bytes())  # type: ignore[no-any-return]


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


# ── restic-b2 ────────────────────────────────────────────────────────────────
def test_restic_b2_on_macos_schedules_a_nightly_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server, "_secret", lambda ctx, f: SECRETS.get(f))
    ctx = Ctx(os=MAC, ex=RuleExecutor())
    ResticB2().install(ctx)
    data = _plist(tmp_path, "restic-b2")
    assert data["ProgramArguments"] == ["/bin/sh", "-c", B2_MAC_SCRIPT]
    assert data["StartCalendarInterval"] == {"Hour": 0, "Minute": 0}
    env = tmp_path / ".config" / "devboost" / "restic-b2.env"
    assert "RESTIC_PASSWORD='p w$1'\n" in env.read_text(encoding="utf-8")  # sh-sourceable
    assert oct(env.stat().st_mode)[-3:] == "600"
    assert (tmp_path / ".config" / "devboost" / "restic-include").exists()
    assert not any("systemctl" in c for c in ctx.ex.calls)  # type: ignore[attr-defined]
    assert ResticB2().verify(ctx) is True


def test_restic_b2_secrets_never_reach_argv_or_the_plist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    distinct = {k: f"SeCrEt-{k}-v4lue" for k in SECRETS}
    monkeypatch.setattr(server, "_secret", lambda ctx, f: distinct.get(f))
    ctx = Ctx(os=MAC, ex=RuleExecutor())
    ResticB2().install(ctx)
    argv = " ".join(" ".join(c) for c in ctx.ex.calls)  # type: ignore[attr-defined]
    plist = (tmp_path / "Library" / "LaunchAgents" / "dev.devboost.restic-b2.plist").read_text(
        encoding="utf-8"
    )
    for secret in distinct.values():
        assert secret not in argv
        assert secret not in plist


def test_b2_mac_script_matches_the_linux_unit_semantics() -> None:
    assert B2_MAC_SCRIPT.startswith('set -a; . "$HOME/.config/devboost/restic-b2.env"; set +a; ')
    assert "restic init >/dev/null 2>&1; " in B2_MAC_SCRIPT  # like ExecStartPre=-
    assert (
        'restic backup --files-from "$HOME/.config/devboost/restic-include" && '
        "restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune"
    ) in B2_MAC_SCRIPT  # ExecStartPost only after a successful ExecStart
    assert "/usr/bin/restic" not in B2_MAC_SCRIPT


def test_restic_b2_on_macos_without_secrets_wires_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server, "_secret", lambda ctx, f: None)
    ctx = Ctx(os=MAC, ex=RuleExecutor(rules=[(("--versions", "restic"), Result(1))]))
    with pytest.raises(NeedsUser, match="secrets") as exc:
        ResticB2().install(ctx)
    assert "RESTIC_PASSWORD" in exc.value.how_to_fix
    assert ["brew", "install", "--formula", "-y", "restic"] in ctx.ex.calls  # type: ignore[attr-defined]
    assert not (tmp_path / "Library" / "LaunchAgents").exists()
    assert not (tmp_path / ".config" / "devboost" / "restic-b2.env").exists()


def test_restic_b2_requires_homebrew_on_macos() -> None:
    """M4-D9: the macOS strategy brews restic, so the module requires Homebrew."""
    assert "homebrew" in [c.name for c in ResticB2.requires]
    assert server._MacResticB2.uses_brew is True


def test_linux_env_file_format_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server, "_secret", lambda ctx, f: SECRETS.get(f))
    envfile = server._b2_prepare(Ctx(os=FEDORA, ex=FakeExecutor()))
    assert envfile is not None
    assert envfile.read_text(encoding="utf-8") == (
        "B2_ACCOUNT_ID=id\nB2_ACCOUNT_KEY=key\n"
        "RESTIC_REPOSITORY=b2:bucket:path\nRESTIC_PASSWORD=p w$1\n"
    )
    assert _mode(envfile) == 0o600


def test_env_file_replaces_a_loose_or_linked_file_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A world-readable leftover becomes 0600, and a symlink planted at the env path is
    replaced, never written through (the secrets must not land in its target)."""
    monkeypatch.setattr(server, "_secret", lambda ctx, f: SECRETS.get(f))
    d = tmp_path / ".config" / "devboost"
    d.mkdir(parents=True)
    target = tmp_path / "elsewhere"
    target.write_text("untouched\n", encoding="utf-8")
    (d / "restic-b2.env").symlink_to(target)
    envfile = server._b2_prepare(Ctx(os=MAC, ex=FakeExecutor()), shell_quoted=True)
    assert envfile is not None and not envfile.is_symlink()
    assert _mode(envfile) == 0o600
    assert target.read_text(encoding="utf-8") == "untouched\n"
    assert not [p.name for p in d.iterdir() if p.name.startswith(".restic-b2.env")]

    envfile.chmod(0o644)
    server._b2_prepare(Ctx(os=MAC, ex=FakeExecutor()), shell_quoted=True)
    assert _mode(envfile) == 0o600


def test_secret_decrypts_with_the_keychain_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = tmp_path / "materialized-key"
    seen: list[Path] = []

    @contextmanager
    def fake_age_key(ctx: Ctx) -> Iterator[Path | None]:
        yield key

    def fake_decrypt(ctx: Ctx, bundle: Path, k: Path) -> dict[str, str]:
        seen.append(k)
        return {"B2_ACCOUNT_ID": "id"}

    monkeypatch.setattr(server, "age_key", fake_age_key)
    monkeypatch.setattr(age, "decrypt", fake_decrypt)
    assert server._secret(Ctx(os=MAC, ex=FakeExecutor()), "B2_ACCOUNT_ID") == "id"
    assert seen == [key]


def test_secret_is_none_without_any_key(monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def no_key(ctx: Ctx) -> Iterator[Path | None]:
        yield None

    monkeypatch.setattr(server, "age_key", no_key)
    assert server._secret(Ctx(os=MAC, ex=FakeExecutor()), "B2_ACCOUNT_ID") is None


def test_keychain_key_is_read_without_argv_and_removed_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end through the real `age_key`: the identity comes from `security … -w`
    stdout, lives in a temp file only while `age -d` runs, and is never on any argv."""
    monkeypatch.setenv("DEVBOOST_SECRETS_KEY", str(tmp_path / "no-such-key.txt"))
    bundle = tmp_path / "secrets.age"
    bundle.write_bytes(b"x")
    monkeypatch.setenv("DEVBOOST_SECRETS", str(bundle))
    identity = "AGE-SECRET-KEY-1TESTTESTTEST"
    ex = RuleExecutor(rules=[
        (("security", "find-generic-password"), Result(0, identity + "\n")),
        (("age", "-d"), Result(0, '{"B2_ACCOUNT_ID": "id"}')),
    ])
    assert server._secret(Ctx(os=MAC, ex=ex), "B2_ACCOUNT_ID") == "id"
    assert not any(identity in " ".join(c) for c in ex.calls)
    age_call = next(c for c in ex.calls if c[:2] == ["age", "-d"])
    assert not Path(age_call[age_call.index("-i") + 1]).exists()


# ── obsidian-sync ────────────────────────────────────────────────────────────
def _vault_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    vault = tmp_path / "Vault"
    monkeypatch.setenv("VAULT_DIR", str(vault))
    monkeypatch.setenv("DEVBOOST_VAULT_REPO", "notes")
    (tmp_path / ".ssh").mkdir(mode=0o700)
    (tmp_path / ".ssh" / "devboost-vault").write_text("priv", encoding="utf-8")
    (tmp_path / ".ssh" / "devboost-vault.pub").write_text("ssh-ed25519 AAA", encoding="utf-8")
    monkeypatch.setattr(
        _credentials, "github_credentials",
        lambda ctx: {"GIT_USER": "alice", "GIT_EMAIL": "a@x", "GITHUB_PAT": "p"},
    )
    monkeypatch.setattr(github, "add_deploy_key", lambda *a, **k: True)
    return vault


def test_obsidian_sync_on_macos_is_a_daily_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = _vault_env(tmp_path, monkeypatch)
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    ObsidianSync().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["git", "clone", "git@devboost-vault.github.com:alice/notes.git", str(vault)] in calls
    data = _plist(tmp_path, "obsidian-sync")
    assert data["StartCalendarInterval"] == {"Hour": 0, "Minute": 0}
    assert data["ProgramArguments"] == [
        "/bin/sh", "-c",
        f"cd {vault} && git add -A && git commit -m auto >/dev/null 2>&1; "
        "git pull --rebase && git push",
    ]
    assert not any("systemctl" in c for c in calls)
    (vault / ".git").mkdir(parents=True)
    assert ObsidianSync().verify(ctx) is True


def test_obsidian_sync_quotes_a_vault_path_with_spaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _vault_env(tmp_path, monkeypatch)
    vault = tmp_path / "My Vault"
    monkeypatch.setenv("VAULT_DIR", str(vault))
    ObsidianSync().install(Ctx(os=MAC, ex=FakeExecutor()))
    script = _plist(tmp_path, "obsidian-sync")["ProgramArguments"][2]  # type: ignore[index]
    assert script.startswith(f"cd '{vault}' && ")


def test_obsidian_sync_on_macos_skips_without_a_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Final review I2: no repo is `blocked` with the fix (as in M3), never a verify fail."""
    monkeypatch.delenv("DEVBOOST_VAULT_REPO", raising=False)
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    with pytest.raises(NeedsUser, match="no vault repo configured") as exc:
        ObsidianSync().install(ctx)
    assert "export DEVBOOST_VAULT_REPO=" in exc.value.how_to_fix
    assert ctx.ex.calls == []  # type: ignore[attr-defined]
    assert ObsidianSync().verify(ctx) is False


def test_obsidian_sync_without_github_credentials_needs_the_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _vault_env(tmp_path, monkeypatch)
    monkeypatch.setattr(_credentials, "github_credentials", lambda ctx: None)
    with pytest.raises(NeedsUser, match="GitHub credentials"):
        ObsidianSync().install(Ctx(os=MAC, ex=FakeExecutor()))


def test_obsidian_sync_deploy_key_failure_needs_the_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _vault_env(tmp_path, monkeypatch)

    def _refused(*a: object, **k: object) -> bool:
        raise GithubError("403")

    monkeypatch.setattr(github, "add_deploy_key", _refused)
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    with pytest.raises(NeedsUser, match="deploy key"):
        ObsidianSync().install(ctx)
    assert not any(c[:2] == ["git", "clone"] for c in ctx.ex.calls)  # type: ignore[attr-defined]


def test_a_zero_config_mac_run_blocks_obsidian_sync_and_restic_b2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Runner contract: with no env and no secrets, neither module ends `fail`."""
    from devboost.core.plan import build_plan
    from devboost.core.registry import load
    from devboost.core.runner import run_plan

    monkeypatch.delenv("DEVBOOST_VAULT_REPO", raising=False)
    monkeypatch.setattr(server, "_secret", lambda ctx, f: None)
    monkeypatch.setattr(_credentials, "github_credentials", lambda ctx: None)
    mods = load()
    plan = [p for p in build_plan(["obsidian-sync", "restic-b2"], mods, MAC,
                                  gpu_marker=tmp_path / "none")
            if p.name in {"obsidian-sync", "restic-b2"}]
    results = run_plan(plan, mods, Ctx(os=MAC, ex=RuleExecutor()))
    status = {r.name: r.status for r in results}
    assert status == {"obsidian-sync": "blocked", "restic-b2": "blocked"}
