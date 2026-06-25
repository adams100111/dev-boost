from pathlib import Path
from typing import Annotated, Optional

import typer

from devboost import __version__, log, osinfo
from devboost.graph import toposort
from devboost.manifest import Module, load_modules
from devboost.plan import build_plan
from devboost.profile import expand, load_profiles
from devboost.runner import RunResult, SubprocessExecutor, run_plan

app = typer.Typer(help="dev-boost portable installer", no_args_is_help=True)

_DEFAULT_ROOT = Path(__file__).resolve().parents[2]
RootOpt = Annotated[Path, typer.Option(help="Repo root holding modules/ + profiles.toml")]
DryOpt = Annotated[bool, typer.Option("--dry-run", help="Preview without executing")]
ForceOpt = Annotated[bool, typer.Option("--force", help="Reinstall even if verify passes")]


def _version(value: Optional[bool]) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        Optional[bool],
        typer.Option("--version", callback=_version, is_eager=True),
    ] = None,
) -> None:
    """dev-boost CLI root."""


def _order(profiles: list[str], root: Path) -> tuple[list[str], dict[str, Module]]:
    modules = load_modules(root / "modules")
    profs = load_profiles(root / "profiles.toml")
    try:
        names = expand(profiles, profs, modules)
    except KeyError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    return toposort(names, modules), modules


def _run(profiles: list[str], root: Path, dry_run: bool, force: bool) -> list[RunResult]:
    order, modules = _order(profiles, root)
    plan = build_plan(order, modules, osinfo.detect(), osinfo.is_headless())
    results = run_plan(plan, SubprocessExecutor(), dry_run=dry_run, force=force)
    if any(r.status == "fail" for r in results):
        raise typer.Exit(code=1)
    return results


@app.command()
def install(
    profiles: list[str],
    root: RootOpt = _DEFAULT_ROOT,
    dry_run: DryOpt = False,
    force: ForceOpt = False,
) -> None:
    """Install one or more tiers/profiles."""
    _run(profiles, root, dry_run, force)


@app.command()
def terminal(
    root: RootOpt = _DEFAULT_ROOT,
    dry_run: DryOpt = False,
    force: ForceOpt = False,
) -> None:
    """Install the terminal tier (any OS, headless-aware)."""
    _run(["terminal"], root, dry_run, force)


@app.command()
def devtools(
    root: RootOpt = _DEFAULT_ROOT,
    dry_run: DryOpt = False,
    force: ForceOpt = False,
) -> None:
    """Install the devtools tier (runtimes + frameworks)."""
    _run(["devtools"], root, dry_run, force)


@app.command(name="list")
def list_(profiles: list[str], root: RootOpt = _DEFAULT_ROOT) -> None:
    """Print the resolved install order for the given profiles."""
    order, _ = _order(profiles, root)
    for name in order:
        typer.echo(name)


@app.command()
def verify(profiles: list[str], root: RootOpt = _DEFAULT_ROOT) -> None:
    """Report which modules of the given profiles are already installed."""
    order, modules = _order(profiles, root)
    ex = SubprocessExecutor()
    for name in order:
        status = "installed" if ex.run(modules[name].verify) == 0 else "missing"
        log.info(f"{name}: {status}")
