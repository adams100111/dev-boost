"""Module-selection helpers for profile-installing commands (--all / --no-all / --app)."""

from __future__ import annotations

import difflib

import typer

from devboost.core import log


def resolve_apps(expanded: list[str], apps: list[str]) -> list[str]:
    """Return the requested *apps* (deduped, order-preserving) if all are in *expanded*.

    On any unknown name, print a 'did you mean' hint and exit non-zero.
    """
    chosen: list[str] = []
    for a in apps:
        if a in expanded:
            chosen.append(a)
            continue
        suggestions = difflib.get_close_matches(a, expanded, n=3, cutoff=0.6)
        hint = f" — did you mean: {', '.join(suggestions)}?" if suggestions else ""
        log.error(f"unknown app {a!r}{hint}")
        raise typer.Exit(code=2)
    seen: set[str] = set()
    result: list[str] = []
    for x in chosen:
        if x not in seen:
            seen.add(x)
            result.append(x)
    return result
