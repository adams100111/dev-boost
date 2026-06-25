import tomllib
from collections.abc import Iterable, Mapping
from pathlib import Path

from devboost.manifest import Module


def load_profiles(path: Path) -> dict[str, list[str]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    profiles = data.get("profiles", {})
    return {str(k): [str(x) for x in v] for k, v in profiles.items()}


def expand(
    names: Iterable[str],
    profiles: Mapping[str, list[str]],
    modules: Mapping[str, Module],
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    def add_module(name: str) -> None:
        if name not in modules:
            raise KeyError(f"unknown module: {name}")
        for dep in modules[name].requires:
            add_module(dep)
        if name not in seen:
            seen.add(name)
            out.append(name)

    def add_token(token: str) -> None:
        if token in profiles:
            for member in profiles[token]:
                add_token(member)
        else:
            add_module(token)

    for n in names:
        add_token(n)
    return out
