"""herdr — opt-in agent-aware terminal multiplexer (pinned, SHA256-verified binary)."""

from __future__ import annotations

import os
from pathlib import Path

from devboost.core import log
from devboost.core.errors import InstallError
from devboost.core.registry import register
from devboost.media.catalog import herdr_pin
from devboost.model import Ctx, Module


@register
class Herdr(Module):
    name = "herdr"
    category = "optional-agents"
    description = "herdr — agent-aware terminal multiplexer (pinned binary)."
    profiles = ("optional-agents", "brain-tools")

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


# Curated, pinned plugin set. (id, "owner/repo[/subdir]", ref) — id from each repo's
# herdr-plugin.toml; ref = newest stable tag (or default-branch commit). Each repo is
# skimmed before its ref is pinned (plugins run unsandboxed as the user).
#
# Originally vetted 9 slugs; 6 were dropped (leaving 3):
# - Four (nickmaglowsch/herdr-session-restore, ridho9/switchr, eugeneb50/herdr-mcp,
#   Taeyoung96/herdr-dotfiles) ship no herdr-plugin.toml (confirmed via GitHub trees API
#   at the resolved commit), so `herdr plugin install` has no manifest to install —
#   they are standalone tools/dotfiles, not herdr plugins.
# - Two dropped by decision: andrewchng/herdr-sessionizer (macOS-only, no-op on Fedora),
#   dcolinmorgan/herdr-remote (repo hygiene concerns: bundles unrelated credential script
#   + unsigned .dmg unsuitable for unattended provisioning USB).
# Final 3 entries vetted clean.
_PLUGINS: tuple[tuple[str, str, str], ...] = (
    (
        "examples.agent-telegram-notify",
        "ogulcancelik/herdr-plugin-examples/agent-telegram-notify",
        "18709cdc851dd63ed0543eb8388343a5446fd8d8",
    ),
    (
        "herdr-file-viewer",
        "smarzban/herdr-file-viewer",
        "21fd39000a6ef1375f3c394ca84d4beeee5eb930",  # v1.14.0
    ),
    (
        "cloudmanic.herdr-plus",
        "cloudmanic/herdr-plus",
        "c29440c9d8b98f385353d0452a59259e8e367235",  # v0.1.16
    ),
)


@register
class HerdrPlugins(Module):
    name = "herdr-plugins"
    category = "optional-agents"
    description = "Curated, pinned herdr plugin set."
    requires = (Herdr,)
    profiles = ("optional-agents", "brain-tools")

    def verify(self, ctx: Ctx) -> bool:
        listed = ctx.ex.run(["herdr", "plugin", "list"]).stdout
        return all(pid in listed for pid, _, _ in _PLUGINS)

    def install(self, ctx: Ctx) -> None:
        for pid, source, ref in _PLUGINS:
            res = ctx.ex.run(["herdr", "plugin", "install", source, "--ref", ref, "--yes"])
            if not res.ok:
                log.warn(f"herdr-plugins: {pid} install failed (non-blocking)")
        self._configure_notify(ctx)

    def _configure_notify(self, ctx: Ctx) -> None:
        """Provision the Telegram notify plugin from env, or skip with a warning.

        Var names (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID) confirmed against the
        agent-telegram-notify README during the skim step; they match verbatim.
        """
        token = os.environ.get("DEVBOOST_HERDR_TELEGRAM_TOKEN")
        chat = os.environ.get("DEVBOOST_HERDR_TELEGRAM_CHAT_ID")
        if not (token and chat):
            log.warn(
                "herdr-plugins: Telegram token/chat unset — notify unconfigured (non-blocking)"
            )
            return
        cfg = ctx.ex.run(
            ["herdr", "plugin", "config-dir", "examples.agent-telegram-notify"]
        ).stdout.strip()
        if not cfg:
            log.warn("herdr-plugins: notify config dir unavailable (non-blocking)")
            return
        env_file = Path(cfg) / ".env"
        env_file.parent.mkdir(parents=True, exist_ok=True)
        env_file.write_text(
            f"TELEGRAM_BOT_TOKEN={token}\nTELEGRAM_CHAT_ID={chat}\n", encoding="utf-8"
        )
