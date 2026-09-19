"""End to end with real gpg + pass + git: genesis → enroll → approve → sync → decrypt → revoke.

Each simulated device has its own HOME (git identity) and GNUPGHOME. GNUPGHOMEs are short
/tmp paths (the gpg-agent socket path is length-limited) and their agents are killed on
teardown. Keys are passphrase-less via loopback — tests only. The "remote" is a local bare
repo: no network, no real $HOME, no host keyring.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from devboost.core.errors import NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import RealExecutor, Result
from devboost.model import Ctx
from devboost.modules._pass import pass_show
from devboost.passstore import approve, audit, enroll, git, gpg, sync
from devboost.passstore.layout import Store

pytestmark = [
    pytest.mark.skipif(
        not all(shutil.which(t) for t in ("gpg", "gpgconf", "pass", "git")),
        reason="needs gpg, pass and git",
    ),
    # Real gpg-agent/pinentry can wedge (stale socket, loopback pinentry misconfigured, an
    # agent waiting on a tty that doesn't exist in a subagent sandbox) with no built-in
    # timeout anywhere in RealExecutor. Bound it so a wedged agent fails the test instead
    # of hanging the whole run; excluded from the fast lane (`pytest -m "not slow"`).
    pytest.mark.slow,
    pytest.mark.timeout(60),
]
FEDORA = OsInfo("fedora", "fedora", "x86_64")


class _DeviceEx(RealExecutor):
    """One simulated device: its own HOME + GNUPGHOME; never hands over the tty."""

    def __init__(self, home: Path, gnupg: Path) -> None:
        self.home = home
        self.gnupg = gnupg

    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        interactive: bool = False,
        timeout: float | None = None,
    ) -> Result:
        merged = {
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GNUPGHOME": str(self.gnupg),
            **(env or {}),
        }
        return super().run(
            argv, sudo=sudo, stdin=stdin, env=merged, cwd=cwd, interactive=False, timeout=timeout
        )


@dataclass
class Device:
    name: str
    ctx: Ctx
    store: Store

    def pass_(self, *args: str, stdin: str | None = None) -> Result:
        return self.ctx.ex.run(["pass", *args], stdin=stdin, env=enroll.pass_env(self.store))


MakeDevice = Callable[[str], Device]


@pytest.fixture
def make_device(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[MakeDevice]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    for var in [v for v in os.environ if v.startswith(("PASSWORD_STORE_", "GIT_"))]:
        monkeypatch.delenv(var)  # host pass/git settings must not leak into the devices
    monkeypatch.delenv("DEVBOOST_NTFY_URL", raising=False)
    gnupg_dirs: list[Path] = []

    def make(name: str) -> Device:
        home = tmp_path / f"home-{name}"
        home.mkdir()
        (home / ".gitconfig").write_text(
            f"[user]\n\tname = {name}\n\temail = {name}@example.com\n"
            "[init]\n\tdefaultBranch = main\n",
            encoding="utf-8",
        )
        gnupg = Path(tempfile.mkdtemp(prefix="dbg", dir="/tmp"))
        gnupg.chmod(0o700)
        gnupg_dirs.append(gnupg)
        return Device(name, Ctx(os=FEDORA, ex=_DeviceEx(home, gnupg)),
                      Store(tmp_path / f"store-{name}"))

    yield make
    for g in gnupg_dirs:
        subprocess.run(["gpgconf", "--homedir", str(g), "--kill", "all"], check=False,
                       capture_output=True)
        # `gpgconf --kill` requests the agent's shutdown but does not wait for it to
        # actually exit and release its file locks (private-keys-v1.d/.lock, sockets).
        # An rmtree attempted immediately can race that shutdown and silently leave the
        # homedir behind (ignore_errors swallows the failure) — retry briefly instead of
        # leaving real, if low-value, key material sitting under /tmp indefinitely.
        for _ in range(10):
            shutil.rmtree(g, ignore_errors=True)
            if not g.exists():
                break
            time.sleep(0.1)


@pytest.fixture
def origin(tmp_path: Path) -> str:
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--quiet", "--bare", "-b", "main", str(bare)], check=True)
    return str(bare)


def _genesis(origin: str, make_device: MakeDevice) -> Device:
    a = make_device("alpha")
    enroll.ensure_clone(a.ctx, a.store, origin)
    acc = enroll.ensure_access(a.ctx, a.store, "alpha", interactive=True, passphrase="")
    assert acc.state == "enrolled" and acc.record is not None
    for entry, secret in (("web/github", "gh-secret"), ("harness/tg", "t\ntoken: T\nchat_id: C")):
        assert a.pass_("insert", "-m", entry, stdin=secret + "\n").ok
    assert git.push(a.ctx, a.store.root).ok
    return a


def _request(dev: Device, origin: str, scope: list[str] | None = None) -> None:
    enroll.ensure_clone(dev.ctx, dev.store, origin)
    with pytest.raises(NeedsUser) as err:
        enroll.ensure_access(dev.ctx, dev.store, dev.name, interactive=True, scope=scope,
                             passphrase="")
    assert err.value.how_to_fix == f"devboost pass approve {dev.name}"


def test_enroll_approve_decrypt_revoke_rotate(origin: str, make_device: MakeDevice) -> None:
    a = _genesis(origin, make_device)
    b = make_device("bravo")
    _request(b, origin)
    assert enroll.local_access(b.ctx, b.store, "bravo").state == "pending"
    assert not b.pass_("show", "web/github").ok  # no access before approval

    done = approve.approve(a.ctx, a.store, "alpha", "bravo", lambda r: True)
    assert done == [approve.Approved("bravo", None)]
    assert len(a.store.gpg_ids()) == 2  # N+1

    assert git.pull(b.ctx, b.store.root).ok
    assert enroll.local_access(b.ctx, b.store, "bravo").state == "enrolled"
    assert b.pass_("show", "web/github").stdout.strip() == "gh-secret"

    entry = approve.revoke(a.ctx, a.store, "alpha", "bravo", lambda r: True)
    assert entry is not None and {"web/github", "harness/tg"} <= set(entry.entries)
    assert a.store.record("revoked", "bravo") is not None
    assert len(a.store.gpg_ids()) == 1
    assert sync.run(a.ctx, a.store, "alpha").status == "ok"  # drops bravo's public key (I1)
    assert entry.fingerprint not in gpg.public_fingerprints(a.ctx)

    assert a.pass_("insert", "-m", "web/new", stdin="fresh\n").ok
    assert git.push(a.ctx, a.store.root).ok
    assert git.pull(b.ctx, b.store.root).ok
    assert b.store.record("revoked", "bravo") is not None
    assert not b.pass_("show", "web/new").ok  # revoked key cannot read new entries

    assert "web/github" in {u.entry for u in approve.unrotated(a.ctx, a.store)}
    assert a.pass_("insert", "-f", "-m", "web/github", stdin="rotated\n").ok
    assert "web/github" not in {u.entry for u in approve.unrotated(a.ctx, a.store)}


def test_scoped_server_reads_only_its_folder(origin: str, make_device: MakeDevice) -> None:
    a = _genesis(origin, make_device)
    srv = make_device("srv")
    _request(srv, origin, scope=["harness"])

    done = approve.approve(a.ctx, a.store, "alpha", "srv", lambda r: True)
    assert done == [approve.Approved("srv", ["harness"])]
    assert len(a.store.gpg_ids()) == 1 and len(a.store.gpg_ids("harness")) == 2

    assert git.pull(srv.ctx, srv.store.root).ok
    assert enroll.local_access(srv.ctx, srv.store, "srv").state == "enrolled"
    assert "chat_id: C" in srv.pass_("show", "harness/tg").stdout
    assert not srv.pass_("show", "web/github").ok


def test_new_device_syncs_keys_writes_and_the_other_device_reads(
    origin: str, make_device: MakeDevice
) -> None:
    """I8: B's sync imports + trusts A's key (D7), so B can write entries A can read."""
    a = _genesis(origin, make_device)
    b = make_device("bravo")
    _request(b, origin)
    approve.approve(a.ctx, a.store, "alpha", "bravo", lambda r: True)
    alpha = a.store.record("devices", "alpha")
    assert alpha is not None
    assert alpha.fingerprint not in gpg.public_fingerprints(b.ctx)

    assert sync.run(b.ctx, b.store, "bravo").status == "ok"
    assert alpha.fingerprint in gpg.public_fingerprints(b.ctx)  # imported by the sync
    assert enroll.local_access(b.ctx, b.store, "bravo").state == "enrolled"

    assert b.pass_("insert", "-m", "web/from-bravo", stdin="written on bravo\n").ok
    assert sync.run(b.ctx, b.store, "bravo", push_only=True).status == "ok"

    assert sync.run(a.ctx, a.store, "alpha").status == "ok"
    assert a.pass_("show", "web/from-bravo").stdout.strip() == "written on bravo"


def test_offline_insert_after_revoke_is_flagged_and_fixed(
    origin: str, make_device: MakeDevice
) -> None:
    """Carry-over I5: bravo, offline, still encrypts to its stale .gpg-id after the revoke."""
    a = _genesis(origin, make_device)
    b = make_device("bravo")
    _request(b, origin)
    approve.approve(a.ctx, a.store, "alpha", "bravo", lambda r: True)
    assert sync.run(b.ctx, b.store, "bravo").status == "ok"  # imports alpha's key
    assert audit.audit(a.ctx, a.store).mismatches == []

    assert approve.revoke(a.ctx, a.store, "alpha", "bravo", lambda r: True) is not None
    # bravo has not pulled the revoke: its .gpg-id still lists both keys
    assert b.pass_("insert", "-m", "web/offline", stdin="late\n").ok
    assert sync.run(b.ctx, b.store, "bravo").status == "ok"  # rebased onto the revoke, pushed
    assert sync.run(a.ctx, a.store, "alpha").status == "ok"  # also deletes bravo's pubkey

    report = audit.audit(a.ctx, a.store)
    assert len(report.mismatches) == 1
    mismatch = report.mismatches[0]
    assert mismatch.entry == "web/offline"
    assert mismatch.extra == ("bravo (revoked)",)
    assert mismatch.missing == ()
    assert mismatch.revoked is True
    # R11: `pass init` with the same ids re-encrypts exactly the differing entry
    assert a.pass_("init", *a.store.gpg_ids()).ok
    assert audit.audit(a.ctx, a.store).mismatches == []


def test_unattended_read_uses_the_cache_and_never_prompts(
    origin: str, make_device: MakeDevice, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R12 with real gpg: a passphrase-protected key, read unattended."""
    a = make_device("alpha")
    enroll.ensure_clone(a.ctx, a.store, origin)
    enroll.ensure_access(a.ctx, a.store, "alpha", interactive=True, passphrase="pw")
    assert a.pass_("insert", "-m", "web/k", stdin="guarded\n").ok
    dev_ex = a.ctx.ex
    assert isinstance(dev_ex, _DeviceEx)
    gnupg = str(dev_ex.gnupg)
    subprocess.run(["gpgconf", "--homedir", gnupg, "--reload", "gpg-agent"], check=True)
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")
    monkeypatch.setenv("PASSWORD_STORE_DIR", str(a.store.root))
    assert pass_show(a.ctx, "web/k", who="t") is None  # uncached: fails fast, skipped

    entry = str(a.store.root / "web" / "k.gpg")
    unlock = a.ctx.ex.run(["gpg", "--batch", "--pinentry-mode", "loopback",
                           "--passphrase", "pw", "--decrypt", entry])
    assert unlock.ok  # caches the passphrase in the agent
    assert pass_show(a.ctx, "web/k", who="t") == "guarded\n"
