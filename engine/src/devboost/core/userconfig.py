"""Per-user dev-boost preferences: ``~/.config/devboost/config.toml``.

Distinct from ``core/settings.py`` (engine env, ``DEVBOOST_*``): this file holds choices a
person makes once per account (which pass repo, what this device is called). Env vars
still win where a module documents one (e.g. ``DEVBOOST_PASS_REPO``).
"""

from __future__ import annotations

import os
import stat
import tempfile
import tomllib
from pathlib import Path
from typing import Any, Literal

import tomli_w
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from devboost.core.errors import ConfigError
from devboost.core.settings import Settings

#: No default: a pass store is personal, and shipping one person's repo as the
#: fallback makes every other install try to clone a repo it cannot read. Unset
#: means "discover it from an existing clone, else ask" (passstore.paths.pass_repo).

DockerRuntimeName = Literal["colima", "orbstack", "docker-desktop"]
DOCKER_RUNTIMES: tuple[DockerRuntimeName, ...] = ("colima", "orbstack", "docker-desktop")
DEFAULT_DOCKER_RUNTIME: DockerRuntimeName = "colima"
_RUNTIME_BY_NAME: dict[str, DockerRuntimeName] = {n: n for n in DOCKER_RUNTIMES}


class UserConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    pass_repo: str | None = None
    #: Extra Claude/Codex plugin marketplaces: name -> "owner/repo". Anything private or
    #: personal belongs here, never in the shipped defaults — those must be reachable by
    #: everyone who installs dev-boost.
    extra_marketplaces: dict[str, str] = Field(default_factory=dict)
    #: Extra plugins to enable, each "plugin@marketplace".
    extra_plugins: tuple[str, ...] = ()
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
        raise ConfigError(f"{p}: invalid value for {_invalid_fields(exc)}") from exc


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


def _invalid_fields(exc: ValidationError) -> str:
    return ", ".join(str(e["loc"][0]) for e in exc.errors() if e["loc"])


def set_user_value(key: str, value: str, path: Path | None = None) -> None:
    """Set one key in config.toml, keeping the others. Refuses to write an invalid file.

    The new file is written to a unique temp file in the same directory, fsynced, given
    the old file's mode and renamed over it, so a reader never sees a partial file. It is
    rewritten with tomli-w, so comments in it are not preserved.
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
        raise ConfigError(f"{p}: invalid value for {_invalid_fields(exc)}") from exc
    p.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(p.stat().st_mode) if p.exists() else None
    fd, tmp_name = tempfile.mkstemp(dir=p.parent, prefix=f".{p.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(tomli_w.dumps(data))
            fh.flush()
            os.fsync(fh.fileno())
        tmp.chmod(mode if mode is not None else 0o644)
        os.replace(tmp, p)
    finally:
        tmp.unlink(missing_ok=True)
