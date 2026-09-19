"""Install a managed user's bootstrap_profiles as that user, via DemotingExecutor."""

from __future__ import annotations

import math
import os
import pwd
import stat
import time
from collections.abc import Callable, Iterator
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

#: One ``os.fwalk`` yield: (dirpath, dirnames, filenames, an open fd for dirpath).
FwalkEntry = tuple[str, list[str], list[str], int]
Fwalk = Callable[[Path], Iterator[FwalkEntry]]
#: ``stat``/``chown`` of a *bare name* relative to an already-open directory fd.
StatAt = Callable[[str, int | None], os.stat_result]
ChownAt = Callable[[str, int, int, int | None], None]

#: sysctl that stops an unprivileged user hardlinking a file they neither own nor can
#: write. 1 on every distro dev-boost targets (Fedora, Debian/Ubuntu, Arch).
PROTECTED_HARDLINKS = Path("/proc/sys/fs/protected_hardlinks")

#: Cap on per-path warnings from one reclaim pass, so a HOME full of vanished cache files
#: (a concurrent `rm -rf`) cannot turn into unbounded log spam.
_WARN_LIMIT = 10


def _run_profiles(ctx: Ctx, tokens: list[str], root: Path) -> None:
    modules = load()
    profiles = load_profiles(root / "profiles.toml")
    validate_profiles(modules, set(profiles))
    order = toposort(expand(tokens, profiles, modules), modules)
    plan = build_plan(order, modules, ctx.os)
    run_plan(plan, modules, ctx)


def _fwalk_nofollow(home: Path) -> Iterator[FwalkEntry]:
    """``os.fwalk`` with the safe settings. Yields nothing when *home* is a symlink."""
    return os.fwalk(home, follow_symlinks=False)


def _stat_at(name: str, dir_fd: int | None) -> os.stat_result:
    return os.stat(name, dir_fd=dir_fd, follow_symlinks=False)


def _chown_at(name: str, uid: int, gid: int, dir_fd: int | None) -> None:
    # fchownat(dir_fd, name, …, AT_SYMLINK_NOFOLLOW): no parent component is re-resolved
    # and a symlink is chowned as a link, never through it.
    os.chown(name, uid, gid, dir_fd=dir_fd, follow_symlinks=False)


def _hardlinks_protected(marker: Path = PROTECTED_HARDLINKS) -> bool:
    """Is ``fs.protected_hardlinks`` on? Unreadable (non-Linux, container) counts as off."""
    try:
        return marker.read_text(encoding="utf-8").strip() == "1"
    except OSError:
        return False


class _Warner:
    """Emits at most ``_WARN_LIMIT`` warnings, then one aggregate line."""

    def __init__(self, limit: int = _WARN_LIMIT) -> None:
        self.limit = limit
        self.count = 0

    def __call__(self, msg: str) -> None:
        self.count += 1
        if self.count <= self.limit:
            log.warn(msg)

    def summarise(self, what: str) -> None:
        if self.count > self.limit:
            log.warn(f"accounts: … and {self.count - self.limit} more {what}")


def _should_reclaim(
    st: os.stat_result, *, since: float, allow_hardlinks: bool
) -> str | None:
    """None when this entry must be handed back, else why it is left alone."""
    if st.st_uid != 0:
        return "not-root-owned"  # already the user's (or another account's)
    if st.st_mtime < since and st.st_ctime < since:
        return "predates-the-run"  # an admin put it there on purpose
    if not allow_hardlinks and stat.S_ISREG(st.st_mode) and st.st_nlink > 1:
        return "multiply-linked"
    return None


