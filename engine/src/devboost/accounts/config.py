"""Typed users.toml model: Pydantic validation -> frozen ManagedUser dataclasses."""

from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import tomli_w
from pydantic import BaseModel, ValidationError, field_validator

from devboost.core.errors import DevbootError

_SIZE_RE = re.compile(r"^\d+(\.\d+)?[KMGT]i?B?$|^\d+$")
_CPU_RE = re.compile(r"^\d+%$")

Privilege = Literal["none", "full", "nopasswd", "allowlist"]


class AccountsError(DevbootError):
    """A users.toml entry is invalid, or a reconcile step failed."""


class _UserRow(BaseModel):
    enabled: bool = True
    shell: str = "/bin/bash"
    lock_shell: bool = False
    linger: bool = False
    privilege: Privilege = "none"
    sudo_commands: list[str] = []
    ram: str | None = None
    cpu: str | None = None
    tasks: int | None = None
    disk: str | None = None
    ssh_authorized_keys: list[str] = []
    bootstrap_profiles: list[str] = []

    @field_validator("ram", "disk")
    @classmethod
    def _size(cls, v: str | None) -> str | None:
        if v is not None and not _SIZE_RE.match(v):
            raise ValueError(f"invalid size {v!r} (expected e.g. '4G', '512M')")
        return v

    @field_validator("cpu")
    @classmethod
    def _cpu(cls, v: str | None) -> str | None:
        if v is not None and not _CPU_RE.match(v):
            raise ValueError(f"invalid cpu {v!r} (expected e.g. '50%', '200%')")
        return v

    @field_validator("tasks")
    @classmethod
    def _tasks(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("tasks must be a positive integer")
        return v

    @field_validator("sudo_commands")
    @classmethod
    def _abs_cmds(cls, v: list[str]) -> list[str]:
        for c in v:
            if not c.startswith("/"):
                raise ValueError(f"sudo command must be an absolute path: {c!r}")
        return v


@dataclass(frozen=True)
class ManagedUser:
    name: str
    enabled: bool
    shell: str
    lock_shell: bool
    linger: bool
    privilege: Privilege
    sudo_commands: tuple[str, ...]
    ram: str | None
    cpu: str | None
    tasks: int | None
    disk: str | None
    ssh_authorized_keys: tuple[str, ...]
    bootstrap_profiles: tuple[str, ...]


def _to_managed(name: str, row: _UserRow) -> ManagedUser:
    return ManagedUser(
        name=name, enabled=row.enabled, shell=row.shell, lock_shell=row.lock_shell,
        linger=row.linger, privilege=row.privilege, sudo_commands=tuple(row.sudo_commands),
        ram=row.ram, cpu=row.cpu, tasks=row.tasks, disk=row.disk,
        ssh_authorized_keys=tuple(row.ssh_authorized_keys),
        bootstrap_profiles=tuple(row.bootstrap_profiles),
    )


def users_path() -> Path:
    return Path(os.environ.get("DEVBOOST_USERS_PATH", "/etc/devboost/users.toml"))


def load_users(path: Path | None = None) -> dict[str, ManagedUser]:
    p = path or users_path()
    if not p.exists():
        return {}
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    rows = data.get("users", {})
    out: dict[str, ManagedUser] = {}
    for name, raw in rows.items():
        try:
            row = _UserRow.model_validate(raw)
        except ValidationError as exc:
            raise AccountsError(f"user {name!r}: {exc}") from exc
        out[str(name)] = _to_managed(str(name), row)
    return out


def dump_users_toml(users: Mapping[str, ManagedUser]) -> str:
    """Serialize managed users to a users.toml string (pure; no I/O)."""
    table: dict[str, dict[str, object]] = {}
    for name, u in users.items():
        row: dict[str, object] = {
            "enabled": u.enabled, "shell": u.shell, "lock_shell": u.lock_shell,
            "linger": u.linger, "privilege": u.privilege,
            "sudo_commands": list(u.sudo_commands),
            "ssh_authorized_keys": list(u.ssh_authorized_keys),
            "bootstrap_profiles": list(u.bootstrap_profiles),
        }
        for k, v in (("ram", u.ram), ("cpu", u.cpu), ("tasks", u.tasks), ("disk", u.disk)):
            if v is not None:
                row[k] = v
        table[name] = row
    return tomli_w.dumps({"users": table})
