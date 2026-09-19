"""M4-owned modules stop with a clear `blocked` on a Mac instead of running Linux commands."""

from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.errors import NeedsUser
from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load
from devboost.core.runner import run_plan
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx, Module
from devboost.modules._pending import MacosPending
from devboost.modules.apps import ObsidianSync
from devboost.modules.dev_hygiene import AspireGc
from devboost.modules.docker import Docker, DockerBuildCacheGc
from devboost.modules.server import ResticB2
from devboost.modules.system import ResticBackup
from tests.core.test_macos_contract import resolvable_on_macos

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
PENDING: list[type[Module]] = [
    Docker, DockerBuildCacheGc, AspireGc, ResticBackup, ResticB2, ObsidianSync,
]


@pytest.mark.parametrize("cls", PENDING)
def test_m4_modules_are_pending_on_macos(cls: type[Module]) -> None:
    strategy = cls.per_os.macos
    assert isinstance(strategy, MacosPending) and strategy.milestone == "M4"
    assert strategy.workaround
    ex = FakeExecutor()
    assert cls().verify(Ctx(os=MAC, ex=ex)) is False
    with pytest.raises(NeedsUser, match="lands in M4"):
        cls().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == []  # nothing Linux-shaped ran
    assert not resolvable_on_macos(cls)  # still a known gap


def test_docker_on_macos_never_calls_sudo(monkeypatch: pytest.MonkeyPatch) -> None:
    # The Linux path ends in `sudo usermod -aG docker <user>`; a Mac run asks for the
    # password only when a module flagged needs_sudo_on_macos is pending, so docker must
    # not reach for sudo at all.
    monkeypatch.setenv("USER", "someone")
    ex = FakeExecutor()
    with pytest.raises(NeedsUser):
        Docker().install(Ctx(os=MAC, ex=ex))
    assert not [c for c in ex.calls if c[0] == "sudo"]
    assert not Docker.needs_sudo_on_macos


def test_linux_plans_are_unchanged(tmp_path: Path) -> None:
    names = [c.name for c in PENDING]
    plan = build_plan(names, load(), FEDORA, gpu_marker=tmp_path / "x")
    assert {p.name: p.skip_reason for p in plan} == {n: None for n in names}


def test_a_pending_module_blocks_what_requires_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")  # nobody at the terminal
    modules = load()
    plan = build_plan(toposort(["data-services"], modules), modules, MAC,
                      gpu_marker=tmp_path / "x")
    results = {r.name: r.status for r in run_plan(plan, modules, Ctx(os=MAC, ex=FakeExecutor()))}
    assert results["docker"] == "blocked"
    assert results["data-services"] == "blocked"
