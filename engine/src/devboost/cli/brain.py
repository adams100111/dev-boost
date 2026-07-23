"""The sandboxed-brain recipe: the `devbrain` managed-account definition + key discovery.

`devboost brain` (in app.py) installs the brain-host tools then reconciles this account —
a capped, sudo-less user whose bootstrap_profiles install herdr et al. into its home.
"""

from __future__ import annotations

import os
from pathlib import Path

from devboost.accounts.config import ManagedUser
from devboost.accounts.form import merge_flags


def default_ssh_keys() -> tuple[str, ...]:
    """Best-effort: the invoking user's public keys, so `mosh devbrain@brain` works.

    Reads ~/.ssh/*.pub. Returns () when none are found — the operator can pass --ssh-key
    explicitly instead.
    """
    home = os.environ.get("HOME")
    if not home:
        return ()
    ssh = Path(home) / ".ssh"
    if not ssh.is_dir():
        return ()
    keys: list[str] = []
    for pub in sorted(ssh.glob("*.pub")):
        try:
            text = pub.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            keys.append(text)
    return tuple(keys)


def devbrain_user(
    *, ssh_keys: tuple[str, ...], ram: str, cpu: str, disk: str, tasks: int
) -> ManagedUser:
    """The devbrain recipe: a capped, sudo-less user that bootstraps the brain-tools profile."""
    return merge_flags(
        "devbrain",
        ram=ram,
        cpu=cpu,
        disk=disk,
        tasks=tasks,
        privilege="none",  # the safety core: cannot sudo
        sudo_commands=(),
        shell="/bin/bash",
        lock_shell=False,
        linger=True,  # herdr / mosh-server persist without an active login
        ssh_keys=ssh_keys,
        bootstrap_profiles=("brain-tools",),
    )
