"""Supported-OS catalog, loaded + validated from ``catalog.toml`` (in-repo pinned data).

Pins are the source of truth (Principle III). Edit ``catalog.toml`` to add a distro/arch or
bump a release; each sha256 must come from the distro's signed CHECKSUM — never invent one.
The TOML is validated at load (structure + 64-hex sha256), so a malformed pin fails loudly
instead of silently shipping a bad hash. Adding an entry needs no code change — it shows up
in the ``devboost installer`` wizard by its friendly name automatically.

Non-OS sections (e.g. ``[ventoy]``) are stripped before OS validation so catalog.toml can
hold arbitrary tooling pins without breaking the structured OS loader.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from pydantic import BaseModel, Field, TypeAdapter

from devboost.core.errors import MediaError
from devboost.core.settings import settings
from devboost.media.config import IsoSpec

# Keys in catalog.toml that are not OS entries and must be stripped before OS validation.
_NON_OS_SECTIONS: frozenset[str] = frozenset({"ventoy"})


@dataclass(frozen=True)
class Os:
    id: str
    name: str
    distro: str
    version: str
    edition: str
    isos: dict[str, IsoSpec]
    autoinstall: dict[str, IsoSpec]


@dataclass(frozen=True)
class VentoySpec:
    """Pinned Ventoy release (from the ``[ventoy]`` block in catalog.toml)."""

    version: str
    url: str
    sha256: str


class _IsoRow(BaseModel):
    url: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class _OsRow(BaseModel):
    name: str
    distro: str
    version: str
    edition: str
    isos: dict[str, _IsoRow] = Field(min_length=1)
    autoinstall: dict[str, _IsoRow] = {}


class _VentoyRow(BaseModel):
    version: str
    url: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


_CATALOG_ADAPTER = TypeAdapter(dict[str, _OsRow])


def load_catalog(path: Path) -> dict[str, Os]:
    """Parse + validate a catalog TOML into typed ``Os`` entries.

    Non-OS sections (e.g. ``[ventoy]``) are stripped before validation so catalog.toml
    can hold arbitrary tooling pins without breaking the OS loader.

    Raises ``MediaError`` if the file is missing, malformed, or has a bad pin.
    """
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        os_raw = {k: v for k, v in raw.items() if k not in _NON_OS_SECTIONS}
        rows = _CATALOG_ADAPTER.validate_python(os_raw)
    except (OSError, ValueError) as exc:  # OSError: missing; ValueError: TOML/validation
        raise MediaError(f"invalid catalog {path}: {exc}") from exc
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
            autoinstall={
                arch: IsoSpec(
                    id=f"{os_id}-netinst", url=iso.url, sha256=iso.sha256, edition="netinst"
                )
                for arch, iso in row.autoinstall.items()
            },
        )
        for os_id, row in rows.items()
    }


@cache
def catalog() -> dict[str, Os]:
    """The validated OS catalog (cached). Source: ``settings.catalog_path`` (catalog.toml)."""
    return load_catalog(settings.catalog_path)


@cache
def ventoy_pin() -> VentoySpec:
    """The pinned Ventoy release (cached). Read from the ``[ventoy]`` block in catalog.toml."""
    path = settings.catalog_path
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        row = _VentoyRow.model_validate(raw["ventoy"])
    except (OSError, KeyError, ValueError) as exc:
        raise MediaError(f"[ventoy] pin missing or invalid in {path}: {exc}") from exc
    return VentoySpec(version=row.version, url=row.url, sha256=row.sha256)


def supported() -> list[Os]:
    """All catalog entries, for the wizard's friendly-named select."""
    return list(catalog().values())


def iso_for(os_id: str, arch: str) -> IsoSpec:
    """The pinned IsoSpec for *os_id* on *arch*, or raise MediaError."""
    os_entry = catalog().get(os_id)
    if os_entry is None:
        raise MediaError(f"unknown OS id {os_id!r}")
    spec = os_entry.isos.get(arch)
    if spec is None:
        raise MediaError(f"no pinned ISO for arch {arch!r} (os_id={os_id!r})")
    return spec


def autoinstall_for(os_id: str, arch: str) -> IsoSpec | None:
    """The pinned zero-touch (netinst) IsoSpec for *os_id*+*arch*, or None if not pinned."""
    os_entry = catalog().get(os_id)
    if os_entry is None:
        return None
    return os_entry.autoinstall.get(arch)


def default_os() -> Os:
    return catalog()["fedora-44"]


def default_iso() -> IsoSpec:
    return default_os().isos["x86_64"]
