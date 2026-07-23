from __future__ import annotations

from pathlib import Path

import pytest

from devboost.cli.brain import DEVBRAIN_DEFAULTS, default_ssh_keys, devbrain_user


def test_devbrain_user_is_capped_sudoless_and_bootstraps_brain_tools() -> None:
    u = devbrain_user(
        ssh_keys=("ssh-ed25519 AAAA me",), ram="8G", cpu="200%", disk="50G", tasks=4096
    )
    assert u.name == "devbrain"
    assert u.privilege == "none"
    assert u.sudo_commands == ()
    assert u.linger is True
    assert (u.ram, u.cpu, u.disk, u.tasks) == ("8G", "200%", "50G", 4096)
    assert u.bootstrap_profiles == ("brain-tools",)
    assert u.ssh_authorized_keys == ("ssh-ed25519 AAAA me",)


def test_default_ssh_keys_reads_pub_files_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ssh = tmp_path / ".ssh"
    ssh.mkdir()
    (ssh / "id_ed25519.pub").write_text("ssh-ed25519 KEY1 a\n", encoding="utf-8")
    (ssh / "id_rsa.pub").write_text("ssh-rsa KEY2 b\n", encoding="utf-8")
    (ssh / "id_ed25519").write_text("PRIVATE", encoding="utf-8")  # not a .pub -> ignored
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_ssh_keys() == ("ssh-ed25519 KEY1 a", "ssh-rsa KEY2 b")


def test_default_ssh_keys_empty_when_no_ssh_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_ssh_keys() == ()


def test_devbrain_defaults() -> None:
    assert DEVBRAIN_DEFAULTS == {"ram": "8G", "cpu": "200%", "disk": "50G", "tasks": 4096}
