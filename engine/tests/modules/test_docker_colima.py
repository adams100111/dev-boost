from __future__ import annotations

import json
import os
import plistlib
from pathlib import Path

import pytest
import yaml

from devboost.core.errors import ConfigError, InstallError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.exec.primitives import launchd
from devboost.model import Ctx
from devboost.modules import _docker_colima as col
from devboost.modules import _docker_runtime as rt
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64")
GIB = 1024**3
RUNNING = (("info", "--json"), Result(0, stdout=json.dumps([{"name": "colima", "running": True}])))
STOPPED = (("info", "--json"), Result(0, stdout=json.dumps([{"name": "colima", "running": False}])))
SIZE = [
    (("hw.ncpu",), Result(0, stdout="10\n")),
    (("hw.memsize",), Result(0, stdout=f"{24 * GIB}\n")),
]


@pytest.fixture(autouse=True)
def _seams(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launchd, "DAEMONS_DIR", tmp_path / "LaunchDaemons")
    monkeypatch.setattr(col, "DOCKER_SOCK", tmp_path / "run" / "docker.sock")
    monkeypatch.setattr(rt, "_sleep", lambda s: None)


def _ctx(*rules: tuple[tuple[str, ...], Result]) -> Ctx:
    return Ctx(os=MAC, ex=RuleExecutor(rules=list(rules)))


def _calls(ctx: Ctx) -> list[list[str]]:
    return ctx.ex.calls  # type: ignore[attr-defined, no-any-return]


# ── config dir (D10) ─────────────────────────────────────────────────────────
def test_home_uses_xdg_when_set(tmp_path: Path) -> None:
    assert col.colima_home() == tmp_path / ".config" / "colima"  # conftest sets XDG


def test_home_prefers_an_existing_dot_colima(tmp_path: Path) -> None:
    (tmp_path / ".colima").mkdir()
    assert col.colima_home() == tmp_path / ".colima"


def test_home_prefers_an_existing_colima_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "ch").mkdir()
    monkeypatch.setenv("COLIMA_HOME", str(tmp_path / "ch"))
    assert col.colima_home() == tmp_path / "ch"


def test_home_without_xdg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME")
    assert col.colima_home() == tmp_path / ".colima"  # macOS fallback
    (tmp_path / ".config" / "colima").mkdir(parents=True)
    assert col.colima_home() == tmp_path / ".config" / "colima"  # launchd's view


def test_ensure_home_pins_the_xdg_dir(tmp_path: Path) -> None:
    assert col.ensure_colima_home() == tmp_path / ".config" / "colima"
    assert (tmp_path / ".config" / "colima").is_dir()


def test_ensure_home_keeps_an_existing_dot_colima(tmp_path: Path) -> None:
    (tmp_path / ".colima").mkdir()
    assert col.ensure_colima_home() == tmp_path / ".colima"
    assert not (tmp_path / ".config" / "colima").exists()


# ── install ──────────────────────────────────────────────────────────────────
def test_install_brews_only_missing_formulae_and_adds_the_plugin_dir(tmp_path: Path) -> None:
    ctx = _ctx(
        (("--versions", "colima"), Result(1)),
        (("--versions", "docker-buildx"), Result(1)),
        (("--cask", "docker-desktop"), Result(1)),
    )
    cfg = tmp_path / ".docker" / "config.json"
    cfg.parent.mkdir()
    cfg.write_text(json.dumps({"cliPluginsExtraDirs": ["/x"], "auths": {}}), encoding="utf-8")
    col.Colima().install(ctx)
    assert ["brew", "install", "--formula", "-y", "colima", "docker-buildx"] in _calls(ctx)
    assert not any(c[:2] == ["brew", "link"] for c in _calls(ctx))
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["cliPluginsExtraDirs"] == ["/x", col.CLI_PLUGINS_DIR]
    assert data["auths"] == {}


def test_install_takes_the_docker_names_back_from_docker_desktop() -> None:
    ctx = _ctx()  # everything "installed", including the docker-desktop cask
    col.Colima().install(ctx)
    assert ["brew", "link", "--overwrite", "docker", "docker-compose"] in _calls(ctx)
    assert not any(c[:2] == ["brew", "install"] for c in _calls(ctx))


def test_installed_needs_every_formula() -> None:
    assert col.Colima().installed(_ctx()) is True
    assert col.Colima().installed(_ctx((("--versions", "docker-compose"), Result(1)))) is False


