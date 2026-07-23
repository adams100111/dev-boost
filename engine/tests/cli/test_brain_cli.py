from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from devboost.cli.app import app

runner = CliRunner()


def test_brain_dry_run_no_apply_persists_devbrain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    users = tmp_path / "users.toml"
    monkeypatch.setenv("DEVBOOST_USERS_PATH", str(users))
    # reconcile.save always shells out (sudo install -d / sudo tee), even under --dry-run —
    # dry_run only short-circuits module installs inside run_plan, not this direct write.
    # Stub it to a plain local write so the test never invokes sudo.
    from devboost.accounts import reconcile
    from devboost.accounts.config import dump_users_toml

    monkeypatch.setattr(
        reconcile,
        "save",
        lambda ctx, users_map: users.write_text(
            dump_users_toml(users_map), encoding="utf-8"
        ),
    )
    # --dry-run makes the brain-host install a no-op; --no-apply skips reconcile.apply_user.
    result = runner.invoke(
        app, ["brain", "--dry-run", "--no-apply", "--ssh-key", "ssh-ed25519 K me"]
    )
    assert result.exit_code == 0, result.stdout

    from devboost.accounts.config import load_users

    u = load_users()["devbrain"]
    assert u.privilege == "none"
    assert u.bootstrap_profiles == ("brain-tools",)
    assert u.linger is True
    assert u.ssh_authorized_keys == ("ssh-ed25519 K me",)


def test_brain_help_lists_it() -> None:
    result = runner.invoke(app, ["brain", "--help"])
    assert result.exit_code == 0
    assert "devbrain" in result.stdout.lower() or "brain" in result.stdout.lower()
