from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from devboost.core import log
from devboost.core.errors import NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load
from devboost.core.userconfig import DockerRuntimeName, set_user_value
from devboost.exec.executor import FakeExecutor
from devboost.exec.primitives import launchd
from devboost.model import Ctx
from devboost.modules import _docker_colima as col
from devboost.modules import _docker_runtime as rt
from devboost.modules import docker as docker_mod
from devboost.modules._docker_colima import Colima
from devboost.modules._docker_desktop import DockerDesktop
from devboost.modules._docker_orbstack import OrbStack
from devboost.modules.docker import BUILDER_GC, Docker, DockerBuildCacheGc
from devboost.modules.macos import Homebrew, Rosetta

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")


class _RecRuntime:
    """A DockerRuntime that records each call as a `rt <name> <method>` command."""

    def __init__(self, name: DockerRuntimeName, *, merged: bool = True) -> None:
        self.name: DockerRuntimeName = name
        self.context_name = f"ctx-{name}"
        self._merged = merged

    def _rec(self, ctx: Ctx, what: str) -> None:
        ctx.ex.run(["rt", self.name, what])

    def daemon_config_path(self) -> Path:
        return Path("/nonexistent")

    def installed(self, ctx: Ctx) -> bool:
        return True

    def install(self, ctx: Ctx) -> None:
        self._rec(ctx, "install")

    def configure(self, ctx: Ctx) -> None:
        self._rec(ctx, "configure")

    def start(self, ctx: Ctx) -> None:
        self._rec(ctx, "start")

    def stop(self, ctx: Ctx) -> None:
        self._rec(ctx, "stop")

    def disable_autostart(self, ctx: Ctx) -> None:
        self._rec(ctx, "disable_autostart")

    def release_socket(self, ctx: Ctx) -> None:
        self._rec(ctx, "release_socket")

    def merge_daemon_config(self, ctx: Ctx, patch: Mapping[str, Any]) -> bool:
        self._rec(ctx, "merge_daemon_config")
        return self._merged

    def daemon_config_has(self, patch: Mapping[str, Any]) -> bool:
        return patch == BUILDER_GC

    def restart_engine(self, ctx: Ctx) -> None:
        self._rec(ctx, "restart_engine")

    def verify(self, ctx: Ctx) -> bool:
        return True


def _use(monkeypatch: pytest.MonkeyPatch, runtime: _RecRuntime) -> None:
    monkeypatch.setattr(docker_mod, "selected_runtime", lambda: runtime)


def test_runtime_for_every_name() -> None:
    assert isinstance(rt.runtime_for("colima"), Colima)
    assert isinstance(rt.runtime_for("orbstack"), OrbStack)
    assert isinstance(rt.runtime_for("docker-desktop"), DockerDesktop)


def test_selected_runtime_follows_the_config() -> None:
    assert isinstance(rt.selected_runtime(), Colima)
    set_user_value("docker_runtime", "orbstack")
    assert isinstance(rt.selected_runtime(), OrbStack)


def test_selected_runtime_env_beats_the_config(monkeypatch: pytest.MonkeyPatch) -> None:
    set_user_value("docker_runtime", "orbstack")
    monkeypatch.setenv("DEVBOOST_DOCKER_RUNTIME", "docker-desktop")
    assert isinstance(rt.selected_runtime(), DockerDesktop)


def test_docker_on_macos_brings_up_the_selected_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _RecRuntime("colima"))
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    Docker().install(ctx)
    assert ctx.ex.calls == [  # type: ignore[attr-defined]
        ["rt", "colima", "install"],
        ["rt", "colima", "configure"],
        ["rt", "colima", "start"],
        ["docker", "context", "use", "ctx-colima"],
    ]
    assert Docker().verify(ctx) is True


def test_docker_warns_about_a_paid_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _RecRuntime("orbstack"))
    warned: list[str] = []
    monkeypatch.setattr(log, "warn", warned.append)
    Docker().install(Ctx(os=MAC, ex=FakeExecutor()))
    assert any("non-commercial" in w for w in warned)


def test_colima_is_not_warned_about(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _RecRuntime("colima"))
    warned: list[str] = []
    monkeypatch.setattr(log, "warn", warned.append)
    Docker().install(Ctx(os=MAC, ex=FakeExecutor()))
    assert warned == []


def test_docker_on_macos_never_touches_systemd(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _RecRuntime("colima"))
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    Docker().install(ctx)
    assert not any("systemctl" in c or "usermod" in c for c in ctx.ex.calls)  # type: ignore[attr-defined]


