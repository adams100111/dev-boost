"""`bootstrap_user` hands back root-owned files it created in the managed user's HOME.

Carry-over audit question — *does the root path actually write user config in-process?*
Yes, in many places: ``jsonc_merge_deep`` and ``_atomic_write`` (editor settings),
``_zed.seed_files``, the ``fs.write`` helpers and the ``shell.py`` rc writers all run
in-process under the root interpreter while ``$HOME`` points at the managed user's home,
so every file they create lands root-owned. ``DemotingExecutor`` only demotes *shelled-out*
commands, never these. Rather than chase 25+ writers, ``reclaim_home`` runs one post-pass
over the target HOME and hands back everything root created during the run — which fixes
all of them at once.

This never runs on macOS: ``accounts`` is in ``cli/host.LINUX_ONLY`` and the root guard in
``cli/host.invocation_error`` refuses euid 0 on a Mac outright.
"""

from __future__ import annotations

import inspect
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
from devboost.accounts.bootstrap import reclaim_home
from devboost.accounts.config import ManagedUser
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx

SINCE = 1_000_000.0
NEW = SINCE + 10.0
OLD = SINCE - 10.0
USER_UID, USER_GID = 1000, 1000


def _user(**over: object) -> ManagedUser:
    base = dict(
        name="dev", enabled=True, shell="/bin/bash", lock_shell=False, linger=False,
        privilege="none", sudo_commands=(), ram=None, cpu=None, tasks=None, disk=None,
        ssh_authorized_keys=(), bootstrap_profiles=("terminal",),
    )
    base.update(over)
    return ManagedUser(**base)  # type: ignore[arg-type]


def _fake_lstat(
    table: Mapping[str, tuple[int, float]], *, nlink: Mapping[str, int] | None = None
) -> Callable[[Path], os.stat_result]:
    """An ``lstat`` that keeps the real mode but forces uid/mtime/ctime from *table*.

    A path missing from *table* is reported as an untouched user-owned file (uid 1000,
    mtime long before ``SINCE``).
    """
    links = nlink or {}

    def lstat(path: Path) -> os.stat_result:
        real = os.lstat(path)  # real mode bits, so dir/file/symlink stay honest
        uid, mtime = table.get(str(path), (USER_UID, OLD))
        fields = list(real)[:10]
        fields[3] = links.get(str(path), 2 if stat.S_ISDIR(real.st_mode) else 1)
        fields[4] = uid
        fields[8] = mtime
        fields[9] = mtime
        return os.stat_result(fields)

    return lstat


class _Recorder:
    """An ``lchown`` that records its calls, optionally raising on chosen paths."""

    def __init__(self, raises: Mapping[str, Exception] | None = None) -> None:
        self.calls: list[tuple[Path, int, int]] = []
        self._raises = dict(raises or {})

    def __call__(self, path: Path, uid: int, gid: int) -> None:
        self.calls.append((path, uid, gid))
        exc = self._raises.get(str(path))
        if exc is not None:
            raise exc

    @property
    def paths(self) -> list[Path]:
        return [c[0] for c in self.calls]


def _write_stderr(msg: str) -> None:
    sys.stderr.write(msg)


@pytest.fixture
def loguru_stderr() -> Iterator[None]:
    """loguru binds the ``sys.stderr`` *object* at import time, so pytest's capture never
    sees it. Swap in a sink that dereferences ``sys.stderr`` at write time (the same trick
    as ``tests/cli/conftest.py``) so ``capsys`` can read the log line."""
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


# --- reclaim_home ---------------------------------------------------------------------


def test_reclaims_new_root_owned_files(home: Path) -> None:
    (home / "a").write_text("a", encoding="utf-8")
    (home / "b").write_text("b", encoding="utf-8")
    nested = home / "nested"
    nested.mkdir()
    (nested / "c").write_text("c", encoding="utf-8")
    table = {str(home / "a"): (0, NEW), str(nested / "c"): (0, NEW)}
    rec = _Recorder()

    done = reclaim_home(
        home, uid=USER_UID, gid=USER_GID, since=SINCE, lstat=_fake_lstat(table), lchown=rec
    )

    assert done == sorted([home / "a", nested / "c"])
    assert set(rec.paths) == {home / "a", nested / "c"}
    assert all(c[1:] == (USER_UID, USER_GID) for c in rec.calls)


def test_reclaims_the_home_directory_itself(home: Path) -> None:
    rec = _Recorder()
    done = reclaim_home(
        home, uid=USER_UID, gid=USER_GID, since=SINCE,
        lstat=_fake_lstat({str(home): (0, NEW)}), lchown=rec,
    )
    assert done == [home]
    assert rec.paths == [home]


