"""Contract for the seeded Zed config: strict JSON (so routine merges never touch a user's
commented edits), every required key present, extension ids = the spec's per-stack table."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

ZED = Path(__file__).resolve().parents[3] / "dotfiles" / "dot_config" / "zed"

#: The checked-in extension list (spec per-stack table; D9: opentofu, not terraform).
EXPECTED_EXTENSIONS = {
    "php", "blade", "csharp", "opentofu", "dockerfile", "docker-compose",
    "toml", "sql", "env", "make", "git-firefly", "tokyo-night",
}
ZED_DEFAULT_EXCLUSIONS = [
    "**/.git", "**/.svn", "**/.hg", "**/.jj", "**/.sl", "**/.repo", "**/CVS",
    "**/.DS_Store", "**/Thumbs.db", "**/.classpath", "**/.settings",
]
SPEC_EXCLUSIONS = [
    "**/node_modules", "**/vendor", "**/bin", "**/obj", "**/.venv", "**/.ddev", "**/.next",
    "**/dist", "**/.expo", "**/ios/Pods", "**/android/build", "**/public/build",
    "**/bootstrap/ssr",
]


@pytest.fixture(scope="module")
def settings() -> dict[str, Any]:
    text = (ZED / "create_settings.json").read_text(encoding="utf-8")
    no_urls = text.replace("https://", "")
    assert "//" not in no_urls and "/*" not in text, "seed must carry no comments"
    data = json.loads(text)  # strict JSON: no comments, no trailing commas
    assert isinstance(data, dict)
    return data


def test_keymap_seed_is_an_empty_array() -> None:
    assert json.loads((ZED / "create_keymap.json").read_text(encoding="utf-8")) == []


def test_extensions_match_the_checked_in_list(settings: dict[str, Any]) -> None:
    assert settings["auto_install_extensions"] == {e: True for e in EXPECTED_EXTENSIONS}


def test_agents_are_registry_entries_without_keys(settings: dict[str, Any]) -> None:
    assert settings["agent_servers"] == {
        "claude-acp": {"type": "registry"},
        "codex-acp": {"type": "registry"},
        "pi-acp": {"type": "registry"},
    }
    text = (ZED / "create_settings.json").read_text(encoding="utf-8").lower()
    assert "api_key" not in text and "token" not in text


def test_csharp_uses_csharp_ls(settings: dict[str, Any]) -> None:
    assert settings["languages"]["CSharp"]["language_servers"] == [
        "csharp-ls", "!roslyn", "!omnisharp", "...",
    ]


def test_php_uses_intelephense_and_blade_gets_tailwind(settings: dict[str, Any]) -> None:
    assert settings["languages"]["PHP"]["language_servers"][0] == "intelephense"
    assert "!phpactor" in settings["languages"]["PHP"]["language_servers"]
    blade_servers = settings["languages"]["Blade"]["language_servers"]
    assert blade_servers == ["tailwindcss-language-server", "..."]
    tw = settings["lsp"]["tailwindcss-language-server"]["settings"]
    assert tw["includeLanguages"] == {"php": "html", "blade": "html"}
    assert {"cn", "clsx", "cva", "tw"} <= set(tw["classFunctions"])


def test_web_eslint_fix_and_python_ruff_format(settings: dict[str, Any]) -> None:
    for lang in ("JavaScript", "TypeScript", "TSX"):
        code_actions = settings["languages"][lang]["code_actions_on_format"]
        assert code_actions == {"source.fixAll.eslint": True}
    assert settings["languages"]["Python"]["formatter"] == {"language_server": {"name": "ruff"}}


def test_telemetry_off(settings: dict[str, Any]) -> None:
    assert settings["telemetry"] == {"diagnostics": False, "metrics": False}


def test_vscode_feel_and_look(settings: dict[str, Any]) -> None:
    assert settings["base_keymap"] == "VSCode"
    theme = {"mode": "system", "dark": "Tokyo Night", "light": "Tokyo Night Light"}
    assert settings["theme"] == theme
    assert settings["buffer_font_family"] == "JetBrainsMono Nerd Font"
    assert settings["terminal"] == {"shell": "system", "font_family": "JetBrainsMono Nerd Font"}
    assert settings["project_panel"]["dock"] == "left"
    assert settings["minimap"]["show"] == "auto"
    assert settings["autosave"] == "on_focus_change"
    assert settings["format_on_save"] == "on"
    assert settings["inlay_hints"]["enabled"] is True
    assert settings["git"]["inline_blame"]["enabled"] is True
    assert settings["scrollbar"] == {"diagnostics": "all", "git_diff": True}
    assert settings["colorize_brackets"] is True


def test_scan_exclusions_restate_zed_defaults_then_spec(settings: dict[str, Any]) -> None:
    assert settings["file_scan_exclusions"] == ZED_DEFAULT_EXCLUSIONS + SPEC_EXCLUSIONS
