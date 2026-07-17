"""Orchestrate the USB build/update stages from a MediaConfig."""

from __future__ import annotations

from devboost.media import stages
from devboost.media.cache import Cache
from devboost.media.config import MediaConfig
from devboost.media.download import Downloader
from devboost.media.report import Reporter
from devboost.model import Ctx


def build(
    ctx: Ctx, cfg: MediaConfig, dl: Downloader, cache: Cache, *, reporter: Reporter
) -> None:
    """Run all build stages for *cfg*.

    The VTOY mount lifecycle (discover → mount → write → umount → sync) is owned by
    ``boot_artifacts`` / ``update_stage`` internally.
    """
    if cfg.mode == "update":
        stages.update_stage(ctx, cfg, dl, cache, reporter=reporter)
    else:
        stages.boot_artifacts(ctx, cfg, dl, cache, reporter=reporter)
