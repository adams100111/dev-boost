"""The installer wizard's prompts — every `default=` must be a real choice.

questionary validates a select's `default` against each Choice's **value** (never its
title) and raises ValueError when it doesn't match.  Nothing here can run against a TTY,
so these tests drive ``wizard.run`` through fakes that reuse questionary's own
InquirerControl for that validation — the exact construction that raised in production.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import questionary
from questionary.prompts.common import InquirerControl

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import RealExecutor
from devboost.media import wizard
from devboost.media.catalog import default_os, iso_for
from devboost.media.config import Device
from devboost.media.marker import Marker
from devboost.media.probe import DiskState
from devboost.model import Ctx

_DEVICE = Device(
    name="sdb", path="/dev/sdb", size="57.3G", model="Cruzer Blade",
    removable=True, mounted=False, vendor="SanDisk", tran="usb",
)
_MARKER = Marker(
    version="0.1.0", os_id="fedora-44", arch="x86_64", built_at="2026-06-26T00:00:00+00:00"
)


def _ctx() -> Ctx:
    # list_removable/probe are stubbed per-test, so the executor is never invoked.
    return Ctx(os=OsInfo(distro="fedora", family="fedora", arch="x86_64"), ex=RealExecutor())


_Choices = Sequence[str | questionary.Choice]


def _value_of(choice: str | questionary.Choice) -> object:
    return choice.value if isinstance(choice, questionary.Choice) else choice


def _yes_to_wipe(message: str, default: bool) -> bool:
    """Confirm the wipe; take the offered default for every other confirm."""
    return True if "destroyed" in message else default


class _Answer:
    def __init__(self, value: object) -> None:
        self._value = value

    def ask(self) -> object:
        return self._value


class _FakePrompts:
    """Stands in for questionary: answers with each prompt's own default, and validates
    that default exactly as questionary does."""

    def __init__(self, confirm: Callable[[str, bool], bool]) -> None:
        self._confirm = confirm
        self.selected: dict[str, object] = {}

    def select(
        self, message: str, choices: _Choices, default: str | None = None, **kw: object
    ) -> _Answer:
        InquirerControl(choices, default, initial_choice=default)  # raises on a bogus default
        value = default if default is not None else _value_of(choices[0])
        self.selected[message] = value
        return _Answer(value)

    def confirm(self, message: str, default: bool = False, **kw: object) -> _Answer:
        return _Answer(self._confirm(message, default))

    def checkbox(
        self, message: str, choices: Sequence[questionary.Choice], **kw: object
    ) -> _Answer:
        return _Answer([c.value for c in choices if c.checked])

    def path(self, message: str, default: str = "", **kw: object) -> _Answer:
        return _Answer(default)

    def install(self, monkeypatch) -> _FakePrompts:  # type: ignore[no-untyped-def]
        for name in ("select", "confirm", "checkbox", "path"):
            monkeypatch.setattr(questionary, name, getattr(self, name))
        return self


def test_wizard_on_blank_stick_defaults_to_the_catalog_os(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(wizard, "list_removable", lambda ctx: [_DEVICE])
    monkeypatch.setattr(wizard, "probe", lambda ctx, device: DiskState("blank"))
    _FakePrompts(_yes_to_wipe).install(monkeypatch)

    cfg = wizard.run(_ctx())

    assert cfg.device == "/dev/sdb"
    assert cfg.mode == "build"
    # Pressing Enter through the OS prompt must select the catalog default, not crash.
    assert cfg.iso == iso_for(default_os().id, cfg.arch)


def test_wizard_on_devboost_stick_defaults_to_the_nondestructive_update(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(wizard, "list_removable", lambda ctx: [_DEVICE])
    monkeypatch.setattr(wizard, "probe", lambda ctx, device: DiskState("devboost", _MARKER))
    _FakePrompts(_yes_to_wipe).install(monkeypatch)

    cfg = wizard.run(_ctx())

    # Enter on the update/rebuild prompt must keep the user's ISOs/secrets.
    assert cfg.mode == "update"
