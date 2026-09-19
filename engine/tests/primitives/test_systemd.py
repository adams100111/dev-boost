from __future__ import annotations

from pathlib import Path

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import systemd
from devboost.model import Ctx

FEDORA = OsInfo("fedora", "fedora", "x86_64")
RELOAD = ["systemctl", "--user", "daemon-reload"]


def test_write_user_unit_reloads_only_on_change(tmp_path: Path) -> None:
    ex = FakeExecutor()
    ctx = Ctx(os=FEDORA, ex=ex)
    assert systemd.write_user_unit(ctx, "x.service", "A\n") is True
    assert ex.calls == [RELOAD]
    assert systemd.unit_current("x.service", "A\n")
    assert systemd.write_user_unit(ctx, "x.service", "A\n") is False
    assert ex.calls == [RELOAD]  # unchanged → no write, no reload
    assert systemd.write_user_unit(ctx, "x.service", "B\n") is True
    assert ex.calls == [RELOAD, RELOAD]
    assert not systemd.unit_current("x.service", "A\n")
    assert not systemd.unit_current("missing.timer", "A\n")


def test_is_active() -> None:
    ex = FakeExecutor()
    ok = Ctx(os=FEDORA, ex=ex)
    assert systemd.is_active(ok, "t.timer", user=True)
    assert ex.calls == [["systemctl", "--user", "is-active", "t.timer"]]
    bad = Ctx(os=FEDORA, ex=FakeExecutor(scripts={"systemctl": Result(3)}))
    assert not systemd.is_active(bad, "t.timer", user=True)
