# USB Experience Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the experience layer to `devboost usb` — a curated OS catalog, update-detect (non-destructive update of an existing dev-boost stick), live `rich` progress, a `--dry-run` preview, and a final summary panel — all behind injected seams.

**Architecture:** Evolve the flat `isos.py` into a richer `catalog.py` (one `Os` entry per distro). Add four new single-responsibility units under `engine/src/devboost/usb/`: `marker.py` (build-time marker JSON), `report.py` (injected `Reporter` seam), `probe.py` (read-only disk-state detection), `preview.py` (dry-run plan renderer). Thread a `Reporter` through `build()`/stages; the `Reporter` is constructor-injected into `UrllibDownloader` so the `Downloader` Protocol `fetch(...)` stays unchanged. The builder branches on a new `cfg.mode` (`build` vs `update`).

**Tech Stack:** Python 3.12, Typer, Pydantic v2, `rich` (progress/panels — promoted to a direct dependency), `questionary` (wizard), stdlib `urllib`/`tempfile`. Tests: `pytest`, `mypy --strict`, `ruff`.

## Global Constraints

- All side effects go through the injected `Executor` (`ctx.ex.run(argv, sudo=...)`) and `Downloader` — never raw `subprocess` or shell strings. Privileged steps (`ventoy`, `mount`, `umount`) pass `sudo=True`.
- The `Downloader` Protocol `fetch(self, url: str, name: str, sha256: str) -> Path` MUST stay byte-for-byte unchanged. The progress reporter is constructor-injected into `UrllibDownloader` only.
- `mypy --strict`, `ruff` (line-length 100), and `pytest` are merge gates — every task ends green on all three. Run from `engine/`: `uv run pytest`, `uv run mypy --strict src`, `uv run ruff check src tests`.
- Every module starts with `from __future__ import annotations`.
- Fedora ISO checksums are in-repo pinned data fetched from Fedora's signed `CHECKSUM` — never invented (Principle III).
- A read-only probe must NEVER block the run: any failure degrades to `DiskState("blank")` with a warning.
- The wipe gate (`if not cfg.assume_yes: raise DeviceError(...)`) in `boot_artifacts` is sacrosanct — it stays the first line and `update_stage` must NOT call `ventoy -i` or wipe.
- `from devboost import __version__` is `"0.1.0"`.

---

### Task 1: Evolve `isos.py` → `catalog.py` (the `Os` model)

**Files:**
- Create: `engine/src/devboost/usb/catalog.py`
- Delete: `engine/src/devboost/usb/isos.py`
- Modify: `engine/src/devboost/usb/wizard.py:15` (import), `engine/src/devboost/cli/usb.py:26,34` (import + help)
- Rename test: `engine/tests/usb/test_isos.py` → `engine/tests/usb/test_catalog.py`

**Interfaces:**
- Consumes: `IsoSpec` from `devboost.usb.config`; `UsbError` from `devboost.core.errors`.
- Produces:
  - `@dataclass(frozen=True) class Os: id: str; name: str; distro: str; version: str; edition: str; isos: dict[str, IsoSpec]`
  - `CATALOG: dict[str, Os]`
  - `supported() -> list[Os]`
  - `iso_for(os_id: str, arch: str) -> IsoSpec` (raises `UsbError` on unknown id or unpinned arch)
  - `default_os() -> Os`, `default_iso() -> IsoSpec`

- [ ] **Step 1: Fetch the REAL Fedora-44 netinst x86_64 sha256.**

The current `isos.py` URL is `https://download.fedoraproject.org/pub/fedora/linux/releases/44/Everything/x86_64/iso/Fedora-Everything-netinst-x86_64-44-1.5.iso` with a 64-zero placeholder. Fetch the signed CHECKSUM and extract the hash:

```bash
curl -fsSL "https://download.fedoraproject.org/pub/fedora/linux/releases/44/Everything/x86_64/iso/Fedora-Everything-netinst-x86_64-44-1.5.iso-CHECKSUM" | grep -i "netinst-x86_64-44-1.5.iso)" 
```
Expected: a line like `SHA256 (Fedora-Everything-netinst-x86_64-44-1.5.iso) = <64 hex>`. Use that hex as `sha256`.

**If the URL 404s or there is no network:** the version/filename pin (`44-1.5`) is wrong or unreachable. Correct the filename/URL from the real Fedora release directory listing if reachable; otherwise keep the 64-zero placeholder, add a code comment `# BLOCKING: real CHECKSUM not fetched — fill before release`, and report this as a `DONE_WITH_CONCERNS` blocker. Do NOT invent a hash. The `test_catalog_default_sha256_is_64_hex` test asserts only the 64-char hex *shape*, so a placeholder still passes the suite while staying visibly unfilled.

- [ ] **Step 2: Write the failing tests** in `engine/tests/usb/test_catalog.py` (delete `test_isos.py` first; recreate with this content):

```python
from __future__ import annotations

import re

import pytest

from devboost.core.errors import UsbError
from devboost.usb.catalog import CATALOG, default_iso, default_os, iso_for, supported


def test_catalog_default_has_required_fields() -> None:
    iso = default_iso()
    assert iso.id in CATALOG
    assert iso.url.startswith("https://") and iso.url.endswith(".iso")
    assert iso.edition


def test_default_os_is_fedora_44() -> None:
    os_entry = default_os()
    assert os_entry.id == "fedora-44"
    assert os_entry.distro == "fedora" and os_entry.version == "44"
    assert "x86_64" in os_entry.isos


def test_supported_returns_friendly_named_entries() -> None:
    names = [o.name for o in supported()]
    assert any("Fedora 44" in n for n in names)
    assert len(supported()) == len(CATALOG)


def test_iso_for_x86_64_returns_spec() -> None:
    spec = iso_for("fedora-44", "x86_64")
    assert spec.id == "fedora-44" and "x86_64" in spec.url


def test_iso_for_unsupported_arch_raises() -> None:
    with pytest.raises(UsbError, match="aarch64"):
        iso_for("fedora-44", "aarch64")


def test_iso_for_unknown_os_raises() -> None:
    with pytest.raises(UsbError, match="unknown OS"):
        iso_for("ubuntu-99", "x86_64")


def test_catalog_default_sha256_is_64_hex() -> None:
    assert re.fullmatch(r"[0-9a-f]{64}", default_iso().sha256)
```

- [ ] **Step 3: Run the tests, verify they fail**

Run: `cd engine && uv run pytest tests/usb/test_catalog.py -q`
Expected: FAIL — `ModuleNotFoundError: devboost.usb.catalog`.

- [ ] **Step 4: Create `engine/src/devboost/usb/catalog.py`**

```python
"""Supported-OS catalog (id -> friendly name + per-arch pinned IsoSpec).

Pins are the in-repo source of truth (Principle III). Update via the Fedora
release CHECKSUM; verify the hash before committing — never invent one. Adding a
distro is one Os entry; it appears in the wizard select with zero code changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from devboost.core.errors import UsbError
from devboost.usb.config import IsoSpec


@dataclass(frozen=True)
class Os:
    id: str
    name: str
    distro: str
    version: str
    edition: str
    isos: dict[str, IsoSpec]


CATALOG: dict[str, Os] = {
    "fedora-44": Os(
        id="fedora-44",
        name="Fedora 44 — Everything (netinst)",
        distro="fedora",
        version="44",
        edition="Everything-netinst",
        isos={
            "x86_64": IsoSpec(
                id="fedora-44",
                url="https://download.fedoraproject.org/pub/fedora/linux/releases/44/Everything/x86_64/iso/Fedora-Everything-netinst-x86_64-44-1.5.iso",
                sha256="<PASTE REAL 64-HEX FROM STEP 1>",
                edition="Everything-netinst",
            ),
        },
    ),
}


def supported() -> list[Os]:
    """All catalog entries, for the wizard's friendly-named select."""
    return list(CATALOG.values())


def iso_for(os_id: str, arch: str) -> IsoSpec:
    """The pinned IsoSpec for *os_id* on *arch*, or raise UsbError."""
    os_entry = CATALOG.get(os_id)
    if os_entry is None:
        raise UsbError(f"unknown OS id {os_id!r}")
    spec = os_entry.isos.get(arch)
    if spec is None:
        raise UsbError(f"no pinned ISO for arch {arch!r} (os_id={os_id!r})")
    return spec


def default_os() -> Os:
    return CATALOG["fedora-44"]


def default_iso() -> IsoSpec:
    return default_os().isos["x86_64"]
```

