"""Tests for the families-based OS-family filter in build_plan."""

from __future__ import annotations

from pathlib import Path

from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load

FEDORA = OsInfo("fedora", "fedora", "x86_64")
DEBIAN = OsInfo("ubuntu", "debian", "x86_64")


# ---------------------------------------------------------------------------
# multimedia profile — Fedora vs. Debian filtering
# ---------------------------------------------------------------------------


def test_plan_families_multimedia_fedora_includes_fedora_modules(tmp_path: Path) -> None:
    """On Fedora, the multimedia plan keeps ffmpeg-full/codecs/openh264."""
    modules = load()
    order = [
        "rpmfusion", "ffmpeg-full", "codecs", "va-hwaccel",
        "openh264", "ffmpeg-ubuntu", "codecs-ubuntu",
    ]
    plan = build_plan(order, modules, FEDORA, gpu_marker=tmp_path / "no-gpu")
    plan_names = [pm.name for pm in plan]

    assert "ffmpeg-full" in plan_names
    assert "codecs" in plan_names
    assert "openh264" in plan_names


def test_plan_families_multimedia_fedora_excludes_debian_modules(tmp_path: Path) -> None:
    """On Fedora, the multimedia plan drops ffmpeg-ubuntu and codecs-ubuntu."""
    modules = load()
    order = [
        "rpmfusion", "ffmpeg-full", "codecs", "va-hwaccel",
        "openh264", "ffmpeg-ubuntu", "codecs-ubuntu",
    ]
    plan = build_plan(order, modules, FEDORA, gpu_marker=tmp_path / "no-gpu")
    plan_names = [pm.name for pm in plan]

    assert "ffmpeg-ubuntu" not in plan_names
    assert "codecs-ubuntu" not in plan_names


def test_plan_families_multimedia_debian_includes_debian_modules(tmp_path: Path) -> None:
    """On Debian/Ubuntu, the multimedia plan keeps ffmpeg-ubuntu and codecs-ubuntu."""
    modules = load()
    order = [
        "rpmfusion", "ffmpeg-full", "codecs", "va-hwaccel",
        "openh264", "ffmpeg-ubuntu", "codecs-ubuntu",
    ]
    plan = build_plan(order, modules, DEBIAN, gpu_marker=tmp_path / "no-gpu")
    plan_names = [pm.name for pm in plan]

    assert "ffmpeg-ubuntu" in plan_names
    assert "codecs-ubuntu" in plan_names


def test_plan_families_multimedia_debian_excludes_fedora_modules(tmp_path: Path) -> None:
    """On Debian/Ubuntu, the multimedia plan drops ffmpeg-full/codecs/openh264."""
    modules = load()
    order = [
        "rpmfusion", "ffmpeg-full", "codecs", "va-hwaccel",
        "openh264", "ffmpeg-ubuntu", "codecs-ubuntu",
    ]
    plan = build_plan(order, modules, DEBIAN, gpu_marker=tmp_path / "no-gpu")
    plan_names = [pm.name for pm in plan]

    assert "ffmpeg-full" not in plan_names
    assert "codecs" not in plan_names
    assert "openh264" not in plan_names


def test_plan_families_multimedia_cross_distro_va_hwaccel_always_included(
    tmp_path: Path,
) -> None:
    """va-hwaccel has no families restriction and must appear on both OSes."""
    modules = load()
    order = ["va-hwaccel"]

    fedora_plan = build_plan(order, modules, FEDORA, gpu_marker=tmp_path / "no-gpu")
    debian_plan = build_plan(order, modules, DEBIAN, gpu_marker=tmp_path / "no-gpu")

    assert any(pm.name == "va-hwaccel" for pm in fedora_plan)
    assert any(pm.name == "va-hwaccel" for pm in debian_plan)


# ---------------------------------------------------------------------------
# hardware-nvidia profile — Fedora vs. Debian filtering
# ---------------------------------------------------------------------------


def test_plan_families_nvidia_fedora_includes_akmod_stack(tmp_path: Path) -> None:
    """On Fedora, the nvidia plan keeps the akmod-based modules."""
    modules = load()
    order = [
        "rpmfusion", "nvidia-akmod", "cuda", "libva-nvidia-driver",
        "secureboot-mok", "nvidia-resign-service", "nvidia-driver-ubuntu",
    ]
    plan = build_plan(order, modules, FEDORA, gpu_marker=tmp_path / "no-gpu")
    plan_names = [pm.name for pm in plan]

    assert "nvidia-akmod" in plan_names
    assert "cuda" in plan_names
    assert "libva-nvidia-driver" in plan_names
    assert "secureboot-mok" in plan_names
    assert "nvidia-resign-service" in plan_names


def test_plan_families_nvidia_fedora_excludes_ubuntu_driver(tmp_path: Path) -> None:
    """On Fedora, the nvidia plan drops nvidia-driver-ubuntu."""
    modules = load()
    order = [
        "rpmfusion", "nvidia-akmod", "cuda", "libva-nvidia-driver",
        "secureboot-mok", "nvidia-resign-service", "nvidia-driver-ubuntu",
    ]
    plan = build_plan(order, modules, FEDORA, gpu_marker=tmp_path / "no-gpu")
    plan_names = [pm.name for pm in plan]

    assert "nvidia-driver-ubuntu" not in plan_names


def test_plan_families_nvidia_debian_includes_ubuntu_driver(tmp_path: Path) -> None:
    """On Debian/Ubuntu, the nvidia plan keeps nvidia-driver-ubuntu."""
    modules = load()
    order = [
        "rpmfusion", "nvidia-akmod", "cuda", "libva-nvidia-driver",
        "secureboot-mok", "nvidia-resign-service", "nvidia-driver-ubuntu",
    ]
    plan = build_plan(order, modules, DEBIAN, gpu_marker=tmp_path / "no-gpu")
    plan_names = [pm.name for pm in plan]

    assert "nvidia-driver-ubuntu" in plan_names


def test_plan_families_nvidia_debian_excludes_akmod_stack(tmp_path: Path) -> None:
    """On Debian/Ubuntu, the nvidia plan drops the fedora akmod-based modules."""
    modules = load()
    order = [
        "rpmfusion", "nvidia-akmod", "cuda", "libva-nvidia-driver",
        "secureboot-mok", "nvidia-resign-service", "nvidia-driver-ubuntu",
    ]
    plan = build_plan(order, modules, DEBIAN, gpu_marker=tmp_path / "no-gpu")
    plan_names = [pm.name for pm in plan]

    assert "nvidia-akmod" not in plan_names
    assert "cuda" not in plan_names
    assert "nvidia-resign-service" not in plan_names


# ---------------------------------------------------------------------------
# Uniform module (no families) is never filtered
# ---------------------------------------------------------------------------


def test_plan_families_uniform_module_not_filtered(tmp_path: Path) -> None:
    """A module with families=() (default) appears in plans for any OS family."""
    modules = load()
    # earlyoom is cross-distro with no families restriction
    order = ["earlyoom"]
    fedora_plan = build_plan(order, modules, FEDORA, gpu_marker=tmp_path / "no-gpu")
    debian_plan = build_plan(order, modules, DEBIAN, gpu_marker=tmp_path / "no-gpu")

    assert any(pm.name == "earlyoom" for pm in fedora_plan)
    assert any(pm.name == "earlyoom" for pm in debian_plan)
