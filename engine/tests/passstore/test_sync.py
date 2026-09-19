from __future__ import annotations

import fcntl
import os
import plistlib
from pathlib import Path

import pytest

from devboost.core.errors import InstallError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.passstore import audit, sync
from devboost.passstore.layout import DeviceRecord, Store
from tests.passstore.fakes import RuleExecutor, colons

FEDORA = OsInfo("fedora", "fedora", "x86_64")
MAC = OsInfo("macos", "macos", "aarch64")
FP_ME = "A" * 40
FP_NEW = "B" * 40


@pytest.fixture(autouse=True)
def _dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.delenv("DEVBOOST_PASS_HOOK", raising=False)


def _store(tmp_path: Path) -> Store:
    root = tmp_path / "store"
    (root / ".git" / "hooks").mkdir(parents=True)
    (root / ".gpg-id").write_text(FP_ME + "\n", encoding="utf-8")
    return Store(root)


def _ex(*extra: tuple[tuple[str, ...], Result]) -> RuleExecutor:
    return RuleExecutor(present={"notify-send"}, rules=[
        *extra,
        (("--list-secret-keys",), Result(0, colons("sec", FP_ME))),
    ])


def _ctx(ex: RuleExecutor, os_: OsInfo = FEDORA) -> Ctx:
    return Ctx(os=os_, ex=ex)


def _notifications(ex: RuleExecutor) -> list[list[str]]:
    return [c for c in ex.calls if c[0] == "notify-send"]


def test_hook_is_a_logic_free_stub_and_idempotent(tmp_path: Path) -> None:
    s = _store(tmp_path)
    assert sync.install_hook(_ctx(_ex()), s, "/bin/devboost") is True
    hook = s.root / ".git" / "hooks" / "post-commit"
    text = hook.read_text(encoding="utf-8")
    assert text.startswith("#!/bin/sh\n") and sync.HOOK_MARK in text
    assert len(text.splitlines()) == 3
    assert "\n/bin/devboost pass sync --push-only --quiet" in text
    assert text.rstrip().endswith("&")
    assert hook.stat().st_mode & 0o111
    assert sync.install_hook(_ctx(_ex()), s, "/bin/devboost") is False
    assert sync.hook_installed(s)


def test_install_hook_pins_core_hooks_path(tmp_path: Path) -> None:
    """A global core.hooksPath would silently disable the store's hook (minor d)."""
    s = _store(tmp_path)
    ex = _ex()
    sync.install_hook(_ctx(ex), s, "/bin/devboost")
    assert ["git", "-C", str(s.root), "config", "--local", "core.hooksPath",
            ".git/hooks"] in ex.calls


def test_hook_and_unit_quote_paths_with_spaces() -> None:
    assert "\n'/opt/my apps/devboost' pass sync" in sync.hook_script("/opt/my apps/devboost")
    unit = sync.service_unit('/opt/my apps/a"b$c%d')
    assert 'ExecStart="/opt/my apps/a\\"b$$c%%d" pass sync --quiet' in unit


def test_foreign_hook_is_backed_up(tmp_path: Path) -> None:
    s = _store(tmp_path)
    hook = s.root / ".git" / "hooks" / "post-commit"
    hook.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
    sync.install_hook(_ctx(_ex()), s, "/bin/devboost")
    assert (hook.parent / "post-commit.devboost-backup").read_text(encoding="utf-8").endswith(
        "echo mine\n")


def test_units_content() -> None:
    assert 'ExecStart="/bin/devboost" pass sync --quiet' in sync.service_unit("/bin/devboost")
    t = sync.timer_unit()
    assert "OnCalendar=*:0/15" in t and "Persistent=true" in t and "WantedBy=timers.target" in t


def test_install_scheduler_linux_enables_timer_and_checks_state(tmp_path: Path) -> None:
    ex = _ex()
    sync.install_scheduler(_ctx(ex), "/bin/devboost")
    units = tmp_path / "home" / ".config" / "systemd" / "user"
    assert (units / sync.SERVICE).exists() and (units / sync.TIMER).exists()
    assert ["systemctl", "--user", "daemon-reload"] in ex.calls
    assert ["systemctl", "--user", "enable", "--now", sync.TIMER] in ex.calls
    assert sync.scheduler_installed(_ctx(ex), "/bin/devboost")
    assert not sync.scheduler_installed(_ctx(ex), "/other/devboost")  # stale ExecStart
    disabled = _ex((("is-enabled",), Result(1)))
    assert not sync.scheduler_installed(_ctx(disabled), "/bin/devboost")
    stopped = _ex((("is-active",), Result(3)))
    assert not sync.scheduler_installed(_ctx(stopped), "/bin/devboost")