- [ ] **Step 5: Update the two importers (keep them green; friendly-name UX comes in Task 10).**

In `engine/src/devboost/usb/wizard.py` line 15, replace:
```python
from devboost.usb.isos import FEDORA, default_iso, iso_for
```
with:
```python
from devboost.usb.catalog import CATALOG, default_iso, iso_for
```
Then in `wizard.py` replace the two `FEDORA` usages (the `list(FEDORA)` choices and any reference) with `list(CATALOG)`:
```python
    iso_id = questionary.select(
        "Fedora ISO:", choices=list(CATALOG), default=default_iso().id
    ).ask()
```

In `engine/src/devboost/cli/usb.py` line 26, replace:
```python
from devboost.usb.isos import FEDORA, default_iso, iso_for
```
with:
```python
from devboost.usb.catalog import CATALOG, default_iso, iso_for
```
Then update the help string on line 34 (`f"ISO id: {', '.join(FEDORA)}"`) to `f"ISO id: {', '.join(CATALOG)}"`.

- [ ] **Step 6: Delete `engine/src/devboost/usb/isos.py`.**

```bash
git rm engine/src/devboost/usb/isos.py engine/tests/usb/test_isos.py
```

- [ ] **Step 7: Run the full gate**

Run: `cd engine && uv run pytest tests/usb/test_catalog.py tests/usb/test_stages.py tests/usb/test_cli_usb.py -q && uv run mypy --strict src && uv run ruff check src tests`
Expected: PASS. (`grep -rn "usb.isos\|FEDORA" engine/src engine/tests` should return nothing.)

- [ ] **Step 8: Commit**

```bash
git add engine/src/devboost/usb/catalog.py engine/tests/usb/test_catalog.py engine/src/devboost/usb/wizard.py engine/src/devboost/cli/usb.py
git commit -m "feat(usb): evolve isos.py into catalog.py with the Os model"
```

---

### Task 2: Build-time marker (`marker.py`)

**Files:**
- Create: `engine/src/devboost/usb/marker.py`
- Test: `engine/tests/usb/test_marker.py`

**Interfaces:**
- Produces:
  - `class Marker(BaseModel): version: str; os_id: str; arch: str; built_at: str`
  - `marker_path(vtoy_mount: Path) -> Path` → `<vtoy_mount>/Bootstrap/.devboost-usb.json`
  - `write_marker(vtoy_mount: Path, marker: Marker) -> Path`
  - `read_marker(directory: Path) -> Marker | None` (looks for `<directory>/Bootstrap/.devboost-usb.json`; returns `None` on missing/unreadable/invalid)

- [ ] **Step 1: Write the failing tests** in `engine/tests/usb/test_marker.py`:

```python
from __future__ import annotations

from pathlib import Path

from devboost.usb.marker import Marker, marker_path, read_marker, write_marker


def _m() -> Marker:
    return Marker(version="0.1.0", os_id="fedora-44", arch="x86_64",
                  built_at="2026-06-26T00:00:00+00:00")


def test_write_then_read_round_trips(tmp_path: Path) -> None:
    vtoy = tmp_path / "VTOY"
    p = write_marker(vtoy, _m())
    assert p == marker_path(vtoy)
    got = read_marker(vtoy)
    assert got == _m()


def test_read_missing_returns_none(tmp_path: Path) -> None:
    assert read_marker(tmp_path) is None


def test_read_invalid_json_returns_none(tmp_path: Path) -> None:
    p = marker_path(tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text("{not json", encoding="utf-8")
    assert read_marker(tmp_path) is None
```

- [ ] **Step 2: Run, verify fail** — `cd engine && uv run pytest tests/usb/test_marker.py -q` → FAIL (no module).

- [ ] **Step 3: Create `engine/src/devboost/usb/marker.py`**

```python
"""The build-time marker (Bootstrap/.devboost-usb.json) that identifies a dev-boost USB."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ValidationError


class Marker(BaseModel):
    version: str
    os_id: str
    arch: str
    built_at: str


def marker_path(vtoy_mount: Path) -> Path:
    return vtoy_mount / "Bootstrap" / ".devboost-usb.json"


def write_marker(vtoy_mount: Path, marker: Marker) -> Path:
    path = marker_path(vtoy_mount)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(marker.model_dump_json(indent=2), encoding="utf-8")
    return path


def read_marker(directory: Path) -> Marker | None:
    path = marker_path(directory)
    if not path.exists():
        return None
    try:
        return Marker.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValidationError, ValueError, OSError):
        return None
```

- [ ] **Step 4: Run, verify pass** — `uv run pytest tests/usb/test_marker.py -q` → PASS.

- [ ] **Step 5: Gate + commit**

```bash
cd engine && uv run mypy --strict src && uv run ruff check src tests
git add engine/src/devboost/usb/marker.py engine/tests/usb/test_marker.py
git commit -m "feat(usb): add the build-time marker schema + read/write"
```

---

### Task 3: Reporter seam (`report.py`) + promote `rich` to a direct dependency

**Files:**
- Create: `engine/src/devboost/usb/report.py`
- Modify: `engine/pyproject.toml` (add `rich` to `dependencies`)
- Test: `engine/tests/usb/test_report.py`

**Interfaces:**
- Produces:
  - `class Reporter(Protocol)` with `step(self, msg: str) -> None`, `progress(self, label: str, total: int) -> AbstractContextManager[Callable[[int], None]]`, `summary(self, panel: str) -> None`
  - `class RichReporter` (real; rich progress/panel)
  - `class FakeReporter` with `.steps: list[str]`, `.summaries: list[str]`, `.progress_calls: list[tuple[str, int]]`, `.advances: list[int]`

- [ ] **Step 1: Add `rich` to `engine/pyproject.toml`.** `rich` is currently only a transitive dep of typer; since this code imports it directly, declare it. In the `dependencies = [...]` array add the line (keep alph-ish order near questionary):

```toml
    "rich>=13.7",
```
Then: `cd engine && uv sync` (resolves; `rich` 15.x already present transitively).

- [ ] **Step 2: Write the failing tests** in `engine/tests/usb/test_report.py`:

```python
from __future__ import annotations

from devboost.usb.report import FakeReporter, Reporter


def test_fake_reporter_records_steps_and_summaries() -> None:
    r = FakeReporter()
    r.step("Ventoy installed")
    r.summary("done")
    assert r.steps == ["Ventoy installed"]
    assert r.summaries == ["done"]


def test_fake_reporter_progress_records_label_total_and_advances() -> None:
    r = FakeReporter()
    with r.progress("fedora-44.iso", 100) as advance:
        advance(40)
        advance(60)
    assert r.progress_calls == [("fedora-44.iso", 100)]
    assert r.advances == [40, 60]


def test_fake_reporter_satisfies_protocol() -> None:
    assert isinstance(FakeReporter(), Reporter)
```

- [ ] **Step 3: Run, verify fail** — `uv run pytest tests/usb/test_report.py -q` → FAIL (no module).

- [ ] **Step 4: Create `engine/src/devboost/usb/report.py`**

