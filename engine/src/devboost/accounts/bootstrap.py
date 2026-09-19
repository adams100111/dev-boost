"""Install a managed user's bootstrap_profiles as that user, via DemotingExecutor."""

from __future__ import annotations

import os
import pwd
import stat
import time
from collections.abc import Callable
from pathlib import Path

from devboost.accounts.config import ManagedUser
from devboost.accounts.reconcile import home_of
from devboost.core import log
from devboost.core.graph import toposort
from devboost.core.plan import build_plan
from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load, validate_profiles
from devboost.core.runner import run_plan
from devboost.exec.executor import DemotingExecutor
from devboost.model import Ctx


def _run_profiles(ctx: Ctx, tokens: list[str], root: Path) -> None:
    modules = load()
    profiles = load_profiles(root / "profiles.toml")
    validate_profiles(modules, set(profiles))
    order = toposort(expand(tokens, profiles, modules), modules)
    plan = build_plan(order, modules, ctx.os)
    run_plan(plan, modules, ctx)


def _reclaim_one(
    path: Path,
    *,
    uid: int,
    gid: int,
    since: float,
    lstat: Callable[[Path], os.stat_result],
    lchown: Callable[[Path, int, int], None],
) -> bool:
    """Hand *path* back to (uid, gid) when root created or touched it during this run."""
    try:
        st = lstat(path)
    except OSError as exc:  # vanished mid-walk, or a directory we may not stat
        log.warn(f"accounts: cannot stat {path} — {exc}")
        return False
    if st.st_uid != 0:
        return False  # already the user's (or another account's): never touch it
    if st.st_mtime < since and st.st_ctime < since:
        return False  # predates the run — an admin put it there on purpose
    if stat.S_ISREG(st.st_mode) and st.st_nlink > 1:
        # Defence in depth: a multiply-linked regular file may be a hardlink the user
        # planted to a root-owned inode elsewhere, and chowning it would hand that inode
        # over. (Linux's fs.protected_hardlinks already blocks planting one.)
        return False
    try:
        lchown(path, uid, gid)  # l-variant: a symlink is chowned, never its target
    except OSError as exc:
        log.warn(f"accounts: could not reclaim {path} — {exc}")
        return False
    return True


def reclaim_home(
    home: Path,
    *,
    uid: int,
    gid: int,
    since: float,
    lstat: Callable[[Path], os.stat_result] = os.lstat,
    lchown: Callable[[Path, int, int], None] = os.lchown,
) -> list[Path]:
    """Give (uid, gid) back every root-owned path under *home* touched since *since*.

    The root path of an ``accounts`` run writes plenty of user config in-process —
    ``jsonc_merge_deep``, ``_atomic_write``, ``_zed.seed_files``, the ``fs.write`` helpers,
    the ``shell.py`` rc writers — and ``DemotingExecutor`` only demotes *shelled-out*
    commands, so those files land root-owned. One post-pass fixes all of them at once.

    Safety (this runs as root, over a directory an unprivileged user controls):

    * the walk is rooted at *home* with ``followlinks=False``, so it never leaves HOME;
    * ownership is changed with ``lchown``, so a symlink planted inside HOME is chowned
      as a *link* and whatever it points at outside HOME is never touched — which also
      makes the stat/chown pair TOCTOU-safe, since swapping the path for a symlink in
      between still cannot reach the target;
    * a path that was not root-owned is never touched, and neither is one that predates
      the run.

    It never raises: a path that vanishes or refuses the chown is logged and skipped.
    Returns the paths actually chowned, sorted.

    This is Linux-only in practice: ``accounts`` is in ``cli/host.LINUX_ONLY`` and the
    root guard in ``cli/host.invocation_error`` refuses euid 0 on macOS outright.
    """
    root = Path(home)
    candidates: list[Path] = [root]
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(dirpath)
        # Real subdirectories come back as their own dirpath, so listing them here would
        # double-visit them — except symlinked dirs, which os.walk lists but never enters.
        # Taking them from the parent's listing covers both exactly once.
        candidates.extend(here / name for name in dirnames)
        candidates.extend(here / name for name in filenames)
    reclaimed = [
        p for p in candidates
        if _reclaim_one(p, uid=uid, gid=gid, since=since, lstat=lstat, lchown=lchown)
    ]
    return sorted(reclaimed)


def bootstrap_user(ctx: Ctx, user: ManagedUser, *, root: Path) -> None:
    """Install user.bootstrap_profiles for *user*: root for privileged, user for the rest."""
    old_home = os.environ.get("HOME")
    home = home_of(user)
    os.environ["HOME"] = home  # modules compute ~paths from $HOME
    since = time.time()
    try:
        demoted = Ctx(
            os=ctx.os,
            ex=DemotingExecutor(ctx.ex, user.name),
            force=ctx.force,
            dry_run=ctx.dry_run,
        )
        _run_profiles(demoted, list(user.bootstrap_profiles), root)
    finally:
        # Still inside the user's HOME: hand back whatever the in-process writers created
        # as root. Runs even when the profiles raised, and never raises itself.
        if os.geteuid() == 0 and not ctx.dry_run:
            try:
                pw = pwd.getpwnam(user.name)
                done = reclaim_home(Path(home), uid=pw.pw_uid, gid=pw.pw_gid, since=since)
                if done:
                    log.info(f"accounts: reclaimed {len(done)} root-owned path(s) in {home}")
            except Exception as exc:  # never mask the run's own error
                log.warn(f"accounts: could not reclaim root-owned files in {home} — {exc}")
        if old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = old_home
