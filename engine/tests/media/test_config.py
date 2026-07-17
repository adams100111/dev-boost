from __future__ import annotations

from pathlib import Path

from devboost.media.config import Device, IsoSpec, MediaConfig


def test_iso_and_device_are_frozen_value_objects() -> None:
    iso = IsoSpec(
        id="fedora-44", url="https://x/f44.iso", sha256="abc", edition="Everything"
    )
    dev = Device(
        name="sdb", path="/dev/sdb", size="32G", model="USB",
        removable=True, mounted=False
    )
    assert iso.id == "fedora-44" and dev.removable is True


def test_config_defaults() -> None:
    iso = IsoSpec(id="fedora-44", url="https://x/f44.iso", sha256="abc", edition="Everything")
    cfg = MediaConfig(device="/dev/sdb", arch="x86_64", iso=iso, cache_dir=Path("/tmp/c"))
    assert cfg.profiles == ("full",)
    assert cfg.secrets_path is None
    assert cfg.mode == "build"
    assert cfg.refresh_iso is False
