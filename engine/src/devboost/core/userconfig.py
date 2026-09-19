"""Per-user dev-boost preferences: ``~/.config/devboost/config.toml``.

Distinct from ``core/settings.py`` (engine env, ``DEVBOOST_*``): this file holds choices a
person makes once per account (which pass repo, what this device is called). Env vars
still win where a module documents one (e.g. ``DEVBOOST_PASS_REPO``).
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from devboost.core.errors import ConfigError

DEFAULT_PASS_REPO = "adams100111/password-store"


class UserConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    pass_repo: str = DEFAULT_PASS_REPO
    device_name: str | None = None


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
