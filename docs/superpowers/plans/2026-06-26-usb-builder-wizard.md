# `devboost usb` Bootable-USB Builder — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `devboost usb` — a typed-Python Typer command that builds a bootable dev-boost Ventoy USB from the terminal, interactively (a questionary wizard, every question defaulted) or fully scripted, downloading + caching the Fedora ISO + frozen binary + Ventoy; replacing `ventoy/make-usb.sh`.

**Architecture:** A thin **wizard** (`questionary`) fills a Pydantic `UsbBuildConfig`; a testable **builder** runs ordered stages over the injected `Executor` (subprocess) + an injected `Downloader` (stdlib `urllib` + `rich` progress) + a `Cache`. Flags set the same config fields and skip the matching prompt, so the command is fully non-interactive too.

**Tech Stack:** Python 3.12, Typer, Pydantic, `questionary` (interactive prompts), `rich` (progress), stdlib `urllib`/`hashlib`/`shutil`; Ventoy CLI via subprocess. Tested with `FakeExecutor` + `FakeDownloader`.

**Design:** `docs/superpowers/specs/2026-06-26-usb-builder-wizard-design.md`.

## Global Constraints

- All code under `engine/` (src-layout package `devboost`); the typed engine is the project.
- Strictly-typed Python; **`mypy --strict` MUST be clean** and **`ruff check` MUST pass** (`engine/pyproject.toml`, line-length 100).
- **Test-first (TDD), comprehensive `pytest`**; unit tests are hermetic — no real `ventoy`/`dnf`/`lsblk`/network/disk writes. All side effects go through `ctx.ex` (an injected `Executor`) or the injected `Downloader`; never call `subprocess`/`urllib` directly in stage logic.
- Run gates from `engine/`: `uv run pytest`, `uv run mypy`, `uv run ruff check`.
- Conventional Commits; **no Claude/Anthropic attribution, no `Co-Authored-By` trailer.**
- House style (pyreview): Pydantic models for structured data, loguru for logging (`devboost.core.log`), custom error hierarchy with chaining, injected dependencies for testability.

---

## File Structure

```
engine/src/devboost/
  usb/
    __init__.py
    config.py        # UsbBuildConfig (Pydantic) + IsoSpec, Device value objects
    errors.py?       # -> reuse core/errors.py (add UsbError subtree there)
    cache.py         # Cache: name+sha256 -> file under cache_dir; verify + reuse
    download.py      # Downloader Protocol, UrllibDownloader, FakeDownloader
    devices.py       # list_removable() + validate() (lsblk via Executor; safety guards)
    isos.py          # FEDORA catalog: id -> IsoSpec(url, sha256, edition)
    builder.py       # build(ctx, cfg, dl): runs the ordered stages
    stages.py        # boot_artifacts, extra_isos, installers (+ P2: mirror)
    wizard.py        # questionary prompts -> UsbBuildConfig (thin)
  cli/usb.py         # the `usb` Typer command (flags + wizard) ; registered in cli/app.py
  core/errors.py     # MODIFY: add UsbError, DeviceError, DownloadError, VentoyError, MirrorError
engine/pyproject.toml  # MODIFY: add `questionary` dependency
engine/tests/usb/      # pytest mirror (test_config, test_cache, test_download, test_devices,
                       #   test_isos, test_builder, test_stages, test_cli_usb, [P2] test_mirror)
ventoy/make-usb.sh     # DELETE (replaced by `devboost usb`)
```

---

# Phase 1 — wizard + boot artifacts + caching + extras

### Task 1: Scaffold the `usb` package, errors, and the `questionary` dependency

**Files:**
- Modify: `engine/pyproject.toml` (add `questionary>=2.0` to `[project].dependencies`)
- Modify: `engine/src/devboost/core/errors.py` (append the `UsbError` subtree)
- Create: `engine/src/devboost/usb/__init__.py` (empty)
- Test: `engine/tests/usb/test_errors.py`

**Interfaces:**
- Produces: `UsbError`, `DeviceError`, `DownloadError`, `VentoyError`, `MirrorError` (all subclass `DevbootError`).

- [ ] **Step 1: Write the failing test** — `engine/tests/usb/test_errors.py`

```python
from __future__ import annotations

import pytest

from devboost.core.errors import (
    DevbootError,
    DeviceError,
    DownloadError,
    UsbError,
    VentoyError,
)


def test_usb_errors_subclass_devboot_error() -> None:
    for cls in (UsbError, DeviceError, DownloadError, VentoyError):
        assert issubclass(cls, DevbootError)
    assert issubclass(DeviceError, UsbError)


def test_download_error_carries_url() -> None:
    err = DownloadError("https://x/iso", "checksum mismatch")
    assert "https://x/iso" in str(err)
    with pytest.raises(UsbError):
        raise err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/usb/test_errors.py -q`
Expected: FAIL — `ImportError: cannot import name 'UsbError'`.

- [ ] **Step 3: Implement** — append to `engine/src/devboost/core/errors.py`

```python
class UsbError(DevbootError):
    """Base for `devboost usb` build failures."""


class DeviceError(UsbError):
    """The target device is unsafe or invalid."""


class DownloadError(UsbError):
    """A download failed or failed verification."""

    def __init__(self, url: str, reason: str) -> None:
        self.url = url
        super().__init__(f"download {url}: {reason}")


class VentoyError(UsbError):
    """A Ventoy install/layout step failed."""


class MirrorError(UsbError):
    """An offline-mirror step failed."""
```

Add `questionary>=2.0` to `engine/pyproject.toml` `[project].dependencies`, and create the empty
`engine/src/devboost/usb/__init__.py`.

- [ ] **Step 4: Sync deps + run gates**

Run: `cd engine && uv sync && uv run pytest tests/usb/test_errors.py -q && uv run mypy && uv run ruff check`
Expected: PASS / clean.

- [ ] **Step 5: Commit**

```bash
git add engine/pyproject.toml engine/uv.lock engine/src/devboost/core/errors.py \
        engine/src/devboost/usb/__init__.py engine/tests/usb/test_errors.py
git commit -m "feat(usb): scaffold usb package + UsbError hierarchy + questionary dep"
```

---

### Task 2: `UsbBuildConfig` + `IsoSpec` + `Device` value objects

**Files:**
- Create: `engine/src/devboost/usb/config.py`
- Test: `engine/tests/usb/test_config.py`

