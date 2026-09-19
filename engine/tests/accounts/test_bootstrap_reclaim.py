"""`bootstrap_user` hands root-owned files it created in the managed user's HOME back.

Carry-over audit question — *does the root path actually write user config in-process?*
Yes, in many places: ``jsonc_merge_deep`` and ``_atomic_write`` (editor settings),
``_zed.seed_files``, the ``fs.write`` helpers and the ``shell.py`` rc writers all run
in-process under the root interpreter while ``$HOME`` points at the managed user's home,
so every file they create lands root-owned. ``DemotingExecutor`` only demotes *shelled-out*
commands, never these. Rather than chase 25+ writers, ``reclaim_home`` runs one post-pass
over the target HOME and hands back everything root created during the run — which fixes
all of them at once.

The pass runs as root over a directory an unprivileged user owns and can rewrite at any
instant, so the tests below are mostly about what it refuses to do: leave HOME, follow a
symlink, re-resolve a path a swap has poisoned, or touch a file that was not root's.

This never runs on macOS: ``accounts`` is in ``cli/host.LINUX_ONLY`` and the root guard in
``cli/host.invocation_error`` refuses euid 0 on a Mac outright.
"""

from __future__ import annotations

import inspect
import math
import os
import pwd
import stat
import sys
import time
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from types import SimpleNamespace

import pytest
from loguru import logger

from devboost.accounts import bootstrap
from devboost.accounts.bootstrap import FwalkEntry, reclaim_home
from devboost.accounts.config import ManagedUser
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx

SINCE = 1_000_000.0
NEW = SINCE + 10.0
OLD = SINCE - 10.0
USER_UID, USER_GID = 1000, 1000

#: The stat overrides a fake applies to a path: (uid, mtime/ctime).
Table = Mapping[str, tuple[int, float]]


def _user(**over: object) -> ManagedUser:
    base = dict(
        name="dev", enabled=True, shell="/bin/bash", lock_shell=False, linger=False,
        privilege="none", sudo_commands=(), ram=None, cpu=None, tasks=None, disk=None,
        ssh_authorized_keys=(), bootstrap_profiles=("terminal",),
    )
    base.update(over)
    return ManagedUser(**base)  # type: ignore[arg-type]


def _index(*roots: Path) -> dict[tuple[int, int], Path]:
    """Map every directory's (st_dev, st_ino) to its path, so a fake can turn the
    ``(name, dir_fd)`` pair ``reclaim_home`` works in back into a path to assert on."""
    out: dict[tuple[int, int], Path] = {}
    for root in roots:
        for dirpath, _dirnames, _filenames in os.walk(root):
            st = os.stat(dirpath)
            out[(st.st_dev, st.st_ino)] = Path(dirpath)
    return out


class _Fakes:
    """``stat_at``/``chown_at`` fakes that key on the real path behind ``(name, dir_fd)``.

    The mode bits stay real (so directories, files and symlinks are honest); only uid,
    mtime/ctime and — where asked — ``st_nlink`` are forced. A path missing from *table*
    reads as an untouched user-owned file.
    """

    def __init__(
        self,
        index: Mapping[tuple[int, int], Path],
        table: Table,
        *,
        nlink: Mapping[str, int] | None = None,
        chown_raises: Mapping[str, Exception] | None = None,
        on_stat: Callable[[Path], None] | None = None,
    ) -> None:
        self.index = dict(index)
        self.table = dict(table)
        self.nlink = dict(nlink or {})
        self.chown_raises = dict(chown_raises or {})
        self.on_stat = on_stat
        self.stat_paths: list[Path] = []
        self.stat_dir_fds: list[tuple[Path, int | None]] = []
        self.chown_calls: list[tuple[Path, int, int, int | None]] = []
        self.fchown_calls: list[tuple[Path, int, int]] = []

    def _inode_path(self, fd: int) -> Path:
        """The path of the inode *fd* holds, searched among the indexed dirs' entries."""
        st = os.fstat(fd)
        for base in self.index.values():
            if (os.lstat(base).st_dev, os.lstat(base).st_ino) == (st.st_dev, st.st_ino):
                return base
            for child in base.iterdir():
                c = os.lstat(child)
                if (c.st_dev, c.st_ino) == (st.st_dev, st.st_ino):
                    return child
        raise AssertionError(f"fstat of an inode outside the index: {st.st_ino}")

    def _forced(self, path: Path, real: os.stat_result) -> os.stat_result:
        uid, when = self.table.get(str(path), (USER_UID, OLD))
        fields = list(real)[:10]
        fields[3] = self.nlink.get(str(path), real.st_nlink)
        fields[4] = uid
        fields[8] = fields[9] = when
        return os.stat_result(fields)

    def fstat_fd(self, fd: int) -> os.stat_result:
        return self._forced(self._inode_path(fd), os.fstat(fd))

    def fchown_fd(self, fd: int, uid: int, gid: int) -> None:
        path = self._inode_path(fd)
        self.fchown_calls.append((path, uid, gid))
        exc = self.chown_raises.get(str(path))
        if exc is not None:
            raise exc

    def resolve(self, name: str, dir_fd: int | None) -> Path:
        if dir_fd is None:
            return Path(name)
        st = os.fstat(dir_fd)
        base = self.index.get((st.st_dev, st.st_ino))
        assert base is not None, f"chown/stat against an unknown directory fd: {st.st_ino}"
        return base if name == "." else base / name

    def stat_at(self, name: str, dir_fd: int | None) -> os.stat_result:
        path = self.resolve(name, dir_fd)
        self.stat_paths.append(path)
        self.stat_dir_fds.append((path, dir_fd))
        real = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        forced = self._forced(path, real)
        if self.on_stat is not None:
            self.on_stat(path)
        return forced

    def chown_at(self, name: str, uid: int, gid: int, dir_fd: int | None) -> None:
        path = self.resolve(name, dir_fd)
        self.chown_calls.append((path, uid, gid, dir_fd))
        exc = self.chown_raises.get(str(path))
        if exc is not None:
            raise exc

    @property
    def chown_paths(self) -> list[Path]:
        return [c[0] for c in self.chown_calls]


