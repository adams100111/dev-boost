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
