from __future__ import annotations

from devboost.accounts.config import ManagedUser
from devboost.accounts.form import merge_flags


def test_merge_flags_builds_managed_user() -> None:
    u = merge_flags(
        "dev", ram="4G", cpu="50%", disk="20G", tasks=200, privilege="nopasswd",
        sudo_commands=(), shell="/bin/bash", lock_shell=False, linger=True,
        ssh_keys=("ssh-ed25519 AAAA",), bootstrap_profiles=("terminal",),
    )
    assert u == ManagedUser(
        name="dev", enabled=True, shell="/bin/bash", lock_shell=False, linger=True,
        privilege="nopasswd", sudo_commands=(), ram="4G", cpu="50%", tasks=200, disk="20G",
        ssh_authorized_keys=("ssh-ed25519 AAAA",), bootstrap_profiles=("terminal",),
    )


def test_merge_flags_defaults_privilege_none() -> None:
    u = merge_flags("dev", ram=None, cpu=None, disk=None, tasks=None, privilege="none",
                    sudo_commands=(), shell="/bin/bash", lock_shell=False, linger=False,
                    ssh_keys=(), bootstrap_profiles=())
    assert u.privilege == "none" and u.ram is None
