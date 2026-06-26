"""Load + validate profiles.toml and expand profile tokens to a flat module set."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from pathlib import Path

from devboost.core.errors import ProfileError
from devboost.model import Module


def load_profiles(path: Path) -> dict[str, list[str]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    raw = data.get("profiles", {})
    if not isinstance(raw, dict):
        raise ProfileError(f"{path}: [profiles] must be a table")
    return {str(k): [str(x) for x in v] for k, v in raw.items()}


def expand(
    tokens: list[str],
    profiles: Mapping[str, list[str]],
    modules: Mapping[str, type[Module]],
) -> list[str]:
    """Expand profile/module tokens transitively to a deduped list of module names."""
    seen: set[str] = set()
    out: list[str] = []
    stack = list(tokens)
    while stack:
        tok = stack.pop(0)
        if tok in seen:
            continue
        seen.add(tok)
        if tok in profiles:
            stack.extend(profiles[tok])
        elif tok in modules:
            out.append(tok)
        else:
            raise ProfileError(f"unknown profile or module: {tok!r}")
    return out
