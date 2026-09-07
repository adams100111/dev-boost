from __future__ import annotations

import json
from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules.claude_plugins import ENABLED_PLUGINS, MARKETPLACES, ClaudePlugins

FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_clickup_marketplace_is_github_not_directory() -> None:
    src = MARKETPLACES["clickup-flow-marketplace"]
    assert src == {"source": "github", "repo": "adams100111/clickup-flow"}
    assert not any(v.get("source") == "directory" for v in MARKETPLACES.values())


def test_merge_preserves_existing_and_adds_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")

    ClaudePlugins()._merge_settings(_ctx())

    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["theme"] == "dark"  # preserved
    clickup = data["extraKnownMarketplaces"]["clickup-flow-marketplace"]
    assert clickup["source"]["source"] == "github"  # schema nests source: {source, repo}
    assert clickup["source"]["repo"] == "adams100111/clickup-flow"
    for plugin in ENABLED_PLUGINS:
        assert data["enabledPlugins"][plugin] is True


def test_merge_leaves_invalid_json_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{ broken", encoding="utf-8")
    ClaudePlugins()._merge_settings(_ctx())
    assert settings.read_text(encoding="utf-8") == "{ broken"
