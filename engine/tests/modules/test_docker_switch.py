from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar

import pytest

from devboost.core.errors import InstallError, NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.core.userconfig import DockerRuntimeName, load_user_config, set_user_value
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx, Module
from devboost.modules import _docker_switch as sw
from devboost.modules.docker import BUILDER_GC

MAC = OsInfo("macos", "macos", "aarch64")


class _Rt:
    """Records each call as `rt <name> <method>` on the executor, so order is checkable."""

    def __init__(
        self, name: DockerRuntimeName, *, installed: bool = True, merged: bool = True,
        fail_start: bool = False,
    ) -> None:
        self.name: DockerRuntimeName = name
        self.context_name = f"ctx-{name}"
        self._installed, self._merged, self._fail_start = installed, merged, fail_start

    def _rec(self, ctx: Ctx, what: str) -> None:
        ctx.ex.run(["rt", self.name, what])

    def daemon_config_path(self) -> Path:
        return Path("/nonexistent")

    def installed(self, ctx: Ctx) -> bool:
        return self._installed

    def install(self, ctx: Ctx) -> None:
        self._rec(ctx, "install")

    def configure(self, ctx: Ctx) -> None:
        self._rec(ctx, "configure")

    def start(self, ctx: Ctx) -> None:
        self._rec(ctx, "start")
        if self._fail_start:
            raise NeedsUser("first launch", "open the app")

    def stop(self, ctx: Ctx) -> None:
        self._rec(ctx, "stop")

    def disable_autostart(self, ctx: Ctx) -> None:
        self._rec(ctx, "disable_autostart")

    def release_socket(self, ctx: Ctx) -> None:
        self._rec(ctx, "release_socket")

    def merge_daemon_config(self, ctx: Ctx, patch: Mapping[str, Any]) -> bool:
        assert patch == BUILDER_GC
        self._rec(ctx, "merge_daemon_config")
        return self._merged

    def daemon_config_has(self, patch: Mapping[str, Any]) -> bool:
        return True

    def restart_engine(self, ctx: Ctx) -> None:
        self._rec(ctx, "restart_engine")

    def verify(self, ctx: Ctx) -> bool:
        return True


@pytest.fixture
def runtimes(monkeypatch: pytest.MonkeyPatch) -> dict[str, _Rt]:
    table = {"colima": _Rt("colima"), "orbstack": _Rt("orbstack"),
             "docker-desktop": _Rt("docker-desktop")}
    monkeypatch.setattr(sw, "runtime_for", lambda name: table[name])
    monkeypatch.setattr(sw, "_verify", lambda ctx, name: True)
    return table


def _mac(present: set[str] | None = None, **scripts: Result) -> Ctx:
    return Ctx(os=MAC, ex=FakeExecutor(present=present if present is not None else {"ddev"},
                                       scripts=dict(scripts)))


def test_colima_to_orbstack_runs_the_spec_steps_in_order(runtimes: dict[str, _Rt]) -> None:
    ctx = _mac()
    report = sw.switch_runtime(ctx, "orbstack", snapshot=True)
    assert ctx.ex.calls == [  # type: ignore[attr-defined]
        ["ddev", "snapshot", "--all"],
        ["ddev", "poweroff"],
        ["rt", "colima", "stop"],
        ["rt", "colima", "disable_autostart"],
        ["rt", "colima", "release_socket"],
        ["rt", "orbstack", "install"],
        ["rt", "orbstack", "configure"],
        ["rt", "orbstack", "start"],
        ["docker", "context", "use", "ctx-orbstack"],
        ["rt", "orbstack", "merge_daemon_config"],
        ["rt", "orbstack", "restart_engine"],
    ]
    assert load_user_config().docker_runtime == "orbstack"
    assert report.previous == "colima" and report.target == "orbstack"
    assert [n for n, _ in report.checks] == list(sw.REVERIFY)
    assert report.ok is True


def test_no_snapshot_still_powers_ddev_off(runtimes: dict[str, _Rt]) -> None:
    ctx = _mac()
    sw.switch_runtime(ctx, "orbstack", snapshot=False)
    assert ctx.ex.calls[0] == ["ddev", "poweroff"]  # type: ignore[attr-defined]


def test_without_ddev_there_is_nothing_to_snapshot(runtimes: dict[str, _Rt]) -> None:
    ctx = _mac(present=set())
    sw.switch_runtime(ctx, "orbstack", snapshot=True)
    assert not any(c[0] == "ddev" for c in ctx.ex.calls)  # type: ignore[attr-defined]


