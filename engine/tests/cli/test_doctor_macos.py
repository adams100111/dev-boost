from __future__ import annotations

import json
from pathlib import Path

import pytest

from devboost.cli.doctor import run_checks
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")


@pytest.fixture(autouse=True)
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("DEVBOOST_BOOTSTRAP_DIR", str(tmp_path / "boot"))


def _names(ctx: Ctx, root: Path) -> dict[str, bool]:
    return {c.name: c.ok for c in run_checks(ctx, root)}


def test_macos_deps_and_probe(tmp_path: Path) -> None:
    ex = FakeExecutor(present={"curl", "brew", "xcode-select"},
                      scripts={"security": Result(44)})
    names = _names(Ctx(os=MAC, ex=ex), tmp_path)
    assert names["dep:brew"] and names["dep:xcode-select"]
    assert "dep:age" not in names
    probe = [c for c in ex.calls if c[0] == "curl"][0]
    assert probe[-1] == "https://formulae.brew.sh/"
    assert "permissions" in names


def test_linux_keeps_fedora_probe_and_age_dep(tmp_path: Path) -> None:
    ex = FakeExecutor(present={"curl", "age"})
    names = _names(Ctx(os=FEDORA, ex=ex), tmp_path)
    assert "dep:age" in names and "permissions" not in names
    probe = [c for c in ex.calls if c[0] == "curl"][0]
    assert probe[-1] == "https://fedoraproject.org/"


def test_macos_checks_age_only_when_a_bundle_exists(tmp_path: Path) -> None:
    # age.decrypt shells out to the `age` CLI, so a bundle makes it a real dependency.
    boot = tmp_path / "boot"
    boot.mkdir()
    (boot / "secrets.age").write_text("cipher", encoding="utf-8")
    ex = FakeExecutor(present={"curl", "brew", "xcode-select"},
                      scripts={"security": Result(44)})
    names = _names(Ctx(os=MAC, ex=ex), tmp_path)
    assert names["dep:age"] is False


def test_rosetta_check_says_how_to_install_it(tmp_path: Path) -> None:
    ex = FakeExecutor(present={"curl", "brew", "xcode-select"},
                      scripts={"security": Result(44), "arch": Result(1)})
    checks = {c.name: c for c in run_checks(Ctx(os=MAC, ex=ex), tmp_path)}
    assert checks["rosetta"].ok is True
    assert "devboost install rosetta" in checks["rosetta"].detail


def test_rosetta_check_lists_intel_only_apps_from_28(tmp_path: Path) -> None:
    body = json.dumps({"SPApplicationsDataType": [{"_name": "OldApp", "arch_kind": "arch_i64"}]})
    ex = FakeExecutor(present={"curl", "brew", "xcode-select"},
                      scripts={"security": Result(44), "system_profiler": Result(0, stdout=body)})
    mac28 = OsInfo("macos", "macos", "aarch64", version_id="28.0")
    checks = {c.name: c for c in run_checks(Ctx(os=mac28, ex=ex), tmp_path)}
    assert checks["rosetta"].ok is True and "OldApp" in checks["rosetta"].detail


def test_rosetta_check_from_28_says_when_it_could_not_list(tmp_path: Path) -> None:
    # A failed system_profiler is not "no Intel-only apps": the user must not be reassured.
    ex = FakeExecutor(present={"curl", "brew", "xcode-select"},
                      scripts={"security": Result(44), "system_profiler": Result(1)})
    mac28 = OsInfo("macos", "macos", "aarch64", version_id="28.0")
    checks = {c.name: c for c in run_checks(Ctx(os=mac28, ex=ex), tmp_path)}
    assert checks["rosetta"].ok is True
    assert "could not list" in checks["rosetta"].detail


def test_rosetta_check_on_27_says_installed(tmp_path: Path) -> None:
    ex = FakeExecutor(present={"curl", "brew", "xcode-select"}, scripts={"security": Result(44)})
    checks = {c.name: c for c in run_checks(Ctx(os=MAC, ex=ex), tmp_path)}
    assert checks["rosetta"].detail == "installed"


def test_no_rosetta_check_on_linux(tmp_path: Path) -> None:
    ex = FakeExecutor(present={"curl", "age"})
    assert "rosetta" not in _names(Ctx(os=FEDORA, ex=ex), tmp_path)
