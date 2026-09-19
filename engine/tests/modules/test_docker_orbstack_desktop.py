from __future__ import annotations

import json
from pathlib import Path

import pytest

from devboost.core.errors import NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.modules import _docker_runtime as rt
from devboost.modules._docker_desktop import DockerDesktop, settings_path, update_settings
from devboost.modules._docker_orbstack import OrbStack
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64")
GIB = 1024**3
SIZE = [
    (("hw.ncpu",), Result(0, stdout="10\n")),
    (("hw.memsize",), Result(0, stdout=f"{24 * GIB}\n")),
]
GC = {"builder": {"gc": {"enabled": True, "defaultKeepStorage": "20GB"}}}


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rt, "_sleep", lambda s: None)


def _ctx(*rules: tuple[tuple[str, ...], Result]) -> Ctx:
    return Ctx(os=MAC, ex=RuleExecutor(rules=list(rules)))


def _calls(ctx: Ctx) -> list[list[str]]:
    return ctx.ex.calls  # type: ignore[attr-defined, no-any-return]


# ── OrbStack ─────────────────────────────────────────────────────────────────
def test_orbstack_install_is_the_cask() -> None:
    ctx = _ctx()
    OrbStack().install(ctx)
    assert _calls(ctx) == [["brew", "install", "--cask", "-y", "--adopt", "orbstack"]]


def test_orbstack_configure_sets_size_and_login_start() -> None:
    ctx = _ctx(*SIZE)
    OrbStack().configure(ctx)
    sets = [c for c in _calls(ctx) if c[:3] == ["orb", "config", "set"]]
    assert sets == [
        ["orb", "config", "set", "cpu", "5"],
        ["orb", "config", "set", "memory_mib", "6144"],
        ["orb", "config", "set", "app.start_at_login", "true"],
    ]


def test_orbstack_before_first_launch_needs_the_user() -> None:
    with pytest.raises(NeedsUser, match="open -a OrbStack"):
        OrbStack().configure(_ctx(*SIZE, (("orb", "config"), Result(1))))
    with pytest.raises(NeedsUser):
        OrbStack().start(_ctx((("orb", "start"), Result(1))))


def test_orbstack_start_stop_autostart() -> None:
    ctx = _ctx()
    OrbStack().start(ctx)
    OrbStack().stop(ctx)
    OrbStack().disable_autostart(ctx)
    OrbStack().release_socket(ctx)
    assert _calls(ctx) == [
        ["orb", "start"],
        ["docker", "--context", "orbstack", "info", "--format", "{{.ServerVersion}}"],
        ["orb", "stop"],
        ["orb", "config", "set", "app.start_at_login", "false"],
    ]


def test_orbstack_daemon_config(tmp_path: Path) -> None:
    ctx = _ctx()
    orb = OrbStack()
    assert orb.daemon_config_path() == tmp_path / ".orbstack" / "config" / "docker.json"
    assert orb.merge_daemon_config(ctx, GC) is True
    assert orb.daemon_config_has(GC) is True
    assert orb.merge_daemon_config(ctx, GC) is False
    orb.restart_engine(ctx)
    assert ["orb", "restart", "docker"] in _calls(ctx)


def test_orbstack_verify() -> None:
    show = (("context", "show"), Result(0, stdout="orbstack\n"))
    assert OrbStack().verify(_ctx(show)) is True
    assert OrbStack().verify(_ctx(show, (("--cask", "orbstack"), Result(1)))) is False


# ── Docker Desktop ───────────────────────────────────────────────────────────
def test_settings_path(tmp_path: Path) -> None:
    assert settings_path() == (
        tmp_path / "Library" / "Group Containers" / "group.com.docker" / "settings-store.json"
    )


def test_update_settings_keeps_the_files_own_key_spelling(tmp_path: Path) -> None:
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"cpus": 2, "AutoStart": False, "Other": 1}), encoding="utf-8")
    assert update_settings(p, {"Cpus": 5, "MemoryMiB": 6144, "AutoStart": True}) is True
    assert json.loads(p.read_text(encoding="utf-8")) == {
        "cpus": 5, "AutoStart": True, "Other": 1, "MemoryMiB": 6144,
    }
    assert update_settings(p, {"Cpus": 5}) is False


def test_desktop_install_frees_the_docker_names_first() -> None:
    ctx = _ctx()  # the docker formula is installed
    DockerDesktop().install(ctx)
    assert _calls(ctx)[-2:] == [
        ["brew", "unlink", "docker", "docker-compose"],
        ["brew", "install", "--cask", "-y", "--adopt", "docker-desktop"],
    ]


def test_desktop_install_without_the_formula() -> None:
    ctx = _ctx((("--versions", "docker"), Result(1)))
    DockerDesktop().install(ctx)
    assert ["brew", "unlink", "docker", "docker-compose"] not in _calls(ctx)


def test_desktop_configure_before_first_launch_needs_the_user() -> None:
    with pytest.raises(NeedsUser, match="open -a Docker"):
        DockerDesktop().configure(_ctx(*SIZE))


def test_desktop_configure_writes_settings_and_restarts_a_running_app() -> None:
    p = settings_path()
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"AutoStart": False}), encoding="utf-8")
    ctx = _ctx(*SIZE)  # engine answers → running
    DockerDesktop().configure(ctx)
    assert json.loads(p.read_text(encoding="utf-8")) == {
        "AutoStart": True, "Cpus": 5, "MemoryMiB": 6144,
    }
    assert ["docker", "desktop", "restart"] in _calls(ctx)


def test_desktop_configure_leaves_a_stopped_app_alone() -> None:
    p = settings_path()
    p.parent.mkdir(parents=True)
    p.write_text("{}", encoding="utf-8")
    ctx = _ctx(*SIZE, (("info",), Result(1)))
    DockerDesktop().configure(ctx)
    assert ["docker", "desktop", "restart"] not in _calls(ctx)


def test_desktop_start_stop_autostart() -> None:
    p = settings_path()
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"AutoStart": True}), encoding="utf-8")
    ctx = _ctx()
    DockerDesktop().start(ctx)
    DockerDesktop().stop(ctx)
    DockerDesktop().disable_autostart(ctx)
    assert ["docker", "desktop", "start"] in _calls(ctx)
    assert ["docker", "desktop", "stop"] in _calls(ctx)
    assert json.loads(p.read_text(encoding="utf-8")) == {"AutoStart": False}
    with pytest.raises(NeedsUser):
        DockerDesktop().start(_ctx((("desktop", "start"), Result(1))))


def test_desktop_daemon_config(tmp_path: Path) -> None:
    ctx = _ctx()
    dd = DockerDesktop()
    assert dd.daemon_config_path() == tmp_path / ".docker" / "daemon.json"
    assert dd.merge_daemon_config(ctx, GC) is True
    assert dd.daemon_config_has(GC) is True
    dd.restart_engine(ctx)
    assert ["docker", "desktop", "restart"] in _calls(ctx)


def test_desktop_verify_uses_desktop_linux_context() -> None:
    show = (("context", "show"), Result(0, stdout="desktop-linux\n"))
    assert DockerDesktop().verify(_ctx(show)) is True
    assert DockerDesktop().verify(_ctx()) is False