def test_a_blocked_runtime_step_stops_the_bring_up(monkeypatch: pytest.MonkeyPatch) -> None:
    """Colima's configure may raise NeedsUser (home split, root-owned docker config); it
    reaches the runner unchanged (reported `blocked`) and nothing after it runs."""

    class _Blocked(_RecRuntime):
        def configure(self, ctx: Ctx) -> None:
            raise NeedsUser("colima home split", "unset COLIMA_HOME")

    _use(monkeypatch, _Blocked("colima"))
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    with pytest.raises(NeedsUser):
        Docker().install(ctx)
    assert ctx.ex.calls == [["rt", "colima", "install"]]  # type: ignore[attr-defined]


def test_build_gc_on_macos_merges_and_restarts_only_on_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use(monkeypatch, _RecRuntime("colima", merged=True))
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    DockerBuildCacheGc().install(ctx)
    assert ctx.ex.calls == [  # type: ignore[attr-defined]
        ["rt", "colima", "merge_daemon_config"],
        ["rt", "colima", "restart_engine"],
    ]
    assert DockerBuildCacheGc().verify(ctx) is True
    _use(monkeypatch, _RecRuntime("colima", merged=False))
    idle = Ctx(os=MAC, ex=FakeExecutor())
    DockerBuildCacheGc().install(idle)
    assert idle.ex.calls == [["rt", "colima", "merge_daemon_config"]]  # type: ignore[attr-defined]


def test_linux_docker_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(docker_mod, "selected_runtime", lambda: pytest.fail("macOS only"))
    ctx = Ctx(os=FEDORA, ex=FakeExecutor(present={"dockerd"}))
    Docker().install(ctx)
    assert ["sudo", "systemctl", "enable", "--now", "docker.service"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_both_plan_on_macos_and_fedora(tmp_path: Path) -> None:
    modules = load()
    for os_info in (MAC, FEDORA):
        plan = build_plan(["docker", "docker-build-gc"], modules, os_info,
                          gpu_marker=tmp_path / "none")
        assert {p.name: p.skip_reason for p in plan} == {
            "docker": None, "docker-build-gc": None,
        }


# ── M4-D2 / M4-D9: the macOS edges ─────────────────────────────────────────────
def test_docker_needs_homebrew_and_orders_after_rosetta() -> None:
    assert Homebrew in Docker.requires
    assert Rosetta in Docker.after  # --vz-rosetta is decided when the VM is first created


def test_both_macos_strategies_declare_brew() -> None:
    assert getattr(Docker.per_os.macos, "uses_brew", False) is True
    assert getattr(DockerBuildCacheGc.per_os.macos, "uses_brew", False) is True


# ── M4-D5: sudo only for Colima's socket LaunchDaemon ──────────────────────────
def _probe(monkeypatch: pytest.MonkeyPatch, current: bool) -> list[Ctx]:
    seen: list[Ctx] = []

    def fake(ctx: Ctx) -> bool:
        seen.append(ctx)
        return current

    monkeypatch.setattr(col, "socket_daemon_current", fake)
    return seen


def test_docker_is_flagged_for_the_macos_sudo_precheck() -> None:
    assert Docker.needs_sudo_on_macos is True


def test_colima_with_a_current_socket_daemon_needs_no_sudo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use(monkeypatch, _RecRuntime("colima"))
    seen = _probe(monkeypatch, current=True)
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    assert Docker().sudo_needed(ctx) is False
    assert len(seen) == 1
    assert ctx.ex.calls == []  # type: ignore[attr-defined]  # a read-only probe


def test_colima_without_a_current_socket_daemon_needs_sudo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use(monkeypatch, _RecRuntime("colima"))
    _probe(monkeypatch, current=False)
    assert Docker().sudo_needed(Ctx(os=MAC, ex=FakeExecutor())) is True


def test_force_with_colima_needs_sudo(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _RecRuntime("colima"))
    _probe(monkeypatch, current=True)
    assert Docker().sudo_needed(Ctx(os=MAC, ex=FakeExecutor(), force=True)) is True


@pytest.mark.parametrize("name", ["orbstack", "docker-desktop"])
@pytest.mark.parametrize("force", [False, True])
def test_orbstack_and_docker_desktop_never_need_sudo(
    monkeypatch: pytest.MonkeyPatch, name: DockerRuntimeName, force: bool
) -> None:
    _use(monkeypatch, _RecRuntime(name))
    seen = _probe(monkeypatch, current=False)
    assert Docker().sudo_needed(Ctx(os=MAC, ex=FakeExecutor(), force=force)) is False
    assert seen == []


def test_sudo_probe_on_a_fresh_mac_uses_the_real_colima_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Default runtime (Colima), no daemon plist yet → the first run asks for sudo."""
    monkeypatch.setattr(launchd, "DAEMONS_DIR", tmp_path / "LaunchDaemons")
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    assert Docker().sudo_needed(ctx) is True
    assert not any(c[0] == "sudo" for c in ctx.ex.calls)  # type: ignore[attr-defined]
