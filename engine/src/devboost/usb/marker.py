"""The build-time marker (Bootstrap/.devboost-usb.json) that identifies a dev-boost USB."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ValidationError


class Marker(BaseModel):
    version: str
    os_id: str
    arch: str
    built_at: str


def marker_path(vtoy_mount: Path) -> Path:
    return vtoy_mount / "Bootstrap" / ".devboost-usb.json"


def write_marker(vtoy_mount: Path, marker: Marker) -> Path:
    path = marker_path(vtoy_mount)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(marker.model_dump_json(indent=2), encoding="utf-8")
    return path


def read_marker(directory: Path) -> Marker | None:
    path = marker_path(directory)
    if not path.exists():
        return None
    try:
        return Marker.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValidationError, ValueError, OSError):
        return None
