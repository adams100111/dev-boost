"""Final review I1: a vendor-installed OrbStack.app / Docker.app counts as installed.

The app bundle constants are neutralised by conftest (HOST_APP_PATHS); each test that needs
an app present creates a bundle under tmp_path and points the constant at it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from devboost.cli import doctor
from devboost.core import log
from devboost.core.errors import PresentUnmanaged
from devboost.core.osinfo import OsInfo
from devboost.core.userconfig import set_user_value
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.modules import _docker_desktop as dd
from devboost.modules import _docker_orbstack as orb
from devboost.modules import _docker_runtime as rt
from devboost.modules import _docker_switch as sw
from devboost.modules import docker as docker_mod
from devboost.modules.docker import Docker
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64")
#: `brew list --cask --versions <cask>` fails: brew does not manage either app.
NO_CASKS = [(("list", "--cask", "orbstack"), Result(1)),
            (("list", "--cask", "docker-desktop"), Result(1))]


@pytest.fixture(autouse=True)
def _seams(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rt, "_sleep", lambda s: None)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)


def _app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, module: object, name: str) -> Path:
    bundle = tmp_path / "Applications" / name
    bundle.mkdir(parents=True)
    monkeypatch.setattr(module, "APP", bundle)
    return bundle


def _ctx(*rules: tuple[tuple[str, ...], Result]) -> Ctx:
    return Ctx(os=MAC, ex=RuleExecutor(rules=[*rules, *NO_CASKS]))


def test_the_app_constants_are_the_vendor_bundles() -> None:
    # conftest points them into tmp_path; the names are what the vendors install.
    assert orb.APP.name == "OrbStack.app" and dd.APP.name == "Docker.app"


@pytest.mark.parametrize(("module", "bundle", "cls"), [
    (orb, "OrbStack.app", orb.OrbStack), (dd, "Docker.app", dd.DockerDesktop),
])
def test_a_hand_installed_app_counts_as_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, module: object, bundle: str, cls: type,
) -> None:
    runtime = cls()
    assert runtime.installed(_ctx()) is False  # neither cask nor app
    _app(tmp_path, monkeypatch, module, bundle)
    assert runtime.installed(_ctx()) is True


def test_hand_installed_orbstack_verifies_after_a_working_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app(tmp_path, monkeypatch, orb, "OrbStack.app")
    ctx = _ctx((("context", "show"), Result(0, stdout="orbstack\n")))
    assert orb.OrbStack().verify(ctx) is True


def test_a_hand_installed_docker_desktop_is_stopped_by_a_switch_to_colima(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app(tmp_path, monkeypatch, dd, "Docker.app")
    set_user_value("docker_runtime", "docker-desktop")
    names = [r.name for r in sw.to_stop(_ctx(), "colima")]
    assert "docker-desktop" in names


def test_install_configures_a_hand_installed_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`devboost install` with docker_runtime=orbstack and a vendor OrbStack.app, run
    without sudo: install_cask raises PresentUnmanaged, and the bring-up carries on."""
    _app(tmp_path, monkeypatch, orb, "OrbStack.app")
    set_user_value("docker_runtime", "orbstack")
    skipped: list[str] = []
    monkeypatch.setattr(log, "skip", skipped.append)

    def _by_hand(self: orb.OrbStack, ctx: Ctx) -> None:
        raise PresentUnmanaged("orbstack")

    monkeypatch.setattr(orb.OrbStack, "install", _by_hand)
    ctx = _ctx((("context", "show"), Result(0, stdout="colima\n")))
    Docker().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["orb", "config", "set", "app.start_at_login", "true"] in calls
    assert ["orb", "start"] in calls
    assert ["docker", "context", "use", "orbstack"] in calls
    assert any("orbstack" in s for s in skipped)


def test_macdocker_install_catches_present_unmanaged(monkeypatch: pytest.MonkeyPatch) -> None:
    order: list[str] = []

    class _Rt(orb.OrbStack):
        def install(self, ctx: Ctx) -> None:
            order.append("install")
            raise PresentUnmanaged("OrbStack.app")

        def configure(self, ctx: Ctx) -> None:
            order.append("configure")

        def start(self, ctx: Ctx) -> None:
            order.append("start")

    monkeypatch.setattr(docker_mod, "selected_runtime", lambda: _Rt())
    monkeypatch.setattr(docker_mod, "_point_cli_at", lambda ctx, r: order.append("context"))
    Docker().install(_ctx())
    assert order == ["install", "configure", "start", "context"]


def test_doctor_and_docker_use_agree_on_a_hand_installed_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _app(tmp_path, monkeypatch, orb, "OrbStack.app")
    set_user_value("docker_runtime", "orbstack")
    ctx = _ctx((("context", "show"), Result(0, stdout="orbstack\n")))
    check = doctor._docker_runtime_check(ctx)
    assert "not installed" not in check.detail
    assert check.ok is True and "healthy" in check.detail
    assert sw._verify(ctx, "docker") is True
