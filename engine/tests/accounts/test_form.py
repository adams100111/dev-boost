from __future__ import annotations

from devboost.accounts.config import ManagedUser
from devboost.accounts.form import (
    BOOTSTRAP_PROFILE_CHOICES,
    merge_flags,
    provisioning_hint,
)
from devboost.core.profiles import load_profiles
from devboost.core.settings import settings


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


def test_bootstrap_profile_choices_are_real_profiles() -> None:
    # The toolchains offered in the create form must be actual profiles, so the
    # picker can never drift into offering a name `devboost install` would reject.
    profiles = load_profiles(settings.profiles_path)
    assert BOOTSTRAP_PROFILE_CHOICES, "at least one toolchain must be offered"
    for name in BOOTSTRAP_PROFILE_CHOICES:
        assert name in profiles, f"{name!r} is not a profile in profiles.toml"


def test_provisioning_hint_present_when_no_toolchains() -> None:
    hint = provisioning_hint(())
    assert hint is not None
    assert "devboost install" in hint
    assert "terminal" in hint and "devtools" in hint


def test_provisioning_hint_absent_when_toolchains_selected() -> None:
    assert provisioning_hint(("terminal",)) is None
