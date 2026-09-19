"""Linux-only modules leave the Mac plan; what macOS already has is reported as provided."""

from __future__ import annotations

from pathlib import Path

from devboost.core.osinfo import LINUX_FAMILIES, OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
OMARCHY = OsInfo("omarchy", "arch", "x86_64", id_like=("arch",))

LINUX_ONLY = [
    "agent-sudo", "browser-view", "caddy", "code-server", "crossarch-build",
    "earlyoom", "gpu-detect", "zram", "gearlever",
]
PROVIDED = ["flameshot", "fwupd", "thermald", "power-profiles-daemon", "va-hwaccel"]


def test_linux_only_modules_leave_the_mac_plan(tmp_path: Path) -> None:
    modules = load()
    for name in LINUX_ONLY:
        assert modules[name].families == LINUX_FAMILIES, name
    assert build_plan(LINUX_ONLY, modules, MAC, gpu_marker=tmp_path / "x") == []


def test_macos_already_provides_these(tmp_path: Path) -> None:
    plan = build_plan(PROVIDED, load(), MAC, gpu_marker=tmp_path / "x")
    assert {p.name: p.skip_reason for p in plan} == {n: "provided-by-macos" for n in PROVIDED}


def test_linux_plans_keep_them(tmp_path: Path) -> None:
    plan = build_plan(LINUX_ONLY + PROVIDED, load(), FEDORA, gpu_marker=tmp_path / "x")
    assert {p.name for p in plan} == set(LINUX_ONLY + PROVIDED)
    assert all(p.skip_reason is None for p in plan)


def test_omarchy_still_provides_its_own(tmp_path: Path) -> None:
    plan = build_plan(["flameshot", "thermald"], load(), OMARCHY, gpu_marker=tmp_path / "x")
    assert {p.skip_reason for p in plan} == {"provided-by-omarchy"}