def _write_stderr(msg: str) -> None:
    sys.stderr.write(msg)


@pytest.fixture
def loguru_stderr() -> Iterator[None]:
    """loguru binds the ``sys.stderr`` *object* at import time, so pytest's capture never
    sees it. Swap in a sink that dereferences ``sys.stderr`` at write time (the same trick
    as ``tests/cli/conftest.py``) so ``capsys`` can read the log lines."""
    logger.remove()
    logger.add(_write_stderr, format="{message}", level="INFO")
    yield
    logger.remove()
    logger.add(sys.stderr, format="{message}", level="INFO")


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home" / "dev"
    h.mkdir(parents=True)
    return h


def _reclaim(home: Path, fakes: _Fakes, *, protected: bool = True) -> list[Path]:
    return reclaim_home(
        home, uid=USER_UID, gid=USER_GID, since=SINCE,
        stat_at=fakes.stat_at, chown_at=fakes.chown_at,
        hardlinks_protected=lambda: protected,
        fstat_fd=fakes.fstat_fd, fchown_fd=fakes.fchown_fd,
    )


# --- what it reclaims -----------------------------------------------------------------


def test_reclaims_new_root_owned_files(home: Path) -> None:
    (home / "a").write_text("a", encoding="utf-8")
    (home / "b").write_text("b", encoding="utf-8")
    nested = home / "nested"
    nested.mkdir()
    (nested / "c").write_text("c", encoding="utf-8")
    fakes = _Fakes(_index(home), {str(home / "a"): (0, NEW), str(nested / "c"): (0, NEW)})

    done = _reclaim(home, fakes)

    assert done == sorted([home / "a", nested / "c"])
    assert set(fakes.chown_paths) == {home / "a", nested / "c"}
    assert all(c[1:3] == (USER_UID, USER_GID) for c in fakes.chown_calls)


def test_reclaims_the_home_directory_itself(home: Path) -> None:
    fakes = _Fakes(_index(home), {str(home): (0, NEW)})
    assert _reclaim(home, fakes) == [home]
    assert fakes.chown_paths == [home]


def test_leaves_old_root_files(home: Path) -> None:
    """A root-owned file the admin placed on purpose, before the run, is left alone."""
    (home / "admin-placed").write_text("x", encoding="utf-8")
    fakes = _Fakes(_index(home), {str(home / "admin-placed"): (0, OLD)})
    assert _reclaim(home, fakes) == []
    assert fakes.chown_calls == []


def test_reclaims_on_ctime_alone(home: Path) -> None:
    """A file root only re-chmod'ed during the run bumps ctime, not mtime."""
    target = home / "rc"
    target.write_text("x", encoding="utf-8")
    fakes = _Fakes(_index(home), {})

    def stat_at(name: str, dir_fd: int | None) -> os.stat_result:
        st = fakes.stat_at(name, dir_fd)
        if fakes.resolve(name, dir_fd) == target:
            fields = list(st)[:10]
            fields[4] = 0
            fields[8] = OLD  # mtime old …
            fields[9] = NEW  # … ctime new
            return os.stat_result(fields)
        return st

    done = reclaim_home(
        home, uid=USER_UID, gid=USER_GID, since=SINCE,
        stat_at=stat_at, chown_at=fakes.chown_at, hardlinks_protected=lambda: True,
    )
    assert done == [target]


