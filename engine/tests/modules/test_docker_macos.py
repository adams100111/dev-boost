from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

from devboost.core import log
from devboost.core.errors import NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load
from devboost.core.userconfig import DockerRuntimeName, set_user_value
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import launchd
from devboost.model import Ctx
from devboost.modules import _docker_colima as col
from devboost.modules import _docker_desktop as dd
from devboost.modules import _docker_runtime as rt
from devboost.modules import docker as docker_mod
from devboost.modules._docker_colima import Colima
from devboost.modules._docker_desktop import DockerDesktop
from devboost.modules._docker_orbstack import OrbStack
from devboost.modules.docker import Docker, DockerBuildCacheGc
from devboost.modules.macos import Homebrew, Rosetta

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")


class _RecRuntime:
    """A DockerRuntime that records each call as a `rt <name> <method>` command."""

    def __init__(
        self, name: DockerRuntimeName, *, merged: bool = True, has: bool = False
    ) -> None:
        self.name: DockerRuntimeName = name
        self.context_name = f"ctx-{name}"
        self._merged = merged
        self._has = has
        self.asked: list[Mapping[str, Any]] = []

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
        self.asked.append(patch)
        return self._has

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
        ["docker", "context", "show"],
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
    runtime = _RecRuntime("colima", merged=True)
    _use(monkeypatch, runtime)
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    DockerBuildCacheGc().install(ctx)
    assert ctx.ex.calls == [  # type: ignore[attr-defined]
        ["rt", "colima", "merge_daemon_config"],
        ["rt", "colima", "restart_engine"],
    ]
    assert DockerBuildCacheGc().verify(ctx) is False
    # "Capped" means builder.gc.enabled only, as on Linux (the user's cap is theirs).
    assert runtime.asked and all(
        a == {"builder": {"gc": {"enabled": True}}} for a in runtime.asked
    )
    _use(monkeypatch, _RecRuntime("colima", has=True))
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
def test_other_runtimes_never_ask_the_colima_probe(
    monkeypatch: pytest.MonkeyPatch, name: DockerRuntimeName
) -> None:
    _use(monkeypatch, _RecRuntime(name))
    seen = _probe(monkeypatch, current=False)
    # Desktop's cask counts as installed here (`brew list --cask` succeeds): no links to make.
    assert Docker().sudo_needed(Ctx(os=MAC, ex=FakeExecutor())) is False
    assert seen == []


