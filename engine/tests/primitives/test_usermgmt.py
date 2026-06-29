from __future__ import annotations

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