def test_leaves_user_owned_files(home: Path) -> None:
    (home / "mine").write_text("x", encoding="utf-8")
    fakes = _Fakes(_index(home), {str(home / "mine"): (USER_UID, NEW)})
    assert _reclaim(home, fakes) == []
    assert fakes.chown_calls == []


# --- what it refuses to do ------------------------------------------------------------


def test_never_follows_symlinks(home: Path, tmp_path: Path) -> None:
    """A hostile symlink inside HOME pointing outside it: the link is chowned as a link,
    and the outside tree is neither walked nor stat'ed."""
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret"
    secret.write_text("root-only", encoding="utf-8")
    (home / "escape").symlink_to(secret)
    (home / "escape-dir").symlink_to(outside, target_is_directory=True)
    fakes = _Fakes(
        _index(home, outside),
        {str(home / "escape"): (0, NEW), str(home / "escape-dir"): (0, NEW)},
    )

    done = _reclaim(home, fakes)

    assert set(done) == {home / "escape", home / "escape-dir"}
    assert not [p for p in fakes.stat_paths if p == outside or outside in p.parents]
    assert not [p for p in fakes.chown_paths if p == outside or outside in p.parents]
    assert secret.read_text(encoding="utf-8") == "root-only"


def test_refuses_a_symlinked_home(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], loguru_stderr: None
) -> None:
    """I1: an admin who relocates a home with `/home/dev -> /srv/dev` must not have the
    target tree reclaimed — `os.walk(followlinks=False)` *does* descend a symlinked top,
    so the pass checks HOME's own mode first and says why it bailed."""
    real = tmp_path / "srv" / "dev"
    real.mkdir(parents=True)
    (real / "file").write_text("x", encoding="utf-8")
    link = tmp_path / "home-link"
    link.symlink_to(real, target_is_directory=True)
    fakes = _Fakes(_index(real), {str(real / "file"): (0, NEW), str(real): (0, NEW)})

    assert _reclaim(link, fakes) == []
    assert fakes.stat_paths == [link]  # HOME's own lstat, nothing under the target
    assert fakes.chown_calls == []
    assert "is a symlink — skipping the reclaim pass" in capsys.readouterr().err


def test_a_mid_pass_directory_swap_cannot_escape_home(home: Path, tmp_path: Path) -> None:
    """C1: the managed user owns HOME and can `rename()` a subdirectory away and drop
    `sub -> /etc` in its place while root is still walking.

    Two guarantees, both structural rather than timing-dependent:

    1. every chown is a **bare name against an open directory fd** (never a path), so no
       parent component is re-resolved — here the swap is sprung from the first `stat_at`
       inside `sub`, and the following chown still lands in the real directory the fd
       holds open, not in the tree the new symlink points at;
    2. `os.fwalk(follow_symlinks=False)` samestat-verifies each fd against the entry it
       classified, so the walk never descends into the swapped-in target either.
    """
    outside = tmp_path / "etc"
    outside.mkdir()
    shadow = outside / "shadow"
    shadow.write_text("root-only", encoding="utf-8")
    sub = home / "sub"
    sub.mkdir()
    (sub / "real").write_text("x", encoding="utf-8")
    index = _index(home, outside)
    sprung: list[bool] = []

    def swap_once(path: Path) -> None:
        # The attacker gets the CPU the moment root stats the first entry inside `sub`.
        if not sprung and path.parent == sub:
            sprung.append(True)
            sub.rename(home / "sub-moved")
            (home / "sub").symlink_to(outside, target_is_directory=True)

    everything_root = {
        str(p): (0, NEW)
        for p in (home, sub, sub / "real", outside, shadow, home / "sub-moved")
    }
    fakes = _Fakes(index, everything_root, on_stat=swap_once)

    done = _reclaim(home, fakes)

    assert sprung, "the swap never fired — the test proves nothing"
    assert not [p for p in done if p == outside or outside in p.parents]
    assert not [p for p in fakes.chown_paths if p == outside or outside in p.parents]
    assert not [p for p in fakes.stat_paths if p == shadow]
    # Every chown went through a directory fd; nothing was chowned by path.
    assert all(c[3] is not None for c in fakes.chown_calls)
    # …and every stat that fed a decision did too: only HOME's own pre-check is by path.
    assert [p for p, fd in fakes.stat_dir_fds if fd is None] == [home]
    assert shadow.read_text(encoding="utf-8") == "root-only"