def test_leaves_old_root_files(home: Path) -> None:
    """A root-owned file the admin placed on purpose, before the run, is left alone."""
    (home / "admin-placed").write_text("x", encoding="utf-8")
    rec = _Recorder()
    done = reclaim_home(
        home, uid=USER_UID, gid=USER_GID, since=SINCE,
        lstat=_fake_lstat({str(home / "admin-placed"): (0, OLD)}), lchown=rec,
    )
    assert done == []
    assert rec.calls == []


def test_reclaims_on_ctime_alone(home: Path) -> None:
    """A file root only re-chmod'ed during the run bumps ctime, not mtime."""
    target = home / "rc"
    target.write_text("x", encoding="utf-8")

    def lstat(path: Path) -> os.stat_result:
        real = os.lstat(path)
        fields = list(real)[:10]
        if path == target:
            fields[4] = 0
            fields[8] = OLD  # mtime old …
            fields[9] = NEW  # … ctime new
        else:
            fields[4] = USER_UID
            fields[8] = fields[9] = OLD
        return os.stat_result(fields)

    rec = _Recorder()
    done = reclaim_home(home, uid=USER_UID, gid=USER_GID, since=SINCE, lstat=lstat, lchown=rec)
    assert done == [target]


def test_leaves_user_owned_files(home: Path) -> None:
    (home / "mine").write_text("x", encoding="utf-8")
    rec = _Recorder()
    done = reclaim_home(
        home, uid=USER_UID, gid=USER_GID, since=SINCE,
        lstat=_fake_lstat({str(home / "mine"): (USER_UID, NEW)}), lchown=rec,
    )
    assert done == []
    assert rec.calls == []


def test_never_follows_symlinks(home: Path, tmp_path: Path) -> None:
    """A hostile symlink inside HOME pointing outside it: the link is chowned with
    ``lchown`` (so the link itself, never its target), and the outside tree is neither
    walked nor stat'ed."""
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret"
    secret.write_text("root-only", encoding="utf-8")
    (home / "escape").symlink_to(secret)
    (home / "escape-dir").symlink_to(outside, target_is_directory=True)

    seen: list[Path] = []
    inner = _fake_lstat({str(home / "escape"): (0, NEW), str(home / "escape-dir"): (0, NEW)})

    def lstat(path: Path) -> os.stat_result:
        seen.append(path)
        return inner(path)

    rec = _Recorder()
    done = reclaim_home(home, uid=USER_UID, gid=USER_GID, since=SINCE, lstat=lstat, lchown=rec)

    assert set(done) == {home / "escape", home / "escape-dir"}
    assert secret not in rec.paths and outside not in rec.paths
    assert not [p for p in seen if outside in p.parents or p == outside]
    assert secret.read_text(encoding="utf-8") == "root-only"


def test_skips_hardlinked_regular_files(home: Path) -> None:
    """Defence in depth: a regular file with more than one link may be a hardlink the
    user planted to a root-owned inode elsewhere; chowning it would hand that inode over.
    (Linux's ``fs.protected_hardlinks`` already blocks planting one, hence *in depth*.)"""
    (home / "linked").write_text("x", encoding="utf-8")
    (home / "plain").write_text("x", encoding="utf-8")
    rec = _Recorder()
    done = reclaim_home(
        home, uid=USER_UID, gid=USER_GID, since=SINCE,
        lstat=_fake_lstat(
            {str(home / "linked"): (0, NEW), str(home / "plain"): (0, NEW)},
            nlink={str(home / "linked"): 2},
        ),
        lchown=rec,
    )
    assert done == [home / "plain"]


def test_error_on_one_path_continues(home: Path) -> None:
    (home / "a").write_text("x", encoding="utf-8")
    (home / "b").write_text("x", encoding="utf-8")
    table = {str(home / "a"): (0, NEW), str(home / "b"): (0, NEW)}
    rec = _Recorder(raises={str(home / "a"): PermissionError("nope")})

    done = reclaim_home(
        home, uid=USER_UID, gid=USER_GID, since=SINCE, lstat=_fake_lstat(table), lchown=rec
    )

    assert done == [home / "b"]
    assert set(rec.paths) == {home / "a", home / "b"}


def test_vanished_path_is_skipped(home: Path) -> None:
    (home / "gone").write_text("x", encoding="utf-8")

    def lstat(path: Path) -> os.stat_result:
        if path == home / "gone":
            raise FileNotFoundError(path)
        return _fake_lstat({})(path)

    rec = _Recorder()
    done = reclaim_home(home, uid=USER_UID, gid=USER_GID, since=SINCE, lstat=lstat, lchown=rec)
    assert done == []
    assert rec.calls == []


def test_defaults_use_os_lchown_and_os_lstat(home: Path) -> None:
    """The security-critical defaults are the l-variants, and a real run over a tree root
    does not own reclaims nothing (the files are the test user's, not root's)."""
    params = inspect.signature(reclaim_home).parameters
    assert params["lstat"].default is os.lstat
    assert params["lchown"].default is os.lchown
    (home / "a").write_text("x", encoding="utf-8")
    assert reclaim_home(home, uid=os.getuid(), gid=os.getgid(), since=time.time()) == []


