"""Build the per-module decision plan (skip reasons) before execution."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from devboost.core.graph import toposort as _toposort
from devboost.core.osinfo import OsInfo
from devboost.model import Module


@dataclass(frozen=True)
class PlannedModule:
    name: str
    skip_reason: str | None = None


def _default_gpu_marker() -> Path:
    """Canonical path for the gpu-vendor marker written by the gpu-detect module."""
    state = os.environ.get("XDG_STATE_HOME") or str(
        Path(os.environ.get("HOME", str(Path.home()))) / ".local" / "state"
    )
    return Path(state) / "devboost" / "gpu-vendor"


def _read_gpu_vendor(marker: Path | None) -> str:
    """Return the contents of the gpu-vendor marker (lower-cased), or '' if absent."""
    path = marker if marker is not None else _default_gpu_marker()
    try:
        return path.read_text(encoding="utf-8").strip().lower()
    except OSError:
        return ""


def _nvidia_module_names(modules: Mapping[str, type[Module]]) -> list[str]:
    """Return all module names in the hardware-nvidia category."""
    return [
        name for name, cls in modules.items()
        if getattr(cls, "category", "") == "hardware-nvidia"
    ]


def build_plan(
    order: list[str],
    modules: Mapping[str, type[Module]],
    os_info: OsInfo,
    *,
    gpu_marker: Path | None = None,
) -> list[PlannedModule]:
    """Build a plan from a topologically-sorted module list.

    GPU auto-inject
    ---------------
    If the gpu-vendor marker file (``~/.local/state/devboost/gpu-vendor`` by default,
    overridable via ``gpu_marker`` for tests) contains the token ``nvidia``, all modules
    in the ``hardware-nvidia`` category are automatically appended to the plan (if not
    already present) and the combined set is re-sorted topologically.

    Headless installs
    -----------------
    ``gui=True`` modules are skipped when the host is headless (a server — see
    ``osinfo.is_headless``, which keys off the systemd default target so a desktop
    mid-provisioning is *not* treated as headless).  Installing a GUI app on a server is
    pointless and can fail outright (e.g. a Flatpak GUI terminal), so it is reported as a
    clean skip rather than a failure.
    """
    effective_order = list(order)

    # GPU auto-inject: add hardware-nvidia modules when the marker indicates NVIDIA hardware.
    vendor = _read_gpu_vendor(gpu_marker)
    if "nvidia" in vendor:
        nvidia_names = _nvidia_module_names(modules)
        missing = [n for n in nvidia_names if n not in effective_order and n in modules]
        if missing:
            combined = list(dict.fromkeys(effective_order + missing))
            effective_order = _toposort(combined, modules)

    # Drop modules that are scoped to a different OS family.
    effective_order = [
        name for name in effective_order
        if not modules[name].families or os_info.family in modules[name].families
    ]

    plan: list[PlannedModule] = []
    for name in effective_order:
        cls = modules[name]
        reason: str | None = None
        if not _supported(cls, os_info):
            reason = "unsupported-os"
        elif cls.gui and os_info.headless:
            reason = "headless"
        plan.append(PlannedModule(name=name, skip_reason=reason))
    return plan


def _supported(cls: type[Module], os_info: OsInfo) -> bool:
    """A per-OS module is unsupported when its per_os map has no entry for this OS."""
    if not cls.per_os.fedora and not cls.per_os.debian and not cls.per_os.arch \
            and not cls.per_os.default:
        return True  # uniform module — supported everywhere it can run
    return cls.per_os.get(os_info) is not None