**Interfaces:**
- Produces:
  - `IsoSpec(id: str, url: str, sha256: str, edition: str)` — frozen dataclass.
  - `Device(name, path, size, model, removable, mounted, vendor="", serial="", tran="")` — frozen
    dataclass. `tran` is the transport (`usb`/`nvme`/…); `vendor`/`serial` aid distinct identification.
    - `label() -> str` — a human, distinct one-liner for the picker, e.g.
      `"/dev/sdb  —  SanDisk Ultra (usb)  —  32G  [sn:4C530001]"`.
  - `UsbBuildConfig` (Pydantic `BaseModel`): `device: str`, `arch: str`, `iso: IsoSpec`, `profiles: tuple[str, ...] = ("full",)`, `secrets_path: Path | None = None`, `extra_isos: tuple[Path, ...] = ()`, `installers: tuple[Path, ...] = ()`, `offline_mirror: bool = False`, `cache_dir: Path`, `assume_yes: bool = False`.

- [ ] **Step 1: Write the failing test** — `engine/tests/usb/test_config.py`

```python
from __future__ import annotations

from pathlib import Path

from devboost.usb.config import Device, IsoSpec, UsbBuildConfig


def test_iso_and_device_are_frozen_value_objects() -> None:
    iso = IsoSpec(id="fedora-44", url="https://x/f44.iso", sha256="abc", edition="Everything")
    dev = Device(name="sdb", path="/dev/sdb", size="32G", model="USB", removable=True, mounted=False)
    assert iso.id == "fedora-44" and dev.removable is True


def test_config_defaults() -> None:
    iso = IsoSpec(id="fedora-44", url="https://x/f44.iso", sha256="abc", edition="Everything")
    cfg = UsbBuildConfig(device="/dev/sdb", arch="x86_64", iso=iso, cache_dir=Path("/tmp/c"))
    assert cfg.profiles == ("full",)
    assert cfg.offline_mirror is False
    assert cfg.secrets_path is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/usb/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError: devboost.usb.config`.

- [ ] **Step 3: Implement** — `engine/src/devboost/usb/config.py`

```python
"""Typed configuration for a `devboost usb` build (filled by flags or the wizard)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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


class UsbBuildConfig(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    device: str
    arch: str
    iso: IsoSpec
    profiles: tuple[str, ...] = ("full",)
    secrets_path: Path | None = None
    extra_isos: tuple[Path, ...] = ()
    installers: tuple[Path, ...] = ()
    offline_mirror: bool = False
    cache_dir: Path
    assume_yes: bool = False
```

- [ ] **Step 4: Run gates**

Run: `cd engine && uv run pytest tests/usb/test_config.py -q && uv run mypy && uv run ruff check`
Expected: PASS / clean.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/usb/config.py engine/tests/usb/test_config.py
git commit -m "feat(usb): UsbBuildConfig + IsoSpec + Device value objects"
```

---

### Task 3: `Cache` — content-addressed download cache

**Files:**
- Create: `engine/src/devboost/usb/cache.py`
- Test: `engine/tests/usb/test_cache.py`

**Interfaces:**
- Produces: `Cache(cache_dir: Path)` with:
  - `path_for(name: str, sha256: str) -> Path` — `<cache_dir>/<name>` (sha is the integrity key).
  - `has(name: str, sha256: str) -> bool` — True iff the file exists AND its sha256 matches.
  - `verify(path: Path, sha256: str) -> bool` — stream-hash a file.

- [ ] **Step 1: Write the failing test** — `engine/tests/usb/test_cache.py`

```python
from __future__ import annotations

import hashlib
from pathlib import Path

from devboost.usb.cache import Cache


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_has_is_true_only_on_matching_checksum(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    name, data = "f44.iso", b"iso-bytes"
    p = cache.path_for(name, _sha(data))
    assert cache.has(name, _sha(data)) is False        # not present yet
    p.write_bytes(data)
    assert cache.has(name, _sha(data)) is True          # present + matches
    assert cache.has(name, _sha(b"other")) is False     # present but wrong checksum
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/usb/test_cache.py -q`
Expected: FAIL — `ModuleNotFoundError: devboost.usb.cache`.

- [ ] **Step 3: Implement** — `engine/src/devboost/usb/cache.py`

```python
"""Content-addressed cache for downloaded build artifacts (ISO, binary, Ventoy)."""

from __future__ import annotations

import hashlib
from pathlib import Path


class Cache:
    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, name: str, sha256: str) -> Path:
        return self.cache_dir / name

    def verify(self, path: Path, sha256: str) -> bool:
        if not path.exists():
            return False
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest() == sha256

    def has(self, name: str, sha256: str) -> bool:
        return self.verify(self.path_for(name, sha256), sha256)
```

- [ ] **Step 4: Run gates**

Run: `cd engine && uv run pytest tests/usb/test_cache.py -q && uv run mypy && uv run ruff check`
Expected: PASS / clean.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/usb/cache.py engine/tests/usb/test_cache.py
git commit -m "feat(usb): content-addressed download Cache"
```

---

### Task 4: `Downloader` — fetch-with-verify behind a seam (urllib + fake)

**Files:**
- Create: `engine/src/devboost/usb/download.py`
- Test: `engine/tests/usb/test_download.py`

**Interfaces:**
- Consumes: `Cache` (Task 3), `DownloadError` (Task 1).
- Produces:
  - `Downloader` Protocol: `fetch(self, url: str, name: str, sha256: str) -> Path`.
  - `UrllibDownloader(cache: Cache)` — cache hit ⇒ return cached path; else stream-download (stdlib
    `urllib`), verify sha256, raise `DownloadError` on mismatch, return the cached path.
  - `FakeDownloader(cache: Cache, blobs: dict[str, bytes])` — tests; "downloads" by writing
    `blobs[url]` to the cache path; records `fetched: list[str]`; verifies sha like the real one.

- [ ] **Step 1: Write the failing test** — `engine/tests/usb/test_download.py`

```python
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from devboost.core.errors import DownloadError
from devboost.usb.cache import Cache
from devboost.usb.download import FakeDownloader


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def test_fake_downloader_writes_verifies_and_caches(tmp_path: Path) -> None:
    data = b"iso-bytes"
    dl = FakeDownloader(Cache(tmp_path), blobs={"https://x/f.iso": data})
    p = dl.fetch("https://x/f.iso", "f.iso", _sha(data))
    assert p.read_bytes() == data
    assert dl.fetched == ["https://x/f.iso"]
    # second fetch is served from cache (no re-download)
    p2 = dl.fetch("https://x/f.iso", "f.iso", _sha(data))
    assert p2 == p and dl.fetched == ["https://x/f.iso"]


def test_fake_downloader_rejects_bad_checksum(tmp_path: Path) -> None:
    dl = FakeDownloader(Cache(tmp_path), blobs={"https://x/f.iso": b"corrupt"})
    with pytest.raises(DownloadError):
        dl.fetch("https://x/f.iso", "f.iso", _sha(b"expected"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/usb/test_download.py -q`