def test_the_real_chown_lands_on_the_link_not_its_target(home: Path, tmp_path: Path) -> None:
    """End-to-end with the *real* ``os.lchown``: a symlink out of HOME is chowned as a
    link, and the file it points at keeps its own ownership and contents."""
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret"
    secret.write_text("root-only", encoding="utf-8")
    link = home / "escape"
    link.symlink_to(secret)
    target_before = os.stat(secret)

    done = reclaim_home(
        home, uid=os.getuid(), gid=os.getgid(), since=SINCE,
        lstat=_fake_lstat({str(link): (0, NEW)}),  # pretend root made the link
    )

    assert done == [link]
    after = os.stat(secret)
    assert (after.st_uid, after.st_gid) == (target_before.st_uid, target_before.st_gid)
    assert secret.read_text(encoding="utf-8") == "root-only"
    assert os.lstat(link).st_uid == os.getuid()


# --- bootstrap_user wiring ------------------------------------------------------------


@pytest.fixture
def _stub_pipeline(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """``_run_profiles`` raises, so the reclaim pass must still run from the ``finally``."""
    order: list[str] = []

    def boom(c: Ctx, tokens: list[str], root: Path) -> None:
        order.append("run")
        raise RuntimeError("profile blew up")

    monkeypatch.setattr(bootstrap, "_run_profiles", boom)
    monkeypatch.setattr(
        pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=4242, pw_gid=4343, pw_name=name)
    )
    yield order


def test_bootstrap_user_calls_reclaim_as_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, _stub_pipeline: list[str]
) -> None:
    calls: list[dict[str, object]] = []

    def recorder(h: Path, *, uid: int, gid: int, since: float) -> list[Path]:
        calls.append({"home": h, "uid": uid, "gid": gid, "since": since,
                      "HOME": os.environ.get("HOME")})
        return [h / "one", h / "two"]

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(bootstrap, "reclaim_home", recorder)
    before = time.time()
    ctx = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor())

    with pytest.raises(RuntimeError, match="profile blew up"):
        bootstrap.bootstrap_user(ctx, _user(), root=tmp_path)

    assert len(calls) == 1
    call = calls[0]
    assert call["home"] == Path("/home/dev")
    assert (call["uid"], call["gid"]) == (4242, 4343)
    assert isinstance(call["since"], float) and call["since"] >= before
    assert call["HOME"] == "/home/dev"  # runs before HOME is restored
    assert os.environ["HOME"] == str(tmp_path)  # …and HOME is restored afterwards


def test_bootstrap_user_logs_the_reclaim_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    loguru_stderr: None,
    _stub_pipeline: list[str],
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        bootstrap, "reclaim_home",
        lambda h, **kw: [h / "one", h / "two"],
    )
    ctx = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor())
    with pytest.raises(RuntimeError):
        bootstrap.bootstrap_user(ctx, _user(), root=tmp_path)
    assert "accounts: reclaimed 2 root-owned path(s) in /home/dev" in capsys.readouterr().err


def test_bootstrap_user_is_silent_when_nothing_was_reclaimed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
    loguru_stderr: None,
    _stub_pipeline: list[str],
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(bootstrap, "reclaim_home", lambda h, **kw: [])
    ctx = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor())
    with pytest.raises(RuntimeError):
        bootstrap.bootstrap_user(ctx, _user(), root=tmp_path)
    assert "reclaimed" not in capsys.readouterr().err


def test_bootstrap_user_never_raises_out_of_the_reclaim_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, _stub_pipeline: list[str]
) -> None:
    """A failure in the reclaim pass must not mask the run's own error, nor escape a
    successful run."""
    def blow_up(h: Path, **kw: object) -> list[Path]:
        raise OSError("walk failed")

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(bootstrap, "reclaim_home", blow_up)
    ctx = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor())
    with pytest.raises(RuntimeError, match="profile blew up"):
        bootstrap.bootstrap_user(ctx, _user(), root=tmp_path)
    assert os.environ["HOME"] == str(tmp_path)


@pytest.mark.parametrize(
    ("euid", "dry_run"),
    [(1000, False), (0, True), (1000, True)],
    ids=["not-root", "dry-run", "neither"],
)
def test_bootstrap_user_skips_reclaim_when_not_root_or_dry_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, _stub_pipeline: list[str],
    euid: int, dry_run: bool,
) -> None:
    calls: list[Path] = []

    def recorder(h: Path, **kw: object) -> list[Path]:
        calls.append(h)
        return []

    monkeypatch.setattr(os, "geteuid", lambda: euid)
    monkeypatch.setattr(bootstrap, "reclaim_home", recorder)
    ctx = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor(), dry_run=dry_run)
    with pytest.raises(RuntimeError):
        bootstrap.bootstrap_user(ctx, _user(), root=tmp_path)
    assert calls == []
