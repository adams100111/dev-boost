"""Module-selection helpers for profile-installing commands (--all / --no-all / --app)."""

from __future__ import annotations

import difflib
from collections.abc import Callable, Mapping
from typing import Any

import typer

from devboost.core import log
from devboost.model import Module

Checklist = Callable[[list[str], Mapping[str, type[Module]]], list[str]]


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


def group_choices(
    expanded: list[str], modules: Mapping[str, type[Module]]
) -> list[tuple[str | None, str | None]]:
    """Rows for a grouped checklist: (header, None) separators + (None, name) items.

    Categories are sorted; modules with an empty category fall under 'Other'.
    """
    by_cat: dict[str, list[str]] = {}
    for name in expanded:
        by_cat.setdefault(modules[name].category or "Other", []).append(name)
    rows: list[tuple[str | None, str | None]] = []
    for cat in sorted(by_cat):
        rows.append((cat, None))
        rows.extend((None, name) for name in by_cat[cat])
    return rows


def prompt_checklist(expanded: list[str], modules: Mapping[str, type[Module]]) -> list[str]:
    """Interactive grouped multi-select (all preselected). Not unit-tested (needs a TTY)."""
    import questionary

    choices: list[Any] = []
    for header, name in group_choices(expanded, modules):
        if header is not None:
            choices.append(questionary.Separator(f"── {header} ──"))
        else:
            choices.append(questionary.Choice(title=name, value=name, checked=True))
    answer = questionary.checkbox("Select apps to install", choices=choices).ask()
    return list(answer) if answer else []


def select_modules(
    expanded: list[str],
    modules: Mapping[str, type[Module]],
    *,
    all_: bool,
    apps: list[str],
    checklist: Checklist | None = None,
) -> list[str]:
    """Narrow *expanded* to the install set. --app wins; else all_; else interactive."""
    if apps:
        return resolve_apps(expanded, apps)
    if all_:
        return expanded
    return (checklist or prompt_checklist)(expanded, modules)
