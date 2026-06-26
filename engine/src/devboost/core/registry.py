"""Module registry: @register + load() auto-discovery + load-time graph validation."""

from __future__ import annotations

import importlib
import pkgutil

from devboost.core.errors import DependencyCycle, ManifestError, ProfileError
from devboost.model import Module

_REGISTRY: dict[str, type[Module]] = {}


def register(cls: type[Module]) -> type[Module]:
    name = getattr(cls, "name", None)
    if not name:
        raise ManifestError(f"{cls.__name__}: missing 'name'")
    if name in _REGISTRY and _REGISTRY[name] is not cls:
        raise ManifestError(f"duplicate module name {name!r}")
    _REGISTRY[name] = cls
    return cls


def _discover() -> None:
    import devboost.modules as pkg

    for mod in pkgutil.iter_modules(pkg.__path__):
        importlib.import_module(f"{pkg.__name__}.{mod.name}")


def load() -> dict[str, type[Module]]:
    """Import every module, then validate the whole catalog before any side effect."""
    _discover()
    modules = dict(_REGISTRY)
    _validate(modules)
    return modules


def _validate(modules: dict[str, type[Module]]) -> None:
    for name, cls in modules.items():
        for dep in cls.requires:
            dep_name = getattr(dep, "name", None)
            if not dep_name or dep_name not in modules:
                raise ManifestError(f"module {name!r} requires unknown module {dep!r}")
    _check_cycles(modules)


def _check_cycles(modules: dict[str, type[Module]]) -> None:
    visiting: set[str] = set()
    done: set[str] = set()

    def walk(name: str, stack: tuple[str, ...]) -> None:
        if name in done:
            return
        if name in visiting:
            raise DependencyCycle(" -> ".join((*stack, name)))
        visiting.add(name)
        for dep in modules[name].requires:
            walk(dep.name, (*stack, name))
        visiting.discard(name)
        done.add(name)

    for name in modules:
        walk(name, ())


def validate_profiles(modules: dict[str, type[Module]], profile_names: set[str]) -> None:
    """Every module's declared profiles must exist in profiles.toml."""
    for name, cls in modules.items():
        for prof in cls.profiles:
            if prof not in profile_names:
                raise ProfileError(f"module {name!r} declares unknown profile {prof!r}")