def test_sudo_probe_on_a_fresh_mac_uses_the_real_colima_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Default runtime (Colima), no daemon plist yet → the first run asks for sudo."""
    monkeypatch.setattr(launchd, "DAEMONS_DIR", tmp_path / "LaunchDaemons")
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    assert Docker().sudo_needed(ctx) is True
    assert not any(c[0] == "sudo" for c in ctx.ex.calls)  # type: ignore[attr-defined]


@pytest.mark.parametrize("force", [False, True])
def test_build_gc_leaves_an_existing_cap_alone(
    monkeypatch: pytest.MonkeyPatch, force: bool
) -> None:
    _use(monkeypatch, _RecRuntime("colima", has=True))
    ctx = Ctx(os=MAC, ex=FakeExecutor(), force=force)
    DockerBuildCacheGc().install(ctx)
    assert ctx.ex.calls == []  # type: ignore[attr-defined]


# ── fix round 1, I2: the real runtimes deep-merge and keep the user's builder keys ─────
_USER_BUILDER = {
    "entitlements": {"network-host": True},
    "gc": {"policy": [{"keepStorage": "5GB", "filter": ["unused-for=48h"]}]},
}


def _runtime_file(name: str, home: Path) -> Path:
    return {
        "colima": home / ".config" / "colima" / "default" / "colima.yaml",
        "orbstack": home / ".orbstack" / "config" / "docker.json",
        "docker-desktop": home / ".docker" / "daemon.json",
    }[name]


def _write_user_config(name: str, path: Path, builder: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if name == "colima":
        path.write_text(yaml.safe_dump({"cpu": 4, "docker": {"builder": builder}}),
                        encoding="utf-8")
    else:
        path.write_text(json.dumps({"log-level": "warn", "builder": builder}),
                        encoding="utf-8")


def _builder(name: str, path: Path) -> Any:
    if name == "colima":
        return yaml.safe_load(path.read_text(encoding="utf-8"))["docker"]["builder"]
    return json.loads(path.read_text(encoding="utf-8"))["builder"]


@pytest.fixture
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rt, "_sleep", lambda s: None)


@pytest.mark.usefixtures("_no_sleep")
@pytest.mark.parametrize("name", ["colima", "orbstack", "docker-desktop"])
def test_build_gc_keeps_the_users_builder_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str
) -> None:
    monkeypatch.setenv("DEVBOOST_DOCKER_RUNTIME", name)
    path = _runtime_file(name, tmp_path)
    _write_user_config(name, path, _USER_BUILDER)
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    assert DockerBuildCacheGc().verify(ctx) is False
    DockerBuildCacheGc().install(ctx)
    assert _builder(name, path) == {
        "entitlements": {"network-host": True},
        "gc": {
            "policy": [{"keepStorage": "5GB", "filter": ["unused-for=48h"]}],
            "enabled": True,
            "defaultKeepStorage": "20GB",
        },
    }
    assert DockerBuildCacheGc().verify(ctx) is True


@pytest.mark.usefixtures("_no_sleep")
@pytest.mark.parametrize("name", ["colima", "orbstack", "docker-desktop"])
def test_build_gc_accepts_the_users_own_cap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str
) -> None:
    monkeypatch.setenv("DEVBOOST_DOCKER_RUNTIME", name)
    path = _runtime_file(name, tmp_path)
    _write_user_config(name, path, {"gc": {"enabled": True, "defaultKeepStorage": "50GB"}})
    before = path.read_bytes()
    ctx = Ctx(os=MAC, ex=FakeExecutor(), force=True)
    assert DockerBuildCacheGc().verify(ctx) is True
    DockerBuildCacheGc().install(ctx)
    assert path.read_bytes() == before
    assert ctx.ex.calls == []  # type: ignore[attr-defined]  # no restart either


# ── fix round 1, M2: a user file is never written as root ─────────────────────
@pytest.mark.skipif(os.geteuid() == 0, reason="root can write anything")
@pytest.mark.parametrize("name", ["orbstack", "docker-desktop"])
def test_an_unwritable_daemon_config_needs_the_user(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str
) -> None:
    monkeypatch.setenv("DEVBOOST_DOCKER_RUNTIME", name)
    path = _runtime_file(name, tmp_path)
    _write_user_config(name, path, {})
    path.chmod(0o444)
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    try:
        with pytest.raises(NeedsUser, match=str(path)):
            DockerBuildCacheGc().install(ctx)
    finally:
        path.chmod(0o644)
    assert not any(c[0] == "sudo" for c in ctx.ex.calls)  # type: ignore[attr-defined]


@pytest.mark.skipif(os.geteuid() == 0, reason="root can write anything")
def test_an_unwritable_config_dir_needs_the_user(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DEVBOOST_DOCKER_RUNTIME", "docker-desktop")
    locked = tmp_path / ".docker"
    locked.mkdir()
    locked.chmod(0o555)
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    try:
        with pytest.raises(NeedsUser, match=str(locked)):
            DockerBuildCacheGc().install(ctx)
    finally:
        locked.chmod(0o755)
    assert not (locked / "daemon.json").exists()
    assert not any(c[0] == "sudo" for c in ctx.ex.calls)  # type: ignore[attr-defined]


# ── fix round 1, M4-D5a / I1: --force counts everywhere; Desktop links into /usr/local ──
@pytest.mark.parametrize("name", ["colima", "orbstack", "docker-desktop"])
def test_force_needs_sudo_for_every_runtime(
    monkeypatch: pytest.MonkeyPatch, name: DockerRuntimeName
) -> None:
    _use(monkeypatch, _RecRuntime(name))
    _probe(monkeypatch, current=True)
    assert Docker().sudo_needed(Ctx(os=MAC, ex=FakeExecutor(), force=True)) is True


def _link_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, writable: bool) -> None:
    root = tmp_path / "usr-local"
    root.mkdir()
    if not writable:
        root.chmod(0o555)
    monkeypatch.setattr(dd, "LINK_DIRS", (root / "bin", root / "cli-plugins"))


@pytest.mark.skipif(os.geteuid() == 0, reason="root can write anything")
def test_desktop_cask_linking_into_a_root_owned_usr_local_needs_sudo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _use(monkeypatch, _RecRuntime("docker-desktop"))
    _link_dirs(monkeypatch, tmp_path, writable=False)
    missing = Ctx(os=MAC, ex=FakeExecutor(scripts={"brew": Result(1)}))
    try:
        assert Docker().sudo_needed(missing) is True
        present = Ctx(os=MAC, ex=FakeExecutor())  # `brew list --cask` succeeds
        assert Docker().sudo_needed(present) is False
    finally:
        (tmp_path / "usr-local").chmod(0o755)
    probe = ["brew", "list", "--cask", "--versions", "docker-desktop"]
    assert probe in missing.ex.calls  # type: ignore[attr-defined]
    assert not any(c[0] == "sudo" for c in missing.ex.calls)  # type: ignore[attr-defined]


def test_desktop_cask_linking_into_writable_dirs_needs_no_sudo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _use(monkeypatch, _RecRuntime("docker-desktop"))
    _link_dirs(monkeypatch, tmp_path, writable=True)
    missing = Ctx(os=MAC, ex=FakeExecutor(scripts={"brew": Result(1)}))
    assert Docker().sudo_needed(missing) is False


def test_orbstack_needs_no_sudo_without_force(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _RecRuntime("orbstack"))
    ctx = Ctx(os=MAC, ex=FakeExecutor(scripts={"brew": Result(1)}))
    assert Docker().sudo_needed(ctx) is False
    assert ctx.ex.calls == []  # type: ignore[attr-defined]


# ── fix round 1, M1: no "current" before Colima's home exists ─────────────────────
def test_colima_probe_needs_sudo_until_the_home_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(launchd, "DAEMONS_DIR", tmp_path / "LaunchDaemons")
    home = col.colima_home()
    assert not home.exists()
    plist = launchd.DAEMONS_DIR / f"{col.SOCKET_LABEL}.plist"
    plist.parent.mkdir(parents=True)
    plist.write_bytes(launchd._plist(
        col.SOCKET_LABEL, col.socket_daemon_args(), start_interval=None,
        start_calendar=None, run_at_load=True, env=None,
    ))
    ctx = Ctx(os=MAC, ex=FakeExecutor())  # `launchctl print` succeeds: loaded
    assert col.socket_daemon_current(ctx) is False
    home.mkdir(parents=True)
    assert col.socket_daemon_current(ctx) is True


# ── fix round 1, M3: the docker context ─────────────────────────────────────────
def _ctx_showing(current: str) -> Ctx:
    return Ctx(os=MAC, ex=FakeExecutor(scripts={"docker": Result(0, stdout=f"{current}\n")}))


def _uses(ctx: Ctx) -> list[list[str]]:
    calls: list[list[str]] = ctx.ex.calls  # type: ignore[attr-defined]
    return [c for c in calls if c[:3] == ["docker", "context", "use"]]


def test_context_already_current_is_not_switched(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _RecRuntime("colima"))
    warned: list[str] = []
    monkeypatch.setattr(log, "warn", warned.append)
    ctx = _ctx_showing("ctx-colima")
    Docker().install(ctx)
    assert _uses(ctx) == []
    assert warned == []


def test_docker_context_env_is_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _RecRuntime("colima"))
    monkeypatch.setenv("DOCKER_CONTEXT", "work-remote")
    warned: list[str] = []
    monkeypatch.setattr(log, "warn", warned.append)
    ctx = _ctx_showing("work-remote")
    Docker().install(ctx)
    assert _uses(ctx) == []
    assert any("DOCKER_CONTEXT=work-remote" in w for w in warned)


def test_switching_away_from_a_users_context_warns(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _RecRuntime("colima"))
    warned: list[str] = []
    monkeypatch.setattr(log, "warn", warned.append)
    ctx = _ctx_showing("my-remote")
    Docker().install(ctx)
    assert _uses(ctx) == [["docker", "context", "use", "ctx-colima"]]
    assert any("my-remote" in w for w in warned)


def test_switching_from_the_default_context_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _RecRuntime("colima"))
    warned: list[str] = []
    monkeypatch.setattr(log, "warn", warned.append)
    ctx = _ctx_showing("default")
    Docker().install(ctx)
    assert _uses(ctx) == [["docker", "context", "use", "ctx-colima"]]
    assert warned == []


# ── fix round 1, M4 ─────────────────────────────────────────────────────────────
def test_docker_warns_about_docker_desktops_licence(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _RecRuntime("docker-desktop"))
    warned: list[str] = []
    monkeypatch.setattr(log, "warn", warned.append)
    Docker().install(Ctx(os=MAC, ex=FakeExecutor()))
    assert any("250 employees" in w for w in warned)
