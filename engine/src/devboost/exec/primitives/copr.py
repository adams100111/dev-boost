"""copr primitive — enable a Fedora COPR repository (idempotent via dnf)."""

from __future__ import annotations

from devboost.model import Ctx


def enable(ctx: Ctx, repo: str) -> None:
    ctx.ex.run(["dnf", "copr", "enable", "-y", repo], sudo=True)
