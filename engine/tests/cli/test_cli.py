from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from devboost import __version__
from devboost.cli.app import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_list_resolves_order(profiles_file: Path) -> None:
    result = runner.invoke(app, ["list", "laravel", "--root", str(profiles_file.parent)])
    assert result.exit_code == 0
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    assert lines.index("docker") < lines.index("ddev")


def test_install_dry_run_no_side_effects(profiles_file: Path) -> None:
    result = runner.invoke(
        app, ["install", "cli", "--root", str(profiles_file.parent), "--dry-run"]
    )
    assert result.exit_code == 0


def test_unknown_profile_exits_nonzero(profiles_file: Path) -> None:
    result = runner.invoke(app, ["list", "nope", "--root", str(profiles_file.parent)])
    assert result.exit_code != 0


def test_offline_filter_marks_network_modules_not_package_modules() -> None:
    """Offline rewrite: network-only modules get needs-network; PackageModule ones do not."""
    from devboost.cli.app import _apply_offline_filter, _order
    from devboost.core.osinfo import OsInfo
    from devboost.core.plan import build_plan
    from devboost.core.settings import settings

    order, modules = _order(["full"], settings.root)
    os_info = OsInfo("fedora", "fedora", "x86_64")
    plan = build_plan(order, modules, os_info)
    filtered = _apply_offline_filter(plan, modules)

    by_name = {pm.name: pm.skip_reason for pm in filtered}
    # Network-only modules (plain Module, install via curl/mise) must be marked
    assert by_name["uv"] == "needs-network"
    assert by_name["web-runtimes"] == "needs-network"
    # PackageModule-based modules must NOT be marked
    assert by_name.get("bat") is None
    assert by_name.get("git") is None