def test_the_walk_never_descends_a_swapped_in_symlink(home: Path, tmp_path: Path) -> None:
    """The same swap, sprung between two `os.fwalk` yields: the target's entries are never
    enumerated as if they were HOME's."""
    outside = tmp_path / "etc"
    outside.mkdir()
    (outside / "shadow").write_text("root-only", encoding="utf-8")
    sub = home / "sub"
    sub.mkdir()
    (sub / "real").write_text("x", encoding="utf-8")
    index = _index(home, outside)

    def swapping_fwalk(top: Path) -> Iterator[FwalkEntry]:
        for i, entry in enumerate(os.fwalk(top, follow_symlinks=False)):
            if i == 0:
                sub.rename(home / "sub-moved")
                (home / "sub").symlink_to(outside, target_is_directory=True)
            yield entry

    fakes = _Fakes(index, {str(p): (0, NEW) for p in (home, home / "sub")})
    done = reclaim_home(
        home, uid=USER_UID, gid=USER_GID, since=SINCE, fwalk=swapping_fwalk,
        stat_at=fakes.stat_at, chown_at=fakes.chown_at, hardlinks_protected=lambda: True,
    )

    assert not [p for p in fakes.stat_paths if p == outside or outside in p.parents]
    assert not [p for p in done if p == outside or outside in p.parents]
    assert (outside / "shadow").read_text(encoding="utf-8") == "root-only"


# --- hardlinks (I2) -------------------------------------------------------------------


def test_hardlinked_files_are_reclaimed_when_the_sysctl_protects_them(home: Path) -> None:
    """`uv` hardlinks from ~/.cache/uv into every venv, and pnpm/npm do the same from
    their stores. With fs.protected_hardlinks=1 the user cannot have planted a link to a
    root-owned inode, so those files are handed back like any other."""
    store = home / ".cache" / "uv"
    store.mkdir(parents=True)
    (store / "wheel").write_text("x", encoding="utf-8")
    os.link(store / "wheel", home / "venv-copy")
    fakes = _Fakes(
        _index(home), {str(store / "wheel"): (0, NEW), str(home / "venv-copy"): (0, NEW)}
    )

    done = _reclaim(home, fakes, protected=True)

    assert done == sorted([store / "wheel", home / "venv-copy"])


def test_hardlinked_files_are_skipped_and_logged_when_unprotected(
    home: Path, capsys: pytest.CaptureFixture[str], loguru_stderr: None
) -> None:
    """Without the sysctl a hardlink may reach a root-owned inode outside HOME, and chown
    follows the inode — so those files stay root-owned, and the operator is told which."""
    (home / "linked").write_text("x", encoding="utf-8")
    (home / "plain").write_text("x", encoding="utf-8")
    fakes = _Fakes(
        _index(home),
        {str(home / "linked"): (0, NEW), str(home / "plain"): (0, NEW)},
        nlink={str(home / "linked"): 2},
    )

    done = _reclaim(home, fakes, protected=False)

    assert done == [home / "plain"]
    err = capsys.readouterr().err
    assert str(home / "linked") in err
    assert "fs.protected_hardlinks is off" in err


# --- the fd-checked chown when the sysctl is off (final review B-I1) ---------------------


def test_unprotected_chown_goes_through_the_opened_fd(home: Path) -> None:
    """With the sysctl off, nothing is chowned by name: the candidate is opened, the fd is
    re-checked, and that same fd is fchown'ed."""
    (home / "plain").write_text("x", encoding="utf-8")
    sub = home / "sub"
    sub.mkdir()
    fakes = _Fakes(_index(home), {str(home / "plain"): (0, NEW), str(sub): (0, NEW)})

    done = _reclaim(home, fakes, protected=False)

    assert done == sorted([home / "plain", sub])
    assert fakes.chown_calls == []
    assert sorted(c[0] for c in fakes.fchown_calls) == sorted([home / "plain", sub])
    assert all(c[1:] == (USER_UID, USER_GID) for c in fakes.fchown_calls)


def test_a_hardlink_planted_after_the_stat_is_caught_on_the_fd(
    home: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], loguru_stderr: None
) -> None:
    """B-I1: the user swaps a checked, singly-linked file for a hardlink to a root-owned
    file elsewhere in the window between the name stat and the chown. The re-check runs on
    the opened fd — the real inode, with its real link count — so the swap is seen and the
    outside file is never chowned."""
    outside = tmp_path / "etc"
    outside.mkdir()
    shadow = outside / "shadow"
    shadow.write_text("root-only", encoding="utf-8")
    target = home / "rc"
    target.write_text("x", encoding="utf-8")
    sprung: list[bool] = []

    def plant_link(path: Path) -> None:
        if path == target and not sprung:
            sprung.append(True)
            target.unlink()
            os.link(shadow, target)  # what fs.protected_hardlinks=0 lets the user do

    index = _index(home, outside)
    fakes = _Fakes(
        index, {str(target): (0, NEW), str(shadow): (0, NEW)}, on_stat=plant_link
    )
    before = os.stat(shadow)

    done = _reclaim(home, fakes, protected=False)

    assert sprung, "the swap never fired — the test proves nothing"
    assert done == []
    assert fakes.chown_calls == []
    assert fakes.fchown_calls == []
    after = os.stat(shadow)
    assert (after.st_uid, after.st_gid, after.st_nlink) == (before.st_uid, before.st_gid, 2)
    assert "2 hardlinks and fs.protected_hardlinks is off" in capsys.readouterr().err


