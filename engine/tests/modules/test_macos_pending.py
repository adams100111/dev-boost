"""A macOS path a later milestone owns: `MacosPending` still blocks cleanly.

M4 closed the whole macOS catalog (`KNOWN_GAPS` is empty — `test_macos_contract.py`); none
of the six modules it used to mark pending (`docker`, `docker-build-gc`, `aspire-gc`,
`restic-backup`, `restic-b2`, `obsidian-sync`) declares `MacosPending` any more. These
tests keep the mechanism itself covered with a synthetic module, for whichever module a
later milestone marks pending next, and pin that none of the six regressed back to it.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from devboost.core.errors import NeedsUser
from devboost.core.osinfo import OsInfo, OsMap
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx, Installer, Module
from devboost.modules._pending import MacosPending
from devboost.modules.apps import ObsidianSync
from devboost.modules.dev_hygiene import AspireGc
from devboost.modules.docker import Docker, DockerBuildCacheGc
from devboost.modules.server import ResticB2
from devboost.modules.system import ResticBackup
from tests.core.test_macos_contract import resolvable_on_macos

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")

#: The six modules M4 closed. None of them may use `MacosPending` again.
CLOSED: list[type[Module]] = [
    Docker, DockerBuildCacheGc, AspireGc, ResticBackup, ResticB2, ObsidianSync,
]


@pytest.mark.parametrize("cls", CLOSED)
def test_m4_modules_no_longer_use_macos_pending(cls: type[Module]) -> None:
    assert not isinstance(cls.per_os.macos, MacosPending)
    assert resolvable_on_macos(cls)


class _FutureThing(Module):
    """Stands in for whatever module a later milestone marks pending next."""

    name = "future-thing"
    category = "apps"
    description = "test-only: exercises the MacosPending mechanism."
    profiles: ClassVar[tuple[str, ...]] = ()
    per_os: ClassVar[OsMap[Installer]] = OsMap(
        macos=MacosPending("M6", "do the thing by hand until M6")
    )


def test_a_pending_module_blocks_with_the_workaround_and_runs_nothing() -> None:
    ex = FakeExecutor()
    assert _FutureThing().verify(Ctx(os=MAC, ex=ex)) is False
    with pytest.raises(NeedsUser, match="lands in M6"):
        _FutureThing().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == []  # nothing Linux-shaped ran


def test_a_pending_module_is_still_an_unresolved_macos_gap() -> None:
    assert not resolvable_on_macos(_FutureThing)


def test_a_pending_module_never_falls_through_to_a_linux_path() -> None:
    # off macOS, a module with no Linux install()/verify() of its own would raise
    # NotImplementedError — MacosPending only ever answers for macOS.
    ex = FakeExecutor()
    with pytest.raises(NotImplementedError):
        _FutureThing().install(Ctx(os=FEDORA, ex=ex))
