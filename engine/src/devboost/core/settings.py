"""Engine configuration from DEVBOOST_* env (pydantic-settings)."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_root() -> Path:
    return Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DEVBOOST_")

    root: Path = _default_root()

    @property
    def profiles_path(self) -> Path:
        return self.root / "profiles.toml"


settings = Settings()
