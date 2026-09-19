from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from devboost.core.errors import NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.exec.primitives import config
from devboost.model import Ctx

CTX = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor())

COMMENTED = """// Zed settings
{
  /* my font */
  "buffer_font_size": 15,
  "url": "https://example.com/a//b", // a URL is not a comment
  "glob": "/* not a comment */",
  "trail": "a,]",
  "auto_install_extensions": {"mine": true,},
  "lsp": {"rust-analyzer": {"settings": {"check": "clippy"}}},
}
"""


def test_strip_jsonc_keeps_strings_and_drops_comments_and_trailing_commas() -> None:
    data = json.loads(config.strip_jsonc(COMMENTED))
    assert data["url"] == "https://example.com/a//b"
    assert data["glob"] == "/* not a comment */"
    assert data["trail"] == "a,]"
    assert data["auto_install_extensions"] == {"mine": True}


def test_strip_jsonc_handles_escaped_quotes() -> None:
    text = '{"a": "say \\"hi\\" // not a comment", "b": 1,}'
    assert json.loads(config.strip_jsonc(text)) == {"a": 'say "hi" // not a comment', "b": 1}


def test_deep_merge_recurses_and_patch_leaves_win() -> None:
    base = {"a": {"x": 1, "keep": True}, "list": [1], "user": "mine"}
    patch = {"a": {"x": 2}, "list": [9], "new": {"k": "v"}}
    assert config.deep_merge(base, patch) == {
        "a": {"x": 2, "keep": True}, "list": [9], "user": "mine", "new": {"k": "v"},
    }
    assert base == {"a": {"x": 1, "keep": True}, "list": [1], "user": "mine"}  # not mutated