Expected: FAIL — `ModuleNotFoundError: devboost.usb.download`.

- [ ] **Step 3: Implement** — `engine/src/devboost/usb/download.py`

```python
"""Download seam: cache-hit-or-fetch-and-verify. Real impl uses stdlib urllib."""

from __future__ import annotations

import shutil
import urllib.request
from pathlib import Path
from typing import Protocol, runtime_checkable

from devboost.core.errors import DownloadError
from devboost.usb.cache import Cache


@runtime_checkable
class Downloader(Protocol):
    def fetch(self, url: str, name: str, sha256: str) -> Path: ...


class UrllibDownloader:
    def __init__(self, cache: Cache) -> None:
        self.cache = cache

    def fetch(self, url: str, name: str, sha256: str) -> Path:
        dest = self.cache.path_for(name, sha256)
        if self.cache.has(name, sha256):
            return dest
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            with urllib.request.urlopen(url) as resp, tmp.open("wb") as out:  # noqa: S310
                shutil.copyfileobj(resp, out)
        except OSError as exc:
            raise DownloadError(url, str(exc)) from exc
        if not self.cache.verify(tmp, sha256):
            tmp.unlink(missing_ok=True)
            raise DownloadError(url, "checksum mismatch")
        tmp.replace(dest)
        return dest


class FakeDownloader:
    def __init__(self, cache: Cache, blobs: dict[str, bytes]) -> None:
        self.cache = cache
        self.blobs = blobs
        self.fetched: list[str] = []

    def fetch(self, url: str, name: str, sha256: str) -> Path:
        dest = self.cache.path_for(name, sha256)
        if self.cache.has(name, sha256):
            return dest
        self.fetched.append(url)
        dest.write_bytes(self.blobs[url])
        if not self.cache.verify(dest, sha256):
            dest.unlink(missing_ok=True)
            raise DownloadError(url, "checksum mismatch")
        return dest
```

- [ ] **Step 4: Run gates**

