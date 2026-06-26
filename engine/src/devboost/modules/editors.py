"""editors profile — VS Code, the fresh terminal editor, and its base LSP set."""

from __future__ import annotations

import json
import os
from pathlib import Path

from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.exec.primitives import mise, pkg
from devboost.exec.resources import resource_path
from devboost.model import Ctx, DnfRepo, Module
from devboost.modules.mise import Mise

_MS_KEY = "https://packages.microsoft.com/keys/microsoft.asc"
_VSCODE_SOURCE: pkg.Source = OsMap(
    fedora=DnfRepo(
        name="code",
        baseurl="https://packages.microsoft.com/yumrepos/vscode",
        gpgcheck=True,
        gpgkey=_MS_KEY,
    )
)
_FRESH_INSTALL = "https://raw.githubusercontent.com/sinelaw/fresh/refs/heads/master/scripts/install.sh"


@register
class Vscode(Module):
    name = "vscode"
    category = "editors"
    description = "Visual Studio Code (Microsoft repo)."
    gui = True
    profiles = ("editors",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("code")

    def install(self, ctx: Ctx) -> None:
        ctx.ex.run(["rpm", "--import", _MS_KEY], sudo=True)
        pkg.install(ctx, "code", source=_VSCODE_SOURCE)


@register
class Fresh(Module):
    name = "fresh"
    category = "editors"
    description = "The fresh terminal editor."
    profiles = ("editors",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("fresh")

    def install(self, ctx: Ctx) -> None:
        # Upstream installer (rpm asset + post-install script); curl|sh escape hatch.
        ctx.ex.run(["sh", "-c", f"curl -fsSL {_FRESH_INSTALL} | sh"])


def _read_servers() -> list[tuple[str, str, str]]:
    """(lang, fresh-cmd, mise-spec) rows from the bundled base servers TSV."""
    rows: list[tuple[str, str, str]] = []
    tsv = resource_path("data", "fresh", "servers.base.tsv").read_text(encoding="utf-8")
    for line in tsv.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) >= 3:
            rows.append((cols[0], cols[1], cols[2]))
    return rows


@register
class FreshLsp(Module):
    name = "fresh-lsp"
    category = "editors"
    description = "Provision fresh's base LSP servers (mise-pinned) + config."
    requires = (Fresh, Mise)
    profiles = ("editors",)

    def _config(self) -> Path:
        return Path(os.environ["HOME"]) / ".config" / "fresh" / "config.json"

    def verify(self, ctx: Ctx) -> bool:
        cfg = self._config()
        return cfg.exists() and all(ctx.ex.which(cmd) for _, cmd, _ in _read_servers())

    def install(self, ctx: Ctx) -> None:
        cfg = self._config()
        if not cfg.exists():
            cfg.parent.mkdir(parents=True, exist_ok=True)
            base = resource_path("data", "fresh", "config.base.json").read_text(encoding="utf-8")
            cfg.write_text(base, encoding="utf-8")
        servers = _read_servers()
        for _, _, spec in servers:
            mise.use_global(ctx, spec)
        # Record the provisioned LSP commands in the fresh config (idempotent merge).
        data = json.loads(cfg.read_text(encoding="utf-8"))
        data.setdefault("lsp", {})
        for lang, cmd, _ in servers:
            data["lsp"][lang] = {"command": cmd}
        cfg.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
