"""herdr — opt-in agent-aware terminal multiplexer (pinned, SHA256-verified binary)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import ClassVar

from devboost.core import log
from devboost.core.errors import InstallError
from devboost.core.registry import register
from devboost.media.catalog import asset_key, herdr_pin
from devboost.model import Ctx, Module
from devboost.modules._pass import pass_fields, pass_show
from devboost.modules.macos import XcodeClt
from devboost.modules.pass_store import PassStore


def _version(text: str) -> tuple[int, int, int] | None:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    return (int(m[1]), int(m[2]), int(m[3])) if m else None


@register
class Herdr(Module):
    name = "herdr"
    category = "cli"
    description = "herdr — agent-aware terminal multiplexer (pinned binary)."
    profiles = ("cli", "brain-tools")
    # Omarchy packages herdr and refreshes its config on update. Dropping our pinned
    # binary on top would DOWNGRADE it (Omarchy ships a newer release than we pin) and
    # then fight `omarchy refresh herdr` on every system update.
    provided_by: ClassVar[tuple[str, ...]] = ("omarchy",)

    #: Same install code on every OS: the catalog pin is keyed by (os, arch).
    portable: ClassVar[bool] = True

    def verify(self, ctx: Ctx) -> bool:
        if not ctx.ex.which("herdr"):
            return False
        res = ctx.ex.run(["herdr", "--version"])
        have = _version(res.stdout)
        if not res.ok or have is None:
            # A corrupt or wrong-arch binary (or one that just fails to run) must not be
            # mistaken for "installed" — treat it as drift so it gets reinstalled.
            return False
        # An older pin is upgraded; a newer herdr (after `herdr update`) is kept as is.
        want = _version(herdr_pin().version)
        return want is None or have >= want

    def install(self, ctx: Ctx) -> None:
        pin = herdr_pin()
        key = asset_key(ctx.os)
        asset = pin.assets.get(key)
        if asset is None:
            raise InstallError("herdr", f"no pinned binary for {key!r}", 1)
        bindir = Path(os.environ["HOME"]) / ".local" / "bin"
        # BSD-safe on macOS: shasum ships with every Mac, and BSD `install` has no -D.
        check = "shasum -a 256 -c -" if ctx.os.family == "macos" else "sha256sum -c -"
        # Download → verify SHA256 (the check fails the `set -e` script on a mismatch,
        # before install) → install onto PATH. No native package is used (see D9). The
        # trap cleans up $tmp on any exit (a checksum mismatch under `set -e` included),
        # not just the happy path.
        script = (
            "set -e\n"
            "tmp=$(mktemp -d)\n"
            'trap \'rm -rf "$tmp"\' EXIT\n'
            f'curl -fL --proto \'=https\' --retry 2 -o "$tmp/herdr" "{asset.url}"\n'
            f'echo "{asset.sha256}  $tmp/herdr" | {check}\n'
            f'mkdir -p "{bindir}"\n'
            f'install -m 755 "$tmp/herdr" "{bindir}/herdr"\n'
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
    # `herdr plugin install` shells out to `git rev-parse` internally, so it hits the
    # same CLT-stub dialog risk as tpm/tmux-persist on a fresh Mac without the CLT.
    requires = (Herdr, XcodeClt)
    after = (PassStore,)
    profiles = ("cli", "optional-agents", "brain-tools")
    portable: ClassVar[bool] = True  # only calls the herdr CLI

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
        """Provision the Telegram notify plugin from pass (devboost/herdr-telegram), else env,
        else skip.

        Var names (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID) confirmed against the
        agent-telegram-notify README during the skim step; they match verbatim.
        """
        stored = pass_show(ctx, "devboost/herdr-telegram", who="herdr-plugins")
        fields = pass_fields(stored) if stored else {}
        token = fields.get("token") or os.environ.get("DEVBOOST_HERDR_TELEGRAM_TOKEN")
        chat = fields.get("chat_id") or os.environ.get("DEVBOOST_HERDR_TELEGRAM_CHAT_ID")
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
