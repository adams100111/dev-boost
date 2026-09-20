from __future__ import annotations

import json
from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.core.userconfig import UserConfig
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules.claude_plugins import (
    ENABLED_PLUGINS,
    MARKETPLACES,
    ClaudePlugins,
    enabled_plugins,
    marketplaces,
)

FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def _enable_clickup(home: Path) -> None:
    """Opt in to the (private) clickup-flow plugin the way a user would."""
    cfg = home / ".config" / "devboost" / "config.toml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(
        'extra_marketplaces = { clickup-flow-marketplace = "adams100111/clickup-flow" }\n'
        'extra_plugins = ["clickup-flow@clickup-flow-marketplace"]\n',
        encoding="utf-8",
    )


def test_every_shipped_marketplace_is_public_and_not_a_local_directory() -> None:
    """A private or personal marketplace in the shipped list makes every OTHER install try
    to register a repo it cannot read. Those belong in `extra_marketplaces`."""
    assert not any(v.get("source") == "directory" for v in MARKETPLACES.values())
    shipped = {v["repo"] for v in MARKETPLACES.values()}
    # clickup-flow is private: shipping it meant every other install tried to register a
    # repo it cannot read. qa-e2e-pilot and wave-pilot share an owner but are public, so
    # they stay — the rule is "reachable by everyone", not "not this person's".
    assert "adams100111/clickup-flow" not in shipped


def test_a_users_own_marketplace_and_plugin_are_merged_in() -> None:
    cfg = UserConfig(
        extra_marketplaces={"mine": "someone/their-market"},
        extra_plugins=("thing@mine",),
    )
    assert marketplaces(cfg)["mine"] == {"source": "github", "repo": "someone/their-market"}
    assert enabled_plugins(cfg)[-1] == "thing@mine"
    assert set(ENABLED_PLUGINS) <= set(enabled_plugins(cfg))


def test_a_users_marketplace_wins_a_name_clash() -> None:
    cfg = UserConfig(extra_marketplaces={"zoom-skills": "me/fork"})
    assert marketplaces(cfg)["zoom-skills"]["repo"] == "me/fork"


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
    zoom = data["extraKnownMarketplaces"]["zoom-skills"]
    assert zoom["source"]["source"] == "github"  # schema nests source: {source, repo}
    assert zoom["source"]["repo"] == "zoom/skills"
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


def test_install_plugins_adds_only_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    from devboost.exec.executor import Result

    # `claude plugin list --json` reports superpowers already installed → it is skipped.
    ctx = _ctx(
        present={"claude"},
        scripts={
            "claude": Result(
                0, stdout='[{"name":"superpowers","marketplace":"claude-plugins-official"}]'
            )
        },
    )
    ClaudePlugins()._install_plugins(ctx)
    joined = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    install_calls = [j for j in joined if "plugin install" in j]
    assert any(
        "ui-ux-pro-max@ui-ux-pro-max-skill" in j and "--yes" in j for j in install_calls
    )
    assert not any("superpowers@claude-plugins-official" in j for j in install_calls)


def test_install_plugins_noop_without_claude(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = _ctx()  # claude not present
    ClaudePlugins()._install_plugins(ctx)
    assert not any("plugin install" in " ".join(c) for c in ctx.ex.calls)  # type: ignore[attr-defined]


def test_clickup_token_written_to_settings_json_preserving_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    from devboost.exec.executor import Result

    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    # pre-existing settings (e.g. from _merge_settings) must be preserved
    settings.write_text(json.dumps({"theme": "dark", "env": {"OTHER": "keep"}}), encoding="utf-8")
    _enable_clickup(tmp_path)
    ctx = _ctx(present={"pass"}, scripts={"pass": Result(0, stdout="pk_secret_123\n")})
    ClaudePlugins()._resolve_clickup_token(ctx)

    data = json.loads(settings.read_text(encoding="utf-8"))
    # Claude Code reads env from the user-global settings.json (no user-level settings.local.json)
    assert data["env"]["CLICKUP_API_TOKEN"] == "pk_secret_123"
    assert data["env"]["OTHER"] == "keep"  # other env preserved
    assert data["theme"] == "dark"  # other keys preserved


def test_clickup_token_absent_pass_degrades(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = _ctx()  # pass not present
    ClaudePlugins()._resolve_clickup_token(ctx)  # must not raise
    assert not (tmp_path / ".claude" / "settings.json").exists()
