"""The stable contract: Ctx, Installer, Module, and the typed install-source value objects.

The engine only ever calls Module.verify(ctx)/install(ctx) + reads class metadata. Everything
else (primitives, per-OS strategies) is how a module implements those two methods.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, NoReturn, Protocol, runtime_checkable

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
class Script:
    url: str


Source = OsMap[DnfRepo | AptRepo | Script]


class Module:
    """Base class for an installable unit. A Module IS an Installer."""

    name: ClassVar[str]
    category: ClassVar[str] = ""
    description: ClassVar[str] = ""
    requires: ClassVar[tuple[type[Module], ...]] = ()
    profiles: ClassVar[tuple[str, ...]] = ()
    families: ClassVar[tuple[str, ...]] = ()
    gui: ClassVar[bool] = False
    per_os: ClassVar[OsMap[Installer]] = OsMap()

    def _strategy(self, ctx: Ctx) -> Installer:
        return self.per_os.get(ctx.os) or self

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
