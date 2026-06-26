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

    @property
    def profiles_path(self) -> Path:
        return self.root / "profiles.toml"


settings = Settings()
