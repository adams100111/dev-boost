"""Engine configuration from DEVBOOST_* env (pydantic-settings)."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from devboost.exec.resources import resource_root


def _default_root() -> Path:
    # Repo root in source mode; _MEIPASS (bundled data) in the frozen binary.
    return resource_root()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DEVBOOST_")

    root: Path = _default_root()
    #: DEVBOOST_DOCKER_RUNTIME — deliberately a plain str: `settings = Settings()` runs at
    #: import, so a Literal here would turn a typo into a traceback on every command.
    #: userconfig.selected_docker_runtime() validates it.
    docker_runtime: str | None = None

    @property
    def profiles_path(self) -> Path:
        return self.root / "profiles.toml"

    @property
    def catalog_path(self) -> Path:
        return self.root / "catalog.toml"


settings = Settings()
