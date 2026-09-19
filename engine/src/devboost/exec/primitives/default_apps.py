"""Default apps on macOS — which app opens a file type — via `utiluti` (Apache-2.0).

Shared by the Zed module (Z2: code and text files open in Zed) and M5's `default-apps`
module; both read their rows from data/macos/default-apps.tsv.

macOS 26.4+ asks the user to confirm EVERY default-app change: one dialog per file type,
and the tool waits for the answer. So:
- a type is only changed when someone can answer (``can_prompt``);
- extensions that share a UTI (yaml/yml, …) cost one dialog, not one each;
- every extension dev-boost has handled is recorded in the state file, so a "no" is never
  asked again and a later change the user makes in Finder is never undone.

Whether a change took is read back from LaunchServices (``type <uti> --bundle-id``), not
taken from utiluti's exit code: a declined dialog may still exit 0. Bundle ids compare
case-insensitively, as LaunchServices does. A ``type set`` that exits non-zero is a tool
failure, not an answer: it is warned about and left unrecorded, so the next run retries.
The state is written atomically after every resolved type, so an interrupted run keeps
the answers already given.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from devboost.core import log
from devboost.core.errors import InstallError
from devboost.core.osinfo import OsInfo
from devboost.exec.primitives.config import _atomic_write
from devboost.exec.resources import tsv_rows
from devboost.model import Ctx

UTILUTI = "utiluti"


@dataclass(frozen=True)
class Association:
    ext: str
    bundle_id: str


@dataclass
class Outcome:
    changed: list[str] = field(default_factory=list)  # UTIs now opening in the app
    already: list[str] = field(default_factory=list)  # UTIs that already did
    refused: list[str] = field(default_factory=list)  # declined, or no UTI for the extension
    pending: list[str] = field(default_factory=list)  # extensions waiting for a person
    failed: list[str] = field(default_factory=list)  # UTIs utiluti could not set (retried)


def table(*parts: str) -> list[Association]:
    """(extension, bundle id) rows of a bundled TSV (e.g. data/macos/default-apps.tsv)."""
    return [Association(c[0].lstrip("."), c[1]) for c in tsv_rows(*parts, min_cols=2)]


def confirmation_required(os_info: OsInfo) -> bool:
    """True from macOS 26.4, which shows a dialog per change; unknown versions assume so."""
    nums = [int(p) for p in os_info.version_id.split(".")[:2] if p.isdigit()]
    if not nums:
        return True
    return (nums[0], nums[1] if len(nums) > 1 else 0) >= (26, 4)


def state_path() -> Path:
    state = os.environ.get("XDG_STATE_HOME") or str(
        Path(os.environ["HOME"]) / ".local" / "state"
    )
    return Path(state) / "devboost" / "default-apps.json"


def _load() -> dict[str, list[str]]:
    path = state_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        log.warn(f"{path}: unreadable ({exc}); treating default-apps state as empty")
        return {}
    if not isinstance(data, dict):
        log.warn(f"{path}: not a JSON object; treating default-apps state as empty")
        return {}
    return {
        str(app): [e for e in exts if isinstance(e, str)]
        for app, exts in data.items()
        if isinstance(exts, list)
    }


def _record(seen: dict[str, list[str]], app: str, exts: Sequence[str]) -> None:
    """Add *exts* as handled for *app* and persist the whole state atomically, now."""
    seen.setdefault(app, []).extend(exts)
    clean = {a: sorted(set(e)) for a, e in seen.items()}
    _atomic_write(state_path(), json.dumps(clean, indent=2, sort_keys=True) + "\n")


def handled(rows: Sequence[Association]) -> bool:
    """True when every row's extension has been handled for its app (set, kept, declined)."""
    seen = _load()
    return all(r.ext in seen.get(r.bundle_id, []) for r in rows)


def _ask(ctx: Ctx, *args: str) -> str | None:
    res = ctx.ex.run([UTILUTI, *args])
    out = res.stdout.strip()
    return out if res.ok and out else None


def _opens_in(ctx: Ctx, uti: str, app: str) -> bool:
    """Does LaunchServices open *uti* in *app*? Bundle ids are case-insensitive."""
    current = _ask(ctx, "type", uti, "--bundle-id")
    return current is not None and current.casefold() == app.casefold()


def apply(ctx: Ctx, rows: Sequence[Association], *, can_prompt: bool) -> Outcome:
    """Make each row's app the default for its extension; see the module docstring."""
    if not ctx.ex.which(UTILUTI):
        raise InstallError("default-apps", f"{UTILUTI} not found (brew install utiluti)", 127)
    seen = _load()
    out = Outcome()
    groups: dict[tuple[str, str], list[str]] = {}
    for row in rows:
        if row.ext in seen.get(row.bundle_id, []):
            continue
        uti = _ask(ctx, "get-uti", row.ext)
        if uti is None:
            out.refused.append(row.ext)
            _record(seen, row.bundle_id, [row.ext])
            continue
        groups.setdefault((row.bundle_id, uti), []).append(row.ext)
    for (app, uti), exts in groups.items():
        if _opens_in(ctx, uti, app):
            out.already.append(uti)
        elif not can_prompt:
            out.pending.extend(exts)
            continue
        elif not ctx.ex.run([UTILUTI, "type", "set", uti, app], interactive=True).ok:
            log.warn(
                f"utiluti could not make {app} open {uti} ({', '.join(exts)}); "
                "dev-boost will try again on the next run"
            )
            out.failed.append(uti)
            continue
        elif _opens_in(ctx, uti, app):
            out.changed.append(uti)
        else:  # the dialog was declined: the old handler is still there
            out.refused.append(uti)
        _record(seen, app, exts)
    return out
