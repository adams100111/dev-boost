from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from devboost.cli.app import app

runner = CliRunner()


def _spies(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, list[Any]]:
    calls: dict[str, list[Any]] = {"run": [], "save": [], "apply": []}
    monkeypatch.setenv("DEVBOOST_USERS_PATH", str(tmp_path / "users.toml"))

    def fake_run(tokens: Any, root: Any, dry_run: Any, force: Any, *a: Any, **k: Any) -> list[Any]:
        calls["run"].append((tokens, dry_run))
        return []

    monkeypatch.setattr("devboost.cli.app._run", fake_run)
    monkeypatch.setattr(
        "devboost.accounts.reconcile.save",
        lambda ctx, users: calls["save"].append(dict(users)),
    )
    monkeypatch.setattr(
        "devboost.accounts.reconcile.apply_user",
        lambda ctx, user, **k: calls["apply"].append(user),
    )
    return calls


def test_brain_no_apply_saves_but_does_not_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _spies(monkeypatch, tmp_path)
    result = runner.invoke(app, ["brain", "--no-apply", "--ssh-key", "ssh-ed25519 K me"])
    assert result.exit_code == 0, result.stdout
    assert calls["run"] and calls["run"][0][0] == ["brain-host"]
    assert len(calls["save"]) == 1
    saved = calls["save"][0]["devbrain"]
    assert saved.privilege == "none"
    assert saved.bootstrap_profiles == ("brain-tools",)
    assert saved.linger is True
    assert saved.ssh_authorized_keys == ("ssh-ed25519 K me",)
    assert calls["apply"] == []  # --no-apply skips apply


def test_brain_default_saves_and_applies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _spies(monkeypatch, tmp_path)
    result = runner.invoke(app, ["brain", "--ssh-key", "ssh-ed25519 K me"])
    assert result.exit_code == 0, result.stdout
    assert len(calls["save"]) == 1
    assert len(calls["apply"]) == 1  # default applies


def test_brain_dry_run_is_pure_preview(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _spies(monkeypatch, tmp_path)
    result = runner.invoke(app, ["brain", "--dry-run"])
    assert result.exit_code == 0, result.stdout
    assert calls["run"] and calls["run"][0][1] is True  # _run received dry_run=True
    assert calls["save"] == []  # dry-run: no persistence
    assert calls["apply"] == []  # dry-run: no apply


def test_brain_help_lists_it() -> None:
    result = runner.invoke(app, ["brain", "--help"])
    assert result.exit_code == 0
