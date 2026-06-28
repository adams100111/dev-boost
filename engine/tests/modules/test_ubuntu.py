"""Ubuntu/Debian path tests — terminal, hardware, and multimedia modules."""

from __future__ import annotations

import pytest

from devboost.core.errors import UnsupportedOS
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.base import BuildTools, DnfTune, FedoraThirdParty, Rpmfusion
from devboost.modules.cli_tools import (
    Atuin,
    Bat,
    Delta,
    Dust,
    Eza,
    Fastfetch,
    Fd,
    Gh,
    Lazydocker,
    Lazygit,
    Tealdeer,
    Yq,
)
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


def test_dust_installs_release_binary_on_ubuntu() -> None:
    """du-dust is absent from Ubuntu apt until 25.10 — install the GitHub release binary."""
    ctx = _ctx()
    Dust().install(ctx)
    joined = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert any("github.com/bootandy/dust" in j and ".local/bin/dust" in j for j in joined)
    assert not any("du-dust" in j for j in joined)


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


def test_lazygit_installs_release_binary_on_ubuntu_without_copr() -> None:
    """lazygit is NOT in Ubuntu apt — install the GitHub release binary; never COPR/apt."""
    ctx = _ctx()
    Lazygit().install(ctx)
    joined = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert not any("copr" in j for j in joined), "COPR must not run on Ubuntu"
    assert not any("apt-get install" in j and "lazygit" in j for j in joined)
    assert any("github.com/jesseduffield/lazygit" in j and ".local/bin/lazygit" in j
               for j in joined)


def test_atuin_uses_official_installer_and_symlinks_on_ubuntu() -> None:
    """atuin is not in Ubuntu apt — official installer, symlinked from ~/.atuin/bin."""
    ctx = _ctx()
    Atuin().install(ctx)
    joined = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert any("setup.atuin.sh" in j for j in joined)
    assert any(".atuin/bin/atuin" in j and ".local/bin/atuin" in j for j in joined)
    assert not any("apt-get install" in j and " atuin" in j for j in joined)


def test_eza_installs_release_binary_on_ubuntu() -> None:
    ctx = _ctx()
    Eza().install(ctx)
    joined = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert any("github.com/eza-community/eza" in j and ".local/bin/eza" in j for j in joined)


def test_yq_installs_release_binary_on_ubuntu() -> None:
    ctx = _ctx()
    Yq().install(ctx)
    joined = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert any("github.com/mikefarah/yq" in j and ".local/bin/yq" in j for j in joined)


def test_fastfetch_installs_release_deb_on_ubuntu() -> None:
    ctx = _ctx()
    Fastfetch().install(ctx)
    joined = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert any("github.com/fastfetch-cli/fastfetch" in j and ".deb" in j for j in joined)


def test_gh_adds_official_apt_repo_on_ubuntu() -> None:
    ctx = _ctx()
    Gh().install(ctx)
    joined = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert any("cli.github.com/packages" in j for j in joined)
    assert any("apt-get install -y gh" in j for j in joined)


def test_tealdeer_verifies_tealdeer_binary_on_ubuntu() -> None:
    """Ubuntu's tealdeer package installs `tealdeer`, not `tldr`."""
    assert Tealdeer().verify(_ctx(present={"tealdeer"})) is True
    assert Tealdeer().verify(_ctx(present={"tldr"})) is False


def test_tealdeer_installs_tealdeer_package_on_ubuntu() -> None:
    ctx = _ctx()
    Tealdeer().install(ctx)
    assert ["sudo", "apt-get", "install", "-y", "tealdeer"] in ctx.ex.calls  # type: ignore[attr-defined]


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
# Mise on Ubuntu — official installer (the apt repo is unreliable / needs a dearmored key)
# ---------------------------------------------------------------------------


def test_mise_uses_official_installer_on_ubuntu() -> None:
    ctx = _ctx()
    Mise().install(ctx)
    joined = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert any("mise.run" in j for j in joined)
    # No apt repo / apt install for mise on Ubuntu anymore.
    assert not any("sources.list.d" in j for j in joined)
    assert not any("apt-get install" in j and "mise" in j for j in joined)