# ── configure ────────────────────────────────────────────────────────────────
def test_start_args_with_and_without_rosetta() -> None:
    assert col.Colima().start_args(_ctx(*SIZE)) == [
        "--vm-type", "vz", "--vz-rosetta", "--mount-type", "virtiofs",
        "--cpu", "5", "--memory", "6", "--disk", "100",
    ]
    no_rosetta = _ctx(*SIZE, (("-x86_64",), Result(1)))
    assert "--vz-rosetta" not in col.Colima().start_args(no_rosetta)


def test_first_configure_creates_the_vm_then_hands_it_to_brew_services(tmp_path: Path) -> None:
    ctx = _ctx(*SIZE, (("launchctl", "print"), Result(1)))
    col.Colima().configure(ctx)
    calls = _calls(ctx)
    start = calls.index(["colima", "start", *col.Colima().start_args(_ctx(*SIZE))])
    assert calls[start + 1] == ["colima", "stop"]
    home = tmp_path / ".config" / "colima"
    plist = tmp_path / "LaunchDaemons" / f"{col.SOCKET_LABEL}.plist"
    assert ["sudo", "tee", str(plist)] in calls
    assert ["sudo", "launchctl", "bootstrap", "system", str(plist)] in calls
    tee = calls.index(["sudo", "tee", str(plist)])
    body = ctx.ex.stdins[tee]  # type: ignore[attr-defined]
    assert plistlib.loads(body.encode("utf-8"))["ProgramArguments"] == [
        "/bin/ln", "-sf", str(home / "default" / "docker.sock"), str(col.DOCKER_SOCK)
    ]


def test_configure_does_not_recreate_an_existing_vm(tmp_path: Path) -> None:
    yaml_path = tmp_path / ".config" / "colima" / "default" / "colima.yaml"
    yaml_path.parent.mkdir(parents=True)
    yaml_path.write_text("cpu: 3\n", encoding="utf-8")
    ctx = _ctx()
    col.Colima().configure(ctx)
    assert not any(c[:2] == ["colima", "start"] for c in _calls(ctx))


def test_configure_raises_when_the_vm_cannot_be_created() -> None:
    with pytest.raises(InstallError, match="colima start"):
        col.Colima().configure(_ctx(*SIZE, (("colima", "start"), Result(1))))


# ── start / stop ─────────────────────────────────────────────────────────────
def test_start_registers_the_service_when_not_running() -> None:
    ctx = _ctx(STOPPED)
    col.Colima().start(ctx)
    assert ["brew", "services", "start", "colima"] in _calls(ctx)
    assert ["docker", "--context", "colima", "info", "--format", "{{.ServerVersion}}"] in _calls(
        ctx
    )


def test_start_leaves_a_running_service_alone() -> None:
    ctx = _ctx(RUNNING)
    col.Colima().start(ctx)
    assert ["brew", "services", "start", "colima"] not in _calls(ctx)


def test_start_raises_when_brew_services_fails() -> None:
    with pytest.raises(InstallError, match="brew services start colima"):
        col.Colima().start(_ctx(STOPPED, (("services", "start"), Result(1))))


def test_stop_and_disable_autostart() -> None:
    ctx = _ctx()
    col.Colima().stop(ctx)
    col.Colima().disable_autostart(ctx)
    assert _calls(ctx) == [
        ["brew", "services", "stop", "colima"],
        ["colima", "stop"],
        ["brew", "services", "stop", "colima"],
    ]


# ── socket ───────────────────────────────────────────────────────────────────
def test_release_socket_removes_the_daemon_and_our_link(tmp_path: Path) -> None:
    col.DOCKER_SOCK.parent.mkdir(parents=True)
    os.symlink(col.Colima().socket_path(), col.DOCKER_SOCK)
    ctx = _ctx()
    col.Colima().release_socket(ctx)
    assert ["sudo", "launchctl", "bootout", f"system/{col.SOCKET_LABEL}"] in _calls(ctx)
    assert ["sudo", "rm", "-f", str(col.DOCKER_SOCK)] in _calls(ctx)


def test_release_socket_keeps_someone_elses_link(tmp_path: Path) -> None:
    col.DOCKER_SOCK.parent.mkdir(parents=True)
    os.symlink(tmp_path / "orbstack.sock", col.DOCKER_SOCK)
    ctx = _ctx()
    col.Colima().release_socket(ctx)
    assert ["sudo", "rm", "-f", str(col.DOCKER_SOCK)] not in _calls(ctx)


