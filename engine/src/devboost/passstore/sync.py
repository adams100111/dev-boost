"""Keep every device's clone current: push on commit (hook), pull every 15 min (timer).

Never raises into the caller for network/git trouble — it logs, notifies (de-duplicated)
and returns a status, because a sync problem must never block anything else.
"""

from __future__ import annotations

import fcntl
import os
import shlex
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from devboost.core import log
from devboost.core.errors import DevbootError
from devboost.exec.primitives import launchd, systemd
from devboost.model import Ctx
from devboost.passstore import enroll, git, gpg, notify
from devboost.passstore.gpg import KeyInfo
from devboost.passstore.layout import DeviceRecord, Store, now_iso
from devboost.passstore.paths import state_dir

SERVICE = "devboost-pass-sync.service"
TIMER = "devboost-pass-sync.timer"
HOOK_MARK = "# managed by devboost (pass-store)"

AGENT = launchd.label("pass-sync")
INTERVAL = 900  # seconds — the same 15 minutes as the systemd timer

SyncStatus = Literal["ok", "skipped", "busy", "no-store", "conflict", "pull-failed",
                     "push-failed"]


@dataclass(frozen=True)
class SyncResult:
    status: SyncStatus
    detail: str = ""


class _State(BaseModel):
    notified: list[str] = []
    # HEAD a failure was last announced at; None = nothing outstanding (HEAD may be "").
    push_failed_head: str | None = None
    conflict_head: str | None = None
    pull_failing: bool = False
    last_sync: str = ""
    # Fingerprints of device keys this device has seen listed (tripwire, I2); None = not
    # seeded yet — the first sync learns the current set silently.
    known_devices: list[str] | None = None


# --- hook + scheduler -----------------------------------------------------------------


def hook_script(bin_: str) -> str:
    """The 3-line post-commit stub: no logic, just a background `devboost` call (D10)."""
    return (
        "#!/bin/sh\n"
        f"{HOOK_MARK} — push each commit in the background; all logic lives in devboost.\n"
        f"{shlex.quote(bin_)} pass sync --push-only --quiet </dev/null >/dev/null 2>&1 &\n"
    )


def _systemd_quote(arg: str) -> str:
    """One ExecStart word: double-quoted, with systemd's `\\`, `"`, `%` and `$` escaped."""
    escaped = arg.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    return '"' + escaped.replace("$", "$$") + '"'


def _hook_path(store: Store) -> Path:
    return store.root / ".git" / "hooks" / "post-commit"


def hook_installed(store: Store) -> bool:
    p = _hook_path(store)
    return p.exists() and HOOK_MARK in p.read_text(encoding="utf-8")


def install_hook(ctx: Ctx, store: Store, bin_: str) -> bool:
    """Write the hook (True if it changed) and pin core.hooksPath so git runs it."""
    git.pin_hooks_path(ctx, store.root)
    p = _hook_path(store)
    body = hook_script(bin_)
    if p.exists():
        current = p.read_text(encoding="utf-8")
        if current == body:
            return False
        if HOOK_MARK not in current:
            p.with_name("post-commit.devboost-backup").write_text(current, encoding="utf-8")
            log.warn(f"pass: existing {p} saved as post-commit.devboost-backup")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    p.chmod(0o755)
    return True


def service_unit(bin_: str) -> str:
    return ("[Unit]\nDescription=devboost pass store sync\n\n[Service]\nType=oneshot\n"
            f"ExecStart={_systemd_quote(bin_)} pass sync --quiet\n")


def timer_unit() -> str:
    return ("[Unit]\nDescription=devboost pass store sync every 15 min\n\n[Timer]\n"
            "OnCalendar=*:0/15\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n")


def agent_args(bin_: str) -> list[str]:
    return [bin_, "pass", "sync", "--quiet"]


def install_scheduler(ctx: Ctx, bin_: str) -> None:
    """The OS seam in sync: a systemd user timer on Linux, a launchd agent on macOS.

    macOS: no RunAtLoad (R2): the agent is loaded mid-install, and an immediate sync would
    race the installer's own git calls. launchd runs a missed interval once on wake.
    """
    if ctx.os.family == "macos":
        launchd.user_agent(ctx, AGENT, agent_args(bin_), start_interval=INTERVAL)
        return
    systemd.write_user_unit(ctx, SERVICE, service_unit(bin_))
    systemd.write_user_unit(ctx, TIMER, timer_unit())
    systemd.enable_user_unit(ctx, TIMER, now=True)


