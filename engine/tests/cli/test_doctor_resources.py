from __future__ import annotations

from pathlib import Path

import pytest

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


def test_doctor_pass_config_check_warns_when_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEVBOOST_PASS_REPO", raising=False)
    monkeypatch.delenv("DEVBOOST_PASS_GPG_ID", raising=False)
    (tmp_path / "profiles.toml").write_text("[profiles]\n", encoding="utf-8")
    ex = FakeExecutor(present={"curl", "age"})
    ctx = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=ex)
    checks = run_checks(ctx, tmp_path)
    pc = [c for c in checks if c.name == "pass-config"]
    assert pc, "pass-config check missing"
    assert pc[0].ok is True  # informational — never blocks doctor
    assert "not set" in pc[0].detail and "DEVBOOST_PASS_REPO" in pc[0].detail


def test_doctor_pass_config_reports_repo_when_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEVBOOST_PASS_REPO", "git@github.com:user/pass-store.git")
    (tmp_path / "profiles.toml").write_text("[profiles]\n", encoding="utf-8")
    ex = FakeExecutor(present={"curl", "age"})
    ctx = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=ex)
    pc = [c for c in run_checks(ctx, tmp_path) if c.name == "pass-config"]
    assert pc and pc[0].ok is True and "DEVBOOST_PASS_REPO set" in pc[0].detail


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


def test_doctor_pi_login_check_is_informational_when_installed_but_unauthenticated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """pi-login must always be ok=True and remind the operator to run `pi /login`."""
    monkeypatch.setenv("HOME", str(tmp_path))  # no ~/.pi/agent/auth.json under here
    (tmp_path / "profiles.toml").write_text("[profiles]\n", encoding="utf-8")
    ex = FakeExecutor(present={"curl", "age", "harness"})
    ctx = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=ex)
    checks = run_checks(ctx, tmp_path)
    pi = next(c for c in checks if c.name == "pi-login")
    assert pi.ok is True
    assert "pi /login" in pi.detail


def test_doctor_pi_login_check_reports_authenticated_when_auth_json_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    auth_dir = tmp_path / ".pi" / "agent"
    auth_dir.mkdir(parents=True)
    (auth_dir / "auth.json").write_text("{}", encoding="utf-8")
    (tmp_path / "profiles.toml").write_text("[profiles]\n", encoding="utf-8")
    ex = FakeExecutor(present={"curl", "age", "harness"})
    ctx = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=ex)
    pi = next(c for c in run_checks(ctx, tmp_path) if c.name == "pi-login")
    assert pi.ok is True
    assert "authenticated" in pi.detail


def test_doctor_pi_login_check_reports_not_installed_when_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "profiles.toml").write_text("[profiles]\n", encoding="utf-8")
    ex = FakeExecutor(present={"curl", "age"})  # no harness/pi
    ctx = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=ex)
    pi = next(c for c in run_checks(ctx, tmp_path) if c.name == "pi-login")
    assert pi.ok is True
    assert "not installed" in pi.detail
