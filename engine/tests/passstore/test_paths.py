from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.errors import ConfigError
from devboost.core.userconfig import UserConfig
from devboost.passstore import paths


def test_pass_repo_env_beats_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEVBOOST_PASS_REPO", raising=False)
    assert paths.pass_repo(UserConfig(pass_repo="me/cfg")) == "me/cfg"
    monkeypatch.setenv("DEVBOOST_PASS_REPO", "me/env")
    assert paths.pass_repo(UserConfig(pass_repo="me/cfg")) == "me/env"


def test_clone_url_shapes() -> None:
    assert paths.clone_url("me/store") == "https://github.com/me/store.git"
    assert paths.clone_url("git@github.com:me/s.git") == "git@github.com:me/s.git"
    assert paths.clone_url("https://example.com/s.git") == "https://example.com/s.git"
    assert paths.clone_url("/srv/store.git") == "/srv/store.git"


def test_store_and_state_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("PASSWORD_STORE_DIR", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    assert paths.store_dir() == tmp_path / ".password-store"
    assert paths.state_dir() == tmp_path / ".local" / "state" / "devboost"
    monkeypatch.setenv("PASSWORD_STORE_DIR", str(tmp_path / "ps"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "st"))
    assert paths.store_dir() == tmp_path / "ps"
    assert paths.state_dir() == tmp_path / "st" / "devboost"


def test_device_name_default_and_config() -> None:
    assert (
        paths.device_name(UserConfig(), hostname="Work-Laptop.local")
        == "work-laptop"
    )
    assert (
        paths.device_name(UserConfig(device_name="Desk 1"), hostname="x")
        == "desk-1"
    )


def test_sanitize_rejects_empty() -> None:
    with pytest.raises(ConfigError, match="device_name"):
        paths.sanitize_name("...")


def test_devboost_bin_prefers_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("devboost.passstore.paths.is_frozen", lambda: False)
    monkeypatch.setattr(
        "devboost.passstore.paths.shutil.which",
        lambda _c: "/home/u/.local/bin/devboost",
    )
    assert paths.devboost_bin() == "/home/u/.local/bin/devboost"
    monkeypatch.setattr("devboost.passstore.paths.shutil.which", lambda _c: None)
    assert paths.devboost_bin() == "devboost"


def test_no_repo_configured_is_none_not_someone_elses_store(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """dev-boost used to fall back to its author's private repo, so every other install
    tried to clone a store it could not read."""
    monkeypatch.delenv("DEVBOOST_PASS_REPO", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PASSWORD_STORE_DIR", str(tmp_path / "nope"))
    assert paths.pass_repo(UserConfig()) is None


def test_an_existing_clone_supplies_its_own_repo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A machine that already has the store needs no configuration: read its origin."""
    monkeypatch.delenv("DEVBOOST_PASS_REPO", raising=False)
    root = tmp_path / "store"
    (root / ".git").mkdir(parents=True)
    (root / ".git" / "config").write_text(
        '[core]\n\trepositoryformatversion = 0\n'
        '[remote "origin"]\n\turl = https://github.com/someone/their-store.git\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("PASSWORD_STORE_DIR", str(root))
    assert paths.pass_repo(UserConfig()) == "https://github.com/someone/their-store.git"
    assert paths.origin_url(tmp_path / "absent") is None