# ── daemon config (colima.yaml `docker:`) ─────────────────────────────────────
GC = {"builder": {"gc": {"enabled": True, "defaultKeepStorage": "20GB"}}}


def _yaml(tmp_path: Path, text: str) -> Path:
    p = tmp_path / ".config" / "colima" / "default" / "colima.yaml"
    p.parent.mkdir(parents=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_merge_daemon_config_keeps_other_keys(tmp_path: Path) -> None:
    p = _yaml(tmp_path, "cpu: 5\ndocker:\n  log-driver: json-file\n")
    assert col.Colima().merge_daemon_config(_ctx(), GC) is True
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    assert data["cpu"] == 5
    assert data["docker"] == {"log-driver": "json-file", **GC}
    assert col.Colima().daemon_config_has(GC) is True
    assert col.Colima().merge_daemon_config(_ctx(), GC) is False  # idempotent


def test_daemon_config_has_is_false_without_the_key(tmp_path: Path) -> None:
    _yaml(tmp_path, "docker: {}\n")
    assert col.Colima().daemon_config_has(GC) is False


def test_invalid_yaml_is_a_config_error(tmp_path: Path) -> None:
    _yaml(tmp_path, "docker: [unclosed\n")
    with pytest.raises(ConfigError, match="invalid YAML"):
        col.Colima().daemon_config_has(GC)


def test_restart_engine_only_when_the_service_runs() -> None:
    ctx = _ctx(RUNNING)
    col.Colima().restart_engine(ctx)
    assert ["brew", "services", "restart", "colima"] in _calls(ctx)
    idle = _ctx(STOPPED)
    col.Colima().restart_engine(idle)
    assert ["brew", "services", "restart", "colima"] not in _calls(idle)


def test_verify() -> None:
    show = (("context", "show"), Result(0, stdout="colima\n"))
    assert col.Colima().verify(_ctx(show)) is True
    assert col.Colima().verify(_ctx(show, (("--versions", "colima"), Result(1)))) is False
    assert col.Colima().verify(_ctx((("context", "show"), Result(0, stdout="default")))) is False


# ── additions beyond the brief ───────────────────────────────────────────────
def test_no_vz_rosetta_on_a_macos_without_full_rosetta() -> None:
    """M4-D8: the gate is ``rosetta_usable`` — support by this macOS AND installed."""
    mac28 = OsInfo("macos", "macos", "aarch64", version_id="28.0")
    ctx = Ctx(os=mac28, ex=RuleExecutor(rules=list(SIZE)))
    args = col.Colima().start_args(ctx)
    assert "--vz-rosetta" not in args
    assert args[:2] == ["--vm-type", "vz"]


def test_colima_satisfies_the_runtime_protocol() -> None:
    runtime: rt.DockerRuntime = col.Colima()
    assert runtime.name == "colima"
    assert runtime.context_name == "colima"


def test_socket_daemon_current_is_a_read_only_probe(tmp_path: Path) -> None:
    """For Docker.sudo_needed (M4-D5): missing, differing or unloaded → not current."""
    loaded = (("launchctl", "print"), Result(0))
    assert col.socket_daemon_current(_ctx(loaded)) is False  # no plist yet
    ctx = _ctx((("launchctl", "print"), Result(1)))
    (tmp_path / ".config" / "colima" / "default").mkdir(parents=True)
    (tmp_path / ".config" / "colima" / "default" / "colima.yaml").write_text("cpu: 5\n")
    col.Colima().configure(ctx)  # the fake `sudo tee` writes nothing; write the file by hand
    plist = tmp_path / "LaunchDaemons" / f"{col.SOCKET_LABEL}.plist"
    plist.parent.mkdir(parents=True)
    tee = _calls(ctx).index(["sudo", "tee", str(plist)])
    plist.write_text(ctx.ex.stdins[tee], encoding="utf-8")  # type: ignore[attr-defined]
    probe = _ctx(loaded)
    assert col.socket_daemon_current(probe) is True
    assert not any(c[0] == "sudo" for c in _calls(probe))
    assert col.socket_daemon_current(_ctx((("launchctl", "print"), Result(1)))) is False
    plist.write_text(plist.read_text(encoding="utf-8").replace("-sf", "-s"), encoding="utf-8")
    assert col.socket_daemon_current(_ctx(loaded)) is False
