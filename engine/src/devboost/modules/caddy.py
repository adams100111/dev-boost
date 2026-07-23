"""caddy — locally-trusted reverse proxy (`tls internal`) for the brain's dev-server UIs.

Fedora (reference) via the official COPR; Debian/Ubuntu (primary, where the brain runs)
via Caddy's Cloudsmith apt repo. Mirrors docker.py's per-OS install shape.
"""

from __future__ import annotations

import os
from pathlib import Path

from devboost.core.errors import UnsupportedOS
from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import AptRepo, Ctx, Module

# Starter Caddyfile the module drops on the box itself. The chezmoi dotfile
# (dotfiles/dot_config/caddy/Caddyfile) only lands via the laptop-only `full` profile, so on a
# brain SERVER (server + brain-host) the binary would install with no config. Written only when
# absent, so operator edits are never clobbered.
_STARTER_CADDYFILE = (
    "# dev-boost starter Caddyfile for the brain box.\n"
    "# *.localhost resolves to 127.0.0.1 (RFC 6761); `tls internal` mints a locally-trusted\n"
    "# cert. Front these with `tailscale serve` to reach them from a laptop over the tailnet.\n"
    "\n"
    "app.localhost {\n"
    "\ttls internal\n"
    "\treverse_proxy localhost:3000\n"
    "}\n"
    "\n"
    "aspire.localhost {\n"
    "\ttls internal\n"
    "\treverse_proxy localhost:18888\n"
    "}\n"
)

# Caddy ships on Fedora only via the official COPR (no plain baseurl repo), so enable it with a
# shell script the way docker.py enables docker-ce. `dnf-command(copr)` provides `copr` on
# dnf4 and dnf5.
_CADDY_COPR_FEDORA = (
    "set -e\n"
    "dnf install -y 'dnf-command(copr)'\n"
    "dnf copr enable -y @caddy/caddy\n"
    "dnf install -y caddy\n"
)


def _caddy_apt_source() -> pkg.Source:
    # Debian/Ubuntu: Caddy's official Cloudsmith apt repo. `signed-by` must match the keyring
    # path Apt.add_repo derives from the URL host (dl.cloudsmith.io -> dl-cloudsmith-io).
    return OsMap(
        debian=AptRepo(
            list_line=(
                "deb [signed-by=/etc/apt/keyrings/dl-cloudsmith-io.gpg]"
                " https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main"
            ),
            key_url="https://dl.cloudsmith.io/public/caddy/stable/gpg.key",
        )
    )


@register
class Caddy(Module):
    name = "caddy"
    category = "brain-host"
    description = "Caddy — locally-trusted reverse proxy (tls internal) for brain dev UIs."
    profiles = ("brain-host",)

    def _caddyfile(self) -> Path:
        return Path(os.environ["HOME"]) / ".config" / "caddy" / "Caddyfile"

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("caddy")

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "debian":
            pkg.install(ctx, "caddy", source=_caddy_apt_source())
        elif ctx.os.family == "fedora":
            ctx.ex.run(["sh", "-c", _CADDY_COPR_FEDORA], sudo=True)
        else:
            raise UnsupportedOS(f"caddy install not implemented for {ctx.os.distro!r}")
        # Drop the starter Caddyfile so a brain SERVER (which doesn't apply the laptop-only
        # dotfiles) has a working config. Never overwrite an existing (possibly edited) file.
        dest = self._caddyfile()
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(_STARTER_CADDYFILE, encoding="utf-8")
