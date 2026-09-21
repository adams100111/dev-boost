"""`devboost permissions` — walk the user through macOS privacy grants."""

from __future__ import annotations

import sys
from typing import Annotated

import typer

from devboost.core import log, osinfo
from devboost.core.registry import load
from devboost.exec.executor import RealExecutor
from devboost.exec.primitives import tcc
from devboost.model import Ctx


def permissions(
    confirm: Annotated[
        str | None, typer.Option("--confirm", help="record that MODULE's grants are done")
    ] = None,
) -> None:
    """List (and open) the macOS privacy permissions installed apps still need."""
    ctx = Ctx(os=osinfo.detect(), ex=RealExecutor())
    if ctx.os.family != "macos":
        log.info("permissions: nothing to do (macOS only)")
        return
    modules = load()
    if confirm is not None:
        if confirm not in modules or not modules[confirm].tcc:
            raise typer.BadParameter(f"{confirm!r} has no privacy permissions to confirm")
        tcc.confirm(confirm, modules[confirm].tcc)
        log.ok(f"permissions: recorded {confirm}")
        return
    todo = {
        name: tcc.pending(name, cls.tcc)
        for name, cls in sorted(modules.items())
        if cls.tcc and cls().verify(ctx)
    }
    todo = {n: g for n, g in todo.items() if g}
    if not todo:
        log.ok("permissions: all granted")
        return
    # One prompt per grant. Asking "Granted everything for <module>?" once, across
    # Microphone, Input Monitoring and Accessibility, meant a single yes marked all
    # three done forever — including the ones the user had not actually switched on.
    for name, grants in todo.items():
        for g in grants:
            setting = tcc.label(g.service)
            log.warn(f"{name}: allow {g.app} in {setting}")
            ctx.ex.run(["open", tcc.settings_url(g.service)])
            if sys.stdin.isatty() and typer.confirm(
                f"  Is {g.app} switched ON under {setting}?", default=False
            ):
                tcc.confirm(name, [g])
