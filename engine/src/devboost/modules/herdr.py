"""herdr — opt-in agent-aware terminal multiplexer (pinned, SHA256-verified binary)."""

from __future__ import annotations

import os
from pathlib import Path

from devboost.core.errors import InstallError
from devboost.core.registry import register
from devboost.media.catalog import herdr_pin
from devboost.model import Ctx, Module


@register
class Herdr(Module):
    name = "herdr"
    category = "optional-agents"
    description = "herdr — agent-aware terminal multiplexer (pinned binary)."
    profiles = ("optional-agents",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("herdr")

    def install(self, ctx: Ctx) -> None:
        pin = herdr_pin()
        asset = pin.assets.get(ctx.os.arch)
        if asset is None:
            raise InstallError("herdr", f"no pinned binary for arch {ctx.os.arch!r}", 1)
        bindir = Path(os.environ["HOME"]) / ".local" / "bin"
        # Download → verify SHA256 (sha256sum -c fails the `set -e` script on mismatch,
        # before install) → install onto PATH. No native package exists for herdr.
        script = (
            "set -e\n"
            "tmp=$(mktemp -d)\n"
            f'curl -fL --retry 2 -o "$tmp/herdr" "{asset.url}"\n'
            f'echo "{asset.sha256}  $tmp/herdr" | sha256sum -c -\n'
            f'install -Dm755 "$tmp/herdr" "{bindir}/herdr"\n'
            'rm -rf "$tmp"\n'
        )
        res = ctx.ex.run(["sh", "-c", script])
        if not res.ok:
            raise InstallError("herdr", "download or checksum verification failed", res.code)
