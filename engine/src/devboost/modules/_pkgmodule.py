"""Shared base for trivial package-install modules (verify = which; install = pkg)."""

from __future__ import annotations

from typing import ClassVar

from devboost.core.osinfo import OsMap
from devboost.exec.primitives import copr, pkg
from devboost.model import Ctx, Module


class PackageModule(Module):
    """A module installed from a single package, verified by a command on PATH."""

    cmd: ClassVar[str]
    fedora_pkg: ClassVar[str]
    debian_pkg: ClassVar[str | None] = None   # apt package name; None → fedora_pkg
    debian_cmd: ClassVar[str | None] = None   # binary on Debian/Ubuntu; None → cmd
    arch_pkg: ClassVar[str | None] = None     # pacman package name; None → fedora_pkg
    arch_cmd: ClassVar[str | None] = None     # binary on Arch/Omarchy; None → cmd
    #: AUR package name, used only when the tool is absent from the official Arch repos.
    #: Set this *instead of* arch_pkg — it opts the module into unreviewed third-party
    #: PKGBUILDs, so it is spelled out per module rather than inferred.
    aur_pkg: ClassVar[str | None] = None
    copr_repo: ClassVar[str | None] = None
    # A single-package/single-binary install is safe to re-run for an in-place upgrade,
    # so package modules opt into `devboost install --update` by default. A specific
    # subclass with install-time side effects may override this back to False.
    self_updating: ClassVar[bool] = True

    def _resolve_cmd(self, ctx: Ctx) -> str:
        names: OsMap[str] = OsMap(
            debian=self.debian_cmd, arch=self.arch_cmd, default=self.cmd
        )
        return names.get(ctx.os) or self.cmd

    def _resolve_pkg(self, ctx: Ctx) -> str:
        names: OsMap[str] = OsMap(
            fedora=self.fedora_pkg,
            debian=self.debian_pkg,
            arch=self.arch_pkg,
            default=self.fedora_pkg,
        )
        return names.get(ctx.os) or self.fedora_pkg

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which(self._resolve_cmd(ctx))

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "fedora" and self.copr_repo is not None:
            copr.enable(ctx, self.copr_repo)
        # An AUR-only tool declares aur_pkg and no arch_pkg: route it to the helper.
        if ctx.os.family == "arch" and self.arch_pkg is None and self.aur_pkg is not None:
            pkg.install_aur(ctx, self.aur_pkg)
            return
        pkg.install(ctx, self._resolve_pkg(ctx))
