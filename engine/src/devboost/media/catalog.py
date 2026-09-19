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

import re
import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from pydantic import BaseModel, Field, TypeAdapter, field_validator

from devboost.core.errors import MediaError
from devboost.core.osinfo import OsInfo
from devboost.core.settings import settings
from devboost.media.config import IsoSpec

# Keys in catalog.toml that are not OS entries and must be stripped before OS validation.
_NON_OS_SECTIONS: frozenset[str] = frozenset({"ventoy", "herdr", "xcode", "voxtype"})


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


@dataclass(frozen=True)
class HerdrAsset:
    url: str
    sha256: str


@dataclass(frozen=True)
class HerdrSpec:
    """Pinned herdr release (from the ``[herdr]`` block in catalog.toml)."""

    version: str
    assets: dict[str, HerdrAsset]  # "<os>-<arch>" (see asset_key) -> asset


_ASSET_KEY = re.compile(r"^(linux|macos)-(x86_64|aarch64)$")


def asset_key(os_info: OsInfo) -> str:
    """The catalog key of a pinned binary for this host: ``<os>-<arch>``.

    Keyed by OS *and* arch (never arch alone), so a Mac can never pick a Linux binary.
    """
    return f"{'macos' if os_info.family == 'macos' else 'linux'}-{os_info.arch}"


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


class _HerdrAssetRow(BaseModel):
    url: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class _HerdrRow(BaseModel):
    version: str
    assets: dict[str, _HerdrAssetRow] = Field(min_length=1)

    @field_validator("assets")
    @classmethod
    def _os_arch_keys(cls, v: dict[str, _HerdrAssetRow]) -> dict[str, _HerdrAssetRow]:
        bad = sorted(k for k in v if not _ASSET_KEY.match(k))
        if bad:
            raise ValueError(f"asset keys must be <linux|macos>-<arch>, got {bad}")
        return v


@dataclass(frozen=True)
class XcodeSpec:
    """Pinned Xcode + iOS simulator runtime (the ``[xcode]`` block)."""

    version: str
    ios_runtime: str
    min_macos: tuple[int, int]


@dataclass(frozen=True)
class ReleaseAsset:
    url: str
    sha256: str


@dataclass(frozen=True)
class VoxtypeSpec:
    """Pinned Voxtype release for Linux and macOS (the ``[voxtype]`` block)."""

    version: str
    assets: dict[str, ReleaseAsset]  # one per VOXTYPE_ASSETS key


_VERSION = r"^\d+\.\d+(\.\d+)?$"


class _XcodeRow(BaseModel):
    version: str = Field(pattern=_VERSION)
    ios_runtime: str = Field(pattern=_VERSION)
    min_macos: str = Field(pattern=r"^\d+\.\d+$")


#: Every asset the voxtype module installs from; a pin missing one fails at load.
VOXTYPE_ASSETS: frozenset[str] = frozenset(
    {"rpm-x86_64", "deb-x86_64", "bin-aarch64", "bin-macos-universal"}
)


class _VoxtypeRow(BaseModel):
    version: str = Field(pattern=_VERSION)
    assets: dict[str, _HerdrAssetRow] = Field(min_length=1)  # url + 64-hex sha256

    @field_validator("assets")
    @classmethod
    def _all_assets(cls, v: dict[str, _HerdrAssetRow]) -> dict[str, _HerdrAssetRow]:
        missing = sorted(VOXTYPE_ASSETS - set(v))
        if missing:
            raise ValueError(f"missing voxtype assets: {', '.join(missing)}")
        return v


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


@cache
def herdr_pin() -> HerdrSpec:
    """The pinned herdr release (cached). Read from the ``[herdr]`` block in catalog.toml."""
    path = settings.catalog_path
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        row = _HerdrRow.model_validate(raw["herdr"])
    except (OSError, KeyError, ValueError) as exc:
        raise MediaError(f"[herdr] pin missing or invalid in {path}: {exc}") from exc
    return HerdrSpec(
        version=row.version,
        assets={a: HerdrAsset(url=r.url, sha256=r.sha256) for a, r in row.assets.items()},
    )


def _section(name: str) -> object:
    path = settings.catalog_path
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))[name]
    except (OSError, KeyError, ValueError) as exc:
        raise MediaError(f"[{name}] pin missing or invalid in {path}: {exc}") from exc


@cache
def xcode_pin() -> XcodeSpec:
    """The pinned Xcode (cached). Read from the ``[xcode]`` block in catalog.toml."""
    try:
        row = _XcodeRow.model_validate(_section("xcode"))
    except ValueError as exc:
        raise MediaError(f"[xcode] pin invalid: {exc}") from exc
    major, minor = (int(p) for p in row.min_macos.split("."))
    return XcodeSpec(
        version=row.version, ios_runtime=row.ios_runtime, min_macos=(major, minor)
    )


@cache
def voxtype_pin() -> VoxtypeSpec:
    """The pinned Voxtype release for Linux and macOS (cached), from ``[voxtype]``."""
    try:
        row = _VoxtypeRow.model_validate(_section("voxtype"))
    except ValueError as exc:
        raise MediaError(f"[voxtype] pin invalid: {exc}") from exc
    return VoxtypeSpec(
        version=row.version,
        assets={k: ReleaseAsset(url=a.url, sha256=a.sha256) for k, a in row.assets.items()},
    )


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
