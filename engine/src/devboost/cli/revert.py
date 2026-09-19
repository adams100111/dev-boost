"""`devboost revert` — undo what a module changed on this machine."""

from __future__ import annotations

from typing import Annotated

import typer

from devboost.core import log, osinfo
from devboost.core.errors import InstallError
from devboost.exec.executor import RealExecutor
from devboost.model import Ctx
from devboost.modules import macos_defaults as md

app = typer.Typer(help="undo a module's changes", no_args_is_help=True)


@app.command("macos-defaults")
def macos_defaults(
    keys: Annotated[
        list[str] | None,
        typer.Argument(
            help="keys to restore (`com.apple.dock:tilesize` or `tilesize`); none = all"
        ),
    ] = None,
) -> None:
    """Restore the macOS defaults recorded before dev-boost changed them."""
    os_info = osinfo.detect()
    if os_info.family != "macos":
        raise typer.BadParameter("revert macos-defaults is macOS-only")
    try:
        ids = md.resolve_ids(keys) if keys else None
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    ctx = Ctx(os=os_info, ex=RealExecutor())
    try:
        done = md.revert(ctx, ids)
    except (md.SnapshotError, InstallError) as exc:
        log.error(f"revert: {exc}")
        raise typer.Exit(1) from exc
    if done:
        log.ok(f"revert: restored {len(done)} setting(s): {', '.join(done)}")
        log.info("revert: `devboost install` re-applies them; leave macos-defaults out of "
                 "the profiles you install to keep them reverted")
    else:
        log.info("revert: nothing recorded to restore")