def test_install_scheduler_linux_rewrite_is_idempotent(tmp_path: Path) -> None:
    sync.install_scheduler(_ctx(_ex()), "/bin/devboost")
    again = _ex()
    sync.install_scheduler(_ctx(again), "/bin/devboost")
    assert ["systemctl", "--user", "daemon-reload"] not in again.calls


def test_install_scheduler_macos_is_a_launchd_agent(tmp_path: Path) -> None:
    ex = _ex()
    sync.install_scheduler(_ctx(ex, MAC), "/bin/devboost")
    plist = tmp_path / "home" / "Library" / "LaunchAgents" / "dev.devboost.pass-sync.plist"
    assert plistlib.loads(plist.read_bytes()) == {
        "Label": "dev.devboost.pass-sync",
        "ProgramArguments": ["/bin/devboost", "pass", "sync", "--quiet"],
        "StartInterval": 900,
    }
    assert ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist)] in ex.calls
    assert not any(c[0] == "systemctl" for c in ex.calls)
    assert sync.scheduler_installed(_ctx(ex, MAC), "/bin/devboost")
    assert not sync.scheduler_installed(_ctx(ex, MAC), "/other/devboost")
    unloaded = _ex((("launchctl", "print"), Result(113)))
    assert not sync.scheduler_installed(_ctx(unloaded, MAC), "/bin/devboost")


def test_hook_env_short_circuits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVBOOST_PASS_HOOK", "off")
    ex = _ex()
    assert sync.run(_ctx(ex), _store(tmp_path), "desk").status == "skipped"
    assert ex.calls == []


def test_pull_push_and_record_last_sync(tmp_path: Path) -> None:
    s = _store(tmp_path)
    ex = _ex((("rev-list",), Result(0, "2\n")))
    assert sync.run(_ctx(ex), s, "desk").status == "ok"
    root = str(s.root)
    assert ex.calls[0] == ["git", "-C", root, "pull", "--rebase", "--autostash", "--quiet"]
    assert ["git", "-C", root, "push", "--quiet", "--set-upstream", "origin", "HEAD"] in ex.calls
    assert sync.last_sync()


def test_push_only_never_pulls(tmp_path: Path) -> None:
    s = _store(tmp_path)
    ex = _ex((("rev-list",), Result(0, "1\n")))
    assert sync.run(_ctx(ex), s, "desk", push_only=True).status == "ok"
    assert not any("pull" in c for c in ex.calls)
    push = ["git", "-C", str(s.root), "push", "--quiet", "--set-upstream", "origin", "HEAD"]
    assert push in ex.calls


def test_gpg_id_conflict_aborts_and_notifies(tmp_path: Path) -> None:
    ex = _ex((("pull",), Result(1)), (("--diff-filter=U",), Result(0, ".gpg-id\n")))
    res = sync.run(_ctx(ex), _store(tmp_path), "desk")
    assert (res.status, res.detail) == ("conflict", ".gpg-id")
    assert any(c[-2:] == ["rebase", "--abort"] for c in ex.calls)
    assert "devboost pass sync --resolve" in _notifications(ex)[0][-1]


def test_push_failure_notifies_once_per_head(tmp_path: Path) -> None:
    s = _store(tmp_path)
    ex = _ex((("rev-list",), Result(0, "1\n")), (("push",), Result(1)),
             (("rev-parse",), Result(0, "h1\n")))
    assert sync.run(_ctx(ex), s, "desk").status == "push-failed"
    assert sync.run(_ctx(ex), s, "desk").status == "push-failed"
    assert len(_notifications(ex)) == 1


def test_pull_failure_notifies_once_until_recovered(tmp_path: Path) -> None:
    s = _store(tmp_path)
    ex = _ex((("pull",), Result(1)))
    assert sync.run(_ctx(ex), s, "desk").status == "pull-failed"
    assert sync.run(_ctx(ex), s, "desk").status == "pull-failed"
    assert len(_notifications(ex)) == 1


