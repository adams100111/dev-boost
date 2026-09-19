"""macos-defaults — the spec §2 `defaults` table: snapshotted first, applied, revertible.

The snapshot records each key's value from *before dev-boost first wrote it* (absent keys
as null) and is never overwritten, so `devboost revert macos-defaults` restores the
machine's own state. Processes restart only when one of their keys changed.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from devboost.core import log
from devboost.core.errors import DevbootError
from devboost.core.macver import macos_version
from devboost.core.osinfo import OsInfo
from devboost.core.registry import register
from devboost.exec.primitives import macdefaults
from devboost.exec.primitives.macdefaults import Value
from devboost.model import Ctx, Module


@dataclass(frozen=True)
class Setting:
    domain: str
    key: str
    value: Value
    #: Process to `killall` when this key changed (None: takes effect at next login).
    restart: str | None = None
    min_macos: tuple[int, int] | None = None
    max_macos: tuple[int, int] | None = None

    @property
    def id(self) -> str:
        return f"{self.domain}:{self.key}"

    def applies(self, os_info: OsInfo) -> bool:
        v = macos_version(os_info)
        if v is None:
            return True
        if self.min_macos is not None and v < self.min_macos:
            return False
        return not (self.max_macos is not None and v > self.max_macos)


def _b(x: bool) -> Value:
    return Value("bool", x)


def _i(x: int) -> Value:
    return Value("int", x)


def _s(x: str) -> Value:
    return Value("string", x)


_G = "NSGlobalDomain"
_FINDER = "com.apple.finder"
_DOCK = "com.apple.dock"
_SHOT = "com.apple.screencapture"
_DS = "com.apple.desktopservices"
#: Restart order, so `killall` calls are deterministic.
_PROCS = ("Dock", "Finder", "SystemUIServer")

SETTINGS: tuple[Setting, ...] = (
    Setting(_G, "KeyRepeat", _i(2)),
    Setting(_G, "InitialKeyRepeat", _i(15)),
    Setting(_G, "ApplePressAndHoldEnabled", _b(False)),
    Setting(_G, "AppleShowAllExtensions", _b(True), "Finder"),
    Setting(_G, "NSAutomaticSpellingCorrectionEnabled", _b(False)),
    Setting(_G, "NSAutomaticQuoteSubstitutionEnabled", _b(False)),
    Setting(_G, "NSAutomaticDashSubstitutionEnabled", _b(False)),
    Setting(_FINDER, "AppleShowAllFiles", _b(True), "Finder"),
    Setting(_FINDER, "ShowPathbar", _b(True), "Finder"),
    Setting(_FINDER, "ShowStatusBar", _b(True), "Finder"),
    Setting(_FINDER, "FXPreferredViewStyle", _s("Nlsv"), "Finder"),
    Setting(_DS, "DSDontWriteNetworkStores", _b(True)),
    Setting(_DS, "DSDontWriteUSBStores", _b(True)),
    Setting(_DOCK, "autohide", _b(True), "Dock"),
    Setting(_DOCK, "tilesize", _i(48), "Dock"),
    Setting(_DOCK, "show-recents", _b(False), "Dock"),
    # Screenshots land on the clipboard, ready for `herdr --remote` Ctrl+V image paste;
    # ⌘⇧5 → Options → "Save to" still saves files.
    Setting(_SHOT, "target", _s("clipboard"), "SystemUIServer"),
    Setting(_SHOT, "type", _s("png"), "SystemUIServer"),
    Setting("com.apple.AppleMultitouchTrackpad", "Clicking", _b(True)),
    Setting("com.apple.driver.AppleBluetoothMultitouch.trackpad", "Clicking", _b(True)),
)

Prior = dict[str, Value | None]

_VERSION = 1
_KINDS = frozenset(("bool", "int", "float", "string", "other"))


class SnapshotError(DevbootError):
    """The snapshot file exists but cannot be trusted; nothing is written until it is fixed.

    Treating it as empty would record dev-boost's own values as the "prior" ones and lose
    the machine's originals for good, so apply and revert both stop instead.
    """


def snapshot_path() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path(os.environ["HOME"]) / ".local" / "state")
    return Path(base) / "devboost" / "macos-defaults.prev.json"


def _encode(v: Value | None) -> dict[str, Any] | None:
    if v is None:
        return None
    if v.kind == "other":
        return {"kind": "other"}
    return {"kind": v.kind, "value": v.value}


def _decode(raw: Any) -> Value | None:
    if raw is None:
        return None
    if not isinstance(raw, dict) or raw.get("kind") not in _KINDS:
        raise ValueError(f"bad entry {raw!r}")
    kind = raw["kind"]
    if kind == "other":
        return Value("other", "")
    value = raw.get("value")
    if kind == "bool" and isinstance(value, bool):
        return Value("bool", value)
    if kind == "int" and isinstance(value, int) and not isinstance(value, bool):
        return Value("int", value)
    if kind == "float" and isinstance(value, int | float) and not isinstance(value, bool):
        return Value("float", float(value))
    if kind == "string" and isinstance(value, str):
        return Value("string", value)
    raise ValueError(f"bad {kind} value {value!r}")


def load_snapshot() -> Prior:
    """The recorded priors; empty when no snapshot exists. Raises SnapshotError if unreadable."""
    path = snapshot_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise SnapshotError(f"cannot read {path}: {exc}") from exc
    try:
        raw = json.loads(text)
        if not isinstance(raw, dict) or raw.get("version") != _VERSION:
            raise ValueError(f"unsupported snapshot version (want {_VERSION})")
        prior = raw.get("prior")
        if not isinstance(prior, dict):
            raise ValueError("no 'prior' table")
        return {str(k): _decode(v) for k, v in prior.items()}
    except ValueError as exc:  # JSONDecodeError is a ValueError
        raise SnapshotError(
            f"{path} is not a valid macos-defaults snapshot ({exc}); it holds the values to "
            "restore, so fix or move it by hand"
        ) from exc


def save_snapshot(prior: Prior) -> None:
    """Write *prior* atomically (temp file + rename); an empty *prior* removes the file."""
    path = snapshot_path()
    if not prior:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"version": _VERSION, "prior": {k: _encode(v) for k, v in sorted(prior.items())}}
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _applicable(ctx: Ctx) -> list[Setting]:
    return [s for s in SETTINGS if s.applies(ctx.os)]


def _restart(ctx: Ctx, procs: set[str]) -> None:
    for proc in sorted(procs, key=_PROCS.index):
        ctx.ex.run(["killall", proc])  # not running → non-zero, harmless


def apply(ctx: Ctx) -> list[str]:
    """Snapshot unrecorded keys, write every key that differs, restart what changed."""
    settings = _applicable(ctx)
    current = {s.id: macdefaults.read(ctx, s.domain, s.key) for s in settings}
    prior = load_snapshot()
    for s in settings:
        prior.setdefault(s.id, current[s.id])
    save_snapshot(prior)  # before the first write, so a crash never loses a prior value
    changed = [s for s in settings if current[s.id] != s.value]
    for s in changed:
        macdefaults.write(ctx, s.domain, s.key, s.value)
    _restart(ctx, {r for s in changed if (r := s.restart) is not None})
    if any(s.restart is None for s in changed):
        log.info("macos-defaults: keyboard, autocorrect, trackpad and .DS_Store changes "
                 "apply fully after you log out and back in")
    return [s.id for s in changed]


def verify_all(ctx: Ctx) -> bool:
    return all(macdefaults.read(ctx, s.domain, s.key) == s.value for s in _applicable(ctx))


def resolve_ids(names: Sequence[str]) -> list[str]:
    """Map `<domain>:<key>` or a table-unique bare key to its id."""
    ids = [s.id for s in SETTINGS]
    out: list[str] = []
    for name in names:
        if name in ids:
            out.append(name)
            continue
        hits = [i for i in ids if i.split(":", 1)[1] == name]
        if len(hits) == 1:
            out.append(hits[0])
        elif hits:
            raise ValueError(f"ambiguous key {name!r}; use one of: {', '.join(hits)}")
        else:
            raise ValueError(f"unknown macos-defaults key {name!r}; known: {', '.join(ids)}")
    return out


def revert(ctx: Ctx, ids: Sequence[str] | None = None) -> list[str]:
    """Restore recorded prior values (all, or *ids*); returns the ids restored.

    Each restored id leaves the snapshot, so a repeat is a no-op. If a restore fails, the
    progress so far is still saved (the failed id keeps its prior) before the error rises.
    """
    prior = load_snapshot()
    wanted = list(prior) if ids is None else list(dict.fromkeys(ids))
    restart = {s.id: s.restart for s in SETTINGS}
    done: list[str] = []
    procs: set[str] = set()
    try:
        for i in wanted:
            if i not in prior:
                log.warn(f"macos-defaults: nothing recorded for {i} — left as is")
                continue
            old = prior[i]
            domain, key = i.split(":", 1)
            if old is not None and old.kind == "other":
                log.warn(
                    f"macos-defaults: {i} held a value dev-boost cannot restore — left as is"
                )
                continue
            if old is None:
                macdefaults.delete(ctx, domain, key)
            else:
                macdefaults.write(ctx, domain, key, old)
            del prior[i]
            done.append(i)
            if (proc := restart.get(i)) is not None:
                procs.add(proc)
    finally:
        if done:
            save_snapshot(prior)
            _restart(ctx, procs)
    return done


@register
class MacosDefaults(Module):
    name = "macos-defaults"
    category = "macos-desktop"
    description = "macOS developer defaults (Finder, Dock, keyboard, screenshots); revertible."
    profiles = ("macos-desktop",)
    families = ("macos",)
    portable = True

    def verify(self, ctx: Ctx) -> bool:
        return verify_all(ctx)

    def install(self, ctx: Ctx) -> None:
        apply(ctx)