def scheduler_installed(ctx: Ctx, bin_: str) -> bool:
    """Installed = what is on disk is exactly what `install_scheduler(bin_)` writes AND the
    scheduler has it live (R3) — a stale path or an unloaded agent means reinstall."""
    if ctx.os.family == "macos":
        return launchd.agent_current(ctx, AGENT, agent_args(bin_), start_interval=INTERVAL)
    return (systemd.unit_current(SERVICE, service_unit(bin_))
            and systemd.unit_current(TIMER, timer_unit())
            and systemd.is_enabled(ctx, TIMER, user=True)
            and systemd.is_active(ctx, TIMER, user=True))


# --- state, log, lock -----------------------------------------------------------------


def _state_file() -> Path:
    return state_dir() / "pass-sync.json"


def _load() -> _State:
    p = _state_file()
    if not p.exists():
        return _State()
    try:
        return _State.model_validate_json(p.read_text(encoding="utf-8"))
    except (ValidationError, OSError, UnicodeDecodeError):
        return _State()  # unreadable state only costs a repeated notice; never raise


def _save(state: _State) -> None:
    p = _state_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")


def _log(msg: str) -> None:
    log.info(f"pass sync: {msg}")
    p = state_dir() / "pass-sync.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(f"{now_iso()} {msg}\n")


@contextmanager
def _lock() -> Iterator[bool]:
    """Non-blocking exclusive lock (D11): a second concurrent sync just yields False."""
    p = state_dir() / "pass-sync.lock"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True


def last_sync() -> str:
    return _load().last_sync


def remember_devices(fingerprints: Iterable[str]) -> None:
    """Record keys this device approved itself, so the tripwire does not announce them."""
    state = _load()
    if state.known_devices is None:
        return  # not seeded yet: the first sync takes in everything listed then anyway
    state.known_devices = sorted({*state.known_devices, *(f.upper() for f in fingerprints)})
    _save(state)


# --- the sync itself ------------------------------------------------------------------


def _access(ctx: Ctx, store: Store, device: str) -> enroll.Access | None:
    try:
        return enroll.local_access(ctx, store, device)
    except DevbootError as exc:
        _log(f"reading this device's access failed: {exc}")
        return None


def _notify_pending(ctx: Ctx, store: Store, acc: enroll.Access | None, state: _State) -> None:
    pending = {f"{r.name}:{r.fingerprint}": r for r in store.records("pending")}
    # Forget requests that were approved or withdrawn, so a re-request is announced again.
    state.notified = [k for k in state.notified if k in pending]
    if acc is None or not enroll.is_workstation(acc):
        return  # only workstations can approve, so only they are asked
    for key, rec in pending.items():
        if key in state.notified:
            continue
        name = notify.clean(rec.name)
        notify.native(ctx, f"pass: {name} wants access",
                      f"{name} ({notify.clean(rec.os)}) requested access. Approve with: "
                      f"devboost pass approve {name}")
        state.notified.append(key)


def _listed_devices(store: Store) -> dict[str, DeviceRecord]:
    """Registered devices whose key a `.gpg-id` really lists — the ones that can read."""
    return {r.fingerprint.upper(): r for r in store.records("devices")
            if enroll.has_access(store, KeyInfo(r.fingerprint, ()), r.scope)}


def _tripwire(ctx: Ctx, store: Store, acc: enroll.Access | None, state: _State) -> None:
    """I2: whoever can push to the store can add a device. Announce, once, every listed
    device key this device never saw — not its own, not one it approved itself."""
    listed = _listed_devices(store)
    if state.known_devices is None:
        state.known_devices = sorted(listed)
        return
    known = set(state.known_devices)
    own = acc.key.fingerprint.upper() if acc is not None and acc.key is not None else None
    for fp, rec in sorted(listed.items()):
        if fp in known:
            continue
        known.add(fp)
        if fp == own:
            continue
        name = notify.clean(rec.name)
        _log(f"new device key {fp} ({name}) is listed in the store")
        notify.native(ctx, "pass: a new device can read your store",
                      f"{name} ({notify.clean(rec.os)}), key {fp}, was added. If you did not "
                      f"approve it: devboost pass revoke {name}, and cut its GitHub access.")
    state.known_devices = sorted(known)


