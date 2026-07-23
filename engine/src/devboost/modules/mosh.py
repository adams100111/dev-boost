"""mosh — roaming-resilient terminal transport (survives sleep / Wi-Fi→cellular)."""

from __future__ import annotations

from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import Ctx, Module


@register
class Mosh(Module):
    name = "mosh"
    category = "remote"
    description = "Mosh — roaming-resilient terminal transport (client + mosh-server)."
    profiles = ("cli", "remote", "brain-host")

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("mosh")

    def install(self, ctx: Ctx) -> None:
        # One package ships both the `mosh` client and `mosh-server`. Its UDP range
        # (60000-61000) rides tailscale0, already allowed by server-firewall — no new
        # firewall rules are required.
        pkg.install(ctx, "mosh")
