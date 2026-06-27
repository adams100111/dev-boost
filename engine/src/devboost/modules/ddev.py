"""Tracer B — per-OS Source (layer 3): third-party repo + install + follow-up command.

requires=(Docker,) exercises class-reference dependencies. The debian= source is the
architecture-ready seam (not implemented for the Fedora-only delivery).
"""

from __future__ import annotations

from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import AptRepo, Ctx, DnfRepo, Module
from devboost.modules.docker import Docker

DDEV_SOURCE: pkg.Source = OsMap(
    fedora=DnfRepo(name="ddev", baseurl="https://pkg.ddev.com/yum/", gpgcheck=False),
    debian=AptRepo(
        list_line=(
            "deb [signed-by=/etc/apt/keyrings/pkg-ddev-com.gpg]"
            " https://pkg.ddev.com/apt/ * *"
        ),
        key_url="https://pkg.ddev.com/apt/gpg.key",
    ),
)


@register
class Ddev(Module):
    name = "ddev"
    category = "dev-stacks"
    description = "Container-based Laravel/PHP dev orchestrator (no host php/composer)."
    requires = (Docker,)
    profiles = ("laravel",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("ddev")

    def install(self, ctx: Ctx) -> None:
        pkg.install(ctx, "ddev", source=DDEV_SOURCE, refresh=True)
        if not ctx.ex.which("mkcert"):
            pkg.install(ctx, "mkcert")
        ctx.ex.run(["mkcert", "-install"])
