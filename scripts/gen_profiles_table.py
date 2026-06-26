#!/usr/bin/env python3
"""Generate the README profiles table from the typed registry + profiles.toml.

Run: uv run --project engine python scripts/gen_profiles_table.py
Reads module category/description from the typed module classes (single source of
truth) and profile membership from profiles.toml.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine" / "src"))

from devboost.core.registry import load  # noqa: E402


def main() -> None:
    modules = load()
    profiles = tomllib.loads((ROOT / "profiles.toml").read_text(encoding="utf-8"))["profiles"]

    print("| Profile | Modules |")
    print("|---|---|")
    for name in sorted(profiles):
        members = ", ".join(f"`{m}`" for m in profiles[name])
        print(f"| `{name}` | {members} |")

    print("\n| Module | Category | Description |")
    print("|---|---|---|")
    for name in sorted(modules):
        cls = modules[name]
        print(f"| `{name}` | {cls.category} | {cls.description} |")


if __name__ == "__main__":
    main()
