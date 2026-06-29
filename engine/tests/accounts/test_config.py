from __future__ import annotations

from pathlib import Path

import pytest

from devboost.accounts.config import (
    AccountsError,
    ManagedUser,
    dump_users_toml,
    load_users,
    users_path,
)


def test_users_path_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DEVBOOST_USERS_PATH", str(tmp_path / "u.toml"))
    assert users_path() == tmp_path / "u.toml"


def test_users_path_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEVBOOST_USERS_PATH", raising=False)
    assert users_path() == Path("/etc/devboost/users.toml")


def test_load_users_parses_and_defaults(tmp_path: Path) -> None:
    p = tmp_path / "u.toml"
    p.write_text(
        '[users.dev]\nram = "4G"\ncpu = "50%"\ntasks = 200\nprivilege = "nopasswd"\n',
        encoding="utf-8",
    )
    users = load_users(p)
    assert set(users) == {"dev"}
    dev = users["dev"]
    assert dev == ManagedUser(
        name="dev", enabled=True, shell="/bin/bash", lock_shell=False, linger=False,
        privilege="nopasswd", sudo_commands=(), ram="4G", cpu="50%", tasks=200,
        disk=None, ssh_authorized_keys=(), bootstrap_profiles=(),
    )


def test_load_users_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_users(tmp_path / "nope.toml") == {}


def test_load_users_rejects_bad_cpu(tmp_path: Path) -> None:
    p = tmp_path / "u.toml"
    p.write_text('[users.dev]\ncpu = "fast"\n', encoding="utf-8")
    with pytest.raises(AccountsError, match="dev"):
        load_users(p)


def test_load_users_rejects_relative_sudo_command(tmp_path: Path) -> None:
    p = tmp_path / "u.toml"
    p.write_text('[users.dev]\nprivilege = "allowlist"\nsudo_commands = ["systemctl restart x"]\n',
                 encoding="utf-8")
    with pytest.raises(AccountsError, match="absolute"):
        load_users(p)


def test_dump_then_load_roundtrips(tmp_path: Path) -> None:
    u = ManagedUser(
        name="dev", enabled=False, shell="/bin/bash", lock_shell=True, linger=True,
        privilege="allowlist", sudo_commands=("/usr/bin/systemctl restart x",),
        ram="2G", cpu="25%", tasks=100, disk="10G",
        ssh_authorized_keys=("ssh-ed25519 AAAA",), bootstrap_profiles=("terminal",),
    )
    p = tmp_path / "u.toml"
    p.write_text(dump_users_toml({"dev": u}), encoding="utf-8")
    assert load_users(p) == {"dev": u}
