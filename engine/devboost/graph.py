from collections.abc import Mapping
from graphlib import CycleError, TopologicalSorter

from devboost.manifest import Module


class DependencyCycle(Exception):
    pass


def toposort(names: list[str], modules: Mapping[str, Module]) -> list[str]:
    selected = set(names)
    ts: TopologicalSorter[str] = TopologicalSorter()
    for name in names:
        deps = [d for d in modules[name].requires if d in selected]
        ts.add(name, *deps)
    try:
        return list(ts.static_order())
    except CycleError as exc:
        raise DependencyCycle(str(exc)) from exc