def reclaim_home(
    home: Path,
    *,
    uid: int,
    gid: int,
    since: float,
    fwalk: Fwalk = _fwalk_nofollow,
    stat_at: StatAt = _stat_at,
    chown_at: ChownAt = _chown_at,
    hardlinks_protected: Callable[[], bool] = _hardlinks_protected,
) -> list[Path]:
    """Give (uid, gid) back every root-owned path under *home* touched since *since*.

    The root path of an ``accounts`` run writes plenty of user config in-process —
    ``jsonc_merge_deep``, ``_atomic_write``, ``_zed.seed_files``, the ``fs.write`` helpers,
    the ``shell.py`` rc writers — and ``DemotingExecutor`` only demotes *shelled-out*
    commands, so those files land root-owned. One post-pass fixes all of them at once.

    Safety. This runs **as root** over a directory an unprivileged user owns and can
    rewrite at any instant, so every operation is performed against an already-open
    directory fd, never by re-resolving a path:

    * ``os.fwalk(follow_symlinks=False)`` opens each directory relative to its parent's fd
      and verifies with ``samestat`` that the fd it got is the directory it classified, so
      swapping a subdirectory for ``sub -> /etc`` mid-pass cannot make the walk descend
      into the target. (``os.walk`` would: it re-resolves by name, and ``lchown`` only
      guards the *final* component of a path.)
    * ownership is changed with ``os.chown(name, …, dir_fd=…, follow_symlinks=False)`` —
      a bare name against that verified fd, so no parent component is re-resolved, and a
      symlink planted inside HOME is chowned as a *link* whose target is never touched.
    * *home* itself is refused unless it is a real directory: ``os.fwalk`` yields nothing
      for a symlinked top, and this checks first so it can say why.
    * a path that was not root-owned is never touched, and neither is one that predates
      the run.

    Hardlinks. ``chown`` follows the *inode*, so a hardlink the user planted to a
    root-owned file elsewhere would hand that inode over. Linux's
    ``fs.protected_hardlinks`` already forbids planting one, so when that sysctl reads 1
    (the default on every distro dev-boost targets) multiply-linked files are reclaimed
    normally — which matters, because hardlink stores *inside* HOME are ordinary: ``uv``
    links from ``~/.cache/uv`` into every venv, and ``pnpm``/``npm`` do the same from their
    content-addressable stores. Only when the sysctl is off or unreadable are multiply-
    linked regular files skipped (and each skip is logged), leaving those stores root-owned.

    It never raises: a path that vanishes or refuses the chown is logged and skipped.
    Returns the paths actually chowned, sorted.

    This is Linux-only in practice: ``accounts`` is in ``cli/host.LINUX_ONLY`` and the
    root guard in ``cli/host.invocation_error`` refuses euid 0 on macOS outright.
    """
    root = Path(home)
    try:
        top = stat_at(str(root), None)
    except OSError as exc:
        log.warn(f"accounts: cannot stat {root} — skipping the reclaim pass ({exc})")
        return []
    if not stat.S_ISDIR(top.st_mode):
        kind = "a symlink" if stat.S_ISLNK(top.st_mode) else "not a directory"
        log.warn(f"accounts: {root} is {kind} — skipping the reclaim pass")
        return []

    allow_hardlinks = hardlinks_protected()
    failed, linked = _Warner(), _Warner()
    reclaimed: list[Path] = []

    for dirpath, dirnames, filenames, dirfd in fwalk(root):
        here = Path(dirpath)
        # Real subdirectories come back as their own dirpath, so taking directories from
        # the *parent's* listing visits each exactly once — and is the only way a
        # symlinked dir (listed, never entered) gets reclaimed as a link. `.` covers HOME
        # itself on the first yield.
        names = ["."] if here == root else []
        names += dirnames + filenames
        for name in names:
            try:
                st = stat_at(name, dirfd)
            except OSError as exc:  # vanished mid-walk
                failed(f"accounts: cannot stat {here / name} — {exc}")
                continue
            why = _should_reclaim(st, since=since, allow_hardlinks=allow_hardlinks)
            if why == "multiply-linked":
                linked(
                    f"accounts: leaving {here / name} root-owned — it has "
                    f"{st.st_nlink} hardlinks and fs.protected_hardlinks is off"
                )
                continue
            if why is not None:
                continue
            try:
                chown_at(name, uid, gid, dirfd)
            except OSError as exc:
                failed(f"accounts: could not reclaim {here / name} — {exc}")
                continue
            reclaimed.append(here if name == "." else here / name)

    failed.summarise("path(s) that could not be reclaimed")
    linked.summarise("multiply-linked path(s)")
    return sorted(reclaimed)


def bootstrap_user(ctx: Ctx, user: ManagedUser, *, root: Path) -> None:
    """Install user.bootstrap_profiles for *user*: root for privileged, user for the rest."""
    old_home = os.environ.get("HOME")
    home = home_of(user)
    os.environ["HOME"] = home  # modules compute ~paths from $HOME
    # Floor to the second: a filesystem with 1 s timestamp granularity truncates, so a
    # file written in this very second would otherwise round below `since` and be missed.
    since = math.floor(time.time())
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
                if pw.pw_dir and pw.pw_dir != home:
                    # home_of() hard-codes /home/<name>, which is what this run put in
                    # $HOME and therefore the only tree the modules wrote into — so that
                    # is what gets reclaimed. A divergence means the two disagree and the
                    # account's real home was never written to; say so rather than
                    # silently reclaiming a tree nobody touched.
                    log.warn(
                        f"accounts: {user.name}'s passwd home is {pw.pw_dir}, but the "
                        f"bootstrap used {home} — reclaiming {home}"
                    )
                done = reclaim_home(Path(home), uid=pw.pw_uid, gid=pw.pw_gid, since=since)
                if done:
                    log.info(f"accounts: reclaimed {len(done)} root-owned path(s) in {home}")
            except Exception as exc:  # never mask the run's own error
                log.warn(f"accounts: could not reclaim root-owned files in {home} — {exc}")
        if old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = old_home
