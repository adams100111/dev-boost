from __future__ import annotations

import pytest

from devboost.core.errors import ConfigError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules.orca import OrcaIde

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