def test_unprotected_leaves_symlinks_root_owned(
    home: Path, capsys: pytest.CaptureFixture[str], loguru_stderr: None
) -> None:
    """A symlink cannot be opened O_NOFOLLOW, so with the sysctl off it is not reclaimed."""
    (home / "link").symlink_to("/nonexistent")
    fakes = _Fakes(_index(home), {str(home / "link"): (0, NEW)})

    assert _reclaim(home, fakes, protected=False) == []
    assert fakes.chown_calls == [] and fakes.fchown_calls == []
    assert "leaving symlink" in capsys.readouterr().err


def test_unprotected_refuses_a_non_regular_inode_on_the_fd(home: Path) -> None:
    """A FIFO has no meaningful link check; the fd path hands back only files and dirs."""
    os.mkfifo(home / "fifo")
    fakes = _Fakes(_index(home), {str(home / "fifo"): (0, NEW)})
    assert _reclaim(home, fakes, protected=False) == []
    assert fakes.fchown_calls == []


def test_protected_mode_never_opens_anything(home: Path) -> None:
    """With the sysctl on, the existing name-relative fchownat path is kept."""
    (home / "a").write_text("x", encoding="utf-8")
    fakes = _Fakes(_index(home), {str(home / "a"): (0, NEW)})

    def no_open(name: str, dir_fd: int) -> int:
        raise AssertionError("open_at must not run when fs.protected_hardlinks is on")

    done = reclaim_home(
        home, uid=USER_UID, gid=USER_GID, since=SINCE,
        stat_at=fakes.stat_at, chown_at=fakes.chown_at, hardlinks_protected=lambda: True,
        open_at=no_open,
    )
    assert done == [home / "a"]
    assert fakes.chown_paths == [home / "a"]


def test_open_at_refuses_symlinks_and_never_blocks_on_a_fifo(tmp_path: Path) -> None:
    """Pins the real flags: O_NOFOLLOW (a symlink fails, ELOOP) and O_NONBLOCK (opening a
    FIFO with no writer returns at once instead of hanging the root pass)."""
    d = tmp_path / "d"
    d.mkdir()
    (d / "file").write_text("x", encoding="utf-8")
    (d / "link").symlink_to(d / "file")
    os.mkfifo(d / "fifo")
    dfd = os.open(d, os.O_RDONLY)
    try:
        with pytest.raises(OSError):
            bootstrap._open_at("link", dfd)
        fd = bootstrap._open_at("fifo", dfd)
        os.close(fd)
        fd = bootstrap._open_at("file", dfd)
        try:
            assert os.fstat(fd).st_ino == os.stat(d / "file").st_ino
        finally:
            os.close(fd)
    finally:
        os.close(dfd)
    assert bootstrap._OPEN_FLAGS & os.O_NOFOLLOW
    assert bootstrap._OPEN_FLAGS & os.O_NONBLOCK


def test_the_real_unprotected_pass_fchowns_the_file(home: Path) -> None:
    """End to end with the real open/fstat-fd/fchown (uid/ctime forced on the stats only):
    the file's group really changes."""
    f = home / "f"
    f.write_text("x", encoding="utf-8")
    others = [g for g in os.getgroups() if g != os.stat(f).st_gid]
    if not others:
        pytest.skip("no second group to chown to")
    fakes = _Fakes(_index(home), {str(f): (0, NEW)})
    done = reclaim_home(
        home, uid=os.getuid(), gid=others[0], since=SINCE,
        stat_at=fakes.stat_at, fstat_fd=fakes.fstat_fd, hardlinks_protected=lambda: False,
    )
    assert done == [f]
    assert os.stat(f).st_gid == others[0]


def test_hardlink_protection_reads_the_sysctl(tmp_path: Path) -> None:
    on, off, absent = tmp_path / "on", tmp_path / "off", tmp_path / "absent"
    on.write_text("1\n", encoding="utf-8")
    off.write_text("0\n", encoding="utf-8")
    assert bootstrap._hardlinks_protected(on) is True
    assert bootstrap._hardlinks_protected(off) is False
    assert bootstrap._hardlinks_protected(absent) is False  # non-Linux: stay careful


