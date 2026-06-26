"""Lifecycle verbs: add / export / diff / update / self-update."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from devboost.core.graph import toposort
from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load, validate_profiles
from devboost.model import Ctx

_MODULE_TEMPLATE = '''"""{name} module."""

from __future__ import annotations

from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import Ctx, Module


@register
class {cls}(Module):
    name = "{name}"
    category = "{name}"
    profiles = ()

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("{name}")

    def install(self, ctx: Ctx) -> None:
        pkg.install(ctx, "{name}")
'''


def scaffold_module(modules_pkg: Path, name: str) -> Path:
    """Write a new typed module file and return its path (SC-008: adding a tool = one file)."""
    cls = "".join(part.capitalize() for part in name.replace("-", "_").split("_"))
    path = modules_pkg / f"{name.replace('-', '_')}.py"
    path.write_text(_MODULE_TEMPLATE.format(name=name, cls=cls), encoding="utf-8")
    return path


def lock_lines(root: Path) -> list[str]:
    """Deterministic lock content: the sorted registered module names."""
    modules = load()
    profiles = load_profiles(root / "profiles.toml")
    validate_profiles(modules, set(profiles))
    return sorted(modules)


def write_lock(root: Path) -> Path:
    lock = root / "devboost.lock"
    lock.write_text("\n".join(lock_lines(root)) + "\n", encoding="utf-8")
    return lock


def export_snapshot(ctx: Ctx, base: Path) -> Path:
    out = base / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=True)
    probes = {
        "dnf.txt": ["dnf", "repoquery", "--userinstalled", "--qf", "%{name}\n"],
        "flatpak.txt": ["flatpak", "list", "--app", "--columns=application"],
        "mise.txt": ["mise", "ls"],
        "vscode-extensions.txt": ["code", "--list-extensions"],
    }
    for fname, argv in probes.items():
        res = ctx.ex.run(argv) if ctx.ex.which(argv[0]) else None
        body = res.stdout if res else f"# {argv[0]} unavailable\n"
        (out / fname).write_text(body, encoding="utf-8")
    return out


def diff_drift(ctx: Ctx, tokens: list[str], root: Path) -> list[str]:
    """Return the names of resolved modules whose verify currently fails (drift)."""
    modules = load()
    profiles = load_profiles(root / "profiles.toml")
    validate_profiles(modules, set(profiles))
    order = toposort(expand(tokens or ["full"], profiles, modules), modules)
    return [name for name in order if not modules[name]().verify(ctx)]


def self_update(ctx: Ctx, root: Path) -> bool:
    """git pull the repo, then re-validate the catalog. Returns True on clean pull."""
    pulled = ctx.ex.run(["git", "-C", str(root), "pull", "--ff-only"]).ok
    lock_lines(root)  # re-validates the catalog (raises on a broken graph)
    return pulled
