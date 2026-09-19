"""CaskApp — a macOS app that is exactly one Homebrew cask (spec §2 casks).

A subclass is data: `cask`, optionally `launch` (opened once so macOS registers its
login item / extension and the app can ask for its permissions), `min_macos`/
`max_macos` (a version gate the plan reports as unsupported-os), and `tcc`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from devboost.core.errors import InstallError, NeedsUser
from devboost.core.macver import macos_version
from devboost.core.osinfo import OsInfo, OsMap
from devboost.model import Ctx, Module, TccGrant
from devboost.modules._brew import BrewCask
from devboost.modules._credentials import is_interactive
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

    Launching the app can pop a TCC permission dialog (Accessibility, Screen Recording,
    Input Monitoring — see `tcc`): never on an unwatched desktop (global constraint:
    "nothing waits on a prompt nobody can see"), matching the precedent in
    `server.py` (Tailscale), `ddev.py` (mkcert -install) and `ios.py` (xcodes sign-in).
    Unattended, a fresh install of an app that needs a grant raises `NeedsUser` instead
    of opening it (reported `blocked`); an app with no `tcc` just skips the launch —
    nothing points the user at it, but nothing needs their attention either.
    """

    cask: str
    launch: str | None = None
    #: TCC grants this app needs, threaded through from the owning `CaskApp` — used only
    #: to decide the unattended NeedsUser path below. Excluded from equality/repr: the
    #: `CaskApp.per_os.macos == CaskInstall(cask, launch)` contract (task-6-brief.md) is
    #: still just the two positional fields.
    tcc: tuple[TccGrant, ...] = field(default=(), compare=False, repr=False)
    #: The registered module name, for the `devboost permissions --confirm <name>` hint.
    module_name: str = field(default="", compare=False, repr=False)

    #: Read by the macOS contract test: a module using this strategy must require Homebrew.
    uses_brew: ClassVar[bool] = True

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
            result = ctx.ex.run(["brew", "trust", "--cask", self.cask])
            if not result.ok:
                raise InstallError("brew", f"brew trust --cask {self.cask}", result.code)
        self._brew_cask().install(ctx)
        if already or self.launch is None:
            return
        if not is_interactive():
            if self.tcc:
                raise NeedsUser(
                    f"{self.launch} is installed but needs its permissions granted",
                    f"open {self.launch} once and grant its permissions, then "
                    f"`devboost permissions --confirm {self.module_name}`",
                )
            return
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
            cls.per_os = OsMap(
                macos=CaskInstall(cls.cask, cls.launch, tcc=cls.tcc, module_name=cls.name)
            )

    @classmethod
    def supported_on(cls, os_info: OsInfo) -> bool:
        v = macos_version(os_info)
        if v is None:
            return True
        if cls.min_macos is not None and v < cls.min_macos:
            return False
        return not (cls.max_macos is not None and v > cls.max_macos)
