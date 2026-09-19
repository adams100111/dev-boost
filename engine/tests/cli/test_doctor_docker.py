from __future__ import annotations

from pathlib import Path

import pytest

from devboost.cli import doctor
from devboost.core.errors import ConfigError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
SHOW = (("context", "show"), Result(0, stdout="colima\n"))
M4_BRAND = (("machdep.cpu.brand_string",), Result(0, stdout="Apple M4 Pro\n"))
M5_BRAND = (("machdep.cpu.brand_string",), Result(0, stdout="Apple M5\n"))


@pytest.fixture(autouse=True)
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("DEVBOOST_DOCKER_RUNTIME", raising=False)


def test_healthy_colima() -> None:
    check = doctor._docker_runtime_check(Ctx(os=MAC, ex=RuleExecutor(rules=[SHOW])))
    assert check.name == "docker-runtime" and check.ok is True
    assert "colima" in check.detail and "healthy" in check.detail


def test_not_installed_is_informational() -> None:
    ex = RuleExecutor(rules=[(("--versions", "colima"), Result(1))])
    check = doctor._docker_runtime_check(Ctx(os=MAC, ex=ex))
    assert check.ok is True and "devboost install docker" in check.detail


def test_installed_but_down_fails() -> None:
    ex = RuleExecutor(rules=[SHOW, (("info",), Result(1))])
    check = doctor._docker_runtime_check(Ctx(os=MAC, ex=ex))
    assert check.ok is False and "not reachable" in check.detail


def test_colima_without_rosetta_notes_the_slowdown() -> None:
    ex = RuleExecutor(rules=[SHOW, (("-x86_64",), Result(1))])
    assert "qemu" in doctor._docker_runtime_check(Ctx(os=MAC, ex=ex)).detail


def test_the_rosetta_note_matches_the_flag_colima_actually_gets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Minor: the note must track `rosetta_usable` (what decides --vz-rosetta), not
    `rosetta_present` — from macOS 28 they disagree."""
    monkeypatch.setattr(doctor, "rosetta_usable", lambda ctx: False)
    ex = RuleExecutor(rules=[SHOW])  # Rosetta IS installed, but this macOS cannot use it
    assert "qemu" in doctor._docker_runtime_check(Ctx(os=MAC, ex=ex)).detail


def test_bad_selection_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def bad() -> None:
        raise ConfigError("unknown docker runtime 'podman'")

    monkeypatch.setattr(doctor, "selected_runtime", bad)
    check = doctor._docker_runtime_check(Ctx(os=MAC, ex=RuleExecutor()))
    assert check.ok is False and "podman" in check.detail


def test_only_macos_runs_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVBOOST_BOOTSTRAP_DIR", str(tmp_path / "boot"))
    names = {c.name for c in doctor.run_checks(Ctx(os=FEDORA, ex=FakeExecutor()), tmp_path)}
    assert "docker-runtime" not in names
    mac_ex = FakeExecutor(present={"curl", "brew", "xcode-select"},
                          scripts={"security": Result(44)})
    mac_names = {c.name for c in doctor.run_checks(Ctx(os=MAC, ex=mac_ex), tmp_path)}
    assert "docker-runtime" in mac_names


DOWN = (("info",), Result(1))


def test_apple_m4_gets_the_sigill_hint() -> None:
    ex = RuleExecutor(rules=[SHOW, DOWN, M4_BRAND])
    detail = doctor._docker_runtime_check(Ctx(os=MAC, ex=ex)).detail
    assert "SIGILL" in detail and "132" in detail and ".NET 10" in detail


def test_apple_m5_gets_the_sigill_hint_too() -> None:
    ex = RuleExecutor(rules=[SHOW, DOWN, M5_BRAND])
    assert "SIGILL" in doctor._docker_runtime_check(Ctx(os=MAC, ex=ex)).detail


def test_a_healthy_check_carries_no_hint() -> None:
    """Minor: the hint is for a check that failed — a healthy runtime says only that."""
    check = doctor._docker_runtime_check(Ctx(os=MAC, ex=RuleExecutor(rules=[SHOW, M4_BRAND])))
    assert check.ok is True and check.detail.endswith("healthy")


def test_non_m4_m5_chip_has_no_sigill_hint() -> None:
    ex = RuleExecutor(rules=[SHOW, DOWN, (("machdep.cpu.brand_string",),
                                          Result(0, stdout="Apple M3 Max\n"))])
    assert "SIGILL" not in doctor._docker_runtime_check(Ctx(os=MAC, ex=ex)).detail


def test_sigill_hint_does_not_invent_an_env_var_workaround() -> None:
    """M4-D20: no confirmed env-var workaround exists (dotnet/runtime#133030) — the hint
    must point at an image/SDK update, never at a flag."""
    ex = RuleExecutor(rules=[SHOW, DOWN, M4_BRAND])
    detail = doctor._docker_runtime_check(Ctx(os=MAC, ex=ex)).detail
    assert "DOTNET_" not in detail
