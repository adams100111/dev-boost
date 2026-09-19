"""macOS privacy permissions (TCC): deep links + a record of what the user confirmed.

macOS offers no supported way for a script to grant or reliably read these grants, so
dev-boost opens the exact System Settings pane and remembers the user's confirmation.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path

from devboost.model import TccGrant, TccService

_LABELS: dict[str, str] = {
    "Accessibility": "Accessibility",
    "ListenEvent": "Input Monitoring",
    "Microphone": "Microphone",
    "ScreenCapture": "Screen Recording",
}


def label(service: TccService) -> str:
    return _LABELS[service]


def settings_url(service: TccService) -> str:
    return f"x-apple.systempreferences:com.apple.preference.security?Privacy_{service}"


def state_file() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path(os.environ["HOME"]) / ".local" / "state")
    return Path(base) / "devboost" / "tcc.json"


def _key(module: str, g: TccGrant) -> str:
    return f"{module}:{g.service}:{g.app}"


def _load() -> set[str]:
    try:
        return set(json.loads(state_file().read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return set()


def pending(module: str, grants: Sequence[TccGrant]) -> list[TccGrant]:
    done = _load()
    return [g for g in grants if _key(module, g) not in done]


def confirm(module: str, grants: Sequence[TccGrant]) -> None:
    done = _load() | {_key(module, g) for g in grants}
    path = state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(done), indent=2) + "\n", encoding="utf-8")


def fix_hint(grants: Sequence[TccGrant]) -> str:
    return "; ".join(
        f"allow {g.app} in {label(g.service)}: open '{settings_url(g.service)}'"
        for g in grants
    )
