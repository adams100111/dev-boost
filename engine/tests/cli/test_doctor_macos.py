from __future__ import annotations

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
