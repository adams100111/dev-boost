from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from devboost.exec.primitives import config, fs
from devboost.model import Ctx


def test_json_merge_creates_and_merges(fedora_ctx: Ctx, tmp_path: Path) -> None:
    p = tmp_path / "sub" / "cfg.json"
    config.json_merge(fedora_ctx, str(p), {"a": 1})
    config.json_merge(fedora_ctx, str(p), {"b": 2})
    assert json.loads(p.read_text()) == {"a": 1, "b": 2}


def test_json_merge_reports_change_and_noop(fedora_ctx: Ctx, tmp_path: Path) -> None:
    p = tmp_path / "cfg.json"
    assert config.json_merge(fedora_ctx, str(p), {"a": 1}) is True   # created
    assert config.json_merge(fedora_ctx, str(p), {"a": 1}) is False  # unchanged


def test_json_merge_preserves_sibling_keys(fedora_ctx: Ctx, tmp_path: Path) -> None:
    # models daemon.json already carrying an nvidia runtime — the merge must not clobber it.
    p = tmp_path / "daemon.json"
    p.write_text(
        '{"runtimes": {"nvidia": {"path": "nvidia-container-runtime"}}}\n', encoding="utf-8"
    )
    changed = config.json_merge(fedora_ctx, str(p), {"builder": {"gc": {"enabled": True}}})
    assert changed is True
    data = json.loads(p.read_text())
    assert data["runtimes"] == {"nvidia": {"path": "nvidia-container-runtime"}}
    assert data["builder"] == {"gc": {"enabled": True}}


def test_json_merge_routes_privileged_write_when_unwritable(
    fedora_ctx: Ctx, tmp_path: Path
) -> None:
    p = tmp_path / "daemon.json"
    p.write_text("{}\n", encoding="utf-8")
    p.chmod(0o444)
    if os.access(str(p), os.W_OK):  # running as root: W_OK ignores mode → can't exercise
        p.chmod(0o644)
        pytest.skip("running as root; the unwritable branch can't be exercised")
    try:
        assert config.json_merge(fedora_ctx, str(p), {"builder": {"gc": {"enabled": True}}}) is True
    finally:
        p.chmod(0o644)
    calls = fedora_ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "tee", str(p)] in calls  # unwritable → routed through the executor


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