```python
"""Injected reporter seam: live rich progress/steps/summary (real) or recorder (fake)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Protocol, runtime_checkable

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn


@runtime_checkable
class Reporter(Protocol):
    def step(self, msg: str) -> None: ...
    def progress(
        self, label: str, total: int
    ) -> AbstractContextManager[Callable[[int], None]]: ...
    def summary(self, panel: str) -> None: ...


class RichReporter:
    def __init__(self) -> None:
        self._console = Console()

    def step(self, msg: str) -> None:
        self._console.print(f"[green]✓[/green] {msg}")

    @contextmanager
    def progress(self, label: str, total: int) -> Iterator[Callable[[int], None]]:
        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            console=self._console,
        ) as prog:
            task_id = prog.add_task(label, total=total or None)

            def advance(n: int) -> None:
                prog.update(task_id, advance=n)

            yield advance

    def summary(self, panel: str) -> None:
        self._console.print(Panel(panel, expand=False))


class FakeReporter:
    def __init__(self) -> None:
        self.steps: list[str] = []
        self.summaries: list[str] = []
        self.progress_calls: list[tuple[str, int]] = []
        self.advances: list[int] = []

    def step(self, msg: str) -> None:
        self.steps.append(msg)

    @contextmanager
    def progress(self, label: str, total: int) -> Iterator[Callable[[int], None]]:
        self.progress_calls.append((label, total))

        def advance(n: int) -> None:
            self.advances.append(n)

        yield advance

    def summary(self, panel: str) -> None:
        self.summaries.append(panel)
```

- [ ] **Step 5: Run, verify pass** — `uv run pytest tests/usb/test_report.py -q` → PASS.

- [ ] **Step 6: Gate + commit**

```bash
cd engine && uv run mypy --strict src && uv run ruff check src tests
git add engine/pyproject.toml engine/uv.lock engine/src/devboost/usb/report.py engine/tests/usb/test_report.py
git commit -m "feat(usb): add the Reporter seam (RichReporter + FakeReporter)"
```

---

### Task 4: Download progress (constructor-injected reporter)

**Files:**
- Modify: `engine/src/devboost/usb/download.py`
- Test: `engine/tests/usb/test_download.py` (add cases; existing ones stay green)

**Interfaces:**
- Consumes: `Reporter` from `devboost.usb.report`.
- Produces: `UrllibDownloader(cache: Cache, reporter: Reporter | None = None)` — `fetch(...)` Protocol unchanged; when a reporter is present and the response advertises `Content-Length`, drives `reporter.progress(...)` with per-chunk byte counts. `FakeDownloader` and the `Downloader` Protocol are untouched.

- [ ] **Step 1: Write the failing test** in `engine/tests/usb/test_download.py` (append). It monkeypatches `urllib.request.urlopen` with a fake response — no real network:

```python
def test_urllib_downloader_drives_progress_with_byte_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import io

    from devboost.usb.cache import Cache
    from devboost.usb.download import UrllibDownloader
    from devboost.usb.report import FakeReporter

    data = b"x" * 2500  # > one 1 MiB chunk is not needed; assert total + chunking
    sha = _sha(data)

    class _Resp(io.BytesIO):
        headers = {"Content-Length": str(len(data))}

        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *a: object) -> None:
            self.close()

    monkeypatch.setattr(
        "devboost.usb.download.urllib.request.urlopen", lambda url: _Resp(data)
    )
    reporter = FakeReporter()
    dl = UrllibDownloader(Cache(tmp_path), reporter)
    out = dl.fetch("https://x/f.iso", "f.iso", sha)
    assert out.read_bytes() == data
    assert reporter.progress_calls == [("f.iso", len(data))]
    assert sum(reporter.advances) == len(data)
```

- [ ] **Step 2: Run, verify fail** — `uv run pytest tests/usb/test_download.py -q -k progress` → FAIL (`UrllibDownloader` takes 1 positional arg / no progress).

- [ ] **Step 3: Edit `engine/src/devboost/usb/download.py`** — change `UrllibDownloader` only:

```python
from devboost.usb.report import Reporter


class UrllibDownloader:
    def __init__(self, cache: Cache, reporter: Reporter | None = None) -> None:
        self.cache = cache
        self.reporter = reporter

    def fetch(self, url: str, name: str, sha256: str) -> Path:
        dest = self.cache.path_for(name, sha256)
        if self.cache.has(name, sha256):
            return dest
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            with urllib.request.urlopen(url) as resp, tmp.open("wb") as out:
                total = int(resp.headers.get("Content-Length", 0) or 0)
                if self.reporter is not None and total:
                    with self.reporter.progress(name, total) as advance:
                        for chunk in iter(lambda: resp.read(1 << 20), b""):
                            out.write(chunk)
                            advance(len(chunk))
                else:
                    shutil.copyfileobj(resp, out)
        except OSError as exc:
            raise DownloadError(url, str(exc)) from exc
        if not self.cache.verify(tmp, sha256):
            tmp.unlink(missing_ok=True)
            raise DownloadError(url, "checksum mismatch")
        tmp.replace(dest)
        return dest
```
(Leave `Downloader` Protocol and `FakeDownloader` exactly as they are.)

- [ ] **Step 4: Run, verify pass** — `uv run pytest tests/usb/test_download.py -q` → PASS (new + existing).

- [ ] **Step 5: Gate + commit**

```bash
cd engine && uv run mypy --strict src && uv run ruff check src tests
git add engine/src/devboost/usb/download.py engine/tests/usb/test_download.py
git commit -m "feat(usb): drive rich download progress from a constructor-injected reporter"
```

---

### Task 5: Read-only disk probe (`probe.py`)

**Files:**
- Create: `engine/src/devboost/usb/probe.py`
- Test: `engine/tests/usb/test_probe.py`

**Interfaces:**
- Consumes: `Ctx`, `read_marker`/`Marker` from `devboost.usb.marker`, `log` from `devboost.core`.
- Produces:
  - `@dataclass(frozen=True) class DiskState: kind: Literal["blank", "ventoy-other", "devboost"]; marker: Marker | None = None`
  - `probe(ctx: Ctx, device: str) -> DiskState`

- [ ] **Step 1: Write the failing tests** in `engine/tests/usb/test_probe.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.usb.marker import Marker, write_marker
from devboost.usb.probe import probe

OS = OsInfo("fedora", "fedora", "x86_64")
_VTOY = 'NAME="sdb1" LABEL="VTOY"\nNAME="sdb2" LABEL="boot"\n'
_NO_VTOY = 'NAME="sdb1" LABEL="data"\n'


def _ctx(lsblk: str, mount_code: int = 0) -> Ctx:
    return Ctx(os=OS, ex=FakeExecutor(
        scripts={"lsblk": Result(0, stdout=lsblk), "mount": Result(mount_code)}
    ))


def test_probe_devboost_when_marker_present(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    mnt = tmp_path / "mnt"
    write_marker(mnt, Marker(version="0.1.0", os_id="fedora-44", arch="x86_64",
                             built_at="2026-06-26T00:00:00+00:00"))
    monkeypatch.setattr("devboost.usb.probe.mkdtemp", lambda **k: str(mnt))
    state = probe(_ctx(_VTOY), "/dev/sdb")
    assert state.kind == "devboost"
    assert state.marker is not None and state.marker.os_id == "fedora-44"


def test_probe_ventoy_other_when_vtoy_without_marker(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    mnt = tmp_path / "mnt"
    mnt.mkdir()
    monkeypatch.setattr("devboost.usb.probe.mkdtemp", lambda **k: str(mnt))
    state = probe(_ctx(_VTOY), "/dev/sdb")
    assert state.kind == "ventoy-other" and state.marker is None


def test_probe_blank_when_no_vtoy_partition() -> None:
    ctx = _ctx(_NO_VTOY)
    state = probe(ctx, "/dev/sdb")
    assert state.kind == "blank"
    # never mounts when there is no VTOY partition
    assert not any("mount" in " ".join(c) for c in ctx.ex.calls)  # type: ignore[attr-defined]


def test_probe_blank_when_mount_fails(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("devboost.usb.probe.mkdtemp", lambda **k: str(tmp_path / "mnt"))
    (tmp_path / "mnt").mkdir()
    state = probe(_ctx(_VTOY, mount_code=1), "/dev/sdb")
    assert state.kind == "blank"


def test_probe_always_unmounts(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    mnt = tmp_path / "mnt"
    mnt.mkdir()
    monkeypatch.setattr("devboost.usb.probe.mkdtemp", lambda **k: str(mnt))
    ctx = _ctx(_VTOY)
    probe(ctx, "/dev/sdb")
    assert any("umount" in " ".join(c) for c in ctx.ex.calls)  # type: ignore[attr-defined]
```

