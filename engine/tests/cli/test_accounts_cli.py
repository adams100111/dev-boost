# engine/tests/cli/test_accounts_cli.py
from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from devboost.cli.app import app

runner = CliRunner()


def test_accounts_subapp_registered() -> None:
    result = runner.invoke(app, ["accounts", "--help"])
    assert result.exit_code == 0
    for verb in ("create", "list", "edit", "disable", "enable", "delete", "apply"):
        assert verb in result.output


def test_accounts_create_writes_entry_with_no_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    users = tmp_path / "users.toml"
    monkeypatch.setenv("DEVBOOST_USERS_PATH", str(users))
    # --no-apply must not touch the system; it only persists the entry locally.
    monkeypatch.setattr("devboost.cli.accounts._save_local", lambda u: users.write_text(
        __import__("devboost.accounts.config", fromlist=["dump_users_toml"]).dump_users_toml(u),
        encoding="utf-8"))
    result = runner.invoke(app, ["accounts", "create", "dev", "--ram", "4G", "--no-apply"])
    assert result.exit_code == 0
    from devboost.accounts.config import load_users
    assert load_users(users)["dev"].ram == "4G"
