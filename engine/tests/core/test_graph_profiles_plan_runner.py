from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.errors import ProfileError
from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load
from devboost.core.runner import run_plan
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx, Module

FEDORA = OsInfo("fedora", "fedora", "x86_64")


def test_toposort_orders_dependencies_first() -> None:
    modules = load()
    order = toposort(["ddev", "docker"], modules)
    assert order.index("docker") < order.index("ddev")


def test_profiles_expand_transitive_and_dedup(profiles_file: Path) -> None:
    modules = load()
    profiles = load_profiles(profiles_file)
    names = expand(["full"], profiles, modules)
    assert set(names) == {"ripgrep", "docker", "ddev"}


def test_profiles_expand_unknown_raises(profiles_file: Path) -> None:
    modules = load()
    profiles = load_profiles(profiles_file)
    with pytest.raises(ProfileError):
        expand(["nope"], profiles, modules)


def test_plan_skips_headless_gui() -> None:
    class GuiApp(Module):
        name = "guiapp"
        gui = True

        def verify(self, ctx: Ctx) -> bool:
            return False

        def install(self, ctx: Ctx) -> None: ...

    headless = OsInfo("fedora", "fedora", "x86_64", headless=True)
    plan = build_plan(["guiapp"], {"guiapp": GuiApp}, headless)
    assert plan[0].skip_reason == "headless-gui"


def test_runner_skips_when_verify_passes() -> None:
    ex = FakeExecutor(present={"rg"})
    modules = load()
    ctx = Ctx(os=FEDORA, ex=ex)
    plan = build_plan(["ripgrep"], modules, FEDORA)
    results = run_plan(plan, modules, ctx)
    assert results[0].status == "skip"
    assert all(c[0] != "dnf" for c in ex.calls)  # nothing installed


def test_runner_installs_then_verifies() -> None:
    # rg absent first; after install, present-set flips via a custom executor.
    class Flipping(FakeExecutor):
        def run(self, argv, *, sudo=False, stdin=None, env=None):  # type: ignore[no-untyped-def]
            res = super().run(argv, sudo=sudo, stdin=stdin, env=env)
            if argv and argv[0] == "dnf":
                self.present.add("rg")
            return res

    ex = Flipping()
    modules = load()
    ctx = Ctx(os=FEDORA, ex=ex)
    plan = build_plan(["ripgrep"], modules, FEDORA)
    results = run_plan(plan, modules, ctx)
    assert results[0].status == "ok"
    assert ["sudo", "dnf", "install", "-y", "ripgrep"] in ex.calls


def test_runner_dry_run_mutates_nothing() -> None:
    ex = FakeExecutor()
    modules = load()
    ctx = Ctx(os=FEDORA, ex=ex, dry_run=True)
    plan = build_plan(["ripgrep"], modules, FEDORA)
    results = run_plan(plan, modules, ctx)
    assert results[0].status == "ok"
    assert ex.calls == []


def test_runner_reports_failure_with_detail() -> None:
    ex = FakeExecutor(scripts={"rpm": Result(1)})  # verify(docker) uses which → stays missing
    modules = load()
    ctx = Ctx(os=FEDORA, ex=ex)
    plan = build_plan(["docker"], modules, FEDORA)
    results = run_plan(plan, modules, ctx)
    # docker installs (dnf) but `which docker` still false → verify-failed-after-install
    assert results[0].status == "fail"
    assert "verify" in results[0].detail
