"""The stable contract: Ctx, Installer, Module, and the typed install-source value objects.

The engine only ever calls Module.verify(ctx)/install(ctx) + reads class metadata. Everything
else (primitives, per-OS strategies) is how a module implements those two methods.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal, NoReturn, Protocol, runtime_checkable

from devboost.core.osinfo import OsInfo, OsMap
from devboost.exec.executor import Executor


@dataclass(frozen=True)
class Ctx:
    """Injected context carried into every install/verify/primitive call."""

    os: OsInfo
    ex: Executor
    force: bool = False
    dry_run: bool = False


@runtime_checkable
class Installer(Protocol):
    def install(self, ctx: Ctx) -> None: ...
    def verify(self, ctx: Ctx) -> bool: ...


# --- typed third-party install sources (layer-3 OS divergence) ---------------------------


@dataclass(frozen=True)
class DnfRepo:
    name: str
    baseurl: str
    gpgcheck: bool = True
    gpgkey: str | None = None


@dataclass(frozen=True)
class AptRepo:  # seam — not implemented for the Fedora-only delivery
    list_line: str
    key_url: str


@dataclass(frozen=True)
class BrewTap:
    """A Homebrew tap (third-party formula/cask repository), e.g. ``ddev/ddev``."""

    name: str
    url: str | None = None


@dataclass(frozen=True)
class Script:
    url: str


#: System Settings → Privacy & Security anchor ids. ListenEvent = "Input Monitoring",
#: ScreenCapture = "Screen Recording".
TccService = Literal["Accessibility", "ListenEvent", "Microphone", "ScreenCapture"]


@dataclass(frozen=True)
class TccGrant:
    """A macOS privacy permission an app needs; only the user can grant it."""

    service: TccService
    app: str


Source = OsMap[DnfRepo | AptRepo | BrewTap | Script]


class Module:
    """Base class for an installable unit. A Module IS an Installer."""

    name: ClassVar[str]
    category: ClassVar[str] = ""
    description: ClassVar[str] = ""
    requires: ClassVar[tuple[type[Module], ...]] = ()
    #: Ordering-only dependencies: when a target is ALSO in the plan, this module runs
    #: after it. Unlike `requires`, a target is never pulled into the plan, and its
    #: failure or `blocked` state never blocks this module — use it for soft inputs the
    #: module degrades without (e.g. secrets read from `pass` while this device awaits
    #: approval).
    after: ClassVar[tuple[type[Module], ...]] = ()
    profiles: ClassVar[tuple[str, ...]] = ()
    self_updating: ClassVar[bool] = False
    families: ClassVar[tuple[str, ...]] = ()
    #: Distro ids / families whose base platform ALREADY provides this concern, so
    #: dev-boost must not install it there. Unlike `families` (which scopes a module to
    #: the OSes it *can* run on, and drops it elsewhere), this keeps the module in the
    #: plan and reports a `provided-by-<distro>` skip — the constitution requires that a
    #: module which does nothing says why. Omarchy, for instance, packages herdr and ships
    #: its own terminal and fonts; reinstalling ours would downgrade or fight the platform.
    provided_by: ClassVar[tuple[str, ...]] = ()
    #: macOS privacy permissions this module's app needs (scripts cannot grant them;
    #: the runner reports them as `blocked` with a one-click fix until confirmed).
    tcc: ClassVar[tuple[TccGrant, ...]] = ()
    #: True when a custom-install module is verified to work unchanged on macOS (no
    #: per_os.macos needed). Read by the macOS catalog contract test.
    portable: ClassVar[bool] = False
    #: True when this module's macOS install runs sudo (or a script that needs a cached
    #: sudo timestamp). A macOS run asks for the password up front only when such a
    #: module is pending; otherwise it never prompts.
    needs_sudo_on_macos: ClassVar[bool] = False
    gui: ClassVar[bool] = False
    per_os: ClassVar[OsMap[Installer]] = OsMap()

    def os_strategy(self, ctx: Ctx) -> Installer | None:
        """The ``per_os`` strategy declared for the running OS, or None.

        A module whose own install()/verify() implement its Linux path calls this first,
        so a declared entry such as ``per_os = OsMap(macos=BrewFormula("x"))`` still
        decides on that OS::

            def install(self, ctx: Ctx) -> None:
                if (s := self.os_strategy(ctx)) is not None:
                    s.install(ctx)
                    return
                ...  # the Linux path
        """
        return self.per_os.get(ctx.os)

    def _strategy(self, ctx: Ctx) -> Installer:
        return self.os_strategy(ctx) or self

    def _require_override(self, what: str) -> NoReturn:
        raise NotImplementedError(
            f"{type(self).__name__} must override {what}() or declare per_os"
        )

    def verify(self, ctx: Ctx) -> bool:
        strat = self._strategy(ctx)
        if strat is self:
            self._require_override("verify")
        return strat.verify(ctx)

    def install(self, ctx: Ctx) -> None:
        strat = self._strategy(ctx)
        if strat is self:
            self._require_override("install")
        strat.install(ctx)
