from __future__ import annotations

import json
from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import github
from devboost.model import Ctx
from devboost.modules.apps import (
    Bitwarden,
    Bruno,
    Flameshot,
    Localsend,
    Obsidian,
    ObsidianSync,
    Vlc,
)
from devboost.modules.dev_hygiene import AspireGc
from devboost.modules.secrets import Secrets
from devboost.modules.ssh_setup import SshSetup

FEDORA = OsInfo("fedora", "fedora", "x86_64")
UBUNTU = OsInfo(distro="ubuntu", family="debian", arch="x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def _ubuntu_ctx(**kw: object) -> Ctx:
    return Ctx(os=UBUNTU, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_flatpak_apps_install_and_are_gui() -> None:
    assert Obsidian.gui and Bruno.gui and Vlc.gui
    ctx = _ctx()
    Obsidian().install(ctx)
    assert ["flatpak", "install", "-y", "flathub", "md.obsidian.Obsidian"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_flatpak_app_verify() -> None:
    ctx = _ctx(scripts={"flatpak": Result(0, stdout="md.obsidian.Obsidian - Obsidian")})
    assert Obsidian().verify(ctx) is True


def test_obsidian_sync_requires() -> None:
    assert {Obsidian, Secrets, SshSetup} <= set(ObsidianSync.requires)


def test_obsidian_sync_skips_without_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEVBOOST_VAULT_REPO", raising=False)
    ctx = _ctx()
    ObsidianSync().install(ctx)  # non-blocking, no calls
    assert ctx.ex.calls == []  # type: ignore[attr-defined]


def test_obsidian_sync_provisions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = tmp_path / "secrets.age"
    bundle.write_text("c", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "Vault"))
    monkeypatch.setenv("DEVBOOST_SECRETS", str(bundle))
    monkeypatch.setenv("DEVBOOST_SECRETS_KEY", str(tmp_path / "key"))
    monkeypatch.setenv("DEVBOOST_VAULT_REPO", "notes")
    (tmp_path / ".ssh").mkdir(mode=0o700)
    (tmp_path / ".ssh" / "devboost-vault").write_text("priv", encoding="utf-8")
    (tmp_path / ".ssh" / "devboost-vault.pub").write_text("ssh-ed25519 AAA", encoding="utf-8")
    monkeypatch.setattr(github, "add_deploy_key", lambda *a, **k: True)

    payload = json.dumps({"GIT_USER": "alice", "GIT_EMAIL": "a@x", "GITHUB_PAT": "p"})
    ctx = _ctx(scripts={"age": Result(0, stdout=payload)})
    ObsidianSync().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert any(c[:2] == ["git", "clone"] for c in calls)
    assert ["systemctl", "--user", "enable", "--now", "devboost-vault-sync.timer"] in calls
    assert (tmp_path / ".config" / "systemd" / "user" / "devboost-vault-sync.timer").exists()


def test_aspire_gc_writes_timer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = _ctx()
    AspireGc().install(ctx)
    assert AspireGc().verify(ctx) is True
    assert ["systemctl", "--user", "enable", "--now", "aspire-gc.timer"] in ctx.ex.calls  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Ubuntu — flatpak apps are cross-distro (no dnf/apt divergence)
# ---------------------------------------------------------------------------


def test_flatpak_apps_install_on_ubuntu() -> None:
    """All FlatpakApp subclasses use flatpak install — fully cross-distro."""
    apps = [Obsidian, Bruno, Bitwarden, Flameshot, Localsend, Vlc]
    for app_cls in apps:
        ctx = _ubuntu_ctx()
        app_cls().install(ctx)
        calls = ctx.ex.calls  # type: ignore[attr-defined]
        assert any(
            c[:3] == ["flatpak", "install", "-y"] and app_cls.app_id in c
            for c in calls
        ), f"{app_cls.name}: flatpak install not called with app_id {app_cls.app_id!r}"


def test_flatpak_app_verify_on_ubuntu() -> None:
    """Verify uses flatpak info — works identically on Ubuntu."""
    ctx = _ubuntu_ctx(scripts={"flatpak": Result(0, stdout="md.obsidian.Obsidian - Obsidian")})
    assert Obsidian().verify(ctx) is True


def test_flatpak_apps_no_dnf_calls_on_ubuntu() -> None:
    """No dnf or rpm commands must appear when installing flatpak apps on Ubuntu."""
    ctx = _ubuntu_ctx()
    Obsidian().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert not any("dnf" in " ".join(c) or "rpm" in " ".join(c) for c in calls)
