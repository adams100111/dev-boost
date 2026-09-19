"""Shared base for fresh LSP-provisioning modules (seed config + mise-pin servers)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from devboost.exec.primitives import mise
from devboost.exec.resources import resource_path, tsv_rows
from devboost.model import Ctx, Module
from devboost.modules import _zed


@dataclass(frozen=True)
class ServerPin:
    """One row of a bundled data/fresh/*.tsv: the in-repo pin for a language server."""

    lang: str
    cmd: str
    spec: str
    args: tuple[str, ...] = ()


def read_pins(tsv_name: str) -> list[ServerPin]:
    """Every server row (with its optional space-separated args) from data/fresh/<tsv_name>."""
    pins: list[ServerPin] = []
    for cols in tsv_rows("data", "fresh", tsv_name):
        args = tuple(cols[3].split()) if len(cols) >= 4 else ()
        pins.append(ServerPin(cols[0], cols[1], cols[2], args))
    return pins


def all_pins() -> list[ServerPin]:
    """Pins from every bundled data/fresh/*.tsv — the single source of truth for versions."""
    return [
        pin
        for tsv in sorted(resource_path("data", "fresh").glob("*.tsv"))
        for pin in read_pins(tsv.name)
    ]


def read_servers(tsv_name: str) -> list[tuple[str, str, str]]:
    """(lang, fresh-cmd, mise-spec) rows from a bundled data/fresh/<tsv_name>."""
    return [(p.lang, p.cmd, p.spec) for p in read_pins(tsv_name)]


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
        # Point Zed at these pinned servers now — the plan has no order between `zed` and
        # the *-lsp modules, so waiting for zed's next verify would cost a second run.
        _zed.refresh_after_lsp(ctx, all_pins())
