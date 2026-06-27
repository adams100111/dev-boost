from __future__ import annotations

from pathlib import Path

from devboost.cli.doctor import all_ok, run_checks
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.resources import resource_path, resource_root
from devboost.model import Ctx


def test_doctor_all_ok_when_deps_present(tmp_path: Path) -> None:
    (tmp_path / "profiles.toml").write_text("[profiles]\n", encoding="utf-8")
    # curl replaces jq; age is still required.  Network probe and disk checks also run.
    ex = FakeExecutor(present={"curl", "age"})
    ctx = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=ex)
    checks = run_checks(ctx, tmp_path)
    assert all_ok(checks)


def test_doctor_fails_on_missing_dep_and_unknown_os(tmp_path: Path) -> None:
    ctx = Ctx(os=OsInfo("unknown", "unknown", "x86_64"), ex=FakeExecutor())
    checks = run_checks(ctx, tmp_path)
    assert not all_ok(checks)
    names = {c.name for c in checks if not c.ok}
    assert "os" in names and "dep:age" in names and "profiles" in names


def test_doctor_checks_curl_not_jq(tmp_path: Path) -> None:
    """curl must be checked; jq must not appear in the dep checks."""
    ctx = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor())
    checks = run_checks(ctx, tmp_path)
    dep_names = {c.name for c in checks if c.name.startswith("dep:")}
    assert "dep:curl" in dep_names
    assert "dep:jq" not in dep_names


def test_doctor_disk_space_check_present(tmp_path: Path) -> None:
    """A disk-space check must appear in the output."""
    ctx = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor(present={"curl", "age"}))
    checks = run_checks(ctx, tmp_path)
    check_names = {c.name for c in checks}
    assert "disk-space" in check_names


def test_doctor_network_check_present(tmp_path: Path) -> None:
    """A network-reachability check must appear in the output."""
    ctx = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor(present={"curl", "age"}))
    checks = run_checks(ctx, tmp_path)
    check_names = {c.name for c in checks}
    assert "network" in check_names


def test_doctor_network_check_fails_when_curl_returns_nonzero(tmp_path: Path) -> None:
    """Network check must fail when curl exits non-zero."""
    ex = FakeExecutor(present={"curl", "age"}, scripts={"curl": Result(1)})
    ctx = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=ex)
    checks = run_checks(ctx, tmp_path)
    net = next(c for c in checks if c.name == "network")
    assert not net.ok


def test_resource_root_from_source_holds_profiles() -> None:
    assert (resource_root() / "profiles.toml").exists()
    assert resource_path("profiles.toml").name == "profiles.toml"