# --- errors ---------------------------------------------------------------------------


def test_error_on_one_path_continues(home: Path) -> None:
    (home / "a").write_text("x", encoding="utf-8")
    (home / "b").write_text("x", encoding="utf-8")
    fakes = _Fakes(
        _index(home),
        {str(home / "a"): (0, NEW), str(home / "b"): (0, NEW)},
        chown_raises={str(home / "a"): PermissionError("nope")},
    )

    done = _reclaim(home, fakes)

    assert done == [home / "b"]
    assert set(fakes.chown_paths) == {home / "a", home / "b"}


def test_vanished_path_is_skipped(home: Path) -> None:
    (home / "gone").write_text("x", encoding="utf-8")
    fakes = _Fakes(_index(home), {})

    def stat_at(name: str, dir_fd: int | None) -> os.stat_result:
        if fakes.resolve(name, dir_fd) == home / "gone":
            raise FileNotFoundError(name)
        return fakes.stat_at(name, dir_fd)

    done = reclaim_home(
        home, uid=USER_UID, gid=USER_GID, since=SINCE,
        stat_at=stat_at, chown_at=fakes.chown_at, hardlinks_protected=lambda: True,
    )
    assert done == []
    assert fakes.chown_calls == []


def test_an_unstattable_home_is_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], loguru_stderr: None
) -> None:
    missing = tmp_path / "nope"
    assert reclaim_home(missing, uid=USER_UID, gid=USER_GID, since=SINCE) == []
    assert "skipping the reclaim pass" in capsys.readouterr().err


def test_per_path_warnings_are_capped(
    home: Path, capsys: pytest.CaptureFixture[str], loguru_stderr: None
) -> None:
    """A concurrent `rm -rf` in a cache dir must not turn into unbounded log spam."""
    names = [f"f{i:02d}" for i in range(25)]
    for name in names:
        (home / name).write_text("x", encoding="utf-8")
    fakes = _Fakes(
        _index(home),
        {str(home / n): (0, NEW) for n in names},
        chown_raises={str(home / n): PermissionError("nope") for n in names},
    )

    assert _reclaim(home, fakes) == []
    err = capsys.readouterr().err
    assert err.count("could not reclaim") == bootstrap._WARN_LIMIT
    assert f"… and {25 - bootstrap._WARN_LIMIT} more" in err


# --- the real primitives --------------------------------------------------------------


def test_defaults_are_the_dir_fd_safe_primitives() -> None:
    """The security-critical defaults are the fd-relative variants, not the path ones."""
    params = inspect.signature(reclaim_home).parameters
    assert params["fwalk"].default is bootstrap._fwalk_nofollow
    assert params["stat_at"].default is bootstrap._stat_at
    assert params["chown_at"].default is bootstrap._chown_at
    assert params["hardlinks_protected"].default is bootstrap._hardlinks_protected
    assert params["open_at"].default is bootstrap._open_at
    assert params["fstat_fd"].default is os.fstat
    assert params["fchown_fd"].default is os.fchown


def test_the_real_stat_at_is_dir_fd_relative_and_nofollow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pins ``_stat_at``: the name resolves against the directory fd, not the cwd, and a
    symlink is stat'ed as a link. (Either mutation used to survive the suite.)"""
    d = tmp_path / "d"
    d.mkdir()
    (d / "x").symlink_to(tmp_path / "target")
    (tmp_path / "target").write_text("t", encoding="utf-8")
    decoy = tmp_path / "cwd"
    decoy.mkdir()
    (decoy / "x").mkdir()  # a same-named DIRECTORY in the cwd
    monkeypatch.chdir(decoy)
    dfd = os.open(d, os.O_RDONLY)
    try:
        assert stat.S_ISLNK(bootstrap._stat_at("x", dfd).st_mode)
    finally:
        os.close(dfd)


def test_the_walk_raising_on_home_itself_escapes_reclaim_home(home: Path) -> None:
    """Documented: an error on HOME itself (here: gone after the pre-check) is raised, not
    swallowed — bootstrap_user is the one that contains it."""

    def vanishing(top: Path) -> Iterator[FwalkEntry]:
        raise FileNotFoundError(str(top))
        yield  # pragma: no cover

    with pytest.raises(FileNotFoundError):
        reclaim_home(home, uid=USER_UID, gid=USER_GID, since=SINCE, fwalk=vanishing)
    assert bootstrap.PROTECTED_HARDLINKS == Path("/proc/sys/fs/protected_hardlinks")


