import pytest

from devboost.graph import DependencyCycle, toposort
from devboost.manifest import Module


def _m(name: str, requires: tuple[str, ...] = ()) -> Module:
    return Module(name, "cli", "true", requires, {"fedora": "x"}, {}, False)


def test_toposort_orders_deps_first() -> None:
    mods = {"a": _m("a", ("b",)), "b": _m("b")}
    assert toposort(["a", "b"], mods) == ["b", "a"]


def test_toposort_detects_cycle() -> None:
    mods = {"a": _m("a", ("b",)), "b": _m("b", ("a",))}
    with pytest.raises(DependencyCycle):
        toposort(["a", "b"], mods)
