from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.errors import UnsupportedOS
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules import server
from devboost.modules.server import ServerFirewall, Tailscale, Zram

UBUNTU = OsInfo(distro="ubuntu", family="debian", arch="aarch64")
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
