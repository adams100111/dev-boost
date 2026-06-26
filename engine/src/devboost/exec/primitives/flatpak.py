"""flatpak primitive — manage remotes and install Flathub apps (idempotent)."""

from __future__ import annotations

from devboost.model import Ctx


def remote_add(ctx: Ctx, name: str, url: str) -> None:
    if name in ctx.ex.run(["flatpak", "remotes"]).stdout.split():
        return
    ctx.ex.run(["flatpak", "remote-add", "--if-not-exists", name, url])


def remote_modify(ctx: Ctx, name: str, *args: str) -> None:
    ctx.ex.run(["flatpak", "remote-modify", *args, name])


def install(ctx: Ctx, app_id: str, *, remote: str = "flathub") -> None:
    ctx.ex.run(["flatpak", "install", "-y", remote, app_id])
