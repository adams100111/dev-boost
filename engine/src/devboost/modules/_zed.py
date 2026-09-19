"""Zed editor configuration — OS-agnostic (Linux and macOS).

dev-boost seeds ~/.config/zed/{settings,keymap}.json once (the same bundled files chezmoi
`create_`s) and afterwards guarantees only the spec's must-have keys, via a comment-tolerant
deep merge. Language servers are pointed at dev-boost's pinned binaries (data/fresh/*.tsv).

macOS (Z2) uses the same config files and paths; the Zed module installs the cask and
makes Zed the default app for code/text files (`ensure_default_apps`).
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from devboost.core import log
from devboost.core.errors import NeedsUser
from devboost.exec.primitives import config, default_apps
from devboost.exec.resources import resource_path, tsv_rows
from devboost.exec.userpaths import mise_shims as mise_shims
from devboost.model import Ctx
from devboost.modules._credentials import is_interactive

if TYPE_CHECKING:  # runtime import would cycle: _lsp calls refresh_after_lsp
    from devboost.modules._lsp import ServerPin

_SEED_DIR = ("dotfiles", "dot_config", "zed")

#: The OS families Zed is managed on. The single source for Zed.families and for every
#: path that writes Zed config on another module's behalf.
SUPPORTED_FAMILIES: tuple[str, ...] = ("fedora", "debian", "arch", "macos")

#: Keys re-asserted on every run (spec "Must-have keys"); everything else is the user's.
_MUST_HAVE: tuple[tuple[str, ...], ...] = (
    ("auto_install_extensions",),
    ("agent_servers",),
    ("languages", "CSharp", "language_servers"),
    ("telemetry",),
)


def home() -> Path:
    return Path(os.environ["HOME"])


def settings_path() -> Path:
    return home() / ".config" / "zed" / "settings.json"


def keymap_path() -> Path:
    return home() / ".config" / "zed" / "keymap.json"


def _seed_text(name: str) -> str:
    return resource_path(*_SEED_DIR, f"create_{name}").read_text(encoding="utf-8")


def seed_files() -> None:
    """Write each seed only when its target is absent — after that the user owns it."""
    for name, target in (("settings.json", settings_path()), ("keymap.json", keymap_path())):
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(_seed_text(name), encoding="utf-8")


def _pick(data: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any]:
    """The value at *path* re-nested alone: ("a", "b") → {"a": {"b": data["a"]["b"]}}."""
    value: Any = data
    for key in path:
        value = value[key]
    nested: dict[str, Any] = {path[-1]: value}
    for key in reversed(path[:-1]):
        nested = {key: nested}
    return nested


def read_lsp_map() -> list[tuple[str, str, str]]:
    """(zed-lsp-id, command, resolver) rows from the bundled data/zed/lsp-binaries.tsv."""
    return [(cols[0], cols[1], cols[2]) for cols in tsv_rows("data", "zed", "lsp-binaries.tsv")]


def lsp_binaries(pins: Sequence[ServerPin], home: Path) -> dict[str, Any]:
    """``lsp.<id>.binary`` entries for every mapped server whose binary exists on disk."""
    by_cmd = {p.cmd: p for p in pins}
    out: dict[str, Any] = {}
    for zed_id, cmd, resolver in read_lsp_map():
        if resolver == "mise":
            pin = by_cmd.get(cmd)
            if pin is None:
                raise ValueError(f"lsp-binaries.tsv: {cmd!r} has no pin in data/fresh/*.tsv")
            path = mise_shims(home) / cmd
            args = list(pin.args)
        elif resolver == "dotnet-tool":
            path = home / ".dotnet" / "tools" / cmd
            args = []
        else:
            raise ValueError(f"lsp-binaries.tsv: unknown resolver {resolver!r} for {cmd!r}")
        if path.exists():
            out[zed_id] = {"binary": {"path": str(path), "arguments": args}}
    return out


def must_have_patch(pins: Sequence[ServerPin], home: Path) -> dict[str, Any]:
    """The keys dev-boost guarantees: sliced from the seed (one source) + pinned LSP paths."""
    seed = json.loads(_seed_text("settings.json"))
    patch: dict[str, Any] = {}
    for path in _MUST_HAVE:
        patch = config.deep_merge(patch, _pick(seed, path))
    binaries = lsp_binaries(pins, home)
    if binaries:
        patch["lsp"] = binaries
    return patch


def config_ok(pins: Sequence[ServerPin]) -> bool:
    return config.jsonc_satisfies(str(settings_path()), must_have_patch(pins, home()))


def supported(ctx: Ctx) -> bool:
    return ctx.os.family in SUPPORTED_FAMILIES


def ensure_config(ctx: Ctx, pins: Sequence[ServerPin]) -> bool:
    """Seed if absent, then merge the must-have keys. True iff settings.json was rewritten.

    Off SUPPORTED_FAMILIES it touches nothing (no seed, no merge, no backup)."""
    if not supported(ctx):
        return False
    seed_files()
    return config.jsonc_merge_deep(ctx, str(settings_path()), must_have_patch(pins, home()))


def refresh_after_lsp(ctx: Ctx, pins: Sequence[ServerPin]) -> None:
    """Called by LSP modules after installing servers, so Zed sees them on the FIRST run
    (the plan has no ordering between `zed` and the *-lsp modules). A no-op off
    SUPPORTED_FAMILIES or when Zed's settings don't exist. Never raises: any failure
    (unparseable or undecodable file, a directory, a permission error, ...) is only a
    warning here; the `zed` module owns reporting it."""
    if not supported(ctx) or not settings_path().exists():
        return
    try:
        ensure_config(ctx, pins)
    except Exception as exc:  # the LSP install must never fail because of Zed's config
        # Escape loguru colour markup so a message containing "<...>" can't raise here.
        log.warn("zed: " + str(exc).replace("<", "\\<"))


ZED_BUNDLE_ID = "dev.zed.Zed"
_DEFAULT_APPS = ("data", "macos", "default-apps.tsv")


def default_app_rows() -> list[default_apps.Association]:
    """The file types that open in Zed on macOS (the Zed rows of the shared table)."""
    return [r for r in default_apps.table(*_DEFAULT_APPS) if r.bundle_id == ZED_BUNDLE_ID]


def default_apps_done() -> bool:
    return default_apps.handled(default_app_rows())


def ensure_default_apps(ctx: Ctx) -> None:
    """macOS: code and text files open in Zed (Zed spec "Default apps").

    macOS 26.4+ asks the user to confirm each file type, so the change is only attempted
    when someone is there; an unattended run raises NeedsUser (Zed itself is done).
    """
    rows = default_app_rows()
    confirm = default_apps.confirmation_required(ctx.os)
    can_prompt = is_interactive() or not confirm
    if can_prompt and confirm and not default_apps.handled(rows):
        log.info("zed: macOS will ask you to confirm Zed as the default app, once per file type")
    out = default_apps.apply(ctx, rows, can_prompt=can_prompt)
    if out.refused:
        log.warn(
            f"zed: not the default app for {', '.join(out.refused)} — "
            "change it in Finder › Get Info › Open with, if you want"
        )
    if out.pending:
        raise NeedsUser(
            f"Zed is not yet the default app for {len(out.pending)} code/text file types",
            "run `devboost install zed` in a terminal — macOS asks you to confirm each "
            "file type once",
        )
