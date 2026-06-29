from __future__ import annotations

import pytest

from devboost.accounts.config import AccountsError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import usermgmt
from devboost.model import Ctx

FEDORA = OsInfo("fedora", "fedora", "x86_64")
UBUNTU = OsInfo(distro="ubuntu", family="debian", arch="x86_64")


def _ctx(os: OsInfo = FEDORA, **kw: object) -> Ctx:
    return Ctx(os=os, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_exists_true_when_getent_ok() -> None:
    ctx = _ctx(scripts={"getent": Result(0)})
    assert usermgmt.exists(ctx, "dev") is True
    assert ["getent", "passwd", "dev"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_exists_false_when_getent_fails() -> None:
    assert usermgmt.exists(_ctx(scripts={"getent": Result(2)}), "dev") is False


def test_uid_of_parses_id() -> None:
    ctx = _ctx(scripts={"id": Result(0, stdout="1005\n")})
    assert usermgmt.uid_of(ctx, "dev") == 1005


def test_admin_group_wheel_when_present() -> None:
    assert usermgmt.admin_group(_ctx(scripts={"getent": Result(0)})) == "wheel"


def test_admin_group_sudo_when_wheel_absent() -> None:
    assert usermgmt.admin_group(_ctx(scripts={"getent": Result(2)})) == "sudo"


def test_ensure_user_creates_with_home_and_shell_when_absent() -> None:
    ctx = _ctx(scripts={"getent": Result(2)})  # does not exist
    usermgmt.ensure_user(ctx, "dev", shell="/bin/bash")
    assert ["sudo", "useradd", "-m", "-s", "/bin/bash", "dev"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_ensure_user_noop_when_present() -> None:
    ctx = _ctx(scripts={"getent": Result(0)})  # exists
    usermgmt.ensure_user(ctx, "dev", shell="/bin/bash")
    assert not any("useradd" in c for c in ctx.ex.calls)  # type: ignore[attr-defined]


def test_lock_sets_password_lock_and_expiry() -> None:
    ctx = _ctx()
    usermgmt.lock(ctx, "dev")
    assert ["sudo", "usermod", "-L", "--expiredate", "1", "dev"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_delete_removes_home() -> None:
    ctx = _ctx()
    usermgmt.delete(ctx, "dev")
    assert ["sudo", "userdel", "-r", "dev"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_ensure_user_creates_with_explicit_home() -> None:
    ctx = _ctx(scripts={"getent": Result(2)})  # user absent
    usermgmt.ensure_user(ctx, "dev", shell="/bin/bash", home="/home/dev")
    assert ["sudo", "useradd", "-m", "-s", "/bin/bash", "-d", "/home/dev", "dev"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_terminate_sessions_ignores_nonzero_exits() -> None:
    ctx = _ctx(scripts={"loginctl": Result(1), "pkill": Result(1)})
    usermgmt.terminate_sessions(ctx, "dev")  # must not raise
    assert ["sudo", "loginctl", "terminate-user", "dev"] in ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "pkill", "-u", "dev"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_sudoers_content_none_for_basic_tiers() -> None:
    assert usermgmt.sudoers_content("dev", "none", ()) is None
    assert usermgmt.sudoers_content("dev", "full", ()) is None


def test_sudoers_content_nopasswd() -> None:
    assert usermgmt.sudoers_content("dev", "nopasswd", ()) == "dev ALL=(ALL) NOPASSWD: ALL\n"


def test_sudoers_content_allowlist() -> None:
    out = usermgmt.sudoers_content("dev", "allowlist", ("/usr/bin/systemctl restart x",))
    assert out == "dev ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart x\n"


def test_sudoers_path_is_dot_free() -> None:
    assert usermgmt.sudoers_path("dev") == "/etc/sudoers.d/devboost-dev"


def test_write_sudoers_validates_then_atomically_moves() -> None:
    ctx = _ctx(scripts={"visudo": Result(0)})
    usermgmt.write_sudoers(ctx, "dev", "dev ALL=(ALL) NOPASSWD: ALL\n")
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert any(c[:2] == ["sudo", "tee"] for c in calls)            # staged write
    assert any(c[1] == "visudo" and "-cf" in c for c in calls)     # validated
    assert any(c[1] == "chmod" and "0440" in c for c in calls)     # mode
    assert any(c[1] == "mv" and c[-1] == "/etc/sudoers.d/devboost-dev" for c in calls)


def test_write_sudoers_raises_on_invalid() -> None:
    ctx = _ctx(scripts={"visudo": Result(1, stderr="parse error")})
    with pytest.raises(AccountsError, match="sudoers"):
        usermgmt.write_sudoers(ctx, "dev", "garbage\n")
    # never moved into place:
    assert not any(c[1:2] == ["mv"] for c in ctx.ex.calls)  # type: ignore[attr-defined]


def test_slice_dropin_text_none_when_all_unset() -> None:
    assert usermgmt.slice_dropin_text(None, None, None) is None


def test_slice_dropin_text_includes_only_set_knobs() -> None:
    text = usermgmt.slice_dropin_text("4G", "50%", 200)
    assert text is not None
    assert "[Slice]" in text
    assert "MemoryMax=4G" in text
    assert "MemoryHigh=" in text          # ~90% derived
    assert "CPUQuota=50%" in text
    assert "TasksMax=200" in text
    text2 = usermgmt.slice_dropin_text(None, "25%", None)
    assert text2 is not None
    assert "MemoryMax" not in text2 and "CPUQuota=25%" in text2


def test_set_slice_writes_dropin_reloads_and_sets_property() -> None:
    ctx = _ctx()
    usermgmt.set_slice(ctx, 1005, ram="4G", cpu="50%", tasks=200)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert any(c[1] == "install" and c[-1].endswith("user-1005.slice.d") for c in calls)
    assert any(c[1] == "tee" and c[-1].endswith("50-devboost.conf") for c in calls)
    assert ["sudo", "systemctl", "daemon-reload"] in calls
    assert any(c[1:4] == ["systemctl", "set-property", "user-1005.slice"] for c in calls)


def test_set_slice_noop_when_all_unset() -> None:
    ctx = _ctx()
    usermgmt.set_slice(ctx, 1005, ram=None, cpu=None, tasks=None)
    assert ctx.ex.calls == []  # type: ignore[attr-defined]


def test_clear_slice_removes_and_resets() -> None:
    ctx = _ctx()
    usermgmt.clear_slice(ctx, 1005)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert any(c[1] == "rm" and c[-1].endswith("50-devboost.conf") for c in calls)
    assert ["sudo", "systemctl", "daemon-reload"] in calls
    assert any(c[1:3] == ["systemctl", "set-property"] and "--runtime" in c for c in calls)


def test_fstype_of_reads_findmnt() -> None:
    ctx = _ctx(scripts={"findmnt": Result(0, stdout="btrfs\n")})
    assert usermgmt.fstype_of(ctx, "/home/dev") == "btrfs"


def test_set_quota_btrfs_enables_and_limits() -> None:
    ctx = _ctx(scripts={"findmnt": Result(0, stdout="btrfs\n")})
    status = usermgmt.set_quota(ctx, "dev", "/home/dev", "20G")
    assert status == "enforced"
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert any(c[1:3] == ["btrfs", "quota"] and "enable" in c for c in calls)
    assert any(c[1:4] == ["btrfs", "qgroup", "limit"] and c[-1] == "/home/dev" for c in calls)


def test_set_quota_ext4_skips_when_not_active() -> None:
    # findmnt -> ext4; quotaon returns non-zero -> skipped, never fails.
    ctx = _ctx(scripts={"findmnt": Result(0, stdout="ext4\n"), "quotaon": Result(1)})
    status = usermgmt.set_quota(ctx, "dev", "/home/dev", "20G")
    assert status.startswith("skipped:")
    assert not any("setquota" in c for c in ctx.ex.calls)  # type: ignore[attr-defined]


def test_set_quota_ext4_enforces_when_active() -> None:
    ctx = _ctx(scripts={"findmnt": Result(0, stdout="ext4\n"), "quotaon": Result(0)},
               present={"setquota"})
    status = usermgmt.set_quota(ctx, "dev", "/home/dev", "20G")
    assert status == "enforced"
    assert any(c[1] == "setquota" and "20G" in c for c in ctx.ex.calls)  # type: ignore[attr-defined]


def test_set_quota_unsupported_fs_skips() -> None:
    ctx = _ctx(scripts={"findmnt": Result(0, stdout="overlay\n")})
    assert usermgmt.set_quota(ctx, "dev", "/home/dev", "20G").startswith("skipped:")


def test_ensure_user_raises_on_useradd_failure() -> None:
    ctx = _ctx(scripts={"getent": Result(2), "useradd": Result(1)})
    with pytest.raises(AccountsError, match="useradd failed for 'dev'"):
        usermgmt.ensure_user(ctx, "dev", shell="/bin/bash")


def test_add_admin_group_raises_on_usermod_failure() -> None:
    ctx = _ctx(scripts={"usermod": Result(1)})
    with pytest.raises(AccountsError, match="failed adding 'dev' to admin group"):
        usermgmt.add_admin_group(ctx, "dev")


def test_set_slice_raises_on_set_property_failure() -> None:
    ctx = _ctx(scripts={"systemctl": Result(1)})
    with pytest.raises(AccountsError, match="failed applying resource caps to user-1005.slice"):
        usermgmt.set_slice(ctx, 1005, ram="4G", cpu=None, tasks=None)