- [ ] **Step 2: Run, verify fail** — `uv run pytest tests/usb/test_probe.py -q` → FAIL (no module).

- [ ] **Step 3: Create `engine/src/devboost/usb/probe.py`**

```python
"""Read-only disk-state detection: is this stick blank, a foreign Ventoy, or dev-boost?"""

from __future__ import annotations

import re
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from tempfile import mkdtemp
from typing import Literal

from devboost.core import log
from devboost.model import Ctx
from devboost.usb.marker import Marker, read_marker

_PAIR = re.compile(r'(\w+)="([^"]*)"')


@dataclass(frozen=True)
class DiskState:
    kind: Literal["blank", "ventoy-other", "devboost"]
    marker: Marker | None = None


def _vtoy_partition(ctx: Ctx, device: str) -> str | None:
    """Return the /dev path of the child partition labelled VTOY, or None."""
    out = ctx.ex.run(["lsblk", "-P", "-o", "NAME,LABEL", device]).stdout
    for line in out.splitlines():
        fields = dict(_PAIR.findall(line))
        if fields.get("LABEL") == "VTOY":
            name = fields.get("NAME", "")
            if not name:
                return None
            return name if name.startswith("/dev/") else f"/dev/{name}"
    return None


def probe(ctx: Ctx, device: str) -> DiskState:
    """Read-only: detect a VTOY partition, ro-mount it, read the dev-boost marker.

    Never blocks: any failure degrades to DiskState("blank") with a warning.
    """
    part = _vtoy_partition(ctx, device)
    if part is None:
        return DiskState("blank")
    mnt = Path(mkdtemp(prefix="devboost-probe-"))
    try:
        if ctx.ex.run(["mount", "-o", "ro", part, str(mnt)], sudo=True).code != 0:
            log.warn(f"probe: could not mount {part} read-only; treating {device} as blank")
            return DiskState("blank")
        marker = read_marker(mnt)
        if marker is not None:
            return DiskState("devboost", marker)
        return DiskState("ventoy-other")
    finally:
        ctx.ex.run(["umount", str(mnt)], sudo=True)
        with suppress(OSError):
            mnt.rmdir()
```

- [ ] **Step 4: Run, verify pass** — `uv run pytest tests/usb/test_probe.py -q` → PASS.

- [ ] **Step 5: Gate + commit**

```bash
cd engine && uv run mypy --strict src && uv run ruff check src tests
git add engine/src/devboost/usb/probe.py engine/tests/usb/test_probe.py
git commit -m "feat(usb): add read-only disk-state probe (blank/ventoy-other/devboost)"
```

---

### Task 6: Config mode + stages (marker write, reporter, `update_stage`)

**Files:**
- Modify: `engine/src/devboost/usb/config.py` (add `mode`, `refresh_iso`)
- Modify: `engine/src/devboost/usb/stages.py` (extract `_stage_payload`; add `reporter` to `boot_artifacts`; add `update_stage`; write marker)
- Modify: `engine/tests/usb/test_stages.py` (existing `boot_artifacts` test needs a `FakeReporter`; add `update_stage` tests)
- Modify: `engine/tests/usb/test_config.py` (assert new defaults)

**Interfaces:**
- Consumes: `Reporter`/`FakeReporter` from `devboost.usb.report`; `Marker`/`write_marker` from `devboost.usb.marker`; `__version__` from `devboost`.
- Produces:
  - `UsbBuildConfig` gains `mode: Literal["build", "update"] = "build"` and `refresh_iso: bool = False`.
  - `boot_artifacts(ctx, cfg, dl, *, vtoy_mount: Path, reporter: Reporter) -> None`
  - `update_stage(ctx, cfg, dl, *, vtoy_mount: Path, reporter: Reporter) -> None`
  - `extra_isos`, `installers`, `mirror` signatures UNCHANGED (the builder emits their step lines).

- [ ] **Step 1: Add config fields.** In `engine/src/devboost/usb/config.py` add `from typing import Literal` and inside `UsbBuildConfig`:

```python
    mode: Literal["build", "update"] = "build"
    refresh_iso: bool = False
```

- [ ] **Step 2: Extend `engine/tests/usb/test_config.py`** `test_config_defaults` with:

```python
    assert cfg.mode == "build"
    assert cfg.refresh_iso is False
```

- [ ] **Step 3: Write failing `update_stage` tests** — add to `engine/tests/usb/test_stages.py`. Reuse the `_LSBLK`, `OS`, and the `fake_resource_path` monkeypatch pattern already in the file. First, update the EXISTING `test_boot_artifacts_installs_ventoy_and_stages_files` call to pass a reporter:

```python
    from devboost.usb.report import FakeReporter
    boot_artifacts(ctx, cfg, dl, vtoy_mount=vtoy, reporter=FakeReporter())
```
And update the no-wipe test similarly:
```python
    with pytest.raises(DeviceError, match="not confirmed"):
        boot_artifacts(ctx, cfg, dl, vtoy_mount=tmp_path / "VTOY", reporter=FakeReporter())
```
Then add new tests:

```python
def test_update_stage_restages_without_wipe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from devboost.usb.report import FakeReporter
    from devboost.usb.stages import update_stage

    iso = IsoSpec(id="fedora-44", url="https://x/f.iso", sha256="a" * 64, edition="Everything")
    cache = Cache(tmp_path / "cache")
    dl = FakeDownloader(cache, blobs={})
    cfg = UsbBuildConfig(
        device="/dev/sdb", arch="x86_64", iso=iso, profiles=("cli",),
        cache_dir=cache.cache_dir, mode="update", assume_yes=True,
    )
    vtoy = tmp_path / "VTOY"
    ctx = Ctx(os=OS, ex=FakeExecutor(scripts={"lsblk": Result(0, stdout=_LSBLK)}))

    ks_template = "ExecStart=/bin/sh -c '/opt/dev-boost/devboost install full'"
    fake_ks = tmp_path / "ks.cfg"; fake_ks.write_text(ks_template, encoding="utf-8")
    fake_json = tmp_path / "ventoy.json"; fake_json.write_bytes(b"{}")
    fake_tar = tmp_path / "devboost-x86_64.tar.gz"; fake_tar.write_bytes(b"tar")

    def fake_resource_path(*parts: str) -> Path:
        return {("ventoy", "ks.cfg"): fake_ks, ("ventoy", "ventoy.json"): fake_json}.get(
            parts, fake_tar
        )

    monkeypatch.setattr("devboost.usb.stages.resource_path", fake_resource_path)
    update_stage(ctx, cfg, dl, vtoy_mount=vtoy, reporter=FakeReporter())

    calls = ctx.ex.calls  # type: ignore[attr-defined]
    flat = [" ".join(c) for c in calls]
    assert any("ventoy -u /dev/sdb" in c for c in flat)
    assert not any("ventoy -i" in c for c in flat)          # never wipes
    assert (vtoy / "Bootstrap" / "devboost.tar.gz").exists()
    assert (vtoy / "Bootstrap" / ".devboost-usb.json").exists()
    assert not (vtoy / "ISO" / "fedora-44.iso").exists()    # payload-only by default
    assert dl.fetched == []                                  # no ISO download


def test_update_stage_refreshes_iso_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib

    from devboost.usb.report import FakeReporter
    from devboost.usb.stages import update_stage

    iso_bytes = b"new-iso"
    sha = hashlib.sha256(iso_bytes).hexdigest()
    iso = IsoSpec(id="fedora-44", url="https://x/f.iso", sha256=sha, edition="Everything")
    cache = Cache(tmp_path / "cache")
    dl = FakeDownloader(cache, blobs={"https://x/f.iso": iso_bytes})
    cfg = UsbBuildConfig(
        device="/dev/sdb", arch="x86_64", iso=iso, profiles=("cli",),
        cache_dir=cache.cache_dir, mode="update", refresh_iso=True, assume_yes=True,
    )
    vtoy = tmp_path / "VTOY"
    ctx = Ctx(os=OS, ex=FakeExecutor(scripts={"lsblk": Result(0, stdout=_LSBLK)}))
    fake_ks = tmp_path / "ks.cfg"; fake_ks.write_text("install full", encoding="utf-8")
    fake_json = tmp_path / "ventoy.json"; fake_json.write_bytes(b"{}")
    fake_tar = tmp_path / "devboost-x86_64.tar.gz"; fake_tar.write_bytes(b"tar")
    monkeypatch.setattr(
        "devboost.usb.stages.resource_path",
        lambda *p: {("ventoy", "ks.cfg"): fake_ks, ("ventoy", "ventoy.json"): fake_json}.get(p, fake_tar),
    )
    update_stage(ctx, cfg, dl, vtoy_mount=vtoy, reporter=FakeReporter())
    assert (vtoy / "ISO" / "fedora-44.iso").read_bytes() == iso_bytes
    assert dl.fetched == ["https://x/f.iso"]
```

