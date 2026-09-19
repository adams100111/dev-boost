"""mosh — roaming-resilient terminal transport (survives sleep / Wi-Fi→cellular)."""

from __future__ import annotations

from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import Ctx, Module
from devboost.modules._brew import BrewFormula
from devboost.modules.macos import Homebrew


@register
class Mosh(Module):
    name = "mosh"
    category = "remote"
    description = "Mosh — roaming-resilient terminal transport (client + mosh-server)."
    profiles = ("cli", "remote", "brain-host")
    requires = (Homebrew,)
    per_os = OsMap(macos=BrewFormula("mosh"))

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        return ctx.ex.which("mosh")

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
        # One package ships both the `mosh` client and `mosh-server`. Its UDP range
        # (60000-61000) needs no new firewall rules: a laptop runs no restrictive host
        # firewall, and on a server the traffic rides tailscale0, which server-firewall
        # already allows.
        pkg.install(ctx, "mosh")
