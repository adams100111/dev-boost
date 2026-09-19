"""A module whose macOS path is designed but owned by a later milestone.

Without this, running such a module on a Mac would execute its Linux path (systemctl,
dnf, /etc/…) and fail with a confusing error. With it, the run reports the module as
`blocked` with the milestone that brings it and a manual workaround, and the modules that
require it are blocked too. The macOS contract test counts it as a known gap.
"""

from __future__ import annotations

from dataclasses import dataclass

from devboost.core.errors import NeedsUser
from devboost.model import Ctx


@dataclass(frozen=True)
class MacosPending:
    milestone: str
    workaround: str

    def verify(self, ctx: Ctx) -> bool:
        return False

    def install(self, ctx: Ctx) -> None:
        raise NeedsUser(
            f"not automated on macOS yet (lands in {self.milestone})", self.workaround
        )
