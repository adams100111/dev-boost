from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from devboost.core.errors import ConfigError
from devboost.core.userconfig import (
    DOCKER_RUNTIMES,
    config_path,
    load_user_config,
    parse_docker_runtime,
    selected_docker_runtime,
    set_user_value,
)


def test_runtime_names() -> None:
    assert DOCKER_RUNTIMES == ("colima", "orbstack", "docker-desktop")


def test_default_is_colima() -> None:
    assert selected_docker_runtime() == "colima"


def test_config_file_beats_the_default(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text('docker_runtime = "orbstack"\n', encoding="utf-8")
    assert selected_docker_runtime(cfg) == "orbstack"


def test_env_beats_the_config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text('docker_runtime = "orbstack"\n', encoding="utf-8")
    monkeypatch.setenv("DEVBOOST_DOCKER_RUNTIME", "docker-desktop")
    assert selected_docker_runtime(cfg) == "docker-desktop"


def test_bad_env_value_is_a_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVBOOST_DOCKER_RUNTIME", "podman")
    with pytest.raises(ConfigError, match="unknown docker runtime 'podman'"):
        selected_docker_runtime()


def test_bad_config_value_is_a_config_error(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text('docker_runtime = "podman"\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="docker_runtime"):
        load_user_config(cfg)


def test_parse_accepts_every_runtime() -> None:
    for name in DOCKER_RUNTIMES:
        assert parse_docker_runtime(name) == name


def test_set_user_value_keeps_other_keys(tmp_path: Path) -> None:
    cfg = tmp_path / "devboost" / "config.toml"
    cfg.parent.mkdir()
    cfg.write_text('pass_repo = "me/store"\n', encoding="utf-8")
    set_user_value("docker_runtime", "orbstack", cfg)
    assert tomllib.loads(cfg.read_text(encoding="utf-8")) == {
        "pass_repo": "me/store",
        "docker_runtime": "orbstack",
    }
    assert [p.name for p in cfg.parent.iterdir()] == ["config.toml"]  # no temp file left


def test_set_user_value_refuses_an_invalid_value(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    with pytest.raises(ConfigError, match="docker_runtime"):
        set_user_value("docker_runtime", "podman", cfg)
    assert not cfg.exists()


def test_set_user_value_defaults_to_the_xdg_config_file() -> None:
    set_user_value("docker_runtime", "colima")
    assert load_user_config(config_path()).docker_runtime == "colima"


def test_set_user_value_keeps_the_file_mode(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text('pass_repo = "me/store"\n', encoding="utf-8")
    cfg.chmod(0o600)
    set_user_value("docker_runtime", "orbstack", cfg)
    assert cfg.stat().st_mode & 0o777 == 0o600


def test_set_user_value_names_the_offending_key(tmp_path: Path) -> None:
    """An invalid key already in the file is blamed, not the key being set."""
    cfg = tmp_path / "config.toml"
    cfg.write_text("device_name = 5\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="device_name") as err:
        set_user_value("docker_runtime", "colima", cfg)
    assert "docker_runtime" not in str(err.value)
    assert cfg.read_text(encoding="utf-8") == "device_name = 5\n"


def test_set_user_value_cleans_up_its_temp_file_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text('pass_repo = "me/store"\n', encoding="utf-8")

    def boom(*_a: object, **_k: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("devboost.core.userconfig.os.replace", boom)
    with pytest.raises(OSError, match="disk full"):
        set_user_value("docker_runtime", "orbstack", cfg)
    assert [p.name for p in tmp_path.iterdir()] == ["config.toml"]
    assert cfg.read_text(encoding="utf-8") == 'pass_repo = "me/store"\n'


def test_set_user_value_uses_a_unique_temp_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Concurrent writers never share a temp file: it comes from mkstemp in the same dir."""
    cfg = tmp_path / "config.toml"
    seen: list[str] = []
    real = __import__("tempfile").mkstemp

    def spy(*a: object, **k: object) -> tuple[int, str]:
        fd, name = real(*a, **k)
        seen.append(name)
        return fd, name

    monkeypatch.setattr("devboost.core.userconfig.tempfile.mkstemp", spy)
    set_user_value("docker_runtime", "orbstack", cfg)
    set_user_value("docker_runtime", "colima", cfg)
    assert len(seen) == 2 and seen[0] != seen[1]
    assert all(Path(n).parent == tmp_path for n in seen)