def _forget_revoked(ctx: Ctx, store: Store) -> None:
    """Delete revoked devices' public keys still in this keyring (I1). Only keys present are
    deleted, so this is a no-op once done; failures are logged, never raised."""
    revoked = store.revoked_fingerprints()
    if not revoked:
        return
    try:
        # Never this device's own key (a revoked device keeps its secret key; gpg refuses).
        own = {k.fingerprint.upper() for k in gpg.secret_keys(ctx)}
        present = (gpg.public_fingerprints(ctx) & revoked) - own
    except DevbootError as exc:
        _log(f"listing keys failed: {exc}")
        return
    for fp in sorted(present):
        res = gpg.delete_public_key(ctx, fp)
        if res.ok:
            _log(f"deleted revoked key {fp}")
        else:
            _log(f"deleting revoked key {fp} failed (exit {res.code})")


def _pull(ctx: Ctx, store: Store, state: _State) -> SyncResult | None:
    """Pull with rebase; a failure result, or None when the pull succeeded."""
    res = git.pull(ctx, store.root)
    if res.ok:
        state.pull_failing = False
        state.conflict_head = None
        return None
    files = git.conflicted(ctx, store.root)
    if files:
        git.abort_rebase(ctx, store.root)
        head = git.head(ctx, store.root)
        _log(f"conflict in {', '.join(files)} at {head} — rebase aborted")
        if state.conflict_head != head:
            notify.native(ctx, "pass sync: conflict",
                          f"Conflict in {notify.clean(', '.join(files), 200)}. Run: "
                          "devboost pass sync --resolve")
            state.conflict_head = head
        return SyncResult("conflict", ", ".join(files))
    _log(f"pull failed (exit {res.code})")
    if not state.pull_failing:
        notify.native(ctx, "pass sync: pull failed",
                      f"git pull failed (exit {res.code}); will retry")
        state.pull_failing = True
    return SyncResult("pull-failed", f"exit {res.code}")


def _push(ctx: Ctx, store: Store, state: _State) -> SyncResult | None:
    """Push when ahead; a failure result (notified once per HEAD), or None on success."""
    if git.ahead(ctx, store.root) > 0:
        res = git.push(ctx, store.root)
        if not res.ok:
            head = git.head(ctx, store.root)
            _log(f"push failed (exit {res.code}) at {head}")
            if state.push_failed_head != head:
                notify.native(ctx, "pass sync: push failed",
                              f"git push failed (exit {res.code}); will retry")
                state.push_failed_head = head
            return SyncResult("push-failed", f"exit {res.code}")
    state.push_failed_head = None
    return None


def _sync(ctx: Ctx, store: Store, device: str, state: _State, push_only: bool) -> SyncResult:
    if not push_only:
        failed = _pull(ctx, store, state)
        if failed is not None:
            if failed.status == "pull-failed":
                # Still push: a store whose first push never landed has no remote branch,
                # so every pull fails until something is pushed.
                _push(ctx, store, state)
            return failed
    failed = _push(ctx, store, state)
    if failed is not None:
        return failed
    if not push_only:
        try:
            enroll.import_device_keys(ctx, store)
        except DevbootError as exc:
            _log(f"importing device keys failed: {exc}")
        _forget_revoked(ctx, store)
        acc = _access(ctx, store, device)
        _notify_pending(ctx, store, acc, state)
        _tripwire(ctx, store, acc, state)
    state.last_sync = now_iso()
    return SyncResult("ok")


def run(ctx: Ctx, store: Store, device: str, *, push_only: bool = False) -> SyncResult:
    if os.environ.get("DEVBOOST_PASS_HOOK") == "off":
        return SyncResult("skipped", "devboost's own commit")
    if not store.is_clone():
        return SyncResult("no-store")
    with _lock() as got:
        if not got:
            return SyncResult("busy")
        state = _load()
        result = _sync(ctx, store, device, state, push_only)
        _save(state)
        return result


def resolve_guidance(ctx: Ctx, store: Store) -> str:
    """D13: explain the manual fix for a conflicted sync; changes nothing itself."""
    files = git.conflicted(ctx, store.root)
    fps = [r.fingerprint for r in store.records("devices") if r.scope is None]
    return "\n".join([
        "devboost pass sync --resolve — nothing is changed automatically.",
        f"store: {store.root}",
        f"conflicted files now: {', '.join(files) or 'none (the last sync aborted its rebase)'}",
        "The device registry (.devboost/devices) says the root .gpg-id must list exactly:",
        *[f"  {fp}" for fp in fps],
        "Fix:",
        f"  cd {store.root}",
        "  git pull --rebase                  # reproduces the conflict",
        "  # write exactly the fingerprints above into .gpg-id, then:",
        "  git add .gpg-id && git rebase --continue",
        f"  pass init {' '.join(fps)}   # re-encrypt every entry to that set",
        "  git push && devboost pass sync",
    ])
