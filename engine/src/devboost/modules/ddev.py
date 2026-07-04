"""Tracer B — per-OS Source (layer 3): third-party repo + install + follow-up command.

requires=(Docker,) exercises class-reference dependencies. The debian= source is the
architecture-ready seam (not implemented for the Fedora-only delivery).
"""

from __future__ import annotations

from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import Ctx, DnfRepo, Module
from devboost.modules.docker import Docker

# Fedora: ddev's own dnf repo. (Debian uses the canonical apt setup below, not an AptRepo —
# a hand-rolled apt list conflicted on Signed-By with the ddev.sources ddev's package ships.)
DDEV_SOURCE: pkg.Source = OsMap(
    fedora=DnfRepo(name="ddev", baseurl="https://pkg.ddev.com/yum/", gpgcheck=False),
)

# Canonical DDEV apt repo, verbatim from ddev's official install docs (keyring ddev.asc +
# deb822 ddev.sources), including the rm -f of older-format / third-party files that would
# otherwise cause "Conflicting values set for option Signed-By" and break apt-get update.
# Run as root; the actual `apt-get install ddev` goes through pkg.install (needrestart-safe).
_DDEV_REPO_DEBIAN = (
    "set -e\n"
    "install -m 0755 -d /etc/apt/keyrings\n"
    "curl -fsSL https://pkg.ddev.com/apt/gpg.key | tee /etc/apt/keyrings/ddev.asc >/dev/null\n"
    "chmod a+r /etc/apt/keyrings/ddev.asc\n"
    "rm -f /etc/apt/keyrings/ddev.gpg /etc/apt/sources.list.d/ddev.list "
    "/etc/apt/sources.list.d/pkg-ddev-com.list\n"
    "printf 'Types: deb\\nURIs: https://pkg.ddev.com/apt/\\nSuites: *\\nComponents: *\\n"
    "Signed-By: /etc/apt/keyrings/ddev.asc\\n'"
    " | tee /etc/apt/sources.list.d/ddev.sources >/dev/null\n"
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
        if ctx.os.family == "debian":
            ctx.ex.run(["sh", "-c", _DDEV_REPO_DEBIAN], sudo=True)  # canonical repo (ddev docs)
            pkg.install(ctx, "ddev", refresh=True)                 # install via the Apt primitive
        else:
            pkg.install(ctx, "ddev", source=DDEV_SOURCE, refresh=True)
        if not ctx.ex.which("mkcert"):
            pkg.install(ctx, "mkcert")
        ctx.ex.run(["mkcert", "-install"])


@register
class DdevRemote(Module):
    name = "ddev-remote"
    category = "dev-stacks"
    description = "On a server, bind ddev's router to all interfaces (tailnet-reachable projects)."
    requires = (Ddev,)
    profiles = ("laravel",)

    def verify(self, ctx: Ctx) -> bool:
        # Only meaningful on a headless server; on a GUI laptop ddev stays on localhost.
        if not ctx.os.headless:
            return True
        out = ctx.ex.run(["ddev", "config", "global"]).stdout
        return "router-bind-all-interfaces=true" in out

    def install(self, ctx: Ctx) -> None:
        if not ctx.os.headless:
            return
        ctx.ex.run(["ddev", "config", "global", "--router-bind-all-interfaces"])