def test_failed_snapshot_aborts_before_touching_the_old_runtime(
    runtimes: dict[str, _Rt],
) -> None:
    ctx = _mac(ddev=Result(1))
    with pytest.raises(InstallError, match="ddev snapshot --all"):
        sw.switch_runtime(ctx, "orbstack", snapshot=True)
    assert ctx.ex.calls == [["ddev", "snapshot", "--all"]]  # type: ignore[attr-defined]
    assert load_user_config().docker_runtime is None


def test_same_runtime_reconfigures_without_stopping(runtimes: dict[str, _Rt]) -> None:
    ctx = _mac(present=set())
    sw.switch_runtime(ctx, "colima", snapshot=False)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["rt", "colima", "stop"] not in calls
    assert ["rt", "colima", "configure"] in calls


def test_an_uninstalled_old_runtime_is_not_stopped(
    runtimes: dict[str, _Rt], monkeypatch: pytest.MonkeyPatch
) -> None:
    runtimes["colima"] = _Rt("colima", installed=False)
    ctx = _mac(present=set())
    sw.switch_runtime(ctx, "orbstack", snapshot=False)
    assert ["rt", "colima", "stop"] not in ctx.ex.calls  # type: ignore[attr-defined]


def test_blocked_new_runtime_leaves_the_saved_choice_alone(runtimes: dict[str, _Rt]) -> None:
    set_user_value("docker_runtime", "colima")
    runtimes["orbstack"] = _Rt("orbstack", fail_start=True)
    with pytest.raises(NeedsUser):
        sw.switch_runtime(_mac(present=set()), "orbstack", snapshot=False)
    assert load_user_config().docker_runtime == "colima"


def test_unchanged_daemon_config_needs_no_restart(runtimes: dict[str, _Rt]) -> None:
    runtimes["orbstack"] = _Rt("orbstack", merged=False)
    ctx = _mac(present=set())
    sw.switch_runtime(ctx, "orbstack", snapshot=False)
    assert ["rt", "orbstack", "restart_engine"] not in ctx.ex.calls  # type: ignore[attr-defined]


def test_report_ok_only_needs_docker_and_build_gc() -> None:
    ok = sw.SwitchReport("colima", "orbstack", (("docker", True), ("docker-build-gc", True),
                                                 ("ddev", False)))
    assert ok.ok is True
    bad = sw.SwitchReport("colima", "orbstack", (("docker", False), ("docker-build-gc", True)))
    assert bad.ok is False


class _Boom(Module):
    name: ClassVar[str] = "boom-probe"

    def verify(self, ctx: Ctx) -> bool:
        raise InstallError("boom", "x", 1)

    def install(self, ctx: Ctx) -> None:
        return None


def test_verify_helper_is_false_for_unknown_or_failing_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sw, "load", lambda: {"boom-probe": _Boom})
    ctx = _mac()
    assert sw._verify(ctx, "boom-probe") is False
    assert sw._verify(ctx, "no-such-module") is False


def test_a_failed_poweroff_after_the_snapshot_still_switches(runtimes: dict[str, _Rt]) -> None:
    """The snapshot is the safety net; stopping the old runtime stops ddev's containers too."""

    class _PoweroffFails(FakeExecutor):
        def run(self, argv: Any, **kw: Any) -> Result:
            super().run(argv, **kw)
            return Result(1) if list(argv) == ["ddev", "poweroff"] else Result(0)

    ctx = Ctx(os=MAC, ex=_PoweroffFails(present={"ddev"}))
    sw.switch_runtime(ctx, "orbstack", snapshot=True)
    assert ["rt", "colima", "stop"] in ctx.ex.calls  # type: ignore[attr-defined]
    assert load_user_config().docker_runtime == "orbstack"


def test_the_snapshot_runs_before_any_runtime_call(runtimes: dict[str, _Rt]) -> None:
    ctx = _mac()
    sw.switch_runtime(ctx, "docker-desktop", snapshot=True)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    first_rt = next(i for i, c in enumerate(calls) if c[0] == "rt")
    assert calls.index(["ddev", "snapshot", "--all"]) < first_rt


def test_a_failed_verify_probe_is_reported_not_raised(
    runtimes: dict[str, _Rt], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sw, "_verify", lambda ctx, name: name != "docker")
    report = sw.switch_runtime(_mac(present=set()), "orbstack", snapshot=False)
    assert dict(report.checks)["docker"] is False
    assert report.ok is False
