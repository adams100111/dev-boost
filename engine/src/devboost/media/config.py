"""Typed configuration for a `devboost installer` build (filled by flags or the wizard)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


@dataclass(frozen=True)
class IsoSpec:
    id: str
    url: str
    sha256: str
    edition: str


@dataclass(frozen=True)
class Device:
    name: str
    path: str
    size: str
    model: str
    removable: bool
    mounted: bool
    vendor: str = ""
    serial: str = ""
    tran: str = ""

    def label(self) -> str:
        name = " ".join(p for p in (self.vendor, self.model) if p) or "unknown"
        tran = f" ({self.tran})" if self.tran else ""
        serial = f"  [sn:{self.serial}]" if self.serial else ""
        return f"{self.path}  —  {name}{tran}  —  {self.size}{serial}"


class MediaConfig(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    device: str
    arch: str
    iso: IsoSpec
    autoinstall_iso: IsoSpec | None = None
    profiles: tuple[str, ...] = ("full",)
    secrets_path: Path | None = None
    # Path to the age private key file (age-key.txt) to stage alongside secrets.age.
    secrets_key_path: Path | None = None
    extra_isos: tuple[Path, ...] = ()
    installers: tuple[Path, ...] = ()
    offline_mirror: bool = False
    cache_dir: Path
    # TTL for the download cache in days; None = keep forever (only applies to persistent cache).
    cache_ttl_days: int | None = None
    assume_yes: bool = False
    mode: Literal["build", "update"] = "build"
    refresh_iso: bool = False
    # Target OS family for staging dispatch ("fedora" | "debian").  Defaults to "fedora"
    # so existing configs are unchanged; Ubuntu builds must set this to "debian".
    os_family: str = "fedora"
