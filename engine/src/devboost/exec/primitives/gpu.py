"""gpu primitive — detect GPU vendor(s) from lspci."""

from __future__ import annotations

from dataclasses import dataclass

from devboost.model import Ctx

_CONTROLLER_KINDS = ("VGA compatible controller", "3D controller", "Display controller")


@dataclass(frozen=True)
class Gpus:
    intel: bool
    amd: bool
    nvidia: bool

    @property
    def any(self) -> bool:
        return self.intel or self.amd or self.nvidia


def detect(ctx: Ctx) -> Gpus:
    lines = [
        ln for ln in ctx.ex.run(["lspci"]).stdout.splitlines()
        if any(k in ln for k in _CONTROLLER_KINDS)
    ]
    return Gpus(
        intel=any("Intel" in ln for ln in lines),
        amd=any("AMD" in ln or "ATI" in ln for ln in lines),
        nvidia=any("NVIDIA" in ln for ln in lines),
    )
