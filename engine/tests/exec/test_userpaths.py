"""One answer for where mise's shims and the user .NET SDK live."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from devboost.exec import userpaths
from devboost.exec.executor import _prepend_mise_dirs
from devboost.modules import _zed


def test_mise_shims_prefer_mise_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MISE_DATA_DIR", str(tmp_path / "m"))
    assert userpaths.mise_shims(tmp_path) == tmp_path / "m" / "shims"


def test_mise_shims_then_xdg_data_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "x"))
    assert userpaths.mise_shims(tmp_path) == tmp_path / "x" / "mise" / "shims"


def test_mise_shims_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", "")  # empty counts as unset, as in mise
    assert userpaths.mise_shims(tmp_path) == tmp_path / ".local" / "share" / "mise" / "shims"


def test_executor_path_uses_the_resolved_shims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("MISE_DATA_DIR", str(tmp_path / "m"))
    parts = _prepend_mise_dirs("/usr/bin", system="Linux").split(os.pathsep)
    assert parts[0] == str(tmp_path / "m" / "shims")
    assert str(tmp_path / ".local" / "share" / "mise" / "shims") not in parts


def test_darwin_path_has_the_user_dotnet_sdk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    dotnet = str(tmp_path / ".dotnet")
    mac = _prepend_mise_dirs("/usr/bin", system="Darwin").split(os.pathsep)
    assert mac.index(str(tmp_path / ".dotnet" / "tools")) < mac.index(dotnet)
    assert mac.index(dotnet) < mac.index("/opt/homebrew/bin") < mac.index("/usr/bin")
    assert dotnet not in _prepend_mise_dirs("/usr/bin", system="Linux").split(os.pathsep)


def test_zed_reuses_the_shared_helper() -> None:
    assert _zed.mise_shims is userpaths.mise_shims
    assert userpaths.dotnet_root(Path("/h")) == Path("/h/.dotnet")