def test_mise_skips_install_if_already_present_on_ubuntu() -> None:
    """If mise is already on PATH, skip the installer entirely."""
    ctx = _ctx(present={"mise"})
    Mise().install(ctx)
    joined = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert not any("mise.run" in j for j in joined)


# ---------------------------------------------------------------------------
# hardware.py — Fedora-only guards on Ubuntu
# ---------------------------------------------------------------------------


from devboost.modules.hardware import (  # noqa: E402
    Cuda,
    LibvaNvidiaDriver,
    NvidiaAkmod,
    NvidiaContainerToolkit,
    NvidiaDriverUbuntu,
    NvidiaResignService,
    SecurebootMok,
)


def test_nvidia_akmod_raises_unsupported_on_ubuntu() -> None:
    ctx = _ctx()
    with pytest.raises(UnsupportedOS, match="Fedora"):
        NvidiaAkmod().install(ctx)


def test_nvidia_akmod_verify_false_on_ubuntu() -> None:
    ctx = _ctx()
    assert NvidiaAkmod().verify(ctx) is False


def test_cuda_raises_unsupported_on_ubuntu() -> None:
    ctx = _ctx()
    with pytest.raises(UnsupportedOS, match="Fedora"):
        Cuda().install(ctx)


def test_libva_nvidia_driver_raises_unsupported_on_ubuntu() -> None:
    ctx = _ctx()
    with pytest.raises(UnsupportedOS, match="Fedora"):
        LibvaNvidiaDriver().install(ctx)


def test_secureboot_mok_raises_unsupported_on_ubuntu() -> None:
    ctx = _ctx()
    with pytest.raises(UnsupportedOS, match="Fedora"):
        SecurebootMok().install(ctx)


def test_nvidia_resign_service_raises_unsupported_on_ubuntu() -> None:
    ctx = _ctx()
    with pytest.raises(UnsupportedOS, match="Fedora"):
        NvidiaResignService().install(ctx)


def test_nvidia_container_toolkit_raises_unsupported_on_ubuntu() -> None:
    ctx = _ctx()
    with pytest.raises(UnsupportedOS, match="Fedora"):
        NvidiaContainerToolkit().install(ctx)


def test_nvidia_driver_ubuntu_installs_via_ubuntu_drivers() -> None:
    ctx = _ctx()
    NvidiaDriverUbuntu().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "apt-get", "install", "-y", "ubuntu-drivers-common"] in calls
    assert ["sudo", "ubuntu-drivers", "autoinstall"] in calls


def test_nvidia_driver_ubuntu_verify_checks_nvidia_smi() -> None:
    ctx = _ctx(present={"nvidia-smi"})
    assert NvidiaDriverUbuntu().verify(ctx) is True


def test_nvidia_driver_ubuntu_verify_false_when_absent() -> None:
    ctx = _ctx()
    assert NvidiaDriverUbuntu().verify(ctx) is False


def test_nvidia_driver_ubuntu_raises_unsupported_on_fedora() -> None:
    fedora_ctx = Ctx(
        os=OsInfo(distro="fedora", family="fedora", arch="x86_64"),
        ex=FakeExecutor(),
    )
    with pytest.raises(UnsupportedOS, match="Ubuntu"):
        NvidiaDriverUbuntu().install(fedora_ctx)


# ---------------------------------------------------------------------------
# multimedia.py — Fedora-only guards + Ubuntu equivalents
# ---------------------------------------------------------------------------


from devboost.modules.multimedia import (  # noqa: E402
    Codecs,
    CodecsUbuntu,
    FfmpegFull,
    FfmpegUbuntu,
    Openh264,
    VaHwaccel,
)


def test_ffmpeg_full_raises_unsupported_on_ubuntu() -> None:
    ctx = _ctx()
    with pytest.raises(UnsupportedOS, match="Fedora"):
        FfmpegFull().install(ctx)


def test_ffmpeg_full_verify_false_on_ubuntu() -> None:
    ctx = _ctx()
    assert FfmpegFull().verify(ctx) is False


