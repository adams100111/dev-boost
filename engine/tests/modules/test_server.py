from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.errors import UnsupportedOS
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules import server
from devboost.modules.dev_stacks import Playwright
from devboost.modules.server import AgentSudo, ResticB2, ServerFirewall, Tailscale, Zram
from devboost.modules.tpm import TmuxPersist

UBUNTU = OsInfo(distro="ubuntu", family="debian", arch="aarch64")
UBUNTU_HEADLESS = OsInfo(distro="ubuntu", family="debian", arch="aarch64", headless=True)
FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _ubuntu(**kw: object) -> Ctx:
    return Ctx(os=UBUNTU, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def _fedora(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def _no_secret(ctx: Ctx, field: str) -> str | None:
    return None


def _has_key(ctx: Ctx, field: str) -> str | None:
    return "tskey-abc" if field == "TAILSCALE_AUTHKEY" else None


# ── tailscale ────────────────────────────────────────────────────────────────
def test_tailscale_verify_detects_binary() -> None:
    assert Tailscale().verify(_ubuntu(present={"tailscale"})) is True
    assert Tailscale().verify(_ubuntu()) is False


def test_tailscale_installs_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """No auth key in secrets → install the client but leave `up` to the operator."""
    monkeypatch.setattr(server, "_secret", _no_secret)
    ctx = _ubuntu()
    Tailscale().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sh", "-c", "curl -fsSL https://tailscale.com/install.sh | sh"] in calls
    assert not any(c[:3] == ["sudo", "tailscale", "up"] for c in calls)


def test_tailscale_up_with_ssh_when_key_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_secret", _has_key)
    ctx = _ubuntu(present={"tailscale"})
    Tailscale().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "tailscale", "up", "--ssh", "--authkey=tskey-abc"] in calls


# ── server-firewall ──────────────────────────────────────────────────────────
def test_firewall_verify_reads_ufw_status() -> None:
    ctx = _ubuntu(present={"ufw"}, scripts={"ufw": Result(0, stdout="Status: active")})
    assert ServerFirewall().verify(ctx) is True
    assert ServerFirewall().verify(_ubuntu()) is False  # ufw absent → False


def test_firewall_baseline_keeps_ssh_and_opens_tailnet() -> None:
    """Baseline MUST NOT lock you out: SSH stays allowed, tailnet opened, then enable."""
    ctx = _ubuntu()
    ServerFirewall().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "apt-get", "install", "-y", "ufw"] in calls
    assert ["sudo", "ufw", "default", "deny", "incoming"] in calls
    assert ["sudo", "ufw", "allow", "OpenSSH"] in calls
    assert ["sudo", "ufw", "allow", "in", "on", "tailscale0"] in calls
    assert ["sudo", "ufw", "--force", "enable"] in calls
    assert any("rpcbind.socket" in c and "mask" in c for c in calls)  # exposure masked


def test_firewall_rejects_fedora() -> None:
    with pytest.raises(UnsupportedOS, match="ufw"):
        ServerFirewall().install(_fedora())


# ── zram ─────────────────────────────────────────────────────────────────────
def test_zram_debian_uses_zram_tools() -> None:
    ctx = _ubuntu()
    Zram().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "apt-get", "install", "-y", "zram-tools"] in calls
    assert ["sudo", "tee", "/etc/default/zramswap"] in calls
    assert ["sudo", "systemctl", "enable", "--now", "zramswap.service"] in calls


def test_zram_fedora_uses_generator() -> None:
    ctx = _fedora()
    Zram().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "dnf", "install", "-y", "zram-generator"] in calls
    assert ["sudo", "tee", "/etc/systemd/zram-generator.conf"] in calls


def test_zram_verify_checks_conf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    conf = tmp_path / "zramswap"
    monkeypatch.setenv("DEVBOOST_ZRAM_CONF", str(conf))
    ctx = _ubuntu()
    assert Zram().verify(ctx) is False
    conf.write_text("x")
    assert Zram().verify(ctx) is True


