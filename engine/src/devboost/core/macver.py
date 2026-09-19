"""macOS version as data (spec §0): modules and table rows gate on (major, minor)."""

from __future__ import annotations

from devboost.core.osinfo import OsInfo


def macos_version(os_info: OsInfo) -> tuple[int, int] | None:
    """(major, minor) of a macOS host; None off macOS or when the version is unknown."""
    if os_info.family != "macos" or not os_info.version_id:
        return None
    parts = os_info.version_id.split(".")
    try:
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
    except ValueError:
        return None
    return (major, minor)