- [ ] **Step 4: Run, verify fail** — `uv run pytest tests/usb/test_stages.py tests/usb/test_config.py -q` → FAIL (`update_stage` missing; `boot_artifacts` got unexpected `reporter`).

- [ ] **Step 5: Edit `engine/src/devboost/usb/stages.py`.** Add imports and replace `boot_artifacts`; add `_stage_payload` + `update_stage`. Leave `render_kscfg`, `extra_isos`, `installers`, `mirror` unchanged.

```python
from datetime import datetime, timezone

from devboost import __version__
from devboost.usb.marker import Marker, write_marker
from devboost.usb.report import Reporter


def _stage_payload(cfg: UsbBuildConfig, *, vtoy_mount: Path, reporter: Reporter) -> None:
    """Lay out ventoy.json + ks.cfg + injection archive + secrets + marker (no wipe, no ISO)."""
    boot = vtoy_mount / "Bootstrap"
    for d in ("ISO", "Bootstrap", "Installers", "ventoy"):
        (vtoy_mount / d).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(resource_path("ventoy", "ventoy.json"), vtoy_mount / "ventoy" / "ventoy.json")
    kscfg = resource_path("ventoy", "ks.cfg").read_text(encoding="utf-8")
    (boot / "ks.cfg").write_text(
        render_kscfg(kscfg, cfg.profiles, offline=cfg.offline_mirror), encoding="utf-8"
    )
    tarball = resource_path("dist", f"devboost-{cfg.arch}.tar.gz")
    if not tarball.exists():
        raise VentoyError(f"injection archive missing: {tarball} (run scripts/build-bundle.sh)")
    shutil.copyfile(tarball, boot / "devboost.tar.gz")
    if cfg.secrets_path is not None:
        shutil.copyfile(cfg.secrets_path, boot / "secrets.age")
    write_marker(vtoy_mount, Marker(
        version=__version__, os_id=cfg.iso.id, arch=cfg.arch,
        built_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    ))
    reporter.step(f"Staged dev-boost payload ({cfg.iso.id}, {cfg.arch})")


def boot_artifacts(
    ctx: Ctx, cfg: UsbBuildConfig, dl: Downloader, *, vtoy_mount: Path, reporter: Reporter
) -> None:
    if not cfg.assume_yes:
        raise DeviceError(f"refusing to wipe {cfg.device}: not confirmed")
    validate(ctx, cfg.device)
    if ctx.ex.run(["ventoy", "-i", cfg.device], sudo=True).code != 0:
        raise VentoyError(f"ventoy install failed on {cfg.device}")
    reporter.step(f"Ventoy installed on {cfg.device}")
    _stage_payload(cfg, vtoy_mount=vtoy_mount, reporter=reporter)
    iso_path = dl.fetch(cfg.iso.url, f"{cfg.iso.id}.iso", cfg.iso.sha256)
    shutil.copyfile(iso_path, vtoy_mount / "ISO" / f"{cfg.iso.id}.iso")
    reporter.step(f"Fedora ISO staged ({cfg.iso.id})")


def update_stage(
    ctx: Ctx, cfg: UsbBuildConfig, dl: Downloader, *, vtoy_mount: Path, reporter: Reporter
) -> None:
    """Non-destructive refresh: ventoy -u + re-stage payload; ISO only when refresh_iso."""
    validate(ctx, cfg.device)
    if ctx.ex.run(["ventoy", "-u", cfg.device], sudo=True).code != 0:
        raise VentoyError(f"ventoy update failed on {cfg.device}")
    reporter.step(f"Ventoy updated on {cfg.device}")
    _stage_payload(cfg, vtoy_mount=vtoy_mount, reporter=reporter)
    if cfg.refresh_iso:
        iso_path = dl.fetch(cfg.iso.url, f"{cfg.iso.id}.iso", cfg.iso.sha256)
        shutil.copyfile(iso_path, vtoy_mount / "ISO" / f"{cfg.iso.id}.iso")
        reporter.step(f"Fedora ISO refreshed ({cfg.iso.id})")
```

- [ ] **Step 6: Run, verify pass** — `uv run pytest tests/usb/test_stages.py tests/usb/test_config.py -q` → PASS.

- [ ] **Step 7: Gate + commit**

```bash
cd engine && uv run mypy --strict src && uv run ruff check src tests
git add engine/src/devboost/usb/config.py engine/src/devboost/usb/stages.py engine/tests/usb/test_stages.py engine/tests/usb/test_config.py
git commit -m "feat(usb): config mode + update_stage + marker write + stage step reporting"
```

---

### Task 7: Builder mode branch + reporter threading

**Files:**
- Modify: `engine/src/devboost/usb/builder.py`
- Modify: `engine/tests/usb/test_builder.py` (existing tests need `reporter=`; add a mode-branch test)

**Interfaces:**
- Consumes: `stages.boot_artifacts`/`update_stage` (now take `reporter`), `Reporter`/`FakeReporter`.
- Produces: `build(ctx, cfg, dl, *, vtoy_mount: Path, reporter: Reporter) -> None` — calls `update_stage` when `cfg.mode == "update"`, else `boot_artifacts`; then extras/installers/mirror with a `reporter.step` after each that runs.

- [ ] **Step 1: Update existing `test_builder.py` tests + add the mode-branch test.** Every existing `build(...)` call needs `reporter=FakeReporter()`, and the monkeypatched stage lambdas already accept `*a, **k` so they tolerate the new kwarg. Add at the top of each test's imports `from devboost.usb.report import FakeReporter`, and append `reporter=FakeReporter()` to each `build(...)` call. Then add:

```python
def test_build_update_mode_calls_update_stage_not_boot(  # type: ignore[no-untyped-def]
    tmp_path: Path, monkeypatch
) -> None:
    import devboost.usb.stages as stages
    from devboost.usb.report import FakeReporter

    order: list[str] = []
    monkeypatch.setattr(stages, "boot_artifacts", lambda *a, **k: order.append("boot"))
    monkeypatch.setattr(stages, "update_stage", lambda *a, **k: order.append("update"))
    monkeypatch.setattr(stages, "extra_isos", lambda *a, **k: None)
    monkeypatch.setattr(stages, "installers", lambda *a, **k: None)

    iso = IsoSpec("fedora-44", "u", hashlib.sha256(b"i").hexdigest(), "E")
    cfg = UsbBuildConfig(
        device="/dev/sdb", arch="x86_64", iso=iso, cache_dir=tmp_path, mode="update"
    )
    build(Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor()),
          cfg, FakeDownloader(Cache(tmp_path), {}), vtoy_mount=tmp_path / "VTOY",
          reporter=FakeReporter())
    assert order == ["update"] and "boot" not in order
```

- [ ] **Step 2: Run, verify fail** — `uv run pytest tests/usb/test_builder.py -q` → FAIL (`build()` missing `reporter`; `update_stage` not branched).

- [ ] **Step 3: Replace `engine/src/devboost/usb/builder.py`**

