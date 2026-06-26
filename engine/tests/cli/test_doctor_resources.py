from __future__ import annotations

from pathlib import Path

from devboost.cli.doctor import all_ok, run_checks
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.exec.resources import resource_path, resource_root
from devboost.model import Ctx


def test_doctor_all_ok_when_deps_present(tmp_path: Path) -> None:
    (tmp_path / "profiles.toml").write_text("[profiles]\n", encoding="utf-8")
    ctx = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor(present={"jq", "age"}))
    checks = run_checks(ctx, tmp_path)
    assert all_ok(checks)


def test_doctor_fails_on_missing_dep_and_unknown_os(tmp_path: Path) -> None:
    ctx = Ctx(os=OsInfo("unknown", "unknown", "x86_64"), ex=FakeExecutor())
    checks = run_checks(ctx, tmp_path)
    assert not all_ok(checks)
    names = {c.name for c in checks if not c.ok}
    assert "os" in names and "dep:age" in names and "profiles" in names


def test_resource_root_from_source_holds_profiles() -> None:
    assert (resource_root() / "profiles.toml").exists()
    assert resource_path("profiles.toml").name == "profiles.toml"
