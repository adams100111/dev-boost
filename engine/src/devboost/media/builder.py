"""Orchestrate the USB build/update stages from a MediaConfig."""

from __future__ import annotations

from pathlib import Path

from devboost.media import stages
from devboost.media.config import MediaConfig
from devboost.media.download import Downloader
from devboost.media.report import Reporter
from devboost.model import Ctx


def build(
    ctx: Ctx, cfg: MediaConfig, dl: Downloader, *, vtoy_mount: Path, reporter: Reporter
) -> None:
    if cfg.mode == "update":
        stages.update_stage(ctx, cfg, dl, vtoy_mount=vtoy_mount, reporter=reporter)
    else:
        stages.boot_artifacts(ctx, cfg, dl, vtoy_mount=vtoy_mount, reporter=reporter)

    stages.extra_isos(cfg, vtoy_mount=vtoy_mount)
    if cfg.extra_isos:
        reporter.step(f"Staged {len(cfg.extra_isos)} extra ISO(s)")
    stages.installers(cfg, vtoy_mount=vtoy_mount)
    if cfg.installers:
        reporter.step(f"Staged {len(cfg.installers)} installer(s)")
    if cfg.offline_mirror:
        stages.mirror(ctx, cfg, vtoy_mount=vtoy_mount)
        reporter.step("Offline mirror built")
