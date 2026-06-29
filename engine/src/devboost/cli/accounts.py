"""The `accounts` sub-app: create/list/edit/disable/enable/delete/apply managed users."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from devboost.accounts import bootstrap as bs
from devboost.accounts import reconcile
from devboost.accounts.config import ManagedUser, Privilege, load_users
from devboost.accounts.form import merge_flags, run_form
from devboost.core import log, osinfo
from devboost.core.settings import settings
from devboost.exec.executor import RealExecutor
from devboost.model import Ctx

app = typer.Typer(help="Manage self-contained, resource-capped sandbox users.")


def _ctx() -> Ctx:
    return Ctx(os=osinfo.detect(), ex=RealExecutor())


def _save_local(users: Mapping[str, ManagedUser]) -> None:
    """Persist users.toml. Overridden in tests; production uses reconcile.save."""
    reconcile.save(_ctx(), users)


@app.command()
def create(
    name: Annotated[str, typer.Argument(help="username")] = "",
    ram: Annotated[str, typer.Option("--ram", help="RAM cap, e.g. 4G")] = "",
    cpu: Annotated[str, typer.Option("--cpu", help="CPU cap, e.g. 50%")] = "",
    disk: Annotated[str, typer.Option("--disk", help="disk quota, e.g. 20G")] = "",
    tasks: Annotated[int, typer.Option("--tasks", help="max processes")] = 0,
    privilege: Annotated[str, typer.Option("--privilege")] = "none",
    sudo_cmd: Annotated[
        list[str], typer.Option("--sudo-cmd", help="allowlist cmd (repeatable)")
    ] = [],  # noqa: B006
    shell: Annotated[str, typer.Option("--shell")] = "/bin/bash",
    lock_shell: Annotated[bool, typer.Option("--lock-shell")] = False,
    linger: Annotated[bool, typer.Option("--linger")] = False,
    ssh_key: Annotated[
        list[str], typer.Option("--ssh-key", help="authorized key (repeatable)")
    ] = [],  # noqa: B006
    with_profile: Annotated[
        list[str], typer.Option("--with-profile", help="bootstrap profile")
    ] = [],  # noqa: B006
    interactive: Annotated[bool, typer.Option("--interactive")] = False,
    apply_: Annotated[bool, typer.Option("--apply/--no-apply")] = True,
    adopt: Annotated[
        bool, typer.Option("--adopt", help="manage an existing unmanaged account")
    ] = False,
) -> None:
    """Create a managed user (interactive form when NAME omitted)."""
    if not name or interactive:
        user = run_form()
    else:
        user = merge_flags(
            name, ram=ram or None, cpu=cpu or None, disk=disk or None,
            tasks=tasks or None, privilege=_privilege(privilege), sudo_commands=tuple(sudo_cmd),
            shell=shell, lock_shell=lock_shell, linger=linger, ssh_keys=tuple(ssh_key),
            bootstrap_profiles=tuple(with_profile),
        )
    users = load_users()
    if user.name in users:
        log.error(f"{user.name}: already managed (use 'accounts edit')")
        raise typer.Exit(2)
    from devboost.exec.primitives import usermgmt as um
    ctx = _ctx()
    if um.exists(ctx, user.name) and not adopt:
        log.error(f"{user.name}: account already exists; pass --adopt to manage it")
        raise typer.Exit(2)
    users[user.name] = user
    _save_local(users)
    if apply_:
        reconcile.apply_user(
            ctx,
            user,
            bootstrap=(lambda c, u: bs.bootstrap_user(c, u, root=settings.root))
            if user.bootstrap_profiles else None,
        )
    log.ok(f"{user.name}: created")


@app.command(name="list")
def list_() -> None:
    """List managed users and their declared caps."""
    users = load_users()
    table = Table("user", "enabled", "ram", "cpu", "tasks", "disk", "privilege")
    for u in users.values():
        table.add_row(u.name, str(u.enabled), u.ram or "-", u.cpu or "-",
                      str(u.tasks or "-"), u.disk or "-", u.privilege)
    Console().print(table)


@app.command()
def edit(name: str) -> None:
    """Edit a managed user via a prefilled form, then re-apply."""
    users = load_users()
    if name not in users:
        log.error(f"{name}: not managed")
        raise typer.Exit(2)
    updated = run_form(default=users[name])
    users[name] = updated
    _save_local(users)
    reconcile.apply_user(_ctx(), updated)
    log.ok(f"{name}: updated")


@app.command()
def disable(name: str) -> None:
    """Lock a managed user (reversible)."""
    user = _require(name)
    disabled = _with_enabled(user, False)
    users = load_users()
    users[name] = disabled
    _save_local(users)
    reconcile.disable_user(_ctx(), disabled)
    log.ok(f"{name}: disabled")


@app.command()
def enable(name: str) -> None:
    """Unlock + re-apply a managed user."""
    user = _with_enabled(_require(name), True)
    users = load_users()
    users[name] = user
    _save_local(users)
    reconcile.enable_user(_ctx(), user)
    log.ok(f"{name}: enabled")


@app.command()
def delete(
    name: str,
    purge: Annotated[
        bool, typer.Option("--purge", help="also sweep orphaned UID-owned files")
    ] = False,
) -> None:
    """Delete a managed user and tear down all its artifacts."""
    user = _require(name)
    reconcile.delete_user(_ctx(), user, purge=purge)
    users = load_users()
    users.pop(name, None)
    _save_local(users)
    log.ok(f"{name}: deleted")


@app.command()
def apply(name: Annotated[str, typer.Argument(help="user (blank = all)")] = "") -> None:
    """Reconcile all managed users, or one."""
    users = load_users()
    ctx = _ctx()
    targets = [_require(name)] if name else list(users.values())
    for u in targets:
        reconcile.apply_user(ctx, u)
    log.ok(f"applied {len(targets)} user(s)")


def _privilege(value: str) -> Privilege:
    if value not in ("none", "full", "nopasswd", "allowlist"):
        log.error(f"invalid privilege {value!r}")
        raise typer.Exit(2)
    return value  # type: ignore[return-value]


def _require(name: str) -> ManagedUser:
    users = load_users()
    if name not in users:
        log.error(f"{name}: not managed")
        raise typer.Exit(2)
    return users[name]


def _with_enabled(u: ManagedUser, enabled: bool) -> ManagedUser:
    return replace(u, enabled=enabled)
