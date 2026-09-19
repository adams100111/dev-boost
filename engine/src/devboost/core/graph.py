"""Deterministic dependency ordering (Kahn / graphlib) over the selected module set."""

from __future__ import annotations

from collections.abc import Mapping
from graphlib import CycleError, TopologicalSorter

from devboost.core.errors import DependencyCycle
from devboost.model import Module


def toposort(names: list[str], modules: Mapping[str, type[Module]]) -> list[str]:
    """Order the requested modules plus the transitive closure of their `requires`.

    `after` targets order the plan only when they are already selected.
    """
    selected: set[str] = set()
    stack = list(names)
    while stack:
        name = stack.pop(0)
        if name in selected:
            continue
        selected.add(name)
        stack.extend(d.name for d in modules[name].requires)

    ts: TopologicalSorter[str] = TopologicalSorter()
    # Sorted, not the raw set: str hashing (and so set iteration) is seeded per-process,
    # so an unsorted `selected` would make TopologicalSorter's tie-breaking among
    # unrelated modules vary run to run despite the same input — not actually
    # deterministic, contrary to this module's docstring.
    for name in sorted(selected):
        soft = (d.name for d in modules[name].after if d.name in selected)
        ts.add(name, *(d.name for d in modules[name].requires), *soft)
    try:
        return list(ts.static_order())
    except CycleError as exc:
        raise DependencyCycle(str(exc)) from exc
