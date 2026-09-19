from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.errors import ConfigError
from devboost.core.userconfig import DEFAULT_PASS_REPO, config_path, load_user_config


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    cfg = load_user_config(tmp_path / "absent.toml")
    assert cfg.pass_repo == DEFAULT_PASS_REPO == "adams100111/password-store"
    assert cfg.device_name is None


def test_values_and_unknown_keys(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text('pass_repo = "me/store"\ndevice_name = "lap"\nother = 1\n', encoding="utf-8")
    cfg = load_user_config(p)
    assert (cfg.pass_repo, cfg.device_name) == ("me/store", "lap")


def test_invalid_toml_is_config_error(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text("pass_repo = \n", encoding="utf-8")
    with pytest.raises(ConfigError, match="config.toml"):
        load_user_config(p)


def test_wrong_type_is_config_error(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text("pass_repo = 3\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="pass_repo"):
        load_user_config(p)


def test_config_path_honours_xdg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert config_path() == tmp_path / "xdg" / "devboost" / "config.toml"
    monkeypatch.delenv("XDG_CONFIG_HOME")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert config_path() == tmp_path / ".config" / "devboost" / "config.toml"
