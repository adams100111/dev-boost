"""CaskApp — a macOS app that is exactly one Homebrew cask (spec §2 casks).

A subclass is data: `cask`, optionally `launch` (opened once so macOS registers its
login item / extension and the app can ask for its permissions), `min_macos`/
`max_macos` (a version gate the plan reports as unsupported-os), and `tcc`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from devboost.core.macver import macos_version
from devboost.core.osinfo import OsInfo, OsMap
from devboost.model import Ctx, Module
from devboost.modules._brew import BrewCask
from devboost.modules.macos import Homebrew  # M5-D1 — Homebrew lives in modules.macos


@dataclass(frozen=True)
class CaskInstall:
    """Wraps `_brew.BrewCask` (M5-D6): verify, plain install, `--update` force-upgrade,
    the present-but-unmanaged case (C-R6) and the greedy-upgrade skip for casks that
    update themselves (C-R17) are all BrewCask's own behaviour — not reimplemented here.

    On top, `install()` opens the app once (`open -g -a`, `-g` so it never steals
    focus) — but only on the call that actually installs the cask for the first time.
    A later `--update` force re-run of an already-present cask therefore never re-opens
    it: `open` can be the trigger for a one-time TCC permission prompt, so repeating it
    on every unattended re-run would be a duplicate, surprising side effect (M5-D6:
    "install twice with force -> no duplicate side effects, no prompts").
    """

    cask: str
    launch: str | None = None

    #: Read by the macOS contract test: a module using this strategy must require Homebrew.
    uses_brew: ClassVar[bool] = True

    @property
    def token(self) -> str:
        """The short name brew lists an installed cask under (e.g. `aerospace`)."""
        return self.cask.rsplit("/", 1)[-1]

    def _brew_cask(self) -> BrewCask:
        return BrewCask(self.cask)

    def verify(self, ctx: Ctx) -> bool:
        return self._brew_cask().verify(ctx)

    def install(self, ctx: Ctx) -> None:
        already = self.verify(ctx)
        if not already and "/" in self.cask:
            # Real-world fact (checked 2026-09-19 on Homebrew 7.0.4): a THIRD-PARTY tap
            # (`user/repo/token`, e.g. `nikitabobko/tap/aerospace`) now raises
            # UntrustedTapError on install until the tap is explicitly trusted — a
            # Homebrew 7 gate, non-interactive and idempotent (`brew trust --cask`
            # just records the grant; a repeat is a no-op, not a prompt).
            ctx.ex.run(["brew", "trust", "--cask", self.cask])
        self._brew_cask().install(ctx)
        if not already and self.launch is not None:
            ctx.ex.run(["open", "-g", "-a", self.launch])


class CaskApp(Module):
    """Base for single-cask macOS apps. Subclasses set `cask` (and optionally the rest)."""

    cask: ClassVar[str]
    launch: ClassVar[str | None] = None
    min_macos: ClassVar[tuple[int, int] | None] = None
    max_macos: ClassVar[tuple[int, int] | None] = None
    families = ("macos",)
    gui = True
    requires = (Homebrew,)

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if "cask" in cls.__dict__:
            cls.per_os = OsMap(macos=CaskInstall(cls.cask, cls.launch))

    @classmethod
    def supported_on(cls, os_info: OsInfo) -> bool:
        v = macos_version(os_info)
        if v is None:
            return True
        if cls.min_macos is not None and v < cls.min_macos:
            return False
        return not (cls.max_macos is not None and v > cls.max_macos)
