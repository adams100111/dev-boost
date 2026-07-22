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
FEDORA_HEADLESS = OsInfo("fedora", "fedora", "x86_64", headless=True)


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


class _GuiApp(Module):
    name = "guiapp"
    gui = True

    def verify(self, ctx: Ctx) -> bool:
        return False

    def install(self, ctx: Ctx) -> None: ...


def test_plan_gui_modules_skipped_when_headless() -> None:
    """GUI modules are skipped on a headless host (server) — installing them is pointless
    and a Flatpak GUI app can fail outright; a clean skip avoids a cascade failure."""
    plan = build_plan(["guiapp"], {"guiapp": _GuiApp}, FEDORA_HEADLESS)
    assert plan[0].skip_reason == "headless"


def test_plan_gui_modules_installed_when_graphical() -> None:
    """On a graphical host the same GUI module is planned for install (no skip)."""
    plan = build_plan(["guiapp"], {"guiapp": _GuiApp}, FEDORA)
    assert plan[0].skip_reason is None


def test_runner_skips_when_verify_passes(tmp_path: Path) -> None:
    ex = FakeExecutor(present={"rg"})
    modules = load()
    ctx = Ctx(os=FEDORA, ex=ex)
    # Isolate the gpu-vendor marker: a real marker (~/.local/state/devboost/gpu-vendor)
    # would auto-inject the hardware-nvidia closure and blow up the ripgrep-only plan.
    plan = build_plan(["ripgrep"], modules, FEDORA, gpu_marker=tmp_path / "no-such-file")
    results = run_plan(plan, modules, ctx)
    assert results[0].status == "skip"
    assert all(c[0] != "dnf" for c in ex.calls)  # nothing installed


def test_runner_installs_then_verifies(tmp_path: Path) -> None:
    # rg absent first; after install, present-set flips via a custom executor.
    class Flipping(FakeExecutor):
        def run(self, argv, *, sudo=False, stdin=None, env=None, cwd=None):  # type: ignore[no-untyped-def]
            res = super().run(argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd)
            if argv and argv[0] == "dnf":
                self.present.add("rg")
            return res

    ex = Flipping()
    modules = load()
    ctx = Ctx(os=FEDORA, ex=ex)
    # Isolate the gpu-vendor marker (see test_runner_skips_when_verify_passes).
    plan = build_plan(["ripgrep"], modules, FEDORA, gpu_marker=tmp_path / "no-such-file")
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


def test_runner_blocks_dependent_when_required_fails() -> None:
    """A module whose require failed must be blocked, not attempted."""
    class Root(Module):
        name = "root-mod"

        def verify(self, ctx: Ctx) -> bool:
            return False

        def install(self, ctx: Ctx) -> None:
            raise RuntimeError("root install failed")

    class Child(Module):
        name = "child-mod"
        requires = (Root,)

        def verify(self, ctx: Ctx) -> bool:
            return False

        def install(self, ctx: Ctx) -> None:
            raise AssertionError("child install must not be called when root failed")

    modules_map: dict[str, type[Module]] = {"root-mod": Root, "child-mod": Child}
    # root-mod first (topo order: dependency before dependent)
    plan = build_plan(["root-mod", "child-mod"], modules_map, FEDORA)
    ex = FakeExecutor()
    ctx = Ctx(os=FEDORA, ex=ex)
    results = run_plan(plan, modules_map, ctx)

    assert results[0].name == "root-mod"
    assert results[0].status == "fail"
    assert results[1].name == "child-mod"
    assert results[1].status == "blocked"
    assert "required-failed:root-mod" in results[1].detail


def test_runner_cascades_block_transitively() -> None:
    """A blocked module also blocks its own dependents (cascade)."""
    class A(Module):
        name = "a-mod"

        def verify(self, ctx: Ctx) -> bool:
            return False

        def install(self, ctx: Ctx) -> None:
            raise RuntimeError("a failed")

    class B(Module):
        name = "b-mod"
        requires = (A,)

        def verify(self, ctx: Ctx) -> bool:
            return False

        def install(self, ctx: Ctx) -> None:
            raise AssertionError("must not run")

    class C(Module):
        name = "c-mod"
        requires = (B,)

        def verify(self, ctx: Ctx) -> bool:
            return False

        def install(self, ctx: Ctx) -> None:
            raise AssertionError("must not run")

    modules_map: dict[str, type[Module]] = {"a-mod": A, "b-mod": B, "c-mod": C}
    plan = build_plan(["a-mod", "b-mod", "c-mod"], modules_map, FEDORA)
    ctx = Ctx(os=FEDORA, ex=FakeExecutor())
    results = run_plan(plan, modules_map, ctx)

    statuses = {r.name: r.status for r in results}
    assert statuses["a-mod"] == "fail"
    assert statuses["b-mod"] == "blocked"
    assert statuses["c-mod"] == "blocked"


def test_plan_nvidia_auto_inject(tmp_path: Path) -> None:
    """When the gpu-vendor marker contains 'nvidia', hardware-nvidia modules are injected."""
    marker = tmp_path / "gpu-vendor"
    marker.write_text("nvidia\n", encoding="utf-8")

    modules = load()
    # Start with only ripgrep selected; no nvidia modules requested.
    plan = build_plan(["ripgrep"], modules, FEDORA, gpu_marker=marker)
    plan_names = [pm.name for pm in plan]

    assert "nvidia-akmod" in plan_names, "nvidia-akmod must be auto-injected on NVIDIA hardware"
    # nvidia-akmod requires rpmfusion, which must appear before it.
    rpmfusion_idx = next((i for i, n in enumerate(plan_names) if n == "rpmfusion"), None)
    nvidia_idx = plan_names.index("nvidia-akmod")
    assert rpmfusion_idx is not None
    assert rpmfusion_idx < nvidia_idx, "rpmfusion must be ordered before nvidia-akmod"


def test_plan_no_nvidia_inject_when_marker_absent(tmp_path: Path) -> None:
    """When the gpu-vendor marker is absent, no hardware-nvidia modules are injected."""
    modules = load()
    # Use a non-existent marker path to simulate absence.
    plan = build_plan(["ripgrep"], modules, FEDORA, gpu_marker=tmp_path / "no-such-file")
    plan_names = [pm.name for pm in plan]
    assert "nvidia-akmod" not in plan_names


def test_plan_no_nvidia_inject_when_gpu_is_amd(tmp_path: Path) -> None:
    """When the gpu-vendor marker says 'amd', no NVIDIA modules are injected."""
    marker = tmp_path / "gpu-vendor"
    marker.write_text("amd\n", encoding="utf-8")

    modules = load()
    plan = build_plan(["ripgrep"], modules, FEDORA, gpu_marker=marker)
    plan_names = [pm.name for pm in plan]
    assert "nvidia-akmod" not in plan_names