```python
"""Orchestrate the USB build/update stages from a UsbBuildConfig."""

from __future__ import annotations

from pathlib import Path

from devboost.model import Ctx
from devboost.usb import stages
from devboost.usb.config import UsbBuildConfig
from devboost.usb.download import Downloader
from devboost.usb.report import Reporter


def build(
    ctx: Ctx, cfg: UsbBuildConfig, dl: Downloader, *, vtoy_mount: Path, reporter: Reporter
) -> None:
    if cfg.mode == "update":
        stages.update_stage(ctx, cfg, dl, vtoy_mount=vtoy_mount, reporter=reporter)
    else:
        stages.boot_artifacts(ctx, cfg, dl, vtoy_mount=vtoy_mount, reporter=reporter)

    stages.extra_isos(cfg, vtoy_mount=vtoy_mount)
    if cfg.extra_isos:
        reporter.step(f"Staged {len(cfg.extra_isos)} extra ISO(s)")
    stages.installers(cfg, vtoy_mount=vtoy_mount)
    if cfg.installers:
        reporter.step(f"Staged {len(cfg.installers)} installer(s)")
    if cfg.offline_mirror:
        stages.mirror(ctx, cfg, vtoy_mount=vtoy_mount)
        reporter.step("Offline mirror built")
```

- [ ] **Step 4: Run, verify pass** — `uv run pytest tests/usb/test_builder.py -q` → PASS.

- [ ] **Step 5: Gate + commit**

```bash
cd engine && uv run mypy --strict src && uv run ruff check src tests
git add engine/src/devboost/usb/builder.py engine/tests/usb/test_builder.py
git commit -m "feat(usb): branch builder on cfg.mode and thread the reporter"
```

---

### Task 8: Dry-run plan renderer (`preview.py`)

**Files:**
- Create: `engine/src/devboost/usb/preview.py`
- Test: `engine/tests/usb/test_preview.py`

**Interfaces:**
- Consumes: `UsbBuildConfig`, `DiskState` from `devboost.usb.probe`.
- Produces: `render_plan(cfg: UsbBuildConfig, state: DiskState, *, download_note: str = "") -> str`

- [ ] **Step 1: Write the failing tests** in `engine/tests/usb/test_preview.py`:

```python
from __future__ import annotations

from pathlib import Path

from devboost.usb.config import IsoSpec, UsbBuildConfig
from devboost.usb.marker import Marker
from devboost.usb.preview import render_plan
from devboost.usb.probe import DiskState

_ISO = IsoSpec(id="fedora-44", url="https://x/f.iso", sha256="a" * 64, edition="Everything")


def _cfg(**kw: object) -> UsbBuildConfig:
    base: dict[str, object] = dict(
        device="/dev/sdb", arch="x86_64", iso=_ISO, cache_dir=Path("/tmp/c")
    )
    base.update(kw)
    return UsbBuildConfig(**base)  # type: ignore[arg-type]


def test_render_plan_blank_build() -> None:
    out = render_plan(_cfg(profiles=("full",)), DiskState("blank"), download_note="≈2.0 GB")
    assert "/dev/sdb" in out
    assert "blank" in out
    assert "build" in out
    assert "fedora-44 (x86_64)" in out
    assert "full" in out
    assert "≈2.0 GB" in out


def test_render_plan_update_shows_detected_marker_and_iso_policy() -> None:
    marker = Marker(version="0.1.0", os_id="fedora-44", arch="x86_64",
                    built_at="2026-06-26T00:00:00+00:00")
    out = render_plan(_cfg(mode="update"), DiskState("devboost", marker))
    assert "dev-boost USB" in out
    assert "update" in out
    assert "payload only" in out


def test_render_plan_offline_note() -> None:
    out = render_plan(_cfg(offline_mirror=True), DiskState("ventoy-other"))
    assert "Offline mirror: yes" in out
    assert "non-dev-boost Ventoy" in out
```

- [ ] **Step 2: Run, verify fail** — `uv run pytest tests/usb/test_preview.py -q` → FAIL (no module).

- [ ] **Step 3: Create `engine/src/devboost/usb/preview.py`**

