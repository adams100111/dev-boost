"""Ubuntu/Debian path tests for terminal-profile modules."""

from __future__ import annotations

import pytest

from devboost.core.errors import UnsupportedOS
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.base import BuildTools, DnfTune, FedoraThirdParty, Rpmfusion
from devboost.modules.cli_tools import Bat, Delta, Dust, Fd, Lazydocker, Lazygit
from devboost.modules.mise import Mise
from devboost.modules.shell import Ghostty

UBUNTU = OsInfo(distro="ubuntu", family="debian", arch="x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=UBUNTU, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Package name resolution
# ---------------------------------------------------------------------------


def test_fd_installs_fd_find_on_ubuntu() -> None:
    ctx = _ctx()
    Fd().install(ctx)
    assert ["sudo", "apt-get", "install", "-y", "fd-find"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_fd_verifies_fdfind_binary_on_ubuntu() -> None:
    ctx = _ctx(present={"fdfind"})
    assert Fd().verify(ctx) is True


def test_fd_does_not_verify_fd_binary_on_ubuntu_when_only_fdfind_present() -> None:
    """On Ubuntu the canonical binary is fdfind; plain 'fd' is not checked."""
    ctx = _ctx(present={"fd"})
    assert Fd().verify(ctx) is False


def test_bat_installs_bat_package_on_ubuntu() -> None:
    ctx = _ctx()
    Bat().install(ctx)
    assert ["sudo", "apt-get", "install", "-y", "bat"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_bat_verifies_batcat_binary_on_ubuntu() -> None:
    ctx = _ctx(present={"batcat"})
    assert Bat().verify(ctx) is True


def test_bat_does_not_verify_bat_binary_on_ubuntu() -> None:
    ctx = _ctx(present={"bat"})
    assert Bat().verify(ctx) is False


def test_dust_installs_du_dust_on_ubuntu() -> None:
    ctx = _ctx()
    Dust().install(ctx)
    assert ["sudo", "apt-get", "install", "-y", "du-dust"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_dust_verifies_dust_binary_on_ubuntu() -> None:
    ctx = _ctx(present={"dust"})
    assert Dust().verify(ctx) is True


def test_delta_installs_git_delta_on_ubuntu() -> None:
    """delta apt name is git-delta (same as Fedora pkg name) — binary is 'delta'."""
    ctx = _ctx()
    Delta().install(ctx)
    assert ["sudo", "apt-get", "install", "-y", "git-delta"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_delta_verifies_delta_binary_on_ubuntu() -> None:
    ctx = _ctx(present={"delta"})
    assert Delta().verify(ctx) is True


# ---------------------------------------------------------------------------
# COPR tools on Ubuntu
# ---------------------------------------------------------------------------


def test_lazygit_installs_via_apt_on_ubuntu_without_copr() -> None:
    """lazygit is in Ubuntu apt (universe); COPR must not be used."""
    ctx = _ctx()
    Lazygit().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert not any("copr" in " ".join(c) for c in calls), "COPR must not run on Ubuntu"
    assert ["sudo", "apt-get", "install", "-y", "lazygit"] in calls


def test_lazydocker_uses_curl_installer_on_ubuntu() -> None:
    """lazydocker has no apt package; falls back to upstream curl installer."""
    ctx = _ctx()
    Lazydocker().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert not any("copr" in " ".join(c) for c in calls)
    assert any("lazydocker" in " ".join(c) and "curl" in " ".join(c) for c in calls)


# ---------------------------------------------------------------------------
# Ghostty — flatpak on Ubuntu
# ---------------------------------------------------------------------------


def test_ghostty_installs_via_flatpak_on_ubuntu() -> None:
    ctx = _ctx(present={"flatpak"})
    Ghostty().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert any("com.mitchellh.ghostty" in " ".join(c) for c in calls)
    assert not any("copr" in " ".join(c) for c in calls)


def test_ghostty_verifies_via_flatpak_list_on_ubuntu() -> None:
    ctx = _ctx(scripts={
        "flatpak": Result(0, stdout="com.mitchellh.ghostty\n")
    })
    assert Ghostty().verify(ctx) is True


def test_ghostty_verify_false_when_not_installed_on_ubuntu() -> None:
    ctx = _ctx(scripts={"flatpak": Result(0, stdout="org.kde.okular\n")})
    assert Ghostty().verify(ctx) is False


# ---------------------------------------------------------------------------
# Fedora-only modules
# ---------------------------------------------------------------------------


def test_rpmfusion_raises_unsupported_on_ubuntu() -> None:
    ctx = _ctx()
    with pytest.raises(UnsupportedOS, match="Fedora"):
        Rpmfusion().install(ctx)


def test_dnf_tune_raises_unsupported_on_ubuntu() -> None:
    ctx = _ctx()
    with pytest.raises(UnsupportedOS, match="Fedora"):
        DnfTune().install(ctx)


def test_fedora_third_party_raises_unsupported_on_ubuntu() -> None:
    ctx = _ctx()
    with pytest.raises(UnsupportedOS, match="Fedora"):
        FedoraThirdParty().install(ctx)


# ---------------------------------------------------------------------------
# BuildTools
# ---------------------------------------------------------------------------


def test_build_tools_uses_build_essential_on_ubuntu() -> None:
    ctx = _ctx()
    BuildTools().install(ctx)
    flat = " ".join(ctx.ex.calls[0])  # type: ignore[attr-defined]
    assert "build-essential" in flat
    assert "gcc-c++" not in flat


# ---------------------------------------------------------------------------
# Mise apt repo on Ubuntu
# ---------------------------------------------------------------------------


def test_mise_adds_apt_repo_on_ubuntu() -> None:
    ctx = _ctx()
    Mise().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    # The mise apt repo must be written to sources.list.d
    assert any("sources.list.d" in " ".join(c) for c in calls)
    # apt-get install mise must follow
    assert ["sudo", "apt-get", "install", "-y", "mise"] in calls


def test_mise_skips_apt_repo_if_already_present_on_ubuntu() -> None:
    """If mise is already on PATH, skip the apt install entirely."""
    ctx = _ctx(present={"mise"})
    Mise().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert not any("apt-get" in " ".join(c) for c in calls)
