"""A module may decline an OS version: the plan reports it as unsupported-os."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from devboost.core.macver import macos_version
from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.model import Ctx, Module

MAC26 = OsInfo("macos", "macos", "aarch64", version_id="26.3")
MAC27 = OsInfo("macos", "macos", "aarch64", version_id="27.0")


class _Needs27(Module):
    name: ClassVar[str] = "needs-27-probe"

    @classmethod
    def supported_on(cls, os_info: OsInfo) -> bool:
        v = macos_version(os_info)
        return v is not None and v >= (27, 0)

    def verify(self, ctx: Ctx) -> bool:
        return False

    def install(self, ctx: Ctx) -> None:
        return None


MODULES: dict[str, type[Module]] = {"needs-27-probe": _Needs27}


def test_version_gate_skips_older_macos(tmp_path: Path) -> None:
    plan = build_plan(["needs-27-probe"], MODULES, MAC26, gpu_marker=tmp_path / "none")
    assert plan[0].skip_reason == "unsupported-os"


def test_version_gate_admits_newer_macos(tmp_path: Path) -> None:
    plan = build_plan(["needs-27-probe"], MODULES, MAC27, gpu_marker=tmp_path / "none")
    assert plan[0].skip_reason is None


def test_default_supported_on_is_true() -> None:
    assert Module.supported_on(MAC26) is True
