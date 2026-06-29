"""Converge one managed user to its declared state, idempotently."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from devboost.accounts.config import ManagedUser, dump_users_toml, users_path
from devboost.core import log
from devboost.exec.primitives import usermgmt as um
from devboost.model import Ctx

Bootstrap = Callable[[Ctx, ManagedUser], None]


def home_of(user: ManagedUser) -> str:
    return f"/home/{user.name}"


def _apply_privilege(ctx: Ctx, user: ManagedUser) -> None:
    if user.privilege in ("full", "nopasswd"):
        um.add_admin_group(ctx, user.name)
    else:
        um.remove_admin_group(ctx, user.name)
    content = um.sudoers_content(user.name, user.privilege, user.sudo_commands)
    if content is None:
        um.remove_sudoers(ctx, user.name)
    else:
        um.write_sudoers(ctx, user.name, content)


def apply_user(ctx: Ctx, user: ManagedUser, *, bootstrap: Bootstrap | None = None) -> None:
    if not user.enabled:
        disable_user(ctx, user)
        return
    home = home_of(user)
    shell = "/usr/sbin/nologin" if user.lock_shell else user.shell
    if user.disk is not None and um.fstype_of(ctx, "/home") == "btrfs":
        um.ensure_subvolume(ctx, home)
        um.ensure_user(ctx, user.name, shell=shell, home=home)
    else:
        um.ensure_user(ctx, user.name, shell=shell)
    um.set_authorized_keys(ctx, user.name, home, user.ssh_authorized_keys)
    (um.enable_linger if user.linger else um.disable_linger)(ctx, user.name)
    _apply_privilege(ctx, user)
    uid = um.uid_of(ctx, user.name)
    um.set_slice(ctx, uid, ram=user.ram, cpu=user.cpu, tasks=user.tasks)
    if user.disk is not None:
        status = um.set_quota(ctx, user.name, home, user.disk)
        (log.ok if status == "enforced" else log.warn)(f"{user.name}: disk quota {status}")
    if bootstrap is not None and user.bootstrap_profiles:
        bootstrap(ctx, user)


def disable_user(ctx: Ctx, user: ManagedUser) -> None:
    um.terminate_sessions(ctx, user.name)
    um.lock(ctx, user.name)


def enable_user(ctx: Ctx, user: ManagedUser) -> None:
    um.unlock(ctx, user.name)
    apply_user(ctx, user)


def delete_user(ctx: Ctx, user: ManagedUser, *, purge: bool = False) -> None:
    um.terminate_sessions(ctx, user.name)
    um.remove_sudoers(ctx, user.name)
    um.remove_admin_group(ctx, user.name)
    if um.exists(ctx, user.name):
        uid = um.uid_of(ctx, user.name)
        um.clear_slice(ctx, uid)
        if user.disk is not None:
            um.clear_quota(ctx, user.name, home_of(user))
        um.delete(ctx, user.name)
        if purge:
            ctx.ex.run(["find", "/", "-xdev", "-uid", str(uid), "-delete"], sudo=True)


def save(ctx: Ctx, users: Mapping[str, ManagedUser]) -> None:
    path = users_path()
    ctx.ex.run(["install", "-d", "-m", "755", str(path.parent)], sudo=True)
    ctx.ex.run(["tee", str(path)], sudo=True, stdin=dump_users_toml(users))