def test_ffmpeg_ubuntu_installs_ffmpeg_via_apt() -> None:
    ctx = _ctx()
    FfmpegUbuntu().install(ctx)
    assert ["sudo", "apt-get", "install", "-y", "ffmpeg"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_ffmpeg_ubuntu_verify_checks_binary() -> None:
    ctx = _ctx(present={"ffmpeg"})
    assert FfmpegUbuntu().verify(ctx) is True


def test_ffmpeg_ubuntu_raises_unsupported_on_fedora() -> None:
    fedora_ctx = Ctx(
        os=OsInfo(distro="fedora", family="fedora", arch="x86_64"),
        ex=FakeExecutor(),
    )
    with pytest.raises(UnsupportedOS, match="Ubuntu"):
        FfmpegUbuntu().install(fedora_ctx)


def test_codecs_raises_unsupported_on_ubuntu() -> None:
    ctx = _ctx()
    with pytest.raises(UnsupportedOS, match="Fedora"):
        Codecs().install(ctx)


def test_codecs_verify_false_on_ubuntu() -> None:
    ctx = _ctx()
    assert Codecs().verify(ctx) is False


def test_codecs_ubuntu_installs_restricted_extras() -> None:
    ctx = _ctx()
    CodecsUbuntu().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "apt-get", "install", "-y",
            "ubuntu-restricted-extras", "libavcodec-extra"] in calls


def test_codecs_ubuntu_verify_checks_dpkg() -> None:
    ctx = _ctx(scripts={"dpkg": Result(0)})
    assert CodecsUbuntu().verify(ctx) is True


def test_codecs_ubuntu_verify_false_on_fedora() -> None:
    fedora_ctx = Ctx(
        os=OsInfo(distro="fedora", family="fedora", arch="x86_64"),
        ex=FakeExecutor(),
    )
    assert CodecsUbuntu().verify(fedora_ctx) is False


def test_codecs_ubuntu_raises_unsupported_on_fedora() -> None:
    fedora_ctx = Ctx(
        os=OsInfo(distro="fedora", family="fedora", arch="x86_64"),
        ex=FakeExecutor(),
    )
    with pytest.raises(UnsupportedOS, match="Ubuntu"):
        CodecsUbuntu().install(fedora_ctx)


def test_openh264_raises_unsupported_on_ubuntu() -> None:
    ctx = _ctx()
    with pytest.raises(UnsupportedOS, match="Fedora"):
        Openh264().install(ctx)


def test_openh264_verify_false_on_ubuntu() -> None:
    ctx = _ctx()
    assert Openh264().verify(ctx) is False


# ---------------------------------------------------------------------------
# VaHwaccel — cross-distro GPU-aware install
# ---------------------------------------------------------------------------


def test_va_hwaccel_ubuntu_intel_installs_intel_media_va_driver() -> None:
    lspci_out = "00:02.0 VGA compatible controller: Intel Corporation UHD Graphics 630"
    ctx = _ctx(scripts={"lspci": Result(0, stdout=lspci_out)})
    VaHwaccel().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "apt-get", "install", "-y", "libva-utils"] in calls
    assert ["sudo", "apt-get", "install", "-y", "intel-media-va-driver"] in calls


def test_va_hwaccel_ubuntu_amd_installs_mesa_va_drivers() -> None:
    lspci_out = "01:00.0 VGA compatible controller: Advanced Micro Devices [AMD/ATI] Navi 23"
    ctx = _ctx(scripts={"lspci": Result(0, stdout=lspci_out)})
    VaHwaccel().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "apt-get", "install", "-y", "mesa-va-drivers"] in calls
    # no dnf swap on Ubuntu
    assert not any("dnf" in " ".join(c) for c in calls)


def test_va_hwaccel_ubuntu_nvidia_installs_vaapi_driver() -> None:
    lspci_out = "01:00.0 VGA compatible controller: NVIDIA Corporation GA106 [GeForce RTX 3060]"
    ctx = _ctx(scripts={"lspci": Result(0, stdout=lspci_out)})
    VaHwaccel().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "apt-get", "install", "-y", "nvidia-vaapi-driver"] in calls


def test_va_hwaccel_verify_cross_distro() -> None:
    """vainfo binary check works on both distros."""
    ctx = _ctx(scripts={"vainfo": Result(0)})
    assert VaHwaccel().verify(ctx) is True
