"""Supported-OS catalog, loaded + validated from ``catalog.toml`` (in-repo pinned data).

Pins are the source of truth (Principle III). Edit ``catalog.toml`` to add a distro/arch or
bump a release; each sha256 must come from the distro's signed CHECKSUM — never invent one.
The TOML is validated at load (structure + 64-hex sha256), so a malformed pin fails loudly
instead of silently shipping a bad hash. Adding an entry needs no code change — it shows up
in the ``devboost usb`` wizard by its friendly name automatically.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from pydantic import BaseModel, Field, TypeAdapter

from devboost.core.errors import UsbError
from devboost.core.settings import settings
from devboost.usb.config import IsoSpec


@dataclass(frozen=True)
class Os:
    id: str
    name: str
    distro: str
    version: str
    edition: str
    isos: dict[str, IsoSpec]


class _IsoRow(BaseModel):
    url: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class _OsRow(BaseModel):
    name: str
    distro: str
    version: str
    edition: str
    isos: dict[str, _IsoRow] = Field(min_length=1)


_CATALOG_ADAPTER = TypeAdapter(dict[str, _OsRow])


def load_catalog(path: Path) -> dict[str, Os]:
    """Parse + validate a catalog TOML into typed ``Os`` entries.

    Raises ``UsbError`` if the file is missing, malformed, or has a bad pin (e.g. a
    sha256 that is not 64 lowercase hex).
    """
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        rows = _CATALOG_ADAPTER.validate_python(raw)
    except (OSError, ValueError) as exc:  # OSError: missing; ValueError: TOML/validation
        raise UsbError(f"invalid catalog {path}: {exc}") from exc
    return {
        os_id: Os(
            id=os_id,
            name=row.name,
            distro=row.distro,
            version=row.version,
            edition=row.edition,
            isos={
                arch: IsoSpec(id=os_id, url=iso.url, sha256=iso.sha256, edition=row.edition)
                for arch, iso in row.isos.items()
            },
        )
        for os_id, row in rows.items()
    }


@cache
def catalog() -> dict[str, Os]:
    """The validated catalog (cached). Source: ``settings.catalog_path`` (catalog.toml)."""
    return load_catalog(settings.catalog_path)


def supported() -> list[Os]:
    """All catalog entries, for the wizard's friendly-named select."""
    return list(catalog().values())


def iso_for(os_id: str, arch: str) -> IsoSpec:
    """The pinned IsoSpec for *os_id* on *arch*, or raise UsbError."""
    os_entry = catalog().get(os_id)
    if os_entry is None:
        raise UsbError(f"unknown OS id {os_id!r}")
    spec = os_entry.isos.get(arch)
    if spec is None:
        raise UsbError(f"no pinned ISO for arch {arch!r} (os_id={os_id!r})")
    return spec


def default_os() -> Os:
    return catalog()["fedora-44"]


def default_iso() -> IsoSpec:
    return default_os().isos["x86_64"]
