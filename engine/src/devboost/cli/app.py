"""The devboost Typer CLI: install / verify / list / terminal / devtools."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from devboost import __version__
from devboost.core import log, osinfo
from devboost.core.graph import toposort
from devboost.core.plan import build_plan
from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load, validate_profiles
from devboost.core.runner import RunResult, run_plan
from devboost.core.settings import settings
from devboost.exec.executor import RealExecutor
from devboost.model import Ctx, Module

app = typer.Typer(help="dev-boost — typed workstation installer", no_args_is_help=True)

ProfilesArg = Annotated[list[str], typer.Argument(help="profiles/modules (default: full)")]
RootOpt = Annotated[Path, typer.Option(help="repo root with profiles.toml + modules")]
DryOpt = Annotated[bool, typer.Option("--dry-run", help="preview without executing")]
ForceOpt = Annotated[bool, typer.Option("--force", help="reinstall even if verify passes")]


def _order(tokens: list[str], root: Path) -> tuple[list[str], dict[str, type[Module]]]:
    modules = load()
    profiles = load_profiles(root / "profiles.toml")
    validate_profiles(modules, set(profiles))
    names = expand(tokens or ["full"], profiles, modules)
    return toposort(names, modules), modules


def _run(tokens: list[str], root: Path, dry_run: bool, force: bool) -> list[RunResult]:
    order, modules = _order(tokens, root)
    ctx = Ctx(os=osinfo.detect(), ex=RealExecutor(), force=force, dry_run=dry_run)
    plan = build_plan(order, modules, ctx.os)
    results = run_plan(plan, modules, ctx)
    if any(r.status == "fail" for r in results):
        raise typer.Exit(code=1)
    return results


def _version(value: bool | None) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main_callback(
    version: Annotated[
        bool | None, typer.Option("--version", callback=_version, is_eager=True)
    ] = None,
) -> None:
    """dev-boost CLI root."""


@app.command()
def install(
    profiles: ProfilesArg = [],
    root: RootOpt = settings.root,
    dry_run: DryOpt = False,
    force: ForceOpt = False,
) -> None:
    """Install one or more profiles/modules (default: full)."""
    _run(profiles, root, dry_run, force)


@app.command(name="list")
def list_(profiles: ProfilesArg = [], root: RootOpt = settings.root) -> None:
    """Print the resolved install order."""
    order, _ = _order(profiles, root)
    for name in order:
        typer.echo(name)


@app.command()
def verify(profiles: ProfilesArg = [], root: RootOpt = settings.root) -> None:
    """Report which modules are installed."""
    order, modules = _order(profiles, root)
    ctx = Ctx(os=osinfo.detect(), ex=RealExecutor())
    failed = False
    for name in order:
        if modules[name]().verify(ctx):
            log.ok(f"{name}: installed")
        else:
            log.error(f"{name}: missing")
            failed = True
    if failed:
        raise typer.Exit(code=1)


@app.command()
def terminal(
    root: RootOpt = settings.root, dry_run: DryOpt = False, force: ForceOpt = False
) -> None:
    """Install the terminal tier."""
    _run(["terminal"], root, dry_run, force)


@app.command()
def devtools(
    root: RootOpt = settings.root, dry_run: DryOpt = False, force: ForceOpt = False
) -> None:
    """Install the devtools tier."""
    _run(["devtools"], root, dry_run, force)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
