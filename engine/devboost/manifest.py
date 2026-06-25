import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ManifestError(Exception):
    pass


@dataclass(frozen=True)
class Module:
    name: str
    category: str
    verify: str
    requires: tuple[str, ...]
    install: dict[str, str]
    fallback: dict[str, str]
    gui: bool


def _parse(path: Path) -> Module:
    data: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
    name = data.get("name", path.stem)
    verify = data.get("verify")
    install = {str(k): str(v) for k, v in data.get("install", {}).items()}
    fallback = {str(k): str(v) for k, v in data.get("fallback", {}).items()}
    if not verify:
        raise ManifestError(f"module {name}: missing 'verify'")
    if not install and not fallback:
        raise ManifestError(f"module {name}: no 'install' path or 'fallback'")
    return Module(
        name=str(name),
        category=str(data.get("category", "")),
        verify=str(verify),
        requires=tuple(str(r) for r in data.get("requires", [])),
        install=install,
        fallback=fallback,
        gui=bool(data.get("gui", False)),
    )


def load_modules(modules_dir: Path) -> dict[str, Module]:
    out: dict[str, Module] = {}
    for entry in sorted(modules_dir.iterdir()):
        toml: Path | None = None
        if entry.is_file() and entry.suffix == ".toml":
            toml = entry
        elif entry.is_dir() and (entry / "module.toml").is_file():
            toml = entry / "module.toml"
        if toml is None:
            continue
        mod = _parse(toml)
        out[mod.name] = mod
    return out
