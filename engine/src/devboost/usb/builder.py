"""Orchestrate the USB build stages from a UsbBuildConfig."""

from __future__ import annotations

from pathlib import Path

from devboost.model import Ctx
from devboost.usb import stages
from devboost.usb.config import UsbBuildConfig
from devboost.usb.download import Downloader


def build(ctx: Ctx, cfg: UsbBuildConfig, dl: Downloader, *, vtoy_mount: Path) -> None:
    stages.boot_artifacts(ctx, cfg, dl, vtoy_mount=vtoy_mount)
    stages.extra_isos(cfg, vtoy_mount=vtoy_mount)
    stages.installers(cfg, vtoy_mount=vtoy_mount)
    if cfg.offline_mirror:
        stages.mirror(ctx, cfg, vtoy_mount=vtoy_mount)
