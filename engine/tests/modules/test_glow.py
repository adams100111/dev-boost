"""glow on every OS: Homebrew, dnf, pacman, and Charm's apt repo on Debian/Ubuntu."""

from __future__ import annotations

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules.cli_tools import Glow

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
UBUNTU = OsInfo("ubuntu", "debian", "x86_64", version_id="24.04")
ARCH = OsInfo("arch", "arch", "x86_64")
OMARCHY = OsInfo("omarchy", "arch", "aarch64", id_like=("arch",))


def test_glow_on_macos_fedora_and_arch() -> None:
    for os_info, call in (
        (MAC, ["brew", "install", "--formula", "-y", "glow"]),
        (FEDORA, ["sudo", "dnf", "install", "-y", "glow"]),
        (ARCH, ["sudo", "pacman", "-S", "--needed", "--noconfirm", "glow"]),
    ):
        ex = FakeExecutor()
        Glow().install(Ctx(os=os_info, ex=ex))
        assert ex.calls[-1] == call, os_info.distro


def test_glow_on_omarchy_uses_the_omarchy_pkg_helper() -> None:
    # Omarchy routes pacman installs through its own omarchy-pkg-* helpers when they're
    # on PATH (pkg.py:Pacman.install) rather than shelling out to pacman directly.
    ex = FakeExecutor(present={"omarchy-pkg-add"})
    Glow().install(Ctx(os=OMARCHY, ex=ex))
    assert ex.calls[-1] == ["omarchy-pkg-add", "glow"]


def test_glow_on_ubuntu_comes_from_charms_apt_repo() -> None:
    ex = FakeExecutor()
    Glow().install(Ctx(os=UBUNTU, ex=ex))
    keyring = next(c for c in ex.calls if c[:2] == ["sudo", "sh"])
    assert "https://repo.charm.sh/apt/gpg.key" in keyring[-1]
    assert "/etc/apt/keyrings/repo-charm-sh.gpg" in keyring[-1]
    assert ["sudo", "tee", "/etc/apt/sources.list.d/repo-charm-sh.list"] in ex.calls
    assert ex.calls[-1] == ["sudo", "apt-get", "install", "-y", "glow"]


def test_glow_is_a_self_updating_cli_tool() -> None:
    assert Glow.profiles == ("cli",) and Glow.self_updating is True
