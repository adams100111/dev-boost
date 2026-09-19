from __future__ import annotations

import json

import pytest

from devboost.core.errors import UnsupportedOS
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import pkg
from devboost.model import Ctx
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")


def test_brew_services_argv_and_env() -> None:
    ex = RuleExecutor()
    assert pkg.brew_services(Ctx(os=MAC, ex=ex), "start", "colima").ok
    assert ex.calls == [["brew", "services", "start", "colima"]]
    assert ex.envs[0] == pkg.BREW_ENV


def test_brew_services_returns_failure_without_raising() -> None:
    ex = RuleExecutor(rules=[(("services",), Result(1))])
    assert pkg.brew_services(Ctx(os=MAC, ex=ex), "stop", "colima").ok is False


def test_service_running_reads_brew_json() -> None:
    running = json.dumps([{"name": "colima", "running": True, "loaded": True}])
    ex = RuleExecutor(rules=[(("info", "--json"), Result(0, stdout=running))])
    assert pkg.service_running(Ctx(os=MAC, ex=ex), "colima") is True
    assert ex.calls == [["brew", "services", "info", "--json", "colima"]]


@pytest.mark.parametrize(
    ("stdout", "code"),
    [
        (json.dumps([{"name": "colima", "running": False}]), 0),
        (json.dumps([{"name": "other", "running": True}]), 0),
        ("not json", 0),
        ("", 1),
    ],
)
def test_service_not_running(stdout: str, code: int) -> None:
    ex = RuleExecutor(rules=[(("info",), Result(code, stdout=stdout))])
    assert pkg.service_running(Ctx(os=MAC, ex=ex), "colima") is False


def test_link_and_unlink_argv() -> None:
    ex = RuleExecutor()
    ctx = Ctx(os=MAC, ex=ex)
    pkg.brew_link(ctx, "docker", "docker-compose", overwrite=True)
    pkg.brew_unlink(ctx, "docker")
    pkg.brew_link(ctx, "docker")
    assert ex.calls == [
        ["brew", "link", "--overwrite", "docker", "docker-compose"],
        ["brew", "unlink", "docker"],
        ["brew", "link", "docker"],
    ]


def test_service_helpers_refuse_off_macos() -> None:
    ctx = Ctx(os=FEDORA, ex=FakeExecutor())
    with pytest.raises(UnsupportedOS):
        pkg.brew_services(ctx, "start", "colima")
    with pytest.raises(UnsupportedOS):
        pkg.service_running(ctx, "colima")
