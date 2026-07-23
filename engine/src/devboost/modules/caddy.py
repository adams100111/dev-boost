"""caddy — locally-trusted reverse proxy (`tls internal`) for the brain's dev-server UIs.

Fedora (reference) via the official COPR; Debian/Ubuntu (primary, where the brain runs)
via Caddy's Cloudsmith apt repo. Mirrors docker.py's per-OS install shape.
"""

from __future__ import annotations

from devboost.core.errors import UnsupportedOS
from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import AptRepo, Ctx, Module

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

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("caddy")

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "debian":
            pkg.install(ctx, "caddy", source=_caddy_apt_source())
        elif ctx.os.family == "fedora":
            ctx.ex.run(["sh", "-c", _CADDY_COPR_FEDORA], sudo=True)
        else:
            raise UnsupportedOS(f"caddy install not implemented for {ctx.os.distro!r}")
