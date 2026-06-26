from __future__ import annotations

import json
from pathlib import Path

from devboost.exec.primitives import config, fs
from devboost.model import Ctx


def test_json_merge_creates_and_merges(fedora_ctx: Ctx, tmp_path: Path) -> None:
    p = tmp_path / "sub" / "cfg.json"
    config.json_merge(fedora_ctx, str(p), {"a": 1})
    config.json_merge(fedora_ctx, str(p), {"b": 2})
    assert json.loads(p.read_text()) == {"a": 1, "b": 2}


def test_json_merge_is_idempotent(fedora_ctx: Ctx, tmp_path: Path) -> None:
    p = tmp_path / "cfg.json"
    config.json_merge(fedora_ctx, str(p), {"a": 1})
    before = p.stat().st_mtime_ns
    config.json_merge(fedora_ctx, str(p), {"a": 1})  # no change
    assert json.loads(p.read_text()) == {"a": 1}
    assert p.stat().st_mtime_ns == before  # not rewritten


def test_ensure_line_appends_once(fedora_ctx: Ctx, tmp_path: Path) -> None:
    p = tmp_path / "rc"
    config.ensure_line(fedora_ctx, str(p), "export X=1")
    config.ensure_line(fedora_ctx, str(p), "export X=1")
    assert p.read_text().count("export X=1") == 1


def test_fs_write_and_exists(fedora_ctx: Ctx, tmp_path: Path) -> None:
    p = tmp_path / "d" / "f.txt"
    assert fs.exists(fedora_ctx, str(p)) is False
    fs.write(fedora_ctx, str(p), "hi")
    assert fs.exists(fedora_ctx, str(p)) is True
    assert p.read_text() == "hi"