def test_pending_request_notified_once(tmp_path: Path) -> None:
    s = _store(tmp_path)
    s.write_record("pending", DeviceRecord(name="lap", fingerprint=FP_NEW, os="ubuntu"), "K")
    ex = _ex()
    sync.run(_ctx(ex), s, "desk")
    sync.run(_ctx(ex), s, "desk")
    notes = _notifications(ex)
    assert len(notes) == 1 and "devboost pass approve lap" in notes[0][-1]
    assert "notified" in (tmp_path / "state" / "devboost" / "pass-sync.json").read_text(
        encoding="utf-8")


def test_unenrolled_device_does_not_notify_pending(tmp_path: Path) -> None:
    s = _store(tmp_path)
    s.write_record("pending", DeviceRecord(name="lap", fingerprint=FP_NEW, os="ubuntu"), "K")
    ex = _ex((("--list-secret-keys",), Result(0, colons("sec", FP_NEW))))
    sync.run(_ctx(ex), s, "lap")
    assert _notifications(ex) == []


def test_concurrent_sync_is_a_noop(tmp_path: Path) -> None:
    lock = tmp_path / "state" / "devboost" / "pass-sync.lock"
    lock.parent.mkdir(parents=True)
    with lock.open("w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ex = _ex()
        assert sync.run(_ctx(ex), _store(tmp_path), "desk").status == "busy"
        assert ex.calls == []


def test_resolve_guidance_lists_registry_fingerprints(tmp_path: Path) -> None:
    s = _store(tmp_path)
    s.write_record("devices", DeviceRecord(name="desk", fingerprint=FP_ME, os="fedora"), "K")
    text = sync.resolve_guidance(_ctx(_ex()), s)
    assert FP_ME in text and f"pass init {FP_ME}" in text and "git rebase --continue" in text


PUSH = ("push", "--quiet", "--set-upstream", "origin", "HEAD")


def _pushed(ex: RuleExecutor, s: Store) -> bool:
    return ["git", "-C", str(s.root), *PUSH] in ex.calls


def _state(tmp_path: Path) -> str:
    return (tmp_path / "state" / "devboost" / "pass-sync.json").read_text(encoding="utf-8")


def test_push_only_without_upstream_pushes_commits_on_no_remote(tmp_path: Path) -> None:
    s = _store(tmp_path)
    ex = _ex((("rev-list", "@{u}..HEAD"), Result(128)),
             (("rev-list", "--remotes=origin"), Result(0, "1\n")))
    assert sync.run(_ctx(ex), s, "desk", push_only=True).status == "ok"
    assert _pushed(ex, s)


def test_failed_pull_without_conflict_still_pushes(tmp_path: Path) -> None:
    s = _store(tmp_path)
    ex = _ex((("pull",), Result(1)), (("rev-list", "@{u}..HEAD"), Result(128)),
             (("rev-list", "--remotes=origin"), Result(0, "1\n")))
    assert sync.run(_ctx(ex), s, "desk").status == "pull-failed"
    assert _pushed(ex, s)


def test_conflict_notifies_once_per_head(tmp_path: Path) -> None:
    s = _store(tmp_path)
    ex = _ex((("pull",), Result(1)), (("--diff-filter=U",), Result(0, ".gpg-id\n")),
             (("rev-parse",), Result(0, "h1\n")))
    assert sync.run(_ctx(ex), s, "desk").status == "conflict"
    assert sync.run(_ctx(ex), s, "desk").status == "conflict"
    assert len(_notifications(ex)) == 1
    ex.rules[2] = (("rev-parse",), Result(0, "h2\n"))
    sync.run(_ctx(ex), s, "desk")
    assert len(_notifications(ex)) == 2


def test_recovered_pull_rearms_the_notice(tmp_path: Path) -> None:
    s = _store(tmp_path)
    ex = _ex((("pull",), Result(1)))
    assert sync.run(_ctx(ex), s, "desk").status == "pull-failed"
    ex.rules[0] = (("pull",), Result(0))
    assert sync.run(_ctx(ex), s, "desk").status == "ok"
    assert '"pull_failing": false' in _state(tmp_path)
    ex.rules[0] = (("pull",), Result(1))
    sync.run(_ctx(ex), s, "desk")
    assert len(_notifications(ex)) == 2


def test_successful_push_clears_failed_head(tmp_path: Path) -> None:
    s = _store(tmp_path)
    ex = _ex((("push",), Result(1)), (("rev-list",), Result(0, "1\n")),
             (("rev-parse",), Result(0, "h1\n")))
    assert sync.run(_ctx(ex), s, "desk").status == "push-failed"
    ex.rules[0] = (("push",), Result(0))
    assert sync.run(_ctx(ex), s, "desk").status == "ok"
    assert '"push_failed_head": null' in _state(tmp_path)
    ex.rules[0] = (("push",), Result(1))
    sync.run(_ctx(ex), s, "desk")
    assert len(_notifications(ex)) == 2


def test_notified_prunes_requests_no_longer_pending(tmp_path: Path) -> None:
    s = _store(tmp_path)
    rec = DeviceRecord(name="lap", fingerprint=FP_NEW, os="ubuntu")
    s.write_record("pending", rec, "K")
    ex = _ex()
    sync.run(_ctx(ex), s, "desk")
    s.record_path("pending", "lap").unlink()
    sync.run(_ctx(ex), s, "desk")
    assert "lap:" not in _state(tmp_path)
    s.write_record("pending", rec, "K")
    sync.run(_ctx(ex), s, "desk")
    assert len(_notifications(ex)) == 2


def test_unreadable_state_does_not_raise(tmp_path: Path) -> None:
    state = tmp_path / "state" / "devboost" / "pass-sync.json"
    state.parent.mkdir(parents=True)
    state.write_bytes(b"\xff\xfe not json")
    assert sync.run(_ctx(_ex()), _store(tmp_path), "desk").status == "ok"


def test_sync_survives_a_failing_gpg(tmp_path: Path) -> None:
    ex = _ex((("--list-secret-keys",), Result(2)), (("--list-keys",), Result(2)))
    assert sync.run(_ctx(ex), _store(tmp_path), "desk").status == "ok"


FP_GONE = "C" * 40


def _with_revoked(tmp_path: Path) -> Store:
    s = _store(tmp_path)
    s.write_record("devices", DeviceRecord(name="lap", fingerprint=FP_GONE, os="fedora"), "K")
    s.move("devices", "revoked", "lap")
    return s


def test_sync_deletes_revoked_public_keys_still_in_the_keyring(tmp_path: Path) -> None:
    s = _with_revoked(tmp_path)
    ex = _ex((("--list-keys",), Result(0, colons("pub", FP_ME) + colons("pub", FP_GONE))))
    assert sync.run(_ctx(ex), s, "desk").status == "ok"
    delete = ["gpg", "--batch", "--yes", "--delete-keys", FP_GONE]
    assert delete in ex.calls
    gone = _ex((("--list-keys",), Result(0, colons("pub", FP_ME))))  # already deleted
    sync.run(_ctx(gone), s, "desk")
    assert delete not in gone.calls


def test_failed_revoked_key_delete_is_logged_not_raised(tmp_path: Path) -> None:
    s = _with_revoked(tmp_path)
    ex = _ex((("--delete-keys",), Result(2)),
             (("--list-keys",), Result(0, colons("pub", FP_GONE))))
    assert sync.run(_ctx(ex), s, "desk").status == "ok"
    log = (tmp_path / "state" / "devboost" / "pass-sync.log").read_text(encoding="utf-8")
    assert FP_GONE in log


# --- tripwire: a device key this device never saw (I2) ------------------------------------

FP_EVIL = "E" * 40


def _list(s: Store, *fps: str) -> None:
    s.gpg_id_path().write_text("".join(f"{fp}\n" for fp in fps), encoding="utf-8")


def _device(s: Store, name: str, fp: str) -> None:
    s.write_record("devices", DeviceRecord(name=name, fingerprint=fp, os="fedora"), "K")


def _tripwires(ex: RuleExecutor) -> list[list[str]]:
    return [c for c in _notifications(ex) if "new device" in c[-2]]


def test_tripwire_seeds_silently_then_notifies_an_unseen_device_once(tmp_path: Path) -> None:
    s = _store(tmp_path)
    _device(s, "desk", FP_ME)
    _list(s, FP_ME, FP_NEW)
    _device(s, "lap", FP_NEW)
    ex = _ex()
    sync.run(_ctx(ex), s, "desk")
    assert _tripwires(ex) == []  # first run: what is there now is simply known
    _list(s, FP_ME, FP_NEW, FP_EVIL)
    _device(s, "evil", FP_EVIL)
    sync.run(_ctx(ex), s, "desk")
    sync.run(_ctx(ex), s, "desk")
    notes = _tripwires(ex)
    assert len(notes) == 1 and "evil" in notes[0][-1] and FP_EVIL in notes[0][-1]
    assert "devboost pass revoke evil" in notes[0][-1]


def test_tripwire_ignores_unlisted_records_own_key_and_devices_approved_here(
    tmp_path: Path,
) -> None:
    s = _store(tmp_path)
    ex = _ex()
    sync.run(_ctx(ex), s, "desk")  # seeds an empty set
    _device(s, "stray", FP_EVIL)  # a record whose key no .gpg-id lists grants nothing
    _device(s, "desk", FP_ME)  # this device's own key, once it is approved
    sync.remember_devices([FP_NEW])  # what `devboost pass approve` on this device records
    _list(s, FP_ME, FP_NEW)
    _device(s, "lap", FP_NEW)
    sync.run(_ctx(ex), s, "desk")
    assert _tripwires(ex) == []


def test_notifications_sanitize_remote_names(tmp_path: Path) -> None:
    s = _store(tmp_path)
    s.write_record("pending", DeviceRecord(name="-x\x1b[2Jy", fingerprint=FP_NEW,
                                           os="\nos"), "K")
    ex = _ex()
    sync.run(_ctx(ex), s, "desk")
    body = _notifications(ex)[0][-1]
    assert body.startswith("x[2Jy (os)") and "\x1b" not in body


def test_tripwire_trusts_no_spoofed_record_name(tmp_path: Path) -> None:
    s = _store(tmp_path)
    _device(s, "desk", FP_ME)
    ex = _ex()
    sync.run(_ctx(ex), s, "desk")  # seed
    _list(s, FP_ME, FP_EVIL)
    spoof = DeviceRecord(name="desk", fingerprint=FP_EVIL, os="fedora")
    (s.meta / "devices" / "evil.json").write_text(spoof.model_dump_json(), encoding="utf-8")
    sync.run(_ctx(ex), s, "desk")
    assert not any("revoke desk" in c[-1] for c in _notifications(ex))


def test_forget_revoked_skips_this_devices_own_key(tmp_path: Path) -> None:
    """A revoked device keeps its own secret key: never try (and fail) to delete it."""
    s = _store(tmp_path)
    s.write_record("devices", DeviceRecord(name="desk", fingerprint=FP_ME, os="fedora"), "K")
    s.move("devices", "revoked", "desk")
    ex = _ex((("--list-keys",), Result(0, colons("pub", FP_ME))))
    sync.run(_ctx(ex), s, "desk")
    assert not any("--delete-keys" in c for c in ex.calls)


# --- recipient audit (R10) --------------------------------------------------------------


def _audited(monkeypatch: pytest.MonkeyPatch, *reports: audit.Report) -> list[int]:
    calls: list[int] = []
    it = iter(reports)

    def fake(ctx: Ctx, store: Store) -> audit.Report:
        calls.append(1)
        return next(it)

    monkeypatch.setattr(audit, "audit", fake)
    return calls


def test_sync_audits_when_head_moves_and_notifies_new_mismatches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = _store(tmp_path)
    bad = audit.Report([audit.Mismatch("web/x", ("bravo (revoked)",), ())], [])
    calls = _audited(monkeypatch, bad, bad)
    ex = _ex((("rev-parse", "HEAD"), Result(0, "h1\n")))
    assert sync.run(_ctx(ex), s, "desk").status == "ok"
    notes = [c for c in _notifications(ex) if "recipients" in c[2]]
    assert len(notes) == 1 and "web/x" in notes[0][3]
    assert "devboost pass audit" in notes[0][3]
    sync.run(_ctx(ex), s, "desk")  # same HEAD → no second audit
    assert len(calls) == 1
    ex2 = _ex((("rev-parse", "HEAD"), Result(0, "h2\n")))
    sync.run(_ctx(ex2), s, "desk")  # HEAD moved, same findings → audited, not re-announced
    assert len(calls) == 2
    assert not [c for c in _notifications(ex2) if "recipients" in c[2]]


def test_sync_audit_failure_is_logged_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = _store(tmp_path)

    def boom(ctx: Ctx, store: Store) -> audit.Report:
        raise InstallError("pass-store", "gpg --list-keys", 2)

    monkeypatch.setattr(audit, "audit", boom)
    ex = _ex((("rev-parse", "HEAD"), Result(0, "h1\n")))
    assert sync.run(_ctx(ex), s, "desk").status == "ok"


def test_push_only_sync_never_audits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    s = _store(tmp_path)
    calls = _audited(monkeypatch)
    sync.run(_ctx(_ex((("rev-parse", "HEAD"), Result(0, "h1\n")))), s, "desk", push_only=True)
    assert calls == []
