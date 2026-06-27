"""Shared base for trivial package-install modules (verify = which; install = pkg)."""

from __future__ import annotations

from typing import ClassVar

from devboost.exec.primitives import copr, pkg
from devboost.model import Ctx, Module


class PackageModule(Module):
    """A module installed from a single package, verified by a command on PATH."""

    cmd: ClassVar[str]
    fedora_pkg: ClassVar[str]
    debian_pkg: ClassVar[str | None] = None   # apt package name; None → fedora_pkg
    debian_cmd: ClassVar[str | None] = None   # binary on Debian/Ubuntu; None → cmd
    copr_repo: ClassVar[str | None] = None

    def _resolve_cmd(self, ctx: Ctx) -> str:
        if ctx.os.family == "debian" and self.debian_cmd is not None:
            return self.debian_cmd
        return self.cmd

    def _resolve_pkg(self, ctx: Ctx) -> str:
        if ctx.os.family == "debian" and self.debian_pkg is not None:
            return self.debian_pkg
        return self.fedora_pkg

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which(self._resolve_cmd(ctx))

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "fedora" and self.copr_repo is not None:
            copr.enable(ctx, self.copr_repo)
        pkg.install(ctx, self._resolve_pkg(ctx))
