"""`devboost docker` — the Docker runtime on macOS (colima | orbstack | docker-desktop)."""

from __future__ import annotations

import os
from dataclasses import replace
from typing import Annotated

import typer

from devboost.cli import host as plat
from devboost.core import log, osinfo
from devboost.core.errors import ConfigError, DevbootError, NeedsUser
from devboost.core.settings import Settings
from devboost.core.userconfig import DockerRuntimeName, parse_docker_runtime
from devboost.exec.executor import NoPromptSudoExecutor, RealExecutor
from devboost.model import Ctx
from devboost.modules._docker_switch import (
    REQUIRED,
    SnapshotFailed,
    saved_runtime,
    sudo_needed,
    switch_runtime,
)

app = typer.Typer(
    help="Docker runtime on macOS: colima (default) | orbstack | docker-desktop",
    no_args_is_help=True,
)

_RESTORE = "  ddev: in each project, `ddev start` then `ddev snapshot restore --latest`"


def _way_back(previous: DockerRuntimeName, *, snapshot: bool) -> None:
    """The recovery hint after a switch that stopped half-way."""
    typer.echo(f"  go back: devboost docker use {previous}  (also stops the half-started one)")
    if snapshot:
        typer.echo(_RESTORE)


@app.command("use")
def use(
    runtime: Annotated[str, typer.Argument(help="colima | orbstack | docker-desktop")],
    snapshot: Annotated[
        bool | None,
        typer.Option(
            "--snapshot/--no-snapshot",
            help="run `ddev snapshot --all` first (asked when omitted)",
        ),
    ] = None,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="never prompt (snapshots unless --no-snapshot)")
    ] = False,
) -> None:
    """Switch this Mac's Docker runtime and reconfigure what depends on it."""
    info = osinfo.detect()
    if info.family != "macos":
        raise typer.BadParameter("`devboost docker use` is macOS-only — Linux runs docker-ce")
    try:
        target = parse_docker_runtime(runtime)
    except ConfigError as exc:
        raise typer.BadParameter(str(exc)) from exc
    env = Settings().docker_runtime
    if env and env != target:
        # The env var beats config.toml, so every later run would drive the old runtime.
        raise typer.BadParameter(
            f"DEVBOOST_DOCKER_RUNTIME={env} is set and overrides the saved choice — "
            f"unset it first; nothing was changed"
        )
    previous = saved_runtime()
    ex = RealExecutor()
    ctx = Ctx(os=info, ex=ex)
    if previous != target:
        log.warn(
            f"Images, volumes and ddev databases stay in {previous}'s VM — they do not move "
            f"to {target}; `devboost docker use {previous}` brings them back."
        )
    has_ddev = ex.which("ddev")
    if snapshot is None:
        unattended = yes or bool(os.environ.get("DEVBOOST_NONINTERACTIVE"))
        snapshot = has_ddev and (
            unattended
            or typer.confirm(
                "Snapshot every ddev project first (ddev snapshot --all)?", default=True
            )
        )
    sudo = sudo_needed(ctx, target)
    try:
        with plat.mac_session(ctx.os, dry_run=False, sudo=sudo) as sudo_held:
            if sudo and not sudo_held:
                # Refuse before the snapshot: a switch that stops half-way leaves no runtime.
                log.error("docker: sudo was not granted — nothing was changed")
                raise typer.Exit(code=1)
            if not sudo:
                # A sudo step that runs anyway fails fast instead of prompting on a hidden
                # tty (ruling C-R18).
                ctx = replace(ctx, ex=NoPromptSudoExecutor(ctx.ex), no_sudo=True)
            report = switch_runtime(ctx, target, snapshot=snapshot)
    except SnapshotFailed as exc:
        log.error(str(exc))
        typer.echo("  nothing was changed: fix ddev, or re-run with --no-snapshot")
        raise typer.Exit(code=1) from exc
    except NeedsUser as exc:
        log.error(f"blocked: {exc.reason}")
        typer.echo(f"  fix: {exc.how_to_fix}")
        _way_back(previous, snapshot=snapshot)
        raise typer.Exit(code=1) from exc
    except (DevbootError, OSError) as exc:
        log.error(str(exc))
        _way_back(previous, snapshot=snapshot)
        raise typer.Exit(code=1) from exc
    except KeyboardInterrupt as exc:
        log.error("docker: interrupted — the switch did not finish")
        _way_back(previous, snapshot=snapshot)
        raise typer.Exit(code=130) from exc
    for name, ok in report.checks:
        if ok:
            typer.echo(f"  ok    {name}")
        elif name in REQUIRED:
            typer.echo(f"  FAIL  {name}")
        else:
            typer.echo(f"  --    {name}  (not set up — devboost install {name})")
    if snapshot:
        typer.echo(_RESTORE)
    if not report.ok:
        raise typer.Exit(code=1)
    log.ok(f"docker runtime: {report.previous} → {report.target}")