def test_the_real_pass_over_a_tree_root_does_not_own_reclaims_nothing(home: Path) -> None:
    (home / "a").write_text("x", encoding="utf-8")
    assert reclaim_home(home, uid=os.getuid(), gid=os.getgid(), since=time.time()) == []


def test_the_real_chown_lands_on_the_link_not_its_target(home: Path, tmp_path: Path) -> None:
    """End-to-end with the *real* ``os.fwalk``/``os.chown``: a symlink out of HOME is
    chowned as a link, and the file it points at keeps its ownership and contents."""
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret"
    secret.write_text("root-only", encoding="utf-8")
    link = home / "escape"
    link.symlink_to(secret)
    target_before = os.stat(secret)
    fakes = _Fakes(_index(home, outside), {str(link): (0, NEW)})
    # A group we belong to that the target is NOT in, so "the chown followed the link"
    # would be visible. Unprivileged tests cannot move a file between users, only groups.
    others = [g for g in os.getgroups() if g != target_before.st_gid]
    new_gid = others[0] if others else os.getgid()

    done = reclaim_home(  # pretend root made the link; real walk, real chown
        home, uid=os.getuid(), gid=new_gid, since=SINCE,
        stat_at=fakes.stat_at, hardlinks_protected=lambda: True,
    )

    assert done == [link]
    after = os.stat(secret)
    assert (after.st_uid, after.st_gid) == (target_before.st_uid, target_before.st_gid)
    # chown bumps ctime even when the ids do not change, so an untouched ctime proves the
    # syscall never reached the target at all.
    assert after.st_ctime_ns == target_before.st_ctime_ns
    assert secret.read_text(encoding="utf-8") == "root-only"
    assert os.lstat(link).st_uid == os.getuid()
    if others:
        assert os.lstat(link).st_gid == new_gid  # …the link itself really was chowned


def test_the_real_pass_refuses_a_symlinked_home(tmp_path: Path) -> None:
    """Belt and braces on I1: even without the explicit check, ``os.fwalk`` yields nothing
    for a symlinked top — so the real primitives cannot walk through one."""
    real = tmp_path / "real"
    real.mkdir()
    (real / "file").write_text("x", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    assert list(bootstrap._fwalk_nofollow(link)) == []
    assert reclaim_home(link, uid=os.getuid(), gid=os.getgid(), since=SINCE) == []


# --- bootstrap_user wiring ------------------------------------------------------------


@pytest.fixture
def _stub_pwd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        pwd, "getpwnam",
        lambda name: SimpleNamespace(
            pw_uid=4242, pw_gid=4343, pw_name=name, pw_dir=f"/home/{name}"
        ),
    )


@pytest.fixture
def _stub_pipeline(monkeypatch: pytest.MonkeyPatch, _stub_pwd: None) -> None:
    """``_run_profiles`` raises, so the reclaim pass must still run from the ``finally``."""

    def boom(c: Ctx, tokens: list[str], root: Path) -> None:
        raise RuntimeError("profile blew up")

    monkeypatch.setattr(bootstrap, "_run_profiles", boom)


def _ctx(**over: object) -> Ctx:
    return Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor(), **over)  # type: ignore[arg-type]


def test_bootstrap_user_calls_reclaim_as_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, _stub_pipeline: None
) -> None:
    calls: list[dict[str, object]] = []

    def recorder(h: Path, *, uid: int, gid: int, since: float) -> list[Path]:
        calls.append({"home": h, "uid": uid, "gid": gid, "since": since,
                      "HOME": os.environ.get("HOME")})
        return [h / "one", h / "two"]

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(bootstrap, "reclaim_home", recorder)
    before = time.time()

    with pytest.raises(RuntimeError, match="profile blew up"):
        bootstrap.bootstrap_user(_ctx(), _user(), root=tmp_path)

    assert len(calls) == 1
    call = calls[0]
    assert call["home"] == Path("/home/dev")
    assert (call["uid"], call["gid"]) == (4242, 4343)
    # Floored to the second, so it may sit up to 1 s before the call (never after).
    assert isinstance(call["since"], int | float) and before - 1 <= call["since"] <= before + 1
    assert call["HOME"] == "/home/dev"  # runs before HOME is restored
    assert os.environ["HOME"] == str(tmp_path)  # …and HOME is restored afterwards


def test_bootstrap_user_floors_since_to_the_second(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, _stub_pwd: None
) -> None:
    """A filesystem with 1 s timestamps truncates, so `since` is floored: a file written
    in this very second must not sort below it."""
    seen: list[float] = []
    monkeypatch.setattr(bootstrap, "_run_profiles", lambda c, tokens, root: None)
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(bootstrap.time, "time", lambda: 1_700_000_123.9)

    def reclaim(h: Path, *, uid: int, gid: int, since: float) -> list[Path]:
        seen.append(since)
        return []

    monkeypatch.setattr(bootstrap, "reclaim_home", reclaim)
    bootstrap.bootstrap_user(_ctx(), _user(), root=tmp_path)
    assert seen == [1_700_000_123]
    assert seen[0] == math.floor(seen[0])


