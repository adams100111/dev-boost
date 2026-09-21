"""macOS privacy permissions (TCC): deep links + a record of what the user confirmed.

macOS offers no supported way for a script to grant or read another app's privacy
grants, so dev-boost opens the exact System Settings pane and remembers the user's
confirmation. That record is the weak point, and it failed in a way worth spelling out:
`devboost permissions` reported "all granted" while an app's Microphone switch was off,
because the record only ever said what the user had once been asked.

Two things make the record trustworthy now.

* A confirmation is stored **with the app bundle's code-signature hash**. TCC binds a
  grant to the signature, so when a bundle is rebuilt macOS sees a different app and the
  grant stops applying. Recording the hash lets a rebuild re-flag the grant instead of
  the record quietly outliving it. This is not hypothetical: an ad-hoc signed bundle
  (`TeamIdentifier=not set`) is re-signed on every rebuild, and dev-boost rebuilds one
  itself — `voxtype setup app-bundle` is documented to reset Accessibility and Input
  Monitoring.
* A confirmation covers **one** grant. The old prompt asked "Granted everything for
  <module>?" across Microphone, Input Monitoring and Accessibility at once, so a single
  yes marked all three done forever — including any the user had not actually granted.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

from devboost.model import TccGrant, TccService

_LABELS: dict[str, str] = {
    "Accessibility": "Accessibility",
    "ListenEvent": "Input Monitoring",
    "Microphone": "Microphone",
    "ScreenCapture": "Screen Recording",
}

#: Where a TccGrant's `app` name is looked for, in order.
_APP_DIRS = ("/Applications", "~/Applications")


def label(service: TccService) -> str:
    return _LABELS[service]


def settings_url(service: TccService) -> str:
    return f"x-apple.systempreferences:com.apple.preference.security?Privacy_{service}"


def state_file() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path(os.environ["HOME"]) / ".local" / "state")
    return Path(base) / "devboost" / "tcc.json"


def _key(module: str, g: TccGrant) -> str:
    return f"{module}:{g.service}:{g.app}"


def app_bundle(app: str) -> Path | None:
    """Where *app* is installed, or None when it cannot be found."""
    for d in _APP_DIRS:
        path = Path(d).expanduser() / f"{app}.app"
        if path.exists():
            return path
    return None


def signature(app: str) -> str | None:
    """The app bundle's code-signature hash, or None when it cannot be read.

    None means "no opinion": the app is not installed where we look, is unsigned, or
    codesign is unavailable. A grant is never re-flagged on no opinion — an unreadable
    signature is not evidence that a permission was lost.
    """
    bundle = app_bundle(app)
    if bundle is None:
        return None
    try:
        probe = subprocess.run(
            ["codesign", "-d", "--verbose=4", str(bundle)],
            capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    # codesign writes its description to stderr. Keep the whole value — the algorithm
    # is part of the identity, e.g. "sha256=1a2b…".
    marker = "CandidateCDHash "
    for line in (probe.stderr or "").splitlines():
        if line.startswith(marker):
            return line[len(marker):].strip() or None
    return None


def _load() -> dict[str, str | None]:
    """The confirmation record, as {key: signature-at-confirm-time}.

    Accepts the pre-signature format (a bare list of keys) so an existing machine is
    readable; those entries carry no signature and are handled by `pending`.
    """
    try:
        raw = json.loads(state_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(raw, list):
        return dict.fromkeys(k for k in raw if isinstance(k, str))
    if isinstance(raw, dict):
        return {k: v if isinstance(v, str) else None for k, v in raw.items()}
    return {}


def pending(module: str, grants: Sequence[TccGrant]) -> list[TccGrant]:
    """The grants still to confirm.

    A grant is pending when it was never confirmed, when the app has been re-signed
    since (so macOS is looking at a different app than the one confirmed), or when it
    was confirmed before signatures were recorded AND the app can be read now — that
    last case establishes a verifiable baseline once, rather than trusting a record
    made under the old blanket prompt.
    """
    done = _load()
    out: list[TccGrant] = []
    for g in grants:
        key = _key(module, g)
        if key not in done:
            out.append(g)
            continue
        recorded = done[key]
        current = signature(g.app)
        if current is None:
            continue  # no opinion: never re-flag on a guess
        if recorded != current:
            out.append(g)
    return out


def confirm(module: str, grants: Sequence[TccGrant]) -> None:
    """Record *grants* as granted, each against the app's signature right now."""
    done = _load()
    for g in grants:
        done[_key(module, g)] = signature(g.app)
    path = state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(done, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def fix_hint(grants: Sequence[TccGrant]) -> str:
    return "; ".join(
        f"allow {g.app} in {label(g.service)}: open '{settings_url(g.service)}'"
        for g in grants
    )
