from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.errors import ConfigError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.orca import OrcaIde, OrcaServe

FEDORA = OsInfo("fedora", "fedora", "x86_64")
FEDORA_ARM = OsInfo("fedora", "fedora", "aarch64")
UBUNTU = OsInfo("ubuntu", "debian", "x86_64")
OMARCHY = OsInfo("omarchy", "arch", "x86_64", id_like=("arch",))
MAC = OsInfo("macos", "macos", "arm64")


def _ctx(os: OsInfo = FEDORA, **kw: object) -> Ctx:
    return Ctx(os=os, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def _joined(ctx: Ctx) -> list[str]:
    return [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]


def test_verify_uses_per_os_command() -> None:
    assert OrcaIde().verify(_ctx(FEDORA, present={"orca-ide"})) is True
    assert OrcaIde().verify(_ctx(OMARCHY, present={"stably-orca"})) is True
    assert OrcaIde().verify(_ctx(OMARCHY, present={"orca-ide"})) is False  # wrong name on arch


def test_fedora_fetches_rpm_and_dnf_installs() -> None:
    ctx = _ctx(FEDORA, present={"orca-ide"})
    OrcaIde().install(ctx)
    j = _joined(ctx)
    assert any("api.github.com/repos/stablyai/orca/releases/latest" in c for c in j)
    assert any(r"orca-ide-" in c and "x86_64" in c and ".rpm" in c for c in j)
    assert any("dnf install -y" in c for c in j)


def test_fedora_arm_matches_aarch64() -> None:
    ctx = _ctx(FEDORA_ARM, present={"orca-ide"})
    OrcaIde().install(ctx)
    assert any("aarch64" in c and ".rpm" in c for c in _joined(ctx))


def test_ubuntu_fetches_deb_amd64_and_apt_installs() -> None:
    ctx = _ctx(UBUNTU, present={"orca-ide"})
    OrcaIde().install(ctx)
    j = _joined(ctx)
    assert any("orca-ide_" in c and "amd64" in c and ".deb" in c for c in j)
    assert any("apt install -y" in c for c in j)


def test_arch_installs_via_aur() -> None:
    ctx = _ctx(OMARCHY, present={"stably-orca", "yay"})
    OrcaIde().install(ctx)
    assert any("stably-orca-bin" in c for c in _joined(ctx))


def test_pinned_version_uses_tag() -> None:
    ctx = _ctx(FEDORA, present={"orca-ide"})
    import os as _os
    _os.environ["DEVBOOST_ORCA_VERSION"] = "1.4.198"
    try:
        OrcaIde().install(ctx)
    finally:
        del _os.environ["DEVBOOST_ORCA_VERSION"]
    assert any("releases/tags/v1.4.198" in c for c in _joined(ctx))


def test_unsupported_os_raises() -> None:
    with pytest.raises(ConfigError):
        OrcaIde().install(_ctx(MAC))


def _serve_ctx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, os: OsInfo = FEDORA, **kw: object
) -> Ctx:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USER", "dev")
    return Ctx(os=os, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def _unit_text(tmp_path: Path) -> str:
    unit = tmp_path / ".config" / "systemd" / "user" / "orca-serve.service"
    return unit.read_text(encoding="utf-8")


def test_serve_writes_unit_with_env_pairing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEVBOOST_ORCA_PAIRING_ADDRESS", "100.64.1.20")
    ctx = _serve_ctx(tmp_path, monkeypatch, FEDORA, present={"orca-ide"})
    OrcaServe().install(ctx)
    u = _unit_text(tmp_path)
    assert "xvfb-run -a orca-ide serve" in u
    assert "--pairing-address 100.64.1.20" in u
    assert "LIBGL_ALWAYS_SOFTWARE=1" in u
    assert "RestartPreventExitStatus=3" in u
    j = _joined(ctx)
    assert any("xorg-x11-server-Xvfb" in c for c in j)              # xvfb on fedora
    assert any("enable-linger dev" in c for c in j)
    assert any("systemctl --user enable --now orca-serve.service" in c for c in j)


def test_serve_derives_tailscale_ip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEVBOOST_ORCA_PAIRING_ADDRESS", raising=False)
    ctx = _serve_ctx(
        tmp_path, monkeypatch, UBUNTU,
        present={"orca-ide", "tailscale"},
        scripts={"tailscale": Result(0, stdout="100.99.1.5\n")},
    )
    OrcaServe().install(ctx)
    u = _unit_text(tmp_path)
    assert "--pairing-address 100.99.1.5" in u
    assert any("xvfb" in c for c in _joined(ctx))  # xvfb on debian


def test_serve_no_pairing_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEVBOOST_ORCA_PAIRING_ADDRESS", raising=False)
    ctx = _serve_ctx(tmp_path, monkeypatch, FEDORA, present={"orca-ide"})  # no tailscale
    with pytest.raises(ConfigError):
        OrcaServe().install(ctx)


def test_serve_custom_port(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVBOOST_ORCA_PAIRING_ADDRESS", "10.0.0.9")
    monkeypatch.setenv("DEVBOOST_ORCA_PORT", "7000")
    ctx = _serve_ctx(tmp_path, monkeypatch, FEDORA, present={"orca-ide"})
    OrcaServe().install(ctx)
    assert "--port 7000" in _unit_text(tmp_path)


def test_serve_verify_uses_is_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ok = _serve_ctx(tmp_path, monkeypatch, FEDORA, present={"orca-ide"})
    assert OrcaServe().verify(ok) is True   # FakeExecutor is-enabled → Result(0)
    bad = _serve_ctx(tmp_path, monkeypatch, FEDORA, scripts={"systemctl": Result(1)})
    assert OrcaServe().verify(bad) is False