```python
"""Render the resolved build/update plan for --dry-run and the wizard recap."""

from __future__ import annotations

from devboost.usb.config import UsbBuildConfig
from devboost.usb.probe import DiskState


def _describe(state: DiskState) -> str:
    if state.kind == "devboost" and state.marker is not None:
        return f"dev-boost USB (built {state.marker.built_at}, {state.marker.os_id})"
    if state.kind == "ventoy-other":
        return "non-dev-boost Ventoy stick"
    return "blank / no dev-boost marker"


def render_plan(cfg: UsbBuildConfig, state: DiskState, *, download_note: str = "") -> str:
    lines = [
        f"Target device : {cfg.device}",
        f"Detected state: {_describe(state)}",
        f"Mode          : {cfg.mode}",
        f"OS            : {cfg.iso.id} ({cfg.arch})",
        f"Profiles      : {', '.join(cfg.profiles)}",
    ]
    if cfg.extra_isos:
        lines.append(f"Extra ISOs    : {len(cfg.extra_isos)}")
    if cfg.installers:
        lines.append(f"Installers    : {len(cfg.installers)}")
    lines.append(f"Offline mirror: {'yes' if cfg.offline_mirror else 'no'}")
    if cfg.mode == "update":
        lines.append(f"ISO refresh   : {'yes' if cfg.refresh_iso else 'no (payload only)'}")
    if download_note:
        lines.append(f"Est. download : {download_note}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run, verify pass** — `uv run pytest tests/usb/test_preview.py -q` → PASS.

- [ ] **Step 5: Gate + commit**

```bash
cd engine && uv run mypy --strict src && uv run ruff check src tests
git add engine/src/devboost/usb/preview.py engine/tests/usb/test_preview.py
git commit -m "feat(usb): add the --dry-run plan renderer"
```

---

### Task 9: CLI — `--dry-run`, `--refresh-iso`, probe/mode, reporter, summary

**Files:**
- Modify: `engine/src/devboost/cli/usb.py`
- Test: `engine/tests/usb/test_cli_usb.py` (add a dry-run test; existing two stay green)

**Interfaces:**
- Consumes: `probe`/`DiskState` from `devboost.usb.probe`, `render_plan` from `devboost.usb.preview`, `RichReporter` from `devboost.usb.report`, `Cache`, `UrllibDownloader`, `build`.
- Produces: the `usb` Typer command gains `--dry-run` and `--refresh-iso`; probes the device to set `cfg.mode`; constructs `RichReporter`; prints a summary panel on success.

- [ ] **Step 1: Write the failing test** in `engine/tests/usb/test_cli_usb.py`. It exercises `--dry-run` with `--no-wizard` so no real build runs, monkeypatching `probe` to avoid touching hardware:

```python
def test_usb_dry_run_previews_without_building(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import devboost.cli.usb as cli_usb
    from devboost.usb.probe import DiskState

    monkeypatch.setattr(cli_usb, "probe", lambda ctx, device: DiskState("blank"))

    called = {"build": False}
    monkeypatch.setattr(cli_usb, "build", lambda *a, **k: called.__setitem__("build", True))
    # Avoid a real HEAD request for the size note.
    monkeypatch.setattr(cli_usb, "_iso_note", lambda cfg: "≈2.0 GB")

    result = runner.invoke(
        app, ["usb", "--device", "/dev/sdb", "--no-wizard", "--dry-run", "--yes"]
    )
    assert result.exit_code == 0
    clean = _strip_ansi(result.stdout)
    assert "/dev/sdb" in clean and "build" in clean
    assert called["build"] is False
```

- [ ] **Step 2: Run, verify fail** — `uv run pytest tests/usb/test_cli_usb.py -q -k dry_run` → FAIL (no `--dry-run`, no `_iso_note`).

- [ ] **Step 3: Rewrite `engine/src/devboost/cli/usb.py`.** Keep the module docstring and the `device is None and no_wizard` early-exit. New version:

```python
"""The `devboost usb` command: flags or wizard -> build/update a bootable Ventoy USB.

NOTE (frozen binary): when running from a frozen devboost binary, the staged injection archive
(dist/devboost-<arch>.tar.gz) must be present alongside the binary. Build it first via
``scripts/build-bundle.sh``; the frozen ``usb`` command does not rebuild the tarball itself.
"""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path
from tempfile import gettempdir
from typing import Annotated

import questionary
import typer

from devboost.core import log, osinfo
from devboost.exec.executor import RealExecutor
from devboost.model import Ctx
from devboost.usb import wizard
from devboost.usb.builder import build
from devboost.usb.cache import Cache
from devboost.usb.catalog import CATALOG, default_iso, iso_for
from devboost.usb.config import UsbBuildConfig
from devboost.usb.download import UrllibDownloader
from devboost.usb.preview import render_plan
from devboost.usb.probe import DiskState, probe
from devboost.usb.report import RichReporter


def _iso_note(cfg: UsbBuildConfig) -> str:
    """Best-effort ISO download size for the dry-run preview (never raises)."""
    cache = Cache(cfg.cache_dir)
    if cache.has(f"{cfg.iso.id}.iso", cfg.iso.sha256):
        return "cached"
    try:
        req = urllib.request.Request(cfg.iso.url, method="HEAD")
        with urllib.request.urlopen(req) as resp:
            size = int(resp.headers.get("Content-Length", 0) or 0)
        return f"≈{size / 1e9:.1f} GB" if size else "unknown"
    except OSError:
        return "unknown"


def _summary_text(cfg: UsbBuildConfig) -> str:
    verb = "Updated" if cfg.mode == "update" else "Built"
    extras: list[str] = []
    if cfg.offline_mirror:
        extras.append("offline-mirror: yes")
    if cfg.extra_isos:
        extras.append(f"+{len(cfg.extra_isos)} extra ISO")
    tail = (" · " + " · ".join(extras)) if extras else ""
    head = (
        f"✅ {verb} {cfg.device} — {cfg.iso.id} ({cfg.arch}) · "
        f"profiles: {' '.join(cfg.profiles)}{tail}"
    )
    if cfg.mode == "update":
        body = "ISOs/secrets preserved. Reboot the target; the firstboot service re-runs your profiles."
    else:
        body = (
            "Boot it: insert the USB → firmware boot menu → pick the USB → Fedora installs "
            "(auto/zero-touch or manual) → on first boot dev-boost installs your profiles. "
            'Bad update later? Reboot → GRUB "Fedora snapshots".'
        )
    return head + "\n" + body


def usb(
    device: Annotated[
        str | None, typer.Option(help="Target removable disk, e.g. /dev/sdb")
    ] = None,
    arch: Annotated[str, typer.Option(help="x86_64 | aarch64")] = "",
    iso: Annotated[str, typer.Option(help=f"ISO id: {', '.join(CATALOG)}")] = "",
    profile: Annotated[list[str], typer.Option(help="Profiles for firstboot (repeatable)")] = [],
    secrets: Annotated[Path | None, typer.Option(help="Path to secrets.age")] = None,
    cache_dir: Annotated[Path | None, typer.Option(help="Download cache dir")] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation / accept wipe")] = False,
    no_wizard: Annotated[
        bool, typer.Option("--no-wizard", help="Fail instead of prompting")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Resolve + print the plan; touch nothing")
    ] = False,
    refresh_iso: Annotated[
        bool, typer.Option("--refresh-iso", help="On update, also re-download the pinned ISO")
    ] = False,
) -> None:
    """Build (or non-destructively update) a dev-boost Ventoy USB."""
    if device is None and no_wizard:
        log.error("--device is required with --no-wizard")
        raise typer.Exit(code=1)

    vtoy = Path(
        os.environ.get("VTOY_MOUNT", f"/run/media/{os.environ.get('USER', 'root')}/VTOY")
    )

    state: DiskState | None = None
    if device is None:
        ctx = Ctx(os=osinfo.detect(), ex=RealExecutor())
        cfg = wizard.run(ctx)
    else:
        os_info = osinfo.detect()
        ctx = Ctx(os=os_info, ex=RealExecutor())
        resolved_arch = arch or os_info.arch
        state = probe(ctx, device)

        if state.kind == "devboost" and not yes:
            mode, assume_yes = "update", True  # update is non-destructive
        else:
            mode, assume_yes = "build", yes
            if not assume_yes and not dry_run:
                ok = questionary.confirm(
                    f"WIPE {device}? All data on it is destroyed.", default=False
                ).ask()
                if not (ok or False):
                    log.error("aborted")
                    raise typer.Exit(code=1)
                assume_yes = True

        cfg = UsbBuildConfig(
            device=device,
            arch=resolved_arch,
            iso=iso_for(iso, resolved_arch) if iso else iso_for(default_iso().id, resolved_arch),
            profiles=tuple(profile) or ("full",),
            secrets_path=secrets,
            cache_dir=cache_dir or Path(gettempdir()) / "devboost-usb",
            mode=mode,  # type: ignore[arg-type]
            refresh_iso=refresh_iso,
            assume_yes=assume_yes,
        )

    if dry_run:
        if state is None:
            state = probe(ctx, cfg.device)
        typer.echo(render_plan(cfg, state, download_note=_iso_note(cfg)))
        raise typer.Exit()

    reporter = RichReporter()
    build(ctx, cfg, UrllibDownloader(Cache(cfg.cache_dir), reporter), vtoy_mount=vtoy,
          reporter=reporter)
    reporter.summary(_summary_text(cfg))
```

Note the `mode` literal: mypy may flag the `str` → `Literal` assignment, hence the `# type: ignore[arg-type]`. If mypy is satisfied without it (it narrows the branches), remove the ignore — ruff will flag an unused ignore.

- [ ] **Step 4: Run, verify pass** — `uv run pytest tests/usb/test_cli_usb.py -q` → PASS (all three).

- [ ] **Step 5: Gate + commit**

```bash
cd engine && uv run mypy --strict src && uv run ruff check src tests
git add engine/src/devboost/cli/usb.py engine/tests/usb/test_cli_usb.py
git commit -m "feat(usb): --dry-run preview, update-detect, reporter, and summary panel in the CLI"
```

---

### Task 10: Wizard — friendly OS catalog + probe branch + update prompt

**Files:**
- Modify: `engine/src/devboost/usb/wizard.py`

**Interfaces:**
- Consumes: `supported`/`default_os`/`iso_for` from `devboost.usb.catalog`; `probe`/`DiskState` from `devboost.usb.probe`.
- Produces: `run(ctx: Ctx) -> UsbBuildConfig` with `mode` set from the probe branch and `refresh_iso` asked only in update mode. (Per spec §10 the wizard is a thin orchestrator and is not unit-tested; it must stay `mypy --strict` + ruff clean and import-valid.)

- [ ] **Step 1: Replace `engine/src/devboost/usb/wizard.py`**

```python
"""Interactive wizard: questionary prompts (each defaulted) -> UsbBuildConfig.

After the device pick we probe (read-only) and branch: an existing dev-boost stick
offers a non-destructive update; a foreign Ventoy or blank stick confirms a wipe.
"""

from __future__ import annotations

import platform
from pathlib import Path
from tempfile import gettempdir

import questionary

from devboost.core.errors import DeviceError
from devboost.model import Ctx
from devboost.usb.catalog import default_os, iso_for, supported
from devboost.usb.config import UsbBuildConfig
from devboost.usb.devices import list_removable
from devboost.usb.probe import probe

_PROFILES = ("full", "terminal", "devtools", "base", "cli", "shell", "gnome")


def _confirm_wipe(device: str, *, label: str) -> None:
    ok = questionary.confirm(f"{label} {device}? All data on it is destroyed.", default=False).ask()
    if not (ok or False):
        raise DeviceError("aborted: device wipe not confirmed")


def run(ctx: Ctx) -> UsbBuildConfig:  # noqa: C901 (thin linear wizard)
    devices = list_removable(ctx)
    if not devices:
        raise DeviceError("no removable disk found — plug in a USB and retry")
    device = questionary.select(
        "Target USB device:",
        choices=[questionary.Choice(d.label(), value=d.path) for d in devices],
    ).ask()
    if device is None:
        raise DeviceError("aborted")

    state = probe(ctx, device)
    mode = "build"
    refresh_iso = False
    if state.kind == "devboost":
        built = state.marker.built_at if state.marker else "unknown"
        os_id = state.marker.os_id if state.marker else "?"
        action = questionary.select(
            f"This is a dev-boost USB ({os_id}, built {built}). What now?",
            choices=[
                questionary.Choice("Update (keep ISOs/secrets, no wipe)", value="update"),
                questionary.Choice("Rebuild (wipe everything)", value="build"),
            ],
            default="Update (keep ISOs/secrets, no wipe)",
        ).ask() or "update"
        mode = action
        if mode == "update":
            refresh_iso = questionary.confirm(
                "Also re-download the pinned Fedora ISO?", default=False
            ).ask() or False
        else:
            _confirm_wipe(device, label="REBUILD — WIPE")
    elif state.kind == "ventoy-other":
        _confirm_wipe(device, label="This is a non-dev-boost Ventoy stick. WIPE")
    else:
        _confirm_wipe(device, label="WIPE")

    arch = questionary.select(
        "Architecture:", choices=["x86_64", "aarch64"], default=platform.machine()
    ).ask()
    if arch is None:
        raise DeviceError("aborted")

    os_id = questionary.select(
        "Operating system:",
        choices=[questionary.Choice(o.name, value=o.id) for o in supported()],
        default=default_os().name,
    ).ask()
    if os_id is None:
        raise DeviceError("aborted")

    profiles = questionary.checkbox(
        "Profiles to install on first boot:",
        choices=[questionary.Choice(p, checked=(p == "full")) for p in _PROFILES],
    ).ask() or ["full"]
    secrets = questionary.path("Path to secrets.age (blank to skip):", default="").ask()
    cache = questionary.path(
        "Cache dir for downloads:", default=str(Path(gettempdir()) / "devboost-usb")
    ).ask()
    if cache is None:
        raise DeviceError("aborted")

    offline_mirror: bool = questionary.confirm(
        "Pre-mirror dnf+flatpak packages for OFFLINE install?"
        " (large — tens of GB; mise/npm/github tools still need network)",
        default=False,
    ).ask() or False

    return UsbBuildConfig(
        device=device,
        arch=arch,
        iso=iso_for(os_id, arch),
        profiles=tuple(profiles),
        secrets_path=Path(secrets) if secrets else None,
        cache_dir=Path(cache),
        offline_mirror=offline_mirror,
        mode=mode,  # type: ignore[arg-type]
        refresh_iso=refresh_iso,
        assume_yes=True,
    )
```
(If mypy narrows `mode`/`action` to `str` and rejects the `Literal` assignment, keep the `# type: ignore[arg-type]`; if it accepts, drop it so ruff/mypy don't flag an unused ignore. The `# noqa: C901` is only needed if ruff's mccabe is enabled and complains — drop it otherwise.)

- [ ] **Step 2: Verify import + gate.** There is no wizard unit test; verify it imports and the suite + type/lint gates pass:

Run: `cd engine && uv run python -c "import devboost.usb.wizard" && uv run pytest -q && uv run mypy --strict src && uv run ruff check src tests`
Expected: import OK; full suite PASS; mypy + ruff clean.

- [ ] **Step 3: Commit**

```bash
git add engine/src/devboost/usb/wizard.py
git commit -m "feat(usb): wizard OS catalog select + probe branch (update/rebuild/wipe)"
```

---

### Task 11: Docs — update behavior, dry-run, and the experience flow

**Files:**
- Modify: `README.md` (the `devboost usb` command row + recovery line)
- Modify: `docs/ventoy.md` (build vs update, dry-run, experience)

**Interfaces:** none (docs only).

- [ ] **Step 1: Update the `devboost usb` row in `README.md`** (the Commands table, currently line ~100). Replace it with:

```markdown
| `devboost usb [--device …] [--iso …] [--dry-run] [--refresh-iso] [--yes]` | Build **or non-destructively update** a bootable Ventoy USB: interactive wizard (or flags) — lists removable disks, probes the target (blank / foreign-Ventoy / existing dev-boost → offers update), downloads + verifies + caches the Fedora ISO with a live progress bar, stages the binary/ks.cfg, and prints a final summary. `--dry-run` previews the whole plan and touches nothing. |
```

- [ ] **Step 2: Add an "Update vs rebuild" + "Dry-run" note to `docs/ventoy.md`** after the "Build the USB (once)" section:

```markdown
## Update vs rebuild

Re-running `devboost usb` on a stick that is **already a dev-boost USB** detects it (via the
`Bootstrap/.devboost-usb.json` marker, read through a read-only mount) and defaults to a
**non-destructive update**: it runs `ventoy -u`, re-stages the `devboost` binary, `ks.cfg`,
`ventoy.json`, and refreshes the marker — while **preserving** `ISO/`, `secrets.age`, and the data
partition. Pass `--refresh-iso` (or accept the wizard prompt) to also re-download the pinned Fedora
ISO. A blank disk or a foreign Ventoy stick still goes through the explicit wipe confirmation.

## Preview first (`--dry-run`)

`devboost usb --device /dev/sdX --dry-run` resolves everything — catalog OS, detected disk state,
build-vs-update mode, profiles, optional stages, and the estimated ISO download — and prints the plan
**without running `ventoy`, downloading, or writing anything**. Use it to rehearse safely.
```

- [ ] **Step 3: Update the recovery line in `README.md`** (currently "Build the stick once: `sudo devboost usb` (interactive)") to mention preview:

```markdown
0. Build the stick once: `sudo devboost usb` (interactive; add `--dry-run` to preview) — see [docs/ventoy.md](docs/ventoy.md).
```

- [ ] **Step 4: Commit**

```bash
git add README.md docs/ventoy.md
git commit -m "docs(usb): document update-detect, --dry-run, and the experience flow"
```

---

## Self-Review

**Spec coverage** (against `docs/superpowers/specs/2026-06-26-usb-experience-layer-design.md`):
- §2 #1 / §5 catalog → Task 1. ✅
- §2 #2/#3 / §6 update-detect (marker, probe, update_stage) → Tasks 2, 5, 6. ✅
- §2 #4 / §7 progress (Reporter, download bar, stage steps) → Tasks 3, 4, 6, 7. ✅
- §2 #5 / §8 dry-run preview → Tasks 8, 9. ✅
- §2 #6 / §9 summary + usage → Task 9 (`_summary_text`/`reporter.summary`). ✅
- §2 #7 real Fedora sha256 → Task 1 Step 1. ✅
- §10 error handling (probe degrades to blank; unpinned OS/arch raises) → Task 5 + Task 1 `iso_for`. ✅
- §10 tests (catalog/marker/probe/report/preview/update_stage/builder/download) → one test file per unit across Tasks 1-8. ✅
- §11 constitution (rich/questionary deps, executor-mediated mount/ventoy, in-repo pins) → Task 3 declares `rich`; probe/stages use `ctx.ex.run(..., sudo=True)`. ✅

**Placeholder scan:** No "TBD"/"handle errors"/"similar to" — every code step has complete code. The single intentional fill-in is the real Fedora sha256 (Task 1 Step 1), which is *data* that must be fetched live, with an explicit fallback + shape-only test.

**Type consistency:** `Reporter` (step/progress/summary) is identical across `report.py`, `download.py`, `stages.py`, `builder.py`. `build(..., *, vtoy_mount, reporter)` matches its call in `cli/usb.py`. `boot_artifacts`/`update_stage` both `(ctx, cfg, dl, *, vtoy_mount, reporter)`. `iso_for(os_id, arch)`, `probe(ctx, device) -> DiskState`, `render_plan(cfg, state, *, download_note="")`, `read_marker(directory)`/`write_marker(vtoy_mount, marker)`, `UsbBuildConfig.mode`/`.refresh_iso` are used consistently. `DiskState.kind` literals (`blank`/`ventoy-other`/`devboost`) match between `probe.py`, `preview.py`, and the wizard/cli branches.

**Cross-task breakage handled:** existing `test_stages.py`/`test_builder.py` calls are updated in-task to pass `reporter=`; `isos.py`/`test_isos.py` are deleted and importers migrated in Task 1; `rich` is declared before first import in Task 3.
