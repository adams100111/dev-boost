"""Shared base for trivial package-install modules (verify = which; install = pkg)."""

from __future__ import annotations

from typing import ClassVar

from devboost.exec.primitives import copr, pkg
from devboost.model import Ctx, Module


class PackageModule(Module):
    """A module installed from a single package, verified by a command on PATH."""

    cmd: ClassVar[str]
    fedora_pkg: ClassVar[str]
    copr_repo: ClassVar[str | None] = None

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which(self.cmd)

    def install(self, ctx: Ctx) -> None:
        if self.copr_repo is not None:
            copr.enable(ctx, self.copr_repo)
        pkg.install(ctx, self.fedora_pkg)
