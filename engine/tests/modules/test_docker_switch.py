from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar

import pytest

from devboost.core.errors import InstallError, NeedsUser, PresentUnmanaged
from devboost.core.osinfo import OsInfo
from devboost.core.userconfig import DockerRuntimeName, load_user_config, set_user_value
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx, Module
from devboost.modules import _docker_desktop
from devboost.modules import _docker_switch as sw
from devboost.modules.docker import BUILDER_GC

MAC = OsInfo("macos", "macos", "aarch64")


class _Rt:
    """Records each call as `rt <name> <method>` on the executor, so order is checkable."""

    def __init__(
        self, name: DockerRuntimeName, *, installed: bool = True, merged: bool = True,
        fail_start: bool = False, by_hand: bool = False,
    ) -> None:
        self.name: DockerRuntimeName = name
        self.context_name = f"ctx-{name}"
        self._installed, self._merged, self._fail_start = installed, merged, fail_start
        self._by_hand = by_hand

    def _rec(self, ctx: Ctx, what: str) -> None:
        ctx.ex.run(["rt", self.name, what])

    def daemon_config_path(self) -> Path:
        return Path("/nonexistent")

    def installed(self, ctx: Ctx) -> bool:
        return self._installed

    def install(self, ctx: Ctx) -> None:
        self._rec(ctx, "install")
        if self._by_hand:
            raise PresentUnmanaged(f"{self.name}.app")

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
    # Docker Desktop is not installed by default, so the spec's colima → orbstack order holds.
    table = {"colima": _Rt("colima"), "orbstack": _Rt("orbstack"),
             "docker-desktop": _Rt("docker-desktop", installed=False)}
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
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
        ["docker", "context", "show"],
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
    with pytest.raises(sw.SnapshotFailed, match="ddev snapshot --all"):
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


def test_the_env_override_never_hides_the_runtime_to_stop(
    runtimes: dict[str, _Rt], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review I-1: env == target must not turn the switch into a same-runtime repair."""
    set_user_value("docker_runtime", "colima")
    monkeypatch.setenv("DEVBOOST_DOCKER_RUNTIME", "orbstack")
    ctx = _mac(present=set())
    report = sw.switch_runtime(ctx, "orbstack", snapshot=False)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert calls[:3] == [["rt", "colima", "stop"], ["rt", "colima", "disable_autostart"],
                         ["rt", "colima", "release_socket"]]
    assert report.previous == "colima"
    assert load_user_config().docker_runtime == "orbstack"


@pytest.mark.parametrize(("previous", "target"),
                         [("orbstack", "docker-desktop"), ("docker-desktop", "orbstack")])
def test_a_hand_installed_target_is_configured_and_started(
    runtimes: dict[str, _Rt], previous: DockerRuntimeName, target: DockerRuntimeName,
) -> None:
    """Review I-2: the vendor's own download raises PresentUnmanaged, as the runner skips it."""
    set_user_value("docker_runtime", previous)
    runtimes["colima"] = _Rt("colima", installed=False)
    runtimes[previous] = _Rt(previous)
    runtimes[target] = _Rt(target, by_hand=True)
    ctx = _mac(present=set())
    report = sw.switch_runtime(ctx, target, snapshot=False)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    after_install = calls[calls.index(["rt", target, "install"]) + 1:]
    assert after_install[:2] == [["rt", target, "configure"], ["rt", target, "start"]]
    assert ["rt", previous, "stop"] in calls
    assert load_user_config().docker_runtime == target
    assert report.ok is True


def test_going_back_stops_the_half_started_runtime(runtimes: dict[str, _Rt]) -> None:
    """A switch to orbstack failed after `start`: `docker use colima` must stop OrbStack."""
    set_user_value("docker_runtime", "colima")
    ctx = _mac(present=set())
    sw.switch_runtime(ctx, "colima", snapshot=False)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["rt", "orbstack", "stop"] in calls
    assert ["rt", "orbstack", "disable_autostart"] in calls
    assert ["rt", "colima", "stop"] not in calls
    assert calls.index(["rt", "orbstack", "stop"]) < calls.index(["rt", "colima", "start"])


def test_every_other_installed_runtime_is_stopped_saved_one_first(
    runtimes: dict[str, _Rt],
) -> None:
    runtimes["docker-desktop"] = _Rt("docker-desktop")
    ctx = _mac(present=set())
    sw.switch_runtime(ctx, "orbstack", snapshot=False)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    stops = [c[1] for c in calls if c[0] == "rt" and c[2] == "stop"]
    assert stops == ["colima", "docker-desktop"]


@pytest.fixture
def probes(monkeypatch: pytest.MonkeyPatch) -> dict[str, bool]:
    state = {"links_root": False, "colima_root": False}
    monkeypatch.setattr(_docker_desktop, "links_need_root", lambda ctx: state["links_root"])
    monkeypatch.setattr(sw, "_colima_release_needs_root", lambda ctx: state["colima_root"])
    return state


@pytest.mark.parametrize(
    ("saved", "target", "colima_installed", "links_root", "colima_root", "want"),
    [
        (None, "orbstack", True, False, False, True),  # nothing saved: colima is previous
        ("orbstack", "colima", False, False, False, True),
        ("orbstack", "docker-desktop", False, False, False, False),
        ("orbstack", "docker-desktop", False, True, False, True),  # cask links need root
        ("docker-desktop", "orbstack", True, False, True, True),  # stray colima daemon
        ("docker-desktop", "orbstack", True, False, False, False),  # stray, nothing as root
    ],
)
def test_sudo_needed(
    runtimes: dict[str, _Rt], probes: dict[str, bool], saved: DockerRuntimeName | None,
    target: DockerRuntimeName, colima_installed: bool, links_root: bool, colima_root: bool,
    want: bool,
) -> None:
    if saved is not None:
        set_user_value("docker_runtime", saved)
    runtimes["colima"] = _Rt("colima", installed=colima_installed)
    probes.update(links_root=links_root, colima_root=colima_root)
    assert sw.sudo_needed(_mac(), target) is want


def test_sudo_needed_reads_the_saved_runtime_not_the_env(
    runtimes: dict[str, _Rt], probes: dict[str, bool], monkeypatch: pytest.MonkeyPatch
) -> None:
    set_user_value("docker_runtime", "colima")
    monkeypatch.setenv("DEVBOOST_DOCKER_RUNTIME", "orbstack")
    assert sw.sudo_needed(_mac(), "orbstack") is True


def test_colima_release_probe_mirrors_release_socket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from devboost.exec.primitives import launchd
    from devboost.modules import _docker_colima

    monkeypatch.setattr(launchd, "DAEMONS_DIR", tmp_path / "LaunchDaemons")
    monkeypatch.setattr(_docker_colima, "DOCKER_SOCK", tmp_path / "docker.sock")
    unloaded = Ctx(os=MAC, ex=FakeExecutor(scripts={"launchctl": Result(113)}))
    assert sw._colima_release_needs_root(unloaded) is False
    (tmp_path / "docker.sock").symlink_to(_docker_colima.Colima().socket_path())
    assert sw._colima_release_needs_root(unloaded) is True
    (tmp_path / "docker.sock").unlink()
    assert sw._colima_release_needs_root(_mac()) is True  # `launchctl print` says loaded
