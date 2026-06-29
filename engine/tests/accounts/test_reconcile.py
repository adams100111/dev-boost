from __future__ import annotations

from devboost.accounts import reconcile
from devboost.accounts.config import ManagedUser
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx

FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def _user(**over: object) -> ManagedUser:
    base = dict(
        name="dev", enabled=True, shell="/bin/bash", lock_shell=False, linger=False,
        privilege="none", sudo_commands=(), ram="4G", cpu="50%", tasks=200, disk=None,
        ssh_authorized_keys=(), bootstrap_profiles=(),
    )
    base.update(over)
    return ManagedUser(**base)  # type: ignore[arg-type]


def test_apply_user_creates_and_caps() -> None:
    ctx = _ctx(scripts={"getent": Result(2), "id": Result(0, stdout="1005\n")})
    reconcile.apply_user(ctx, _user())
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "useradd", "-m", "-s", "/bin/bash", "dev"] in calls
    assert any(c[1:4] == ["systemctl", "set-property", "user-1005.slice"] for c in calls)


def test_apply_user_nopasswd_writes_sudoers() -> None:
    ctx = _ctx(scripts={"getent": Result(2), "id": Result(0, stdout="1005\n"), "visudo": Result(0)})
    reconcile.apply_user(ctx, _user(privilege="nopasswd"))
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert any(c[1] == "mv" and c[-1] == "/etc/sudoers.d/devboost-dev" for c in calls)


def test_apply_user_disabled_locks_instead_of_creating() -> None:
    ctx = _ctx(scripts={"getent": Result(0), "id": Result(0, stdout="1005\n")})
    reconcile.apply_user(ctx, _user(enabled=False))
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "usermod", "-L", "--expiredate", "1", "dev"] in calls


def test_delete_user_tears_down_and_removes() -> None:
    ctx = _ctx(scripts={"id": Result(0, stdout="1005\n"), "findmnt": Result(0, stdout="ext4\n")})
    reconcile.delete_user(ctx, _user())
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "userdel", "-r", "dev"] in calls
    assert any(c[1] == "rm" and "sudoers.d/devboost-dev" in c[-1] for c in calls)
    assert any(c[1] == "rm" and "50-devboost.conf" in c[-1] for c in calls)
