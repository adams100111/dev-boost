# engine/tests/modules/test_codex_config.py
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.codex_config import CodexConfig

FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_merge_sets_prefs_and_preserves_device_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = tmp_path / ".codex" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        '[projects."/x"]\ntrust_level = "trusted"\n\n[mcp_servers.foo]\ncommand = "bar"\n',
        encoding="utf-8",
    )
    ctx = _ctx(present={"pass"}, scripts={"pass": Result(0, stdout="pk_secret_9\n")})
    CodexConfig().install(ctx)

    data = tomllib.loads(cfg.read_text(encoding="utf-8"))
    assert data["model"] == "gpt-5.6-sol"
    assert data["model_reasoning_effort"] == "low"
    assert data["features"]["hooks"] is True
    assert data["shell_environment_policy"]["inherit"] == "core"
    assert data["shell_environment_policy"]["set"]["CLICKUP_API_TOKEN"] == "pk_secret_9"
    # device state preserved untouched
    assert data["projects"]["/x"]["trust_level"] == "trusted"
    assert data["mcp_servers"]["foo"]["command"] == "bar"


def test_merge_degrades_without_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".codex").mkdir(parents=True)
    ctx = _ctx()  # pass absent
    CodexConfig().install(ctx)  # must not raise
    data = tomllib.loads((tmp_path / ".codex" / "config.toml").read_text(encoding="utf-8"))
    assert data["model"] == "gpt-5.6-sol"  # prefs still applied
    assert "set" not in data.get("shell_environment_policy", {})  # token skipped
