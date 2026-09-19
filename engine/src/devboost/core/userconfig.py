"""Per-user dev-boost preferences: ``~/.config/devboost/config.toml``.

Distinct from ``core/settings.py`` (engine env, ``DEVBOOST_*``): this file holds choices a
person makes once per account (which pass repo, what this device is called). Env vars
still win where a module documents one (e.g. ``DEVBOOST_PASS_REPO``).
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, Literal

import tomli_w
from pydantic import BaseModel, ConfigDict, ValidationError

from devboost.core.errors import ConfigError
from devboost.core.settings import Settings

DEFAULT_PASS_REPO = "adams100111/password-store"

DockerRuntimeName = Literal["colima", "orbstack", "docker-desktop"]
DOCKER_RUNTIMES: tuple[DockerRuntimeName, ...] = ("colima", "orbstack", "docker-desktop")
DEFAULT_DOCKER_RUNTIME: DockerRuntimeName = "colima"
_RUNTIME_BY_NAME: dict[str, DockerRuntimeName] = {n: n for n in DOCKER_RUNTIMES}


class UserConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    pass_repo: str = DEFAULT_PASS_REPO
    device_name: str | None = None
    docker_runtime: DockerRuntimeName | None = None


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path(os.environ["HOME"]) / ".config"
    return root / "devboost" / "config.toml"


def load_user_config(path: Path | None = None) -> UserConfig:
    p = path if path is not None else config_path()
    if not p.exists():
        return UserConfig()
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{p}: invalid TOML ({exc})") from exc
    try:
        return UserConfig.model_validate(data)
    except ValidationError as exc:
        fields = ", ".join(str(e["loc"][0]) for e in exc.errors() if e["loc"])
        raise ConfigError(f"{p}: invalid value for {fields}") from exc


def parse_docker_runtime(value: str) -> DockerRuntimeName:
    """The runtime named by ``value``, or a ConfigError listing the valid names."""
    name = _RUNTIME_BY_NAME.get(value)
    if name is None:
        raise ConfigError(
            f"unknown docker runtime {value!r} "
            f"(expected one of: {', '.join(DOCKER_RUNTIMES)})"
        )
    return name


def selected_docker_runtime(path: Path | None = None) -> DockerRuntimeName:
    """DEVBOOST_DOCKER_RUNTIME > ``docker_runtime`` in config.toml > colima (spec §4)."""
    env = Settings().docker_runtime
    if env:
        return parse_docker_runtime(env)
    return load_user_config(path).docker_runtime or DEFAULT_DOCKER_RUNTIME


def set_user_value(key: str, value: str, path: Path | None = None) -> None:
    """Set one key in config.toml, keeping the others. Refuses to write an invalid file.

    The file is rewritten with tomli-w, so comments in it are not preserved.
    """
    p = path if path is not None else config_path()
    data: dict[str, Any] = {}
    if p.exists():
        try:
            data = tomllib.loads(p.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"{p}: invalid TOML ({exc})") from exc
    data[key] = value
    try:
        UserConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"{p}: invalid value for {key}") from exc
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(tomli_w.dumps(data), encoding="utf-8")
    tmp.replace(p)
