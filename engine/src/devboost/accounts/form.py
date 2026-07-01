"""Interactive create/edit form + a pure flag->ManagedUser builder."""

from __future__ import annotations

from devboost.accounts.config import ManagedUser, Privilege

#: Toolchains offered (unchecked) in the interactive create form and named by the
#: post-create hint. Kept a subset of profiles.toml (guarded by a test).
BOOTSTRAP_PROFILE_CHOICES: tuple[str, ...] = ("terminal", "devtools")


def provisioning_hint(bootstrap_profiles: tuple[str, ...]) -> str | None:
    """Follow-up command to suggest when a user is created with no toolchains.

    Returns None when profiles were already selected to bootstrap.
    """
    if bootstrap_profiles:
        return None
    return (
        "provision this user's toolchain later: "
        f"devboost install {' '.join(BOOTSTRAP_PROFILE_CHOICES)}"
    )


def merge_flags(
    name: str,
    *,
    ram: str | None,
    cpu: str | None,
    disk: str | None,
    tasks: int | None,
    privilege: Privilege,
    sudo_commands: tuple[str, ...],
    shell: str,
    lock_shell: bool,
    linger: bool,
    ssh_keys: tuple[str, ...],
    bootstrap_profiles: tuple[str, ...],
    enabled: bool = True,
) -> ManagedUser:
    return ManagedUser(
        name=name, enabled=enabled, shell=shell, lock_shell=lock_shell, linger=linger,
        privilege=privilege, sudo_commands=sudo_commands, ram=ram, cpu=cpu, tasks=tasks,
        disk=disk, ssh_authorized_keys=ssh_keys, bootstrap_profiles=bootstrap_profiles,
    )


def run_form(default: ManagedUser | None = None) -> ManagedUser:  # pragma: no cover (TTY)
    """questionary-driven create/edit form. Prefilled from *default* when editing."""
    import questionary

    d = default
    name_default = d.name if d else ""
    name = questionary.text("Username:", default=name_default).ask()
    ram_default = d.ram or "" if d else ""
    ram = questionary.text(
        "RAM cap (e.g. 4G, blank = none):", default=ram_default
    ).ask()
    cpu_default = d.cpu or "" if d else ""
    cpu = questionary.text(
        "CPU cap (e.g. 50%, blank = none):", default=cpu_default
    ).ask()
    disk_default = d.disk or "" if d else ""
    disk = questionary.text(
        "Disk cap (e.g. 20G, blank = none):", default=disk_default
    ).ask()
    tasks_default = str(d.tasks) if d and d.tasks else ""
    tasks_s = questionary.text(
        "Max processes (blank = none):", default=tasks_default
    ).ask()
    priv_default = d.privilege if d else "none"
    privilege = questionary.select(
        "Privileges:",
        choices=["none", "full", "nopasswd", "allowlist"],
        default=priv_default,
    ).ask()
    # Optional, opt-in toolchain bootstrap — nothing checked by default so a bare
    # account stays the fast path. Existing selections (incl. any not in the
    # standard set) are preserved and pre-checked when editing.
    existing = list(d.bootstrap_profiles) if d else []
    choices = list(dict.fromkeys([*BOOTSTRAP_PROFILE_CHOICES, *existing]))
    bootstrap = questionary.checkbox(
        "Install toolchains now? (space to toggle, enter to skip):",
        choices=[questionary.Choice(p, checked=p in existing) for p in choices],
    ).ask()
    return merge_flags(
        name,
        ram=ram or None,
        cpu=cpu or None,
        disk=disk or None,
        tasks=int(tasks_s) if tasks_s else None,
        privilege=privilege,
        sudo_commands=d.sudo_commands if d else (),
        shell=d.shell if d else "/bin/bash",
        lock_shell=d.lock_shell if d else False,
        linger=d.linger if d else False,
        ssh_keys=d.ssh_authorized_keys if d else (),
        bootstrap_profiles=tuple(bootstrap or ()),
        enabled=d.enabled if d else True,
    )