Run: `cd engine && uv run pytest tests/usb/test_download.py -q && uv run mypy && uv run ruff check`
Expected: PASS / clean. (If ruff flags `S310` and the rule isn't enabled, drop the `# noqa`.)

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/usb/download.py engine/tests/usb/test_download.py
git commit -m "feat(usb): Downloader seam (urllib + fake) with verify+cache"
```

---

### Task 5: `devices` — list removable disks + safety guards

**Files:**
- Create: `engine/src/devboost/usb/devices.py`
- Test: `engine/tests/usb/test_devices.py`

**Interfaces:**
- Consumes: `Ctx`/`Executor` (`devboost.model`), `Device` (Task 2), `DeviceError` (Task 1).
- Produces:
  - `list_removable(ctx: Ctx) -> list[Device]` — parse `lsblk -P` (key=`"value"` pairs — robust to
    empty/multi-word fields, unlike column splitting) over
    `PATH,SIZE,TYPE,RM,MOUNTPOINT,MODEL,VENDOR,SERIAL,TRAN`; return only removable, unmounted disks.
  - `validate(ctx: Ctx, path: str) -> None` — raise `DeviceError` unless the path is a whole disk,
    `RM=1`, and unmounted (ports `make-usb.sh`'s guards).

- [ ] **Step 1: Write the failing test** — `engine/tests/usb/test_devices.py`

```python
from __future__ import annotations

import pytest

from devboost.core.errors import DeviceError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.usb.devices import list_removable, validate

OS = OsInfo("fedora", "fedora", "x86_64")
# lsblk -P output (one device per line, key="value" pairs)
_LSBLK = (
    'PATH="/dev/sda" SIZE="512G" TYPE="disk" RM="0" MOUNTPOINT="" MODEL="Samsung SSD 980"'
    ' VENDOR="Samsung" SERIAL="S1" TRAN="nvme"\n'
    'PATH="/dev/sdb" SIZE="32G" TYPE="disk" RM="1" MOUNTPOINT="" MODEL="Ultra"'
    ' VENDOR="SanDisk" SERIAL="4C53" TRAN="usb"\n'
    'PATH="/dev/sdc" SIZE="16G" TYPE="disk" RM="1" MOUNTPOINT="/run/media/u/X" MODEL="Cruzer"'
    ' VENDOR="SanDisk" SERIAL="ABC" TRAN="usb"\n'
)


def test_list_removable_filters_to_unmounted_removable_disks() -> None:
    ctx = Ctx(os=OS, ex=FakeExecutor(scripts={"lsblk": Result(0, stdout=_LSBLK)}))
    devs = list_removable(ctx)
    assert [d.path for d in devs] == ["/dev/sdb"]          # sda fixed, sdc mounted -> excluded
    d = devs[0]
    assert d.size == "32G" and d.model == "Ultra" and d.vendor == "SanDisk" and d.tran == "usb"
    assert d.label() == "/dev/sdb  —  SanDisk Ultra (usb)  —  32G  [sn:4C53]"


def test_validate_rejects_fixed_and_mounted() -> None:
    ctx = Ctx(os=OS, ex=FakeExecutor(scripts={"lsblk": Result(0, stdout=_LSBLK)}))
    with pytest.raises(DeviceError):
        validate(ctx, "/dev/sda")          # RM=0 -> rejected
    with pytest.raises(DeviceError):
        validate(ctx, "/dev/sdc")          # mounted -> rejected
    validate(ctx, "/dev/sdb")              # removable, unmounted -> OK (no raise)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/usb/test_devices.py -q`
Expected: FAIL — `ModuleNotFoundError: devboost.usb.devices`.

- [ ] **Step 3: Implement** — `engine/src/devboost/usb/devices.py`

```python
"""Removable-device discovery + safety guards (the single destructive target)."""

from __future__ import annotations

import re

from devboost.core.errors import DeviceError
from devboost.model import Ctx
from devboost.usb.config import Device

# `lsblk -P` emits robust key="value" pairs (safe for empty/multi-word fields like MODEL).
_FIELDS = ["PATH", "SIZE", "TYPE", "RM", "MOUNTPOINT", "MODEL", "VENDOR", "SERIAL", "TRAN"]
_PAIR = re.compile(r'(\w+)="([^"]*)"')


def _parse(ctx: Ctx) -> list[Device]:
    out = ctx.ex.run(["lsblk", "-d", "-P", "-o", ",".join(_FIELDS)]).stdout
    devices: list[Device] = []
    for line in out.splitlines():
        f = dict(_PAIR.findall(line))
        if not f.get("PATH") or f.get("TYPE") != "disk":
            continue
        devices.append(Device(
            name=f["PATH"].rsplit("/", 1)[-1],
            path=f["PATH"],
            size=f.get("SIZE", ""),
            model=f.get("MODEL", "").strip(),
            removable=f.get("RM") == "1",
            mounted=bool(f.get("MOUNTPOINT", "").strip()),
            vendor=f.get("VENDOR", "").strip(),
            serial=f.get("SERIAL", "").strip(),
            tran=f.get("TRAN", "").strip(),
        ))
    return devices


def list_removable(ctx: Ctx) -> list[Device]:
    return [d for d in _parse(ctx) if d.removable and not d.mounted]


def validate(ctx: Ctx, path: str) -> None:
    match = next((d for d in _parse(ctx) if d.path == path), None)
    if match is None:
        raise DeviceError(f"{path}: not a block device")
    if not match.removable:
        raise DeviceError(f"refusing {path}: not a removable whole disk")
    if match.mounted:
        raise DeviceError(f"refusing {path}: mounted — unmount first")
```

- [ ] **Step 4: Run gates**

Run: `cd engine && uv run pytest tests/usb/test_devices.py -q && uv run mypy && uv run ruff check`
Expected: PASS / clean.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/usb/devices.py engine/tests/usb/test_devices.py
git commit -m "feat(usb): removable-device discovery + safety guards"
```

---

### Task 6: `isos` — the Fedora ISO catalog

**Files:**
- Create: `engine/src/devboost/usb/isos.py`
- Test: `engine/tests/usb/test_isos.py`

**Interfaces:**
- Consumes: `IsoSpec` (Task 2).
- Produces: `FEDORA: dict[str, IsoSpec]` (pinned id → url + sha256 + edition) and
  `default_iso() -> IsoSpec`. Resolve real URLs/checksums in the plan's research note below.

> **Implementer note:** populate `FEDORA` from the live Fedora release data at build time — fetch the
> current `Fedora-Everything-netinst-<arch>` URL + its published `CHECKSUM` SHA256 from
> `https://getfedora.org` / the mirror metalink. Verify the pin with context7 / the Fedora docs before
> committing (do **not** invent a checksum). The test below only checks shape, not the literal hash.

- [ ] **Step 1: Write the failing test** — `engine/tests/usb/test_isos.py`

```python
from __future__ import annotations

from devboost.usb.isos import FEDORA, default_iso


def test_catalog_has_a_default_with_required_fields() -> None:
    iso = default_iso()
    assert iso.id in FEDORA
    assert iso.url.startswith("https://") and iso.url.endswith(".iso")
    assert len(iso.sha256) == 64 and iso.edition
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/usb/test_isos.py -q`
Expected: FAIL — `ModuleNotFoundError: devboost.usb.isos`.

- [ ] **Step 3: Implement** — `engine/src/devboost/usb/isos.py`

```python
"""Pinned Fedora ISO catalog (id -> url + sha256 + edition).

Pins are the in-repo source of truth (Principle III). Update via the Fedora release
metalink/CHECKSUM; verify the hash before committing — never invent one.
"""

from __future__ import annotations

from devboost.usb.config import IsoSpec

# NOTE: replace <SHA256_FROM_FEDORA_CHECKSUM> with the real published hash at implementation time.
FEDORA: dict[str, IsoSpec] = {
    "fedora-44": IsoSpec(
        id="fedora-44",
        url="https://download.fedoraproject.org/pub/fedora/linux/releases/44/Everything/x86_64/iso/Fedora-Everything-netinst-x86_64-44-1.5.iso",
        sha256="<SHA256_FROM_FEDORA_CHECKSUM>",
        edition="Everything-netinst",
    ),
}


def default_iso() -> IsoSpec:
    return FEDORA["fedora-44"]
```

- [ ] **Step 4: Run gates** (the literal sha is a placeholder for the *test*, which only checks
  `len == 64`; use a 64-char dummy until the real pin is filled, then replace).

Run: `cd engine && uv run pytest tests/usb/test_isos.py -q && uv run mypy && uv run ruff check`
Expected: PASS / clean.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/usb/isos.py engine/tests/usb/test_isos.py
git commit -m "feat(usb): pinned Fedora ISO catalog"
```

---

### Task 7: `stages.boot_artifacts` + `ks.cfg` profile injection

**Files:**
- Create: `engine/src/devboost/usb/stages.py`
- Test: `engine/tests/usb/test_stages.py`

**Interfaces:**
- Consumes: `Ctx` (`ctx.ex`), `UsbBuildConfig` (Task 2), `Downloader` (Task 4), `resource_path` (`devboost.exec.resources`), `VentoyError` (Task 1).
- Produces:
  - `render_kscfg(template: str, profiles: tuple[str, ...]) -> str` — replace the firstboot
    `devboost install full` with `devboost install <profiles>`.
  - `boot_artifacts(ctx: Ctx, cfg: UsbBuildConfig, dl: Downloader, *, vtoy_mount: Path) -> None` —
    `ventoy -i` (guarded), copy `ventoy.json` + rendered `ks.cfg` + the injection tarball (+ secrets)
    to the VTOY partition, and the downloaded ISO into `ISO/`.

- [ ] **Step 1: Write the failing test** — `engine/tests/usb/test_stages.py`

```python
from __future__ import annotations

import hashlib
from pathlib import Path

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.usb.cache import Cache
from devboost.usb.config import IsoSpec, UsbBuildConfig
from devboost.usb.download import FakeDownloader
from devboost.usb.stages import boot_artifacts, render_kscfg

OS = OsInfo("fedora", "fedora", "x86_64")


def test_render_kscfg_substitutes_profiles() -> None:
    tmpl = "ExecStart=/bin/sh -c '/opt/dev-boost/devboost install full >> /var/log/x 2>&1'"
    out = render_kscfg(tmpl, ("cli", "shell"))
    assert "devboost install cli shell" in out and "install full" not in out


def test_boot_artifacts_installs_ventoy_and_stages_files(tmp_path: Path) -> None:
    iso_bytes = b"fedora-iso"
    sha = hashlib.sha256(iso_bytes).hexdigest()
    iso = IsoSpec(id="fedora-44", url="https://x/f.iso", sha256=sha, edition="Everything")
    # the injection tarball must already exist in dist/ (built earlier); fake it via cache too
    cache = Cache(tmp_path / "cache")
    dl = FakeDownloader(cache, blobs={"https://x/f.iso": iso_bytes})
    cfg = UsbBuildConfig(device="/dev/sdb", arch="x86_64", iso=iso,
                         profiles=("cli",), cache_dir=cache.cache_dir)
    vtoy = tmp_path / "VTOY"
    ctx = Ctx(os=OS, ex=FakeExecutor())
    boot_artifacts(ctx, cfg, dl, vtoy_mount=vtoy)

    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["ventoy", "-i", "/dev/sdb"] in calls or ["sudo", "ventoy", "-i", "/dev/sdb"] in calls
    assert (vtoy / "Bootstrap" / "ks.cfg").read_text().count("devboost install cli") == 1
    assert (vtoy / "ISO" / "fedora-44.iso").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/usb/test_stages.py -q`
Expected: FAIL — `ModuleNotFoundError: devboost.usb.stages`.

- [ ] **Step 3: Implement** — `engine/src/devboost/usb/stages.py`

```python
"""Builder stages: install Ventoy + lay out the USB; optional extras."""

from __future__ import annotations

import shutil
from pathlib import Path

from devboost.core.errors import VentoyError
from devboost.exec.resources import resource_path
from devboost.model import Ctx
from devboost.usb.config import UsbBuildConfig
from devboost.usb.devices import validate
from devboost.usb.download import Downloader


def render_kscfg(template: str, profiles: tuple[str, ...]) -> str:
    return template.replace("devboost install full", "devboost install " + " ".join(profiles))


def boot_artifacts(
    ctx: Ctx, cfg: UsbBuildConfig, dl: Downloader, *, vtoy_mount: Path
) -> None:
    validate(ctx, cfg.device)
    if ctx.ex.run(["ventoy", "-i", cfg.device], sudo=True).code != 0:
        raise VentoyError(f"ventoy install failed on {cfg.device}")

    boot = vtoy_mount / "Bootstrap"
    for d in ("ISO", "Bootstrap", "Installers", "ventoy"):
        (vtoy_mount / d).mkdir(parents=True, exist_ok=True)

    shutil.copyfile(resource_path("ventoy", "ventoy.json"), vtoy_mount / "ventoy" / "ventoy.json")
    kscfg = resource_path("ventoy", "ks.cfg").read_text(encoding="utf-8")
    (boot / "ks.cfg").write_text(render_kscfg(kscfg, cfg.profiles), encoding="utf-8")

    tarball = resource_path("dist", f"devboost-{cfg.arch}.tar.gz")
    if not tarball.exists():
        raise VentoyError(f"injection archive missing: {tarball} (run scripts/build-bundle.sh)")
    shutil.copyfile(tarball, boot / "devboost.tar.gz")

    if cfg.secrets_path is not None:
        shutil.copyfile(cfg.secrets_path, boot / "secrets.age")

    iso_path = dl.fetch(cfg.iso.url, f"{cfg.iso.id}.iso", cfg.iso.sha256)
    shutil.copyfile(iso_path, vtoy_mount / "ISO" / f"{cfg.iso.id}.iso")
```

> Note: `resource_path("ventoy", …)` and `resource_path("dist", …)` resolve under the repo root in
> source mode and `_MEIPASS` when frozen. For the frozen `devboost usb`, bundle `ventoy/` via
> `build-bundle.sh` (add `--add-data "${ROOT}/ventoy:ventoy"`); record that in Task 10.

- [ ] **Step 4: Run gates**

Run: `cd engine && uv run pytest tests/usb/test_stages.py -q && uv run mypy && uv run ruff check`
Expected: PASS / clean. (If the test needs `dist/devboost-x86_64.tar.gz`, create a dummy file in the
test via `tmp_path` + monkeypatch `resource_path`, or build it first; adjust the test fixture
accordingly — keep it hermetic.)

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/usb/stages.py engine/tests/usb/test_stages.py
git commit -m "feat(usb): boot-artifacts stage (ventoy install + layout + ks.cfg profiles)"
```

---

### Task 8: `stages.extras` — extra ISOs + installers

**Files:**
- Modify: `engine/src/devboost/usb/stages.py` (add `extra_isos` + `installers`)
- Test: `engine/tests/usb/test_stages.py` (add cases)

**Interfaces:**
- Produces: `extra_isos(cfg, *, vtoy_mount: Path) -> None` (copy `cfg.extra_isos` → `ISO/`);
  `installers(cfg, *, vtoy_mount: Path) -> None` (copy `cfg.installers` → `Installers/`).

- [ ] **Step 1: Write the failing test** (append to `test_stages.py`)

```python
def test_extra_isos_and_installers_are_staged(tmp_path: Path) -> None:
    from devboost.usb.config import IsoSpec, UsbBuildConfig
    from devboost.usb.stages import extra_isos, installers

    extra = tmp_path / "win.iso"; extra.write_bytes(b"win")
    inst = tmp_path / "tool.run"; inst.write_bytes(b"run")
    iso = IsoSpec(id="fedora-44", url="u", sha256="s", edition="E")
    cfg = UsbBuildConfig(device="/dev/sdb", arch="x86_64", iso=iso, cache_dir=tmp_path,
                         extra_isos=(extra,), installers=(inst,))
    vtoy = tmp_path / "VTOY"; (vtoy / "ISO").mkdir(parents=True); (vtoy / "Installers").mkdir()
    extra_isos(cfg, vtoy_mount=vtoy)
    installers(cfg, vtoy_mount=vtoy)
    assert (vtoy / "ISO" / "win.iso").exists() and (vtoy / "Installers" / "tool.run").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/usb/test_stages.py::test_extra_isos_and_installers_are_staged -q`
Expected: FAIL — `ImportError: cannot import name 'extra_isos'`.

- [ ] **Step 3: Implement** (append to `stages.py`)

```python
def extra_isos(cfg: UsbBuildConfig, *, vtoy_mount: Path) -> None:
    for src in cfg.extra_isos:
        shutil.copyfile(src, vtoy_mount / "ISO" / src.name)


def installers(cfg: UsbBuildConfig, *, vtoy_mount: Path) -> None:
    for src in cfg.installers:
        shutil.copyfile(src, vtoy_mount / "Installers" / src.name)
```

- [ ] **Step 4: Run gates**

Run: `cd engine && uv run pytest tests/usb/test_stages.py -q && uv run mypy && uv run ruff check`
Expected: PASS / clean.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/usb/stages.py engine/tests/usb/test_stages.py
git commit -m "feat(usb): optional extra-ISO + installer staging"
```

---

### Task 9: `builder.build` — orchestrate the stages + mount handling

**Files:**
- Create: `engine/src/devboost/usb/builder.py`
- Test: `engine/tests/usb/test_builder.py`

**Interfaces:**
- Consumes: all of `stages` (Tasks 7–8), `Ctx`, `UsbBuildConfig`, `Downloader`.
- Produces: `build(ctx: Ctx, cfg: UsbBuildConfig, dl: Downloader, *, vtoy_mount: Path) -> None` —
  runs `boot_artifacts`, then `extra_isos`, then `installers` (mirror added in P2 when
  `cfg.offline_mirror`). The caller resolves `vtoy_mount` (Ventoy labels the data partition `VTOY`).

- [ ] **Step 1: Write the failing test** — `engine/tests/usb/test_builder.py`

```python
from __future__ import annotations

import hashlib
from pathlib import Path

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.usb.builder import build
from devboost.usb.cache import Cache
from devboost.usb.config import IsoSpec, UsbBuildConfig
from devboost.usb.download import FakeDownloader


def test_build_runs_boot_then_extras(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import devboost.usb.stages as stages

    order: list[str] = []
    monkeypatch.setattr(stages, "boot_artifacts", lambda *a, **k: order.append("boot"))
    monkeypatch.setattr(stages, "extra_isos", lambda *a, **k: order.append("extra"))
    monkeypatch.setattr(stages, "installers", lambda *a, **k: order.append("installers"))

    data = b"iso"; iso = IsoSpec("fedora-44", "u", hashlib.sha256(data).hexdigest(), "E")
    cfg = UsbBuildConfig(device="/dev/sdb", arch="x86_64", iso=iso, cache_dir=tmp_path)
    build(Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor()),
          cfg, FakeDownloader(Cache(tmp_path), {}), vtoy_mount=tmp_path / "VTOY")
    assert order == ["boot", "extra", "installers"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/usb/test_builder.py -q`
Expected: FAIL — `ModuleNotFoundError: devboost.usb.builder`.

- [ ] **Step 3: Implement** — `engine/src/devboost/usb/builder.py`

```python
"""Orchestrate the USB build stages from a UsbBuildConfig."""

from __future__ import annotations

from pathlib import Path

from devboost.model import Ctx
from devboost.usb import stages
from devboost.usb.config import UsbBuildConfig
from devboost.usb.download import Downloader


def build(ctx: Ctx, cfg: UsbBuildConfig, dl: Downloader, *, vtoy_mount: Path) -> None:
    stages.boot_artifacts(ctx, cfg, dl, vtoy_mount=vtoy_mount)
    stages.extra_isos(cfg, vtoy_mount=vtoy_mount)
    stages.installers(cfg, vtoy_mount=vtoy_mount)
    # P2: if cfg.offline_mirror: stages.mirror(ctx, cfg, vtoy_mount=vtoy_mount)
```

- [ ] **Step 4: Run gates**

Run: `cd engine && uv run pytest tests/usb/test_builder.py -q && uv run mypy && uv run ruff check`
Expected: PASS / clean.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/usb/builder.py engine/tests/usb/test_builder.py
git commit -m "feat(usb): builder orchestrates boot + extras stages"
```

---

### Task 10: `wizard` + the `devboost usb` CLI command; delete `make-usb.sh`

**Files:**
- Create: `engine/src/devboost/usb/wizard.py`
- Create: `engine/src/devboost/cli/usb.py`
- Modify: `engine/src/devboost/cli/app.py` (register the `usb` command)
- Modify: `scripts/build-bundle.sh` (bundle `ventoy/` so the frozen `usb` command can stage it)
- Delete: `ventoy/make-usb.sh`
- Test: `engine/tests/usb/test_cli_usb.py`

**Interfaces:**
- Consumes: `list_removable`, `default_iso`, `FEDORA`, `build`, `UsbBuildConfig`, `UrllibDownloader`, `Cache`.
- Produces:
  - `wizard.run(ctx: Ctx, *, defaults: UsbBuildConfig | None = None) -> UsbBuildConfig` — questionary
    prompts (each seeded with a default); returns a config. (Thin; not unit-tested.)
  - `usb(...)` Typer command: flags `--device`, `--arch`, `--iso`, `--profile` (repeatable),
    `--secrets`, `--cache-dir`, `--yes`, `--no-wizard`. When a required field is missing and
    `--no-wizard` is not set, runs the wizard; else validates flags. Then resolves the VTOY mount and
    calls `build(...)`.

- [ ] **Step 1: Write the failing test** — `engine/tests/usb/test_cli_usb.py`

```python
from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from devboost.cli.app import app

runner = CliRunner()


def test_usb_help_lists_the_command() -> None:
    result = runner.invoke(app, ["usb", "--help"])
    assert result.exit_code == 0
    assert "--device" in result.stdout and "--profile" in result.stdout


def test_usb_no_wizard_requires_device(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    # --no-wizard with no --device should error out (exit 1), not prompt.
    result = runner.invoke(app, ["usb", "--no-wizard"])
    assert result.exit_code != 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/usb/test_cli_usb.py -q`
Expected: FAIL — no `usb` command registered.

- [ ] **Step 3: Implement** — `engine/src/devboost/usb/wizard.py`

```python
"""Interactive wizard: questionary prompts (each defaulted) -> UsbBuildConfig."""

from __future__ import annotations

import platform
from pathlib import Path
from tempfile import gettempdir

import questionary

from devboost.core.errors import DeviceError
from devboost.model import Ctx
from devboost.usb.config import UsbBuildConfig
from devboost.usb.devices import list_removable
from devboost.usb.isos import FEDORA, default_iso

_PROFILES = ("full", "terminal", "devtools", "base", "cli", "shell", "gnome")


def run(ctx: Ctx) -> UsbBuildConfig:
    devices = list_removable(ctx)
    if not devices:
        raise DeviceError("no removable disk found — plug in a USB and retry")
    device = questionary.select(
        "Target USB device (WILL BE WIPED):",
        choices=[questionary.Choice(d.label(), value=d.path) for d in devices],
    ).ask()
    # Distinct, safe labels like:  /dev/sdb  —  SanDisk Ultra (usb)  —  32G  [sn:4C53]
    # (list_removable already filtered to removable + unmounted disks; the builder re-validate()s.)

    arch = questionary.select("Architecture:", choices=["x86_64", "aarch64"],
                              default=platform.machine()).ask()
    iso_id = questionary.select("Fedora ISO:", choices=list(FEDORA), default=default_iso().id).ask()
    profiles = questionary.checkbox(
        "Profiles to install on first boot:",
        choices=[questionary.Choice(p, checked=(p == "full")) for p in _PROFILES],
    ).ask() or ["full"]
    secrets = questionary.path("Path to secrets.age (blank to skip):", default="").ask()
    cache = questionary.path("Cache dir for downloads:", default=str(Path(gettempdir()) / "devboost-usb")).ask()

    return UsbBuildConfig(
        device=device, arch=arch, iso=FEDORA[iso_id], profiles=tuple(profiles),
        secrets_path=Path(secrets) if secrets else None, cache_dir=Path(cache),
    )
```

Then `engine/src/devboost/cli/usb.py`:

```python
"""The `devboost usb` command: flags or wizard -> build a bootable Ventoy USB."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import gettempdir
from typing import Annotated, Optional

import typer

from devboost.core import log, osinfo
from devboost.exec.executor import RealExecutor
from devboost.model import Ctx
from devboost.usb import wizard
from devboost.usb.builder import build
from devboost.usb.cache import Cache
from devboost.usb.config import UsbBuildConfig
from devboost.usb.download import UrllibDownloader
from devboost.usb.isos import FEDORA, default_iso


def usb(
    device: Annotated[Optional[str], typer.Option(help="Target removable disk, e.g. /dev/sdb")] = None,
    arch: Annotated[str, typer.Option(help="x86_64 | aarch64")] = "",
    iso: Annotated[str, typer.Option(help=f"ISO id: {', '.join(FEDORA)}")] = "",
    profile: Annotated[list[str], typer.Option(help="Profiles for firstboot (repeatable)")] = [],
    secrets: Annotated[Optional[Path], typer.Option(help="Path to secrets.age")] = None,
    cache_dir: Annotated[Optional[Path], typer.Option(help="Download cache dir")] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
    no_wizard: Annotated[bool, typer.Option("--no-wizard", help="Fail instead of prompting")] = False,
) -> None:
    """Build a bootable dev-boost Ventoy USB (interactive, or fully via flags)."""
    ctx = Ctx(os=osinfo.detect(), ex=RealExecutor())
    if device is None and not no_wizard:
        cfg = wizard.run(ctx)
    elif device is None:
        log.error("--device is required with --no-wizard")
        raise typer.Exit(code=1)
    else:
        cfg = UsbBuildConfig(
            device=device,
            arch=arch or osinfo.detect().arch,
            iso=FEDORA[iso] if iso else default_iso(),
            profiles=tuple(profile) or ("full",),
            secrets_path=secrets,
            cache_dir=cache_dir or Path(gettempdir()) / "devboost-usb",
            assume_yes=yes,
        )
    vtoy = Path(os.environ.get("VTOY_MOUNT", f"/run/media/{os.environ.get('USER', 'root')}/VTOY"))
    build(ctx, cfg, UrllibDownloader(Cache(cfg.cache_dir)), vtoy_mount=vtoy)
    log.ok(f"usb: built {cfg.device} (Fedora {cfg.iso.id}, profiles {' '.join(cfg.profiles)})")
```

Register in `engine/src/devboost/cli/app.py` (near the other `@app.command()`s):

```python
from devboost.cli.usb import usb as _usb
app.command(name="usb")(_usb)
```

Add to `scripts/build-bundle.sh` data args: `data_args+=(--add-data "${ROOT}/ventoy:ventoy")`
and (so the frozen `usb` can stage the injection archive) `--add-data "${ROOT}/dist:dist"` is NOT
appropriate (dist is the output); instead the frozen `usb` command should rebuild/download the
tarball — note this limitation in the command help. Finally: `git rm ventoy/make-usb.sh`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/usb/test_cli_usb.py -q`
Expected: FAIL — `usb` not registered.

- [ ] **Step 3: Implement** the three files above + delete `make-usb.sh`.

- [ ] **Step 4: Run gates + full suite**

Run: `cd engine && uv run pytest -q && uv run mypy && uv run ruff check`
Expected: PASS / clean (whole suite stays green).

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/usb/wizard.py engine/src/devboost/cli/usb.py \
        engine/src/devboost/cli/app.py scripts/build-bundle.sh engine/tests/usb/test_cli_usb.py
git rm ventoy/make-usb.sh
git commit -m "feat(usb): devboost usb command + questionary wizard; remove make-usb.sh"
```

**Checkpoint (Phase 1):** `devboost usb --help` works; `devboost usb --device … --iso … --yes`
builds a USB non-interactively; the wizard fills the same config; `make-usb.sh` is gone; gates green.

---

# Phase 2 — offline dnf+flatpak mirror (in this spec)

> **Honest scope (from the design §7):** only dnf + flatpak are mirror-able. Modules that install via
> `mise`/`npm`/GitHub-releases/`curl|sh` still need network; under `--offline` they are skipped with a
> clear "needs network" report. Do **not** claim a 100%-offline install.

### Task 11: profile → package-set introspection

**Files:**
- Create: `engine/src/devboost/usb/mirror.py`
- Test: `engine/tests/usb/test_mirror.py`

**Interfaces:**
- Consumes: `registry.load`, `profiles.expand`, the typed modules. Add a `RecordingExecutor` (a
  variant of `FakeExecutor` that records `pkg`/`flatpak` calls) used to *describe* what a profile
  would install without performing it.
- Produces: `package_set(profiles: tuple[str, ...], root: Path) -> tuple[set[str], set[str]]` —
  returns `(dnf_packages, flatpak_app_ids)` by running each module's `install` against a recording
  executor over a Fedora `Ctx` and collecting `dnf install` package args + `flatpak install` app ids.

- [ ] **Step 1: Write the failing test** — `engine/tests/usb/test_mirror.py`

```python
from __future__ import annotations

from pathlib import Path

from devboost.core.settings import settings
from devboost.usb.mirror import package_set


def test_package_set_collects_dnf_and_flatpak_for_cli_and_apps() -> None:
    dnf, flat = package_set(("cli", "apps"), settings.root)
    assert "ripgrep" in dnf                    # a cli package (from a PackageModule)
    assert "md.obsidian.Obsidian" in flat      # an apps flatpak id
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd engine && uv run pytest tests/usb/test_mirror.py -q`
Expected: FAIL — `ModuleNotFoundError: devboost.usb.mirror`.

- [ ] **Step 3: Implement** — `engine/src/devboost/usb/mirror.py`

```python
"""Offline mirror: describe a profile's dnf/flatpak package set, then materialize it."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx

_FEDORA = OsInfo("fedora", "fedora", "x86_64")


class _Recorder(FakeExecutor):
    """Records dnf-install package args and flatpak-install app ids; never mutates anything."""

    def __init__(self) -> None:
        super().__init__()
        self.dnf: set[str] = set()
        self.flatpak: set[str] = set()

    def run(self, argv: Sequence[str], *, sudo: bool = False, stdin: str | None = None,
            env: Mapping[str, str] | None = None) -> Result:
        a = list(argv)
        if a[:2] == ["dnf", "install"]:
            self.dnf.update(x for x in a[2:] if not x.startswith("-"))
        elif a[:2] == ["flatpak", "install"]:
            self.flatpak.update(x for x in a[2:] if not x.startswith("-") and x != "flathub")
        return super().run(argv, sudo=sudo, stdin=stdin, env=env)


def package_set(profiles: tuple[str, ...], root: Path) -> tuple[set[str], set[str]]:
    modules = load()
    profs = load_profiles(root / "profiles.toml")
    order = toposort(expand(list(profiles), profs, modules), modules)
    rec = _Recorder()
    ctx = Ctx(os=_FEDORA, ex=rec, force=True)   # force=True so verify never short-circuits install
    for name in order:
        try:
            modules[name]().install(ctx)
        except Exception:  # noqa: BLE001 — describing only; ignore modules needing real state
            continue
    return rec.dnf, rec.flatpak
```

> **Implementer note:** some modules read files/env during `install` (e.g. secrets, dotfiles). The
> `try/except` keeps the *describe* pass robust — those modules contribute nothing to the mirror and
> are exactly the network/stateful ones documented as "needs network." Verify the collected sets on a
> Fedora box and expand the test with `base`/`system` once confirmed.

- [ ] **Step 4: Run gates**

Run: `cd engine && uv run pytest tests/usb/test_mirror.py -q && uv run mypy && uv run ruff check`
Expected: PASS / clean.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/usb/mirror.py engine/tests/usb/test_mirror.py
git commit -m "feat(usb): profile->package-set introspection for the offline mirror"
```

---

### Task 12: dnf reposync + flatpak bundle stages

**Files:**
- Modify: `engine/src/devboost/usb/mirror.py` (add `mirror_dnf`, `mirror_flatpak`)
- Test: `engine/tests/usb/test_mirror.py` (add cases)

**Interfaces:**
- Produces:
  - `mirror_dnf(ctx, packages: set[str], dest: Path) -> None` — `dnf download --resolve --destdir
    <dest> <pkgs>` then `createrepo_c <dest>` (all via `ctx.ex`).
  - `mirror_flatpak(ctx, app_ids: set[str], dest: Path) -> None` — `flatpak create-usb`/bundle each id
    into `<dest>` (via `ctx.ex`).

- [ ] **Step 1: Write the failing test** (append to `test_mirror.py`)

```python
def test_mirror_dnf_downloads_and_creates_repo(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from devboost.core.osinfo import OsInfo
    from devboost.exec.executor import FakeExecutor
    from devboost.model import Ctx
    from devboost.usb.mirror import mirror_dnf

    ctx = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor())
    mirror_dnf(ctx, {"ripgrep", "git"}, tmp_path)
    calls = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert any("dnf download --resolve" in c and "ripgrep" in c for c in calls)
    assert any(c.startswith("createrepo_c") or "createrepo" in c for c in calls)
```

- [ ] **Step 2–5:** implement `mirror_dnf`/`mirror_flatpak` (sorted package args for determinism),
  run gates, commit `feat(usb): dnf reposync + flatpak bundle mirror stages`.

```python
def mirror_dnf(ctx: Ctx, packages: set[str], dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    ctx.ex.run(["dnf", "download", "--resolve", "--destdir", str(dest), *sorted(packages)], sudo=True)
    ctx.ex.run(["createrepo_c", str(dest)], sudo=True)


def mirror_flatpak(ctx: Ctx, app_ids: set[str], dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for app in sorted(app_ids):
        ctx.ex.run(["flatpak", "create-usb", str(dest), app])
```

---

### Task 13: wire the mirror into the builder + wizard + offline firstboot

**Files:**
- Modify: `engine/src/devboost/usb/stages.py` (add `mirror(ctx, cfg, *, vtoy_mount)`)
- Modify: `engine/src/devboost/usb/builder.py` (call `mirror` when `cfg.offline_mirror`)
- Modify: `engine/src/devboost/usb/wizard.py` (add the offline-mirror confirm, default False, with a size/scope warning)
- Modify: `engine/src/devboost/usb/stages.py` `render_kscfg` → when offline, append `--offline` to the firstboot `devboost install`
- Modify: `engine/src/devboost/cli/install.py`/`app.py` — add an `--offline` flag to `install` that points dnf/flatpak at `/run/media/.../Bootstrap/repo` (documented partial-offline behavior)
- Test: `engine/tests/usb/test_stages.py` + `engine/tests/cli/test_cli.py` (offline flag)

**Interfaces:**
- Produces: `stages.mirror(ctx, cfg, *, vtoy_mount)` — `package_set` → `mirror_dnf` + `mirror_flatpak`
  into `vtoy_mount/Bootstrap/repo/{dnf,flatpak}`. `render_kscfg(..., offline: bool)` appends `--offline`.
  `devboost install --offline` configures the local repos and skips network-only modules with a report.

- [ ] **Steps 1–5 (TDD each):**
  - Test: `render_kscfg(tmpl, ("full",), offline=True)` contains `devboost install full --offline`.
  - Test: `build(...)` with `cfg.offline_mirror=True` calls `stages.mirror` (monkeypatch + assert order
    `boot, extra, installers, mirror`).
  - Test: `devboost install full --offline --dry-run` exits 0 and (with a `FakeExecutor`) prints a
    "needs network" skip line for a known network-only module (e.g. `uv` / `web-runtimes`).
  - Implement minimally, run `uv run pytest && uv run mypy && uv run ruff check`, commit
    `feat(usb): offline dnf+flatpak mirror stage + offline-aware firstboot`.

**Checkpoint (Phase 2):** `devboost usb` with the offline option mirrors dnf+flatpak into the USB and
writes an `--offline` firstboot; `devboost install --offline` uses the local repos and clearly reports
the documented network-only gaps. Whole suite green; `mypy --strict` + ruff clean.

---

## Documentation (fold into the last task of each phase)

- Update `README.md` "Recovery walkthrough" / commands: add `devboost usb` (replaces "build the USB"
  guidance and the old `make-usb.sh`).
- Update `docs/ventoy.md` to describe `devboost usb` (wizard + flags + caching + offline option) and
  the injection-archive flow.
- Note in `docs/architecture.md` delivery section that `make-usb.sh` is replaced by `devboost usb`.

## Self-Review

- **Spec coverage:** §1–§9 → Tasks 1–10 (P1); §7 offline mirror → Tasks 11–13 (P2); §8 caching →
  Tasks 3–4; §9 testing → every task's TDD cycle; §4 wizard⟂builder → Tasks 9–10; replace make-usb.sh
  → Task 10. Open questions (§12) carried as implementer notes (ISO pin, package-set introspection,
  root/sudo). No gaps.
- **Placeholders:** the only intentional one is the Fedora ISO sha256 (Task 6) — flagged with explicit
  instructions to fetch+verify the real hash from Fedora before committing (never invent it); the test
  checks shape only. No other TBDs.
- **Type consistency:** `UsbBuildConfig`/`IsoSpec`/`Device` (Task 2) used unchanged in 5–10;
  `Downloader.fetch(url, name, sha256)` consistent across Tasks 4/7/9; `build(ctx, cfg, dl, *,
  vtoy_mount)` consistent in Tasks 9/10/13; `render_kscfg` signature extended (not renamed) in Task 13.
