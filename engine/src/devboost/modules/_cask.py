"""CaskApp — a macOS app that is exactly one Homebrew cask (spec §2 casks).

A subclass is data: `cask`, optionally `launch` (opened once so macOS registers its
login item / extension and the app can ask for its permissions), `min_macos`/
`max_macos` (a version gate the plan reports as unsupported-os), and `tcc`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from devboost.core import log
from devboost.core.errors import InstallError, NeedsUser
from devboost.core.macver import macos_version
from devboost.core.osinfo import OsInfo, OsMap
from devboost.exec.primitives import macdefaults
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
    #: Open the app even on an unattended run. Default False: `open` is a surprising side
    #: effect mid-install. True only for apps whose whole purpose is to be *running* — a
    #: menu-bar monitor installed but never started shows the user nothing at all.
    #: Excluded from equality/repr, like `tcc`, to keep the two-positional-field contract.
    launch_unattended: bool = field(default=False, compare=False, repr=False)
    #: Defaults domain the app reads its own settings from, e.g. "eu.exelban.Stats".
    defaults_domain: str = field(default="", compare=False, repr=False)
    #: (key, value) pairs seeded into `defaults_domain` right after the cask lands and
    #: before the app is ever opened. Only keys that are ABSENT are written, so a setting
    #: the user later changes in the app's own UI is never undone by a later run.
    defaults_seed: tuple[tuple[str, bool], ...] = field(default=(), compare=False, repr=False)

    #: Read by the macOS contract test: a module using this strategy must require Homebrew.
    uses_brew: ClassVar[bool] = True

    def _brew_cask(self) -> BrewCask:
        return BrewCask(self.cask)

    def verify(self, ctx: Ctx) -> bool:
        return self._brew_cask().verify(ctx)

    def _seed_defaults(self, ctx: Ctx) -> bool:
        """Write the seeded keys the domain does not already carry. True if any were."""
        wrote = False
        for key, on in self.defaults_seed:
            if macdefaults.read(ctx, self.defaults_domain, key) is None:
                macdefaults.write(ctx, self.defaults_domain, key, macdefaults.Value("bool", on))
                wrote = True
        return wrote

    def _apply_seeded(self, ctx: Ctx, wrote: bool) -> None:
        """Restart the app when seeding changed something and it is ALREADY running.

        An app that reads its whole defaults domain at startup does not notice a write —
        and worse, writes its in-memory copy back when it exits, discarding what we set.
        Seeding before *our* launch is not enough: on a machine where the app was already
        up, the settings were written correctly and silently never took effect.

        Restart only on an attended run, and only when something actually changed, the
        same rule `macos-defaults` uses for Dock and Finder: killing a GUI app on a
        desktop that may be in use is not something to do unasked.
        """
        if not wrote or self.launch is None:
            return
        if not ctx.ex.run(["pgrep", "-x", self.launch]).ok:
            return  # not running: it will read the seeded values when it next starts
        if not is_interactive():
            log.info(f"{self.launch} not restarted (nobody at the terminal); the new "
                     f"settings apply next time it starts, or now with "
                     f"`killall {self.launch} && open -a {self.launch}`")
            return
        ctx.ex.run(["killall", self.launch])
        ctx.ex.run(["open", "-g", "-a", self.launch])

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
        # Before the `already`/launch returns below: an app that reads its settings once
        # at startup must be seeded while it is not running, and seeding is idempotent
        # (absent keys only), so it is safe on a re-run of an already-present cask.
        seeded = self._seed_defaults(ctx)
        if already or self.launch is None:
            # Already present: our launch below never runs, so an app that is up right now
            # would otherwise keep — and then write back — its pre-seeding settings.
            self._apply_seeded(ctx, seeded)
            return
        if not is_interactive():
            if self.tcc:
                raise NeedsUser(
                    f"{self.launch} is installed but needs its permissions granted",
                    f"open {self.launch} once and grant its permissions, then "
                    f"`devboost permissions --confirm {self.module_name}`",
                )
            if not self.launch_unattended:
                return
        ctx.ex.run(["open", "-g", "-a", self.launch])


class CaskApp(Module):
    """Base for single-cask macOS apps. Subclasses set `cask` (and optionally the rest)."""

    cask: ClassVar[str]
    launch: ClassVar[str | None] = None
    launch_unattended: ClassVar[bool] = False
    defaults_domain: ClassVar[str] = ""
    defaults_seed: ClassVar[tuple[tuple[str, bool], ...]] = ()
    min_macos: ClassVar[tuple[int, int] | None] = None
    max_macos: ClassVar[tuple[int, int] | None] = None
    families = ("macos",)
    gui = True
    requires = (Homebrew,)

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if "cask" in cls.__dict__:
            cls.per_os = OsMap(
                macos=CaskInstall(
                    cls.cask,
                    cls.launch,
                    tcc=cls.tcc,
                    module_name=cls.name,
                    launch_unattended=cls.launch_unattended,
                    defaults_domain=cls.defaults_domain,
                    defaults_seed=cls.defaults_seed,
                )
            )

    @classmethod
    def supported_on(cls, os_info: OsInfo) -> bool:
        v = macos_version(os_info)
        if v is None:
            return True
        if cls.min_macos is not None and v < cls.min_macos:
            return False
        return not (cls.max_macos is not None and v > cls.max_macos)
