"""Shared base for fresh LSP-provisioning modules (seed config + mise-pin servers)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import ClassVar

from devboost.exec.primitives import mise
from devboost.exec.resources import resource_path
from devboost.model import Ctx, Module


def read_servers(tsv_name: str) -> list[tuple[str, str, str]]:
    """(lang, fresh-cmd, mise-spec) rows from a bundled data/fresh/<tsv_name>."""
    rows: list[tuple[str, str, str]] = []
    text = resource_path("data", "fresh", tsv_name).read_text(encoding="utf-8")
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) >= 3:
            rows.append((cols[0], cols[1], cols[2]))
    return rows


def fresh_config() -> Path:
    return Path(os.environ["HOME"]) / ".config" / "fresh" / "config.json"


def seed_base_config() -> None:
    cfg = fresh_config()
    if not cfg.exists():
        cfg.parent.mkdir(parents=True, exist_ok=True)
        base = resource_path("data", "fresh", "config.base.json").read_text(encoding="utf-8")
        cfg.write_text(base, encoding="utf-8")


def merge_lsp(servers: list[tuple[str, str, str]]) -> None:
    cfg = fresh_config()
    data = json.loads(cfg.read_text(encoding="utf-8"))
    data.setdefault("lsp", {})
    for lang, cmd, _ in servers:
        data["lsp"][lang] = {"command": cmd}
    cfg.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


class LspModule(Module):
    """Seed fresh's config and mise-pin the language servers listed in `servers_file`."""

    servers_file: ClassVar[str]
    category = "editors"

    def verify(self, ctx: Ctx) -> bool:
        return fresh_config().exists() and all(
            ctx.ex.which(cmd) for _, cmd, _ in read_servers(self.servers_file)
        )

    def install(self, ctx: Ctx) -> None:
        seed_base_config()
        servers = read_servers(self.servers_file)
        for _, _, spec in servers:
            mise.use_global(ctx, spec)
        merge_lsp(servers)
