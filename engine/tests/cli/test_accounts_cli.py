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
    # OS-account check must see the user as absent so the test is host-independent.
    monkeypatch.setattr("devboost.exec.primitives.usermgmt.exists", lambda ctx, name: False)
    # --no-apply must not touch the system; it only persists the entry locally.
    monkeypatch.setattr("devboost.cli.accounts._save_local", lambda u: users.write_text(
        __import__("devboost.accounts.config", fromlist=["dump_users_toml"]).dump_users_toml(u),
        encoding="utf-8"))
    result = runner.invoke(app, ["accounts", "create", "dev", "--ram", "4G", "--no-apply"])
    assert result.exit_code == 0
    from devboost.accounts.config import load_users
    assert load_users(users)["dev"].ram == "4G"


def test_accounts_passwd_sets_password_via_primitive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from devboost.accounts.config import dump_users_toml
    from devboost.accounts.form import merge_flags

    dev = merge_flags(
        "dev", ram=None, cpu=None, disk=None, tasks=None, privilege="full",
        sudo_commands=(), shell="/bin/bash", lock_shell=False, linger=False,
        ssh_keys=(), bootstrap_profiles=(),
    )
    users = tmp_path / "users.toml"
    users.write_text(dump_users_toml({"dev": dev}), encoding="utf-8")
    monkeypatch.setenv("DEVBOOST_USERS_PATH", str(users))
    # getpass reads the tty, not stdin — stub it (new + confirm both return the same).
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "s3cret")
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "devboost.exec.primitives.usermgmt.set_password",
        lambda ctx, user, password: captured.update(user=user, password=password),
    )
    result = runner.invoke(app, ["accounts", "passwd", "dev"])
    assert result.exit_code == 0
    assert captured == {"user": "dev", "password": "s3cret"}


def test_accounts_passwd_unknown_user_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    users = tmp_path / "users.toml"
    users.write_text("", encoding="utf-8")
    monkeypatch.setenv("DEVBOOST_USERS_PATH", str(users))
    assert runner.invoke(app, ["accounts", "passwd", "ghost"]).exit_code == 2


def test_accounts_apply_unknown_user_exits_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    users = tmp_path / "users.toml"
    users.write_text("", encoding="utf-8")  # empty registry — no managed users
    monkeypatch.setenv("DEVBOOST_USERS_PATH", str(users))
    result = runner.invoke(app, ["accounts", "apply", "nope"])
    assert result.exit_code == 2
