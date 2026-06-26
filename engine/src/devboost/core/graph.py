"""Deterministic dependency ordering (Kahn / graphlib) over the selected module set."""

from __future__ import annotations

from collections.abc import Mapping
from graphlib import CycleError, TopologicalSorter

from devboost.core.errors import DependencyCycle
from devboost.model import Module


def toposort(names: list[str], modules: Mapping[str, type[Module]]) -> list[str]:
    """Order the requested modules plus the transitive closure of their `requires`."""
    selected: set[str] = set()
    stack = list(names)
    while stack:
        name = stack.pop(0)
        if name in selected:
            continue
        selected.add(name)
        stack.extend(d.name for d in modules[name].requires)

    ts: TopologicalSorter[str] = TopologicalSorter()
    for name in selected:
        ts.add(name, *(d.name for d in modules[name].requires))
    try:
        return list(ts.static_order())
    except CycleError as exc:
        raise DependencyCycle(str(exc)) from exc
