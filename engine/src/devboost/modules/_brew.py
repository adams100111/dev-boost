"""Homebrew install strategies — the ``per_os.macos`` answer for most modules.

A strategy is an ``Installer`` (``install``/``verify`` over ``Ctx``). Declare one as
``per_os = OsMap(macos=BrewFormula("starship"))``. A module whose own ``install``/``verify``
implement the Linux path hands off to it first, via ``Module.os_strategy`` (model.py).
"""

from __future__ import annotations

from dataclasses import dataclass

from devboost.core.errors import UnsupportedOS
from devboost.exec.primitives import pkg
from devboost.model import Ctx


@dataclass(frozen=True, init=False)
class BrewFormula:
    """One or more Homebrew formulae, verified with ``brew list`` — never ``which``.

    macOS ships its own old git/curl/bash/…, so a PATH lookup would report a tool as
    installed that brew never installed. ``ctx.force`` upgrades in place (``--update`` only
    forces modules marked ``self_updating``).
    macOS only, like ``BrewCask``: off macOS ``verify`` is False and ``install`` raises
    UnsupportedOS — a formula name must never reach dnf/apt/pacman.
    """

    formulae: tuple[str, ...]

    def __init__(self, *formulae: str) -> None:
        if not formulae:
            raise ValueError("BrewFormula needs at least one formula")
        object.__setattr__(self, "formulae", formulae)

    def verify(self, ctx: Ctx) -> bool:
        if ctx.os.family != "macos":
            return False
        return all(pkg.installed(ctx, f) for f in self.formulae)

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family != "macos":
            raise UnsupportedOS(f"Homebrew formulae are macOS-only; detected {ctx.os.distro!r}")
        if not ctx.force:
            # `brew install` of an installed formula is a no-op — no pre-check needed.
            pkg.install(ctx, *self.formulae)
            return
        present = [f for f in self.formulae if pkg.installed(ctx, f)]
        if present:
            pkg.upgrade(ctx, *present)
        missing = [f for f in self.formulae if f not in present]
        if missing:
            pkg.install(ctx, *missing)


@dataclass(frozen=True)
class BrewCask:
    """A Homebrew cask (an app). Casks with ``auto_updates`` update themselves (spec §6)."""

    cask: str

    def verify(self, ctx: Ctx) -> bool:
        return pkg.cask_installed(ctx, self.cask)

    def install(self, ctx: Ctx) -> None:
        pkg.install_cask(ctx, self.cask)