# ── restic → b2 ──────────────────────────────────────────────────────────────
def _b2_secrets(ctx: Ctx, field: str) -> str | None:
    return {
        "B2_ACCOUNT_ID": "id",
        "B2_ACCOUNT_KEY": "key",
        "RESTIC_REPOSITORY": "b2:bucket:path",
        "RESTIC_PASSWORD": "pw",
    }.get(field)


def test_restic_b2_skips_timer_without_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No destination → install restic but wire no timer (never point a timer at nowhere)."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(server, "_secret", _no_secret)
    ctx = _ubuntu()
    ResticB2().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "apt-get", "install", "-y", "restic"] in calls
    assert not any("restic-b2.timer" in c for c in calls)


def test_restic_b2_wires_timer_with_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(server, "_secret", _b2_secrets)
    ctx = _ubuntu(present={"restic"})
    ResticB2().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["systemctl", "--user", "enable", "--now", "restic-b2.timer"] in calls
    d = tmp_path / ".config" / "systemd" / "user"
    assert (d / "restic-b2.service").exists() and (d / "restic-b2.timer").exists()
    envfile = tmp_path / ".config" / "devboost" / "restic-b2.env"
    assert "RESTIC_PASSWORD=pw" in envfile.read_text(encoding="utf-8")
    assert oct(envfile.stat().st_mode)[-3:] == "600"  # secrets stay 0600, off the unit


# ── playwright: headless-shell on servers, full Chromium on GUI ───────────────
def test_playwright_headless_box_installs_shell_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = Ctx(os=UBUNTU_HEADLESS, ex=FakeExecutor())
    Playwright().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "npx", "--yes", "playwright", "install-deps", "chromium"] in calls
    assert ["npx", "--yes", "playwright", "install", "chromium-headless-shell"] in calls
    assert Playwright().verify(ctx) is True  # marker written


def test_playwright_gui_box_installs_full_chromium(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = _ubuntu()  # headless=False → full headed-capable Chromium too
    Playwright().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["npx", "--yes", "playwright", "install", "chromium", "chromium-headless-shell"] in calls


def test_playwright_installs_chromium_libs_via_dnf_on_fedora(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fedora: Playwright's install-deps is apt-only, so install Chromium's system libs via dnf
    (best-effort). NOT the apt install-deps path."""
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = _fedora()
    Playwright().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    dnf = next(c for c in calls if c[:3] == ["sudo", "dnf", "install"])
    assert "nss" in dnf and "mesa-libgbm" in dnf and "gtk3" in dnf
    assert not any("install-deps" in " ".join(c) for c in calls)  # not the apt path


# ── agent-sudo (passwordless sudo so agents don't hang) ───────────────────────
def test_agent_sudo_verify_uses_sudo_n(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUDO_USER", raising=False)
    monkeypatch.setenv("USER", "dev")
    assert AgentSudo().verify(_ubuntu(scripts={"sudo": Result(0)})) is True
    # sudo would need a password → not verified
    assert AgentSudo().verify(_ubuntu(scripts={"sudo": Result(1)})) is False


def test_agent_sudo_installs_via_visudo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUDO_USER", raising=False)
    monkeypatch.setenv("USER", "dev")
    ctx = _ubuntu()
    AgentSudo().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    # staged content is visudo-validated before it's moved into place (never corrupt sudoers)
    assert ["sudo", "visudo", "-cf", "/etc/sudoers.d/.devboost-stage"] in calls
    assert [
        "sudo", "mv", "-f", "/etc/sudoers.d/.devboost-stage", "/etc/sudoers.d/devboost-dev",
    ] in calls


# ── tmux-persist (reboot survival) ────────────────────────────────────────────
def test_tmux_persist_clones_resurrect_and_continuum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = _ubuntu()
    assert TmuxPersist().verify(ctx) is False
    TmuxPersist().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    cloned = [c[-2] for c in calls if c[:2] == ["git", "clone"]]
    assert any("tmux-resurrect" in u for u in cloned)
    assert any("tmux-continuum" in u for u in cloned)