def test_bootstrap_user_reclaims_after_a_successful_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, _stub_pwd: None
) -> None:
    """The normal path: the profiles succeed, the reclaim still runs, nothing is raised."""
    order: list[str] = []
    monkeypatch.setattr(
        bootstrap, "_run_profiles",
        lambda c, tokens, root: order.append("run"),
    )
    def reclaim(h: Path, **kw: object) -> list[Path]:
        order.append("reclaim")
        return []

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(bootstrap, "reclaim_home", reclaim)

    bootstrap.bootstrap_user(_ctx(), _user(), root=tmp_path)

    assert order == ["run", "reclaim"]
    assert os.environ["HOME"] == str(tmp_path)


def test_bootstrap_user_logs_the_reclaim_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    loguru_stderr: None, _stub_pipeline: None,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(bootstrap, "reclaim_home", lambda h, **kw: [h / "one", h / "two"])
    with pytest.raises(RuntimeError):
        bootstrap.bootstrap_user(_ctx(), _user(), root=tmp_path)
    assert "accounts: reclaimed 2 root-owned path(s) in /home/dev" in capsys.readouterr().err


def test_bootstrap_user_is_silent_when_nothing_was_reclaimed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    loguru_stderr: None, _stub_pipeline: None,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(bootstrap, "reclaim_home", lambda h, **kw: [])
    with pytest.raises(RuntimeError):
        bootstrap.bootstrap_user(_ctx(), _user(), root=tmp_path)
    assert "reclaimed" not in capsys.readouterr().err


def test_bootstrap_user_warns_when_the_passwd_home_diverges(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    loguru_stderr: None,
) -> None:
    """home_of() hard-codes /home/<name>; that is the tree the modules wrote into, so it
    is the tree that gets reclaimed — but a divergence from passwd is worth saying."""
    monkeypatch.setattr(bootstrap, "_run_profiles", lambda c, tokens, root: None)
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        pwd, "getpwnam",
        lambda name: SimpleNamespace(pw_uid=1, pw_gid=1, pw_name=name, pw_dir="/srv/dev"),
    )
    seen: list[Path] = []

    def reclaim(h: Path, **kw: object) -> list[Path]:
        seen.append(h)
        return []

    monkeypatch.setattr(bootstrap, "reclaim_home", reclaim)

    bootstrap.bootstrap_user(_ctx(), _user(), root=tmp_path)

    assert seen == [Path("/home/dev")]  # the tree the run actually wrote to
    assert "passwd home is /srv/dev" in capsys.readouterr().err


def test_bootstrap_user_never_raises_out_of_the_reclaim_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, _stub_pipeline: None
) -> None:
    """A failure in the reclaim pass must not mask the run's own error."""

    def blow_up(h: Path, **kw: object) -> list[Path]:
        raise OSError("walk failed")

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(bootstrap, "reclaim_home", blow_up)
    with pytest.raises(RuntimeError, match="profile blew up"):
        bootstrap.bootstrap_user(_ctx(), _user(), root=tmp_path)
    assert os.environ["HOME"] == str(tmp_path)


def test_bootstrap_user_never_raises_out_of_the_reclaim_pass_on_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, _stub_pwd: None
) -> None:
    """…nor escape a successful run."""

    def blow_up(h: Path, **kw: object) -> list[Path]:
        raise OSError("walk failed")

    monkeypatch.setattr(bootstrap, "_run_profiles", lambda c, tokens, root: None)
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(bootstrap, "reclaim_home", blow_up)
    bootstrap.bootstrap_user(_ctx(), _user(), root=tmp_path)
    assert os.environ["HOME"] == str(tmp_path)


@pytest.mark.parametrize(
    ("euid", "dry_run"),
    [(1000, False), (0, True), (1000, True)],
    ids=["not-root", "dry-run", "neither"],
)
def test_bootstrap_user_skips_reclaim_when_not_root_or_dry_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, _stub_pipeline: None,
    euid: int, dry_run: bool,
) -> None:
    calls: list[Path] = []

    def recorder(h: Path, **kw: object) -> list[Path]:
        calls.append(h)
        return []

    monkeypatch.setattr(os, "geteuid", lambda: euid)
    monkeypatch.setattr(bootstrap, "reclaim_home", recorder)
    with pytest.raises(RuntimeError):
        bootstrap.bootstrap_user(_ctx(dry_run=dry_run), _user(), root=tmp_path)
    assert calls == []
