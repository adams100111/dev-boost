from __future__ import annotations

import fcntl
from pathlib import Path

import pytest

from devboost.core.errors import UnsupportedOS
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.passstore import sync
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
    assert sync.install_hook(s, "/bin/devboost") is True
    hook = s.root / ".git" / "hooks" / "post-commit"
    text = hook.read_text(encoding="utf-8")
    assert text.startswith("#!/bin/sh\n") and sync.HOOK_MARK in text
    assert len(text.splitlines()) == 3
    assert "\n/bin/devboost pass sync --push-only --quiet" in text
    assert text.rstrip().endswith("&")
    assert hook.stat().st_mode & 0o111
    assert sync.install_hook(s, "/bin/devboost") is False
    assert sync.hook_installed(s)


def test_hook_and_unit_quote_paths_with_spaces() -> None:
    assert "\n'/opt/my apps/devboost' pass sync" in sync.hook_script("/opt/my apps/devboost")
    unit = sync.service_unit('/opt/my apps/a"b$c%d')
    assert 'ExecStart="/opt/my apps/a\\"b$$c%%d" pass sync --quiet' in unit


def test_foreign_hook_is_backed_up(tmp_path: Path) -> None:
    s = _store(tmp_path)
    hook = s.root / ".git" / "hooks" / "post-commit"
    hook.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
    sync.install_hook(s, "/bin/devboost")
    assert (hook.parent / "post-commit.devboost-backup").read_text(encoding="utf-8").endswith(
        "echo mine\n")


def test_units_content() -> None:
    assert 'ExecStart="/bin/devboost" pass sync --quiet' in sync.service_unit("/bin/devboost")
    t = sync.timer_unit()
    assert "OnCalendar=*:0/15" in t and "Persistent=true" in t and "WantedBy=timers.target" in t


def test_install_scheduler_linux_enables_timer(tmp_path: Path) -> None:
    ex = _ex()
    sync.install_scheduler(_ctx(ex), "/bin/devboost")
    units = tmp_path / "home" / ".config" / "systemd" / "user"
    assert (units / sync.SERVICE).exists() and (units / sync.TIMER).exists()
    assert ["systemctl", "--user", "enable", "--now", sync.TIMER] in ex.calls
    assert sync.scheduler_installed(_ctx(ex))


def test_install_scheduler_macos_is_p2(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedOS, match="P2"):
        sync.install_scheduler(_ctx(_ex(), MAC), "/bin/devboost")


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
