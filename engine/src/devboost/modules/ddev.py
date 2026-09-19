"""Tracer B — per-OS Source (layer 3): third-party repo + install + follow-up command.

requires=(Docker,) exercises class-reference dependencies. The debian= source is the
architecture-ready seam (not implemented for the Fedora-only delivery).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from devboost.core.errors import InstallError, NeedsUser
from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import BrewTap, Ctx, DnfRepo, Module
from devboost.modules._credentials import is_interactive
from devboost.modules.docker import Docker
from devboost.modules.macos import Homebrew

# Fedora: ddev's own dnf repo. (Debian uses the canonical apt setup below, not an AptRepo —
# a hand-rolled apt list conflicted on Signed-By with the ddev.sources ddev's package ships.)
# macOS: ddev is not in homebrew-core; its own tap is the documented install.
DDEV_SOURCE: pkg.Source = OsMap(
    fedora=DnfRepo(name="ddev", baseurl="https://pkg.ddev.com/yum/", gpgcheck=False),
    macos=BrewTap("ddev/ddev"),
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


def _trust_ddev_tap(ctx: Ctx) -> None:
    """Homebrew 7 raises ``UntrustedTapError`` for a third-party tap's formulae/casks
    unless the tap is trusted first (ruling C-M4-T1; ``brew help trust``: ``--tap``).
    Idempotent — safe to run whether or not ``ddev/ddev`` is already trusted."""
    res = ctx.ex.run(["brew", "trust", "--tap", "ddev/ddev"])
    if not res.ok:
        raise InstallError("ddev", "brew trust --tap ddev/ddev", res.code)


@dataclass(frozen=True)
class _DdevMac:
    """macOS (spec §2): ddev from its tap, mkcert from homebrew-core, and mkcert's local CA
    trusted once. `mkcert -install` asks for your password through sudo in the terminal
    (macOS may also show a trust-settings authorization dialog), so that step runs only
    when someone is there; otherwise the module is `blocked` with the one command to run."""

    uses_brew: ClassVar[bool] = True

    @staticmethod
    def _ca_ready(ctx: Ctx) -> bool:
        """The CA exists AND macOS trusts it. rootCA.pem alone is not enough: mkcert writes
        it before the trust step (and on any `mkcert <host>`), so a cancelled `-install`
        would leave it behind. `security verify-cert` is a read-only trust check."""
        res = ctx.ex.run(["mkcert", "-CAROOT"])
        root = res.stdout.strip()
        if not (res.ok and root):
            return False
        pem = Path(root) / "rootCA.pem"
        return pem.is_file() and ctx.ex.run(["security", "verify-cert", "-c", str(pem)]).ok

    def verify(self, ctx: Ctx) -> bool:
        return (
            pkg.installed(ctx, "ddev") and pkg.installed(ctx, "mkcert") and self._ca_ready(ctx)
        )

    def install(self, ctx: Ctx) -> None:
        present = [f for f in ("ddev", "mkcert") if pkg.installed(ctx, f)]
        if ctx.force and present:
            # Trust the tap before the upgrade too, not only before the first install: the
            # trust store follows XDG_CONFIG_HOME, so a ddev installed from a bootstrap
            # shell (store in ~/.homebrew) is untrusted from a shell whose env.sh sets it,
            # and `brew upgrade` then fails with UntrustedTapError (final review M3). The
            # step is idempotent; a re-run that upgrades nothing still never calls it.
            if "ddev" in present:
                _trust_ddev_tap(ctx)
            pkg.upgrade(ctx, *present)
        if "ddev" not in present:
            _trust_ddev_tap(ctx)
            pkg.install(ctx, "ddev/ddev/ddev", source=DDEV_SOURCE)
        if "mkcert" not in present:
            pkg.install(ctx, "mkcert")
        if self._ca_ready(ctx):
            return
        if not is_interactive():
            raise NeedsUser(
                "mkcert's local CA is not trusted yet (HTTPS for ddev sites)",
                "run `mkcert -install` in a terminal — macOS asks for your password once",
            )
        res = ctx.ex.run(["mkcert", "-install"], interactive=True)
        if not res.ok:
            raise InstallError("ddev", "mkcert -install", res.code)


@register
class Ddev(Module):
    name = "ddev"
    category = "dev-stacks"
    description = "Container-based Laravel/PHP dev orchestrator (no host php/composer)."
    requires = (Docker, Homebrew)
    profiles = ("laravel",)
    per_os = OsMap(macos=_DdevMac())

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        return ctx.ex.which("ddev")

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
        if ctx.os.family == "arch":
            # ddev publishes no pacman repo and Arch packages no `ddev`; `ddev-bin` is
            # the maintained AUR build of the upstream release binary.
            pkg.install_aur(ctx, "ddev-bin")
        elif ctx.os.family == "debian":
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
    portable: ClassVar[bool] = True  # a no-op off headless hosts; the ddev CLI is the same

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
