"""Render the resolved build/update plan for --dry-run and the wizard recap."""

from __future__ import annotations

from devboost.media.config import MediaConfig
from devboost.media.probe import DiskState


def _describe(state: DiskState) -> str:
    if state.kind == "devboost" and state.marker is not None:
        return f"dev-boost USB (built {state.marker.built_at}, {state.marker.os_id})"
    if state.kind == "ventoy-other":
        return "non-dev-boost Ventoy stick"
    return "blank / no dev-boost marker"


def render_plan(cfg: MediaConfig, state: DiskState, *, download_note: str = "") -> str:
    lines = [
        f"Target device : {cfg.device}",
        f"Detected state: {_describe(state)}",
        f"Mode          : {cfg.mode}",
        f"OS            : {cfg.iso.id} ({cfg.arch})",
        f"Profiles      : {', '.join(cfg.profiles)}",
    ]
    if cfg.iso_path is not None:
        # No hash here: --dry-run resolves and prints the plan and touches nothing. A wrong
        # hash is caught on the real run, before the wipe.
        lines.append(f"ISO source    : local ISO {cfg.iso_path} (verified before any wipe)")
    if cfg.autoinstall_iso is not None:
        lines.append("Zero-touch    : netinst auto-install staged")
    if cfg.mode == "update":
        lines.append(f"ISO refresh   : {'yes' if cfg.refresh_iso else 'no (payload only)'}")
    if download_note:
        lines.append(f"Est. download : {download_note}")
    return "\n".join(lines)
