"""flatpak primitive — manage remotes and install Flathub apps (idempotent).

OS-agnostic: uses the pkg primitive (which dispatches to apt/dnf/…) to ensure
flatpak itself is installed before any flatpak command runs.
"""

from __future__ import annotations

from devboost.exec.primitives import pkg
from devboost.model import Ctx


def _ensure_flatpak(ctx: Ctx) -> None:
    """Install the flatpak package via the OS package manager if not yet present."""
    if not ctx.ex.which("flatpak"):
        pkg.install(ctx, "flatpak")


def remote_add(ctx: Ctx, name: str, url: str) -> None:
    _ensure_flatpak(ctx)
    if name in ctx.ex.run(["flatpak", "remotes"]).stdout.split():
        return
    ctx.ex.run(["flatpak", "remote-add", "--if-not-exists", name, url])


def remote_modify(ctx: Ctx, name: str, *args: str) -> None:
    ctx.ex.run(["flatpak", "remote-modify", *args, name])


# The canonical Flathub repo descriptor — added on demand so installs work on a fresh box.
_FLATHUB_URL = "https://flathub.org/repo/flathub.flatpakrepo"


def install(ctx: Ctx, app_id: str, *, remote: str = "flathub") -> None:
    _ensure_flatpak(ctx)
    # A freshly-installed flatpak has no remotes; an install against a missing remote fails.
    if remote == "flathub":
        remote_add(ctx, "flathub", _FLATHUB_URL)
    ctx.ex.run(["flatpak", "install", "-y", remote, app_id])
