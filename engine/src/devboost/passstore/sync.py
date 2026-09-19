"""Keep every device's clone current: push on commit (hook), pull every 15 min (timer).

Never raises into the caller for network/git trouble — it logs, notifies (de-duplicated)
and returns a status, because a sync problem must never block anything else.
"""

from __future__ import annotations

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from devboost.core import log
from devboost.core.errors import DevbootError, UnsupportedOS
from devboost.exec.primitives import systemd
from devboost.model import Ctx
from devboost.passstore import enroll, git, notify
from devboost.passstore.layout import Store, now_iso
from devboost.passstore.paths import state_dir

SERVICE = "devboost-pass-sync.service"
TIMER = "devboost-pass-sync.timer"
HOOK_MARK = "# managed by devboost (pass-store)"

SyncStatus = Literal["ok", "skipped", "busy", "no-store", "conflict", "pull-failed",
                     "push-failed"]


@dataclass(frozen=True)
class SyncResult:
    status: SyncStatus
    detail: str = ""


class _State(BaseModel):
    notified: list[str] = []
    push_failed_head: str = ""
    pull_failing: bool = False
    last_sync: str = ""


# --- hook + scheduler -----------------------------------------------------------------


def hook_script(bin_: str) -> str:
    """The 3-line post-commit stub: no logic, just a background `devboost` call (D10)."""
    return (
        "#!/bin/sh\n"
        f"{HOOK_MARK} — push each commit in the background; all logic lives in devboost.\n"
        f'"{bin_}" pass sync --push-only --quiet </dev/null >/dev/null 2>&1 &\n'
    )


def _hook_path(store: Store) -> Path:
    return store.root / ".git" / "hooks" / "post-commit"


def hook_installed(store: Store) -> bool:
    p = _hook_path(store)
    return p.exists() and HOOK_MARK in p.read_text(encoding="utf-8")


def install_hook(store: Store, bin_: str) -> bool:
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
            f"ExecStart={bin_} pass sync --quiet\n")


def timer_unit() -> str:
    return ("[Unit]\nDescription=devboost pass store sync every 15 min\n\n[Timer]\n"
            "OnCalendar=*:0/15\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n")


def install_scheduler(ctx: Ctx, bin_: str) -> None:
    """The only OS seam in sync: systemd user timer on Linux, launchd agent in P2."""
    if ctx.os.family == "macos":
        # P2: launchd.user_agent(ctx, launchd.label("pass-sync"), [bin_, "pass", "sync",
        #     "--quiet"], start_interval=900)
        raise UnsupportedOS("pass sync scheduling on macOS arrives in P2 (launchd agent)")
    systemd.write_user_unit(ctx, SERVICE, service_unit(bin_))
    systemd.write_user_unit(ctx, TIMER, timer_unit())
    systemd.enable_user_unit(ctx, TIMER, now=True)


def scheduler_installed(ctx: Ctx) -> bool:
    return (systemd._user_unit_dir() / TIMER).exists()


# --- state, log, lock -----------------------------------------------------------------


def _state_file() -> Path:
    return state_dir() / "pass-sync.json"


def _load() -> _State:
    p = _state_file()
    if not p.exists():
        return _State()
    try:
        return _State.model_validate_json(p.read_text(encoding="utf-8"))
    except ValidationError:
        return _State()


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


# --- the sync itself ------------------------------------------------------------------


def _notify_pending(ctx: Ctx, store: Store, device: str, state: _State) -> None:
    if not enroll.is_workstation(enroll.local_access(ctx, store, device)):
        return  # only workstations can approve, so only they are asked
    for rec in store.records("pending"):
        key = f"{rec.name}:{rec.fingerprint}"
        if key in state.notified:
            continue
        notify.native(ctx, f"pass: {rec.name} wants access",
                      f"{rec.name} ({rec.os}) requested access. Approve with: "
                      f"devboost pass approve {rec.name}")
        state.notified.append(key)


def _pull(ctx: Ctx, store: Store, state: _State) -> SyncResult | None:
    """Pull with rebase; a failure result, or None when the pull succeeded."""
    res = git.pull(ctx, store.root)
    if res.ok:
        state.pull_failing = False
        return None
    files = git.conflicted(ctx, store.root)
    if files:
        git.abort_rebase(ctx, store.root)
        _log(f"conflict in {', '.join(files)} — rebase aborted")
        notify.native(ctx, "pass sync: conflict",
                      f"Conflict in {', '.join(files)}. Run: devboost pass sync --resolve")
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
    state.push_failed_head = ""
    return None


def _sync(ctx: Ctx, store: Store, device: str, state: _State, push_only: bool) -> SyncResult:
    if not push_only:
        failed = _pull(ctx, store, state)
        if failed is not None:
            return failed
    failed = _push(ctx, store, state)
    if failed is not None:
        return failed
    if not push_only:
        try:
            enroll.import_device_keys(ctx, store)
        except DevbootError as exc:
            _log(f"importing device keys failed: {exc}")
        _notify_pending(ctx, store, device, state)
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