def test_merge_preserves_nested_user_keys(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    p.write_text(COMMENTED, encoding="utf-8")
    patch = {
        "auto_install_extensions": {"php": True},
        "lsp": {"rust-analyzer": {"binary": {"path": "/x"}}},
    }
    assert config.jsonc_merge_deep(CTX, str(p), patch) is True
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["auto_install_extensions"] == {"mine": True, "php": True}
    assert data["lsp"]["rust-analyzer"] == {
        "settings": {"check": "clippy"}, "binary": {"path": "/x"},
    }
    assert data["buffer_font_size"] == 15


def test_needed_change_writes_backup_of_original_bytes(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    p.write_text(COMMENTED, encoding="utf-8")
    config.jsonc_merge_deep(CTX, str(p), {"telemetry": {"metrics": False}})
    bak = tmp_path / "settings.json.devboost-bak"
    assert bak.read_text(encoding="utf-8") == COMMENTED
    assert not (tmp_path / "settings.json.devboost-tmp").exists()


def test_noop_leaves_commented_file_byte_identical(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    p.write_text(COMMENTED, encoding="utf-8")
    patch = {"auto_install_extensions": {"mine": True}}
    assert config.jsonc_merge_deep(CTX, str(p), patch) is False
    assert p.read_text(encoding="utf-8") == COMMENTED
    assert not (tmp_path / "settings.json.devboost-bak").exists()


def test_merge_is_idempotent(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    p.write_text("{}", encoding="utf-8")
    patch = {"agent_servers": {"claude-acp": {"type": "registry"}}}
    assert config.jsonc_merge_deep(CTX, str(p), patch) is True
    first = p.read_text(encoding="utf-8")
    assert config.jsonc_merge_deep(CTX, str(p), patch) is False
    assert p.read_text(encoding="utf-8") == first


def test_absent_file_is_created_without_backup(tmp_path: Path) -> None:
    p = tmp_path / "zed" / "settings.json"
    assert config.jsonc_merge_deep(CTX, str(p), {"telemetry": {"metrics": False}}) is True
    assert json.loads(p.read_text(encoding="utf-8")) == {"telemetry": {"metrics": False}}
    assert not (tmp_path / "zed" / "settings.json.devboost-bak").exists()


@pytest.mark.parametrize("body", ['{"a": ', "[1, 2]", "/* unterminated {"])
def test_unparseable_raises_needs_user_with_keys_and_never_rewrites(
    tmp_path: Path, body: str
) -> None:
    p = tmp_path / "settings.json"
    p.write_text(body, encoding="utf-8")
    patch = {"telemetry": {"metrics": False, "diagnostics": False}}
    with pytest.raises(NeedsUser) as exc:
        config.jsonc_merge_deep(CTX, str(p), patch)
    assert "telemetry.metrics" in exc.value.how_to_fix
    assert "telemetry.diagnostics" in exc.value.how_to_fix
    assert p.read_text(encoding="utf-8") == body


def test_jsonc_satisfies(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    assert config.jsonc_satisfies(str(p), {"a": 1}) is False  # absent
    p.write_text('{"a": 1, "b": {"c": 2}} // ok', encoding="utf-8")
    assert config.jsonc_satisfies(str(p), {"a": 1, "b": {"c": 2}}) is True
    assert config.jsonc_satisfies(str(p), {"b": {"d": 3}}) is False
    p.write_text("{nope", encoding="utf-8")
    assert config.jsonc_satisfies(str(p), {"a": 1}) is False


def test_backup_not_overwritten_when_raw_has_no_comments_or_trailing_commas(tmp_path: Path) -> None:
    """Z-R4: a plain-JSON file (no comments/trailing commas) doesn't get backed up on a
    rewrite, once a backup already exists — an uncommented file must never clobber a
    previously saved backup of the user's original commented file."""
    p = tmp_path / "settings.json"
    p.write_text('{"a": 1}', encoding="utf-8")
    bak = tmp_path / "settings.json.devboost-bak"
    bak.write_text(COMMENTED, encoding="utf-8")  # pre-existing backup of the real original
    assert config.jsonc_merge_deep(CTX, str(p), {"b": 2}) is True
    assert bak.read_text(encoding="utf-8") == COMMENTED  # untouched


def test_backup_written_for_plain_json_when_none_exists_yet(tmp_path: Path) -> None:
    """Z-R4: even a plain-JSON file (no comments) gets a first backup when none exists yet."""
    p = tmp_path / "settings.json"
    p.write_text('{"a": 1}', encoding="utf-8")
    bak = tmp_path / "settings.json.devboost-bak"
    assert not bak.exists()
    assert config.jsonc_merge_deep(CTX, str(p), {"b": 2}) is True
    assert bak.read_text(encoding="utf-8") == '{"a": 1}'


def test_undecodable_file_raises_needs_user_with_keys_and_never_rewrites(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    body = b'{"font": "caf\xe9"}'  # latin-1, not UTF-8
    p.write_bytes(body)
    with pytest.raises(NeedsUser) as exc:
        config.jsonc_merge_deep(CTX, str(p), {"telemetry": {"metrics": False}})
    assert "telemetry.metrics" in exc.value.how_to_fix
    assert p.read_bytes() == body
    assert not (tmp_path / "settings.json.devboost-bak").exists()


def test_symlinked_file_is_written_through_and_the_link_kept(tmp_path: Path) -> None:
    real = tmp_path / "dotfiles" / "settings.json"
    real.parent.mkdir()
    real.write_text('{"a": 1}', encoding="utf-8")
    link = tmp_path / "zed" / "settings.json"
    link.parent.mkdir()
    link.symlink_to(real)
    assert config.jsonc_merge_deep(CTX, str(link), {"b": 2}) is True
    assert link.is_symlink() and link.resolve() == real.resolve()
    assert json.loads(real.read_text(encoding="utf-8")) == {"a": 1, "b": 2}
    assert not list(real.parent.glob("*.devboost-tmp"))


def test_rewrite_keeps_the_original_file_mode(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    p.write_text('{"a": 1}', encoding="utf-8")
    p.chmod(0o600)
    assert config.jsonc_merge_deep(CTX, str(p), {"b": 2}) is True
    assert p.stat().st_mode & 0o777 == 0o600


def test_non_ascii_round_trips_unescaped(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    p.write_text('{"ui_font_family": "Noto Sans 日本語", "x": "café"}', encoding="utf-8")
    assert config.jsonc_merge_deep(CTX, str(p), {"b": 2}) is True
    text = p.read_text(encoding="utf-8")
    assert "日本語" in text and "café" in text and "\\u" not in text
    assert json.loads(text)["ui_font_family"] == "Noto Sans 日本語"


def test_failed_write_leaves_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = tmp_path / "settings.json"
    p.write_text('{"a": 1}', encoding="utf-8")

    def _denied(*_: object) -> None:
        raise PermissionError(13, "Permission denied", str(p))

    monkeypatch.setattr(os, "replace", _denied)
    with pytest.raises(PermissionError):
        config.jsonc_merge_deep(CTX, str(p), {"b": 2})
    assert p.read_text(encoding="utf-8") == '{"a": 1}'
    assert not (tmp_path / "settings.json.devboost-tmp").exists()
