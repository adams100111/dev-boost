# `devboost usb` Experience Layer — Design

**Status:** Approved for implementation (grilled 2026-06-26; all §12 questions resolved)
**Date:** 2026-06-26
**Author:** brainstorming session
**Constitution:** aligns with v3.0.1 (typed Python + Typer; bash only as the non-logic bootstrap
stub; pytest + `mypy --strict` + ruff gates)
**Builds on:** the `devboost usb` builder (`docs/superpowers/specs/2026-06-26-usb-builder-wizard-design.md`,
implemented under `engine/src/devboost/usb/`).

---

## 1. Summary

The `devboost usb` builder works, but the *experience* is thin: silent downloads, a wipe-or-nothing
flow, a one-line result, and no safe rehearsal. This spec adds the experience layer the builder was
always meant to have, as five cohesive pieces in **one spec**:

1. **Supported-OS catalog** — a curated, pinned registry the user selects from (never a URL); adding a
   new distro is one entry that appears in the dropdown automatically.
2. **Update-detect** — recognize an existing dev-boost USB and offer a non-destructive **update**
   instead of a wipe.
3. **Live progress + per-stage status** — a real `rich` download bar + step indicators.
4. **`--dry-run` preview** — resolve and show the whole plan without touching the disk (safe rehearsal).
5. **Final summary + usage instructions** — a result panel + how-to-boot.

All side effects stay behind the injected `Executor`/`Downloader`; a new injected `Reporter` seam
makes progress/output testable. Privileged steps (mount, ventoy) shell through the executor with sudo.

---

## 2. Decisions locked (brainstorming)

| # | Question | Decision |
|---|----------|----------|
| 1 | OS selection | Curated **catalog** registry; user picks a friendly-named entry; `--iso` takes a catalog **id**, never a URL. Adding a distro = one entry. Arch-aware. |
| 2 | Update detection | Read-only probe for a build-time **marker** (`Bootstrap/.devboost-usb.json`) + Ventoy signature → `blank` / `ventoy-other` / `devboost(meta)`. |
| 3 | Update behavior | Non-destructive: `ventoy -u` + re-stage binary/`ks.cfg`/`ventoy.json` + refresh marker; **keep** `ISO/`, `secrets.age`, data. Default action when a dev-boost stick is detected. |
| 4 | Progress | A `Reporter` seam (`RichReporter` + `FakeReporter`); real `rich` download bar + per-stage steps. **Reporter is constructor-injected into `UrllibDownloader(cache, reporter)` — the `Downloader` Protocol `fetch(url, name, sha256)` is unchanged; `build()`/stages take an explicit `*, reporter`.** |
| 5 | Dry-run | `--dry-run` resolves + renders the full plan and exits; touches nothing (the read-only probe runs — a transient `mount -o ro` is the only effect). |
| 6 | Summary | `rich` result panel (device · OS · profiles · options) + short boot/usage instructions. |
| 7 | Scope | One spec; privileged mount/ventoy via the executor (sudo). Real Fedora-44 sha256 fetched from Fedora's signed `CHECKSUM` at implementation time (verified, never invented; unblocks real runs). |
| 8 | Catalog unit | **Evolve `isos.py` → `catalog.py`**: fold the parallel `FEDORA` + `_ARCH_SUPPORT` dicts into one `Os` entry per distro (`isos: dict[arch, IsoSpec]`); keep `iso_for(os_id, arch)`; update the importers + `test_isos.py`. Adding a distro = one `Os` entry. |

---

## 3. Goals / Non-goals

**Goals**
- Pick the OS from a curated, extensible dropdown (no URLs); adding a distro is one catalog entry.
- Detect an existing dev-boost USB and update it without wiping (preserve ISOs/secrets/data).
- Show real download progress + per-stage status; end with a clear summary + how-to.
- A safe `--dry-run` rehearsal that mutates nothing.
- Fill the real Fedora-44 checksum so a real/VM run completes.
- Typed, hermetic tests (probe/reporter/preview/update path); `mypy --strict` + ruff + pytest green.

**Non-goals**
- Not delivering new OSes (only the Fedora-44 entry is pinned/real; the catalog is *shaped* for more —
  adding Ubuntu etc. is a later data/validation task).
- Not a TUI/curses app — `questionary` prompts + `rich` progress/panels in the terminal.
- Not changing the firstboot/Kickstart contract or the offline-mirror scope.
- Not auto-fetching checksums at runtime — catalog pins are maintained in-repo (Principle III).

---

## 4. Architecture

New/changed units under `engine/src/devboost/usb/` (each one responsibility, behind a seam):

```
catalog.py    # (expands isos.py) Distro registry: Os(id,name,distro,version,edition) + per-arch IsoSpec;
              #   supported() list for the select; iso_for(id, arch). Friendly names. Real pins.
probe.py      # read-only disk-state detection: probe(ctx, device) -> DiskState
              #   (BLANK | VENTOY_OTHER | DEVBOOST(meta)); mounts VTOY ro via executor (sudo), reads marker.
report.py     # Reporter Protocol + RichReporter (rich progress + steps + summary panel) + FakeReporter (tests)
marker.py     # the .devboost-usb.json schema (Marker: version, os_id, arch, built_at) + read/write
preview.py    # render_plan(cfg, state) -> str : the --dry-run plan summary (also feeds the wizard recap)
config.py     # + mode: Literal["build","update"] ; (Marker lives in marker.py)
stages.py     # + update_stage (ventoy -u + re-stage, no wipe) ; build writes the marker ; reporter.step calls
builder.py    # branch on cfg.mode (build vs update) ; thread the Reporter
download.py   # UrllibDownloader takes a Reporter → real rich progress (currently silent)
wizard.py     # OS select shows catalog friendly names ; after device pick, probe + branch (update/rebuild/wipe)
cli/usb.py    # --dry-run flag ; construct + inject the Reporter ; print the final summary panel
```

**Data flow:** wizard/flags → resolve OS via `catalog.iso_for(id, arch)` → `probe(device)` → set
`cfg.mode` (build/update) → (if `--dry-run`) `preview.render_plan` + exit → else `builder.build`
with a `Reporter` → stages emit `reporter.step(...)`, download drives the progress bar, build/update
writes the marker → `cli` prints the summary panel.

## 5. Supported-OS catalog (§2 #1)

```python
@dataclass(frozen=True)
class Os:
    id: str            # "fedora-44"
    name: str          # "Fedora 44 — Everything (netinst)"   (shown in the select)
    distro: str        # "fedora"
    version: str       # "44"
    edition: str       # "Everything-netinst"
    isos: dict[str, IsoSpec]   # arch -> IsoSpec(url, sha256)

CATALOG: dict[str, Os] = { "fedora-44": Os(... isos={"x86_64": IsoSpec(url=..., sha256=<REAL>)}) }

def supported() -> list[Os]: ...                 # for the wizard select (friendly names)
def iso_for(os_id: str, arch: str) -> IsoSpec:   # raises UsbError if the id/arch isn't pinned
```

The wizard renders `supported()` as `questionary.Choice(os.name, value=os.id)`. Implementation fills
the **real Fedora-44 `Everything-netinst` x86_64 sha256** from the Fedora `CHECKSUM` (verified, not
invented). Adding a distro later = append an `Os` entry; it shows up in the select with zero code
changes.

## 6. Update-detect (§2 #2, #3)

`marker.py` — `Marker(version: str, os_id: str, arch: str, built_at: str)` ↔ `Bootstrap/.devboost-usb.json`.

`probe.py`:
```python
@dataclass(frozen=True)
class DiskState:
    kind: Literal["blank", "ventoy-other", "devboost"]
    marker: Marker | None = None

def probe(ctx: Ctx, device: str) -> DiskState
```
Read-only: find the Ventoy data partition by enumerating the device's children with
`lsblk -P -o NAME,LABEL <device>` (executor call) and selecting the child whose `LABEL == "VTOY"`;
mount that partition read-only to a temp dir (`tmp_path`/`mkdtemp`) via the executor
(`mount -o ro <part> <dir>`, sudo), look for `Bootstrap/.devboost-usb.json`, then **unmount in a
`finally`** (`umount <dir>`, sudo) so the mount never leaks even on a parse error. Returns
`devboost(meta)` if the marker parses, `ventoy-other` if a `VTOY` partition exists without our marker,
else `blank`. Any failure — no `VTOY` child, mount fails, unreadable/invalid marker — degrades to
`DiskState("blank")` with a warning (a read-only probe never blocks the run). No writes.

Wizard branch after the device pick:
- **devboost** → `questionary.select("This is a dev-boost USB (<os>, built <date>). What now?",
  ["Update (keep ISOs/secrets, no wipe)", "Rebuild (wipe)"], default=Update)`.
- **ventoy-other** → confirm wipe (default No), warning it's a non-dev-boost Ventoy stick.
- **blank** → the existing wipe confirmation.

`stages.update_stage(ctx, cfg, *, vtoy_mount)` (no wipe): `ventoy -u <device>`, re-stage
`devboost.tar.gz` + rendered `ks.cfg` + `ventoy.json`, refresh the marker; leave `ISO/`,
`secrets.age`, and the data partition untouched. `boot_artifacts` (the wipe path) writes the marker
after the layout. `builder.build` calls `update_stage` when `cfg.mode == "update"`, else the
build path; extras/mirror stages run in both modes when selected.

## 7. Progress + per-stage status (§2 #4)

`report.py`:
```python
class Reporter(Protocol):
    def step(self, msg: str) -> None: ...          # "✓ Ventoy installed"
    def progress(self, label: str, total: int) -> AbstractContextManager[Callable[[int], None]]: ...
    def summary(self, panel: str) -> None: ...

class RichReporter:  # rich.progress bar + step lines + rich.panel summary
class FakeReporter:  # records steps:list[str] + summaries:list[str]; progress is a no-op recorder
```
The reporter is **constructor-injected**: `UrllibDownloader(cache, reporter)` holds it and drives
`progress(...)` with the HTTP `Content-Length` while streaming (falls back to an indeterminate spinner
when absent). The shared `Downloader` Protocol — `fetch(url, name, sha256) -> Path` — is **unchanged**,
so `FakeDownloader` and every existing `fetch(...)` call site stay untouched; the progress bar is an
implementation detail of the real downloader. Each builder stage calls `reporter.step(...)` at
completion; `build()` and the stages take an explicit keyword-only `reporter` (matching the existing
`*, vtoy_mount` style). Download-progress tests construct a real `UrllibDownloader` against a
local/in-memory HTTP source with a `FakeReporter` and assert the byte-count callbacks; stage-step
tests inject `FakeReporter` and assert the step sequence.

## 8. Dry-run preview (§2 #5)

`preview.render_plan(cfg: UsbBuildConfig, state: DiskState) -> str` returns a `rich`-renderable
summary: target device + detected state (blank/ventoy-other/dev-boost vX), mode (build/update), OS
(name + arch), profiles, optional stages (extra ISOs, installers, offline mirror), estimated download
(ISO size from `Content-Length` HEAD, or "cached"). `devboost usb --dry-run` resolves everything
(including `probe`, which is read-only) and prints the plan, then exits 0 — **no `ventoy`, no
download, no writes.** The same renderer feeds a one-screen recap in the interactive wizard before the
final go/no-go.

## 9. Final summary + usage instructions (§2 #6)

On success `cli/usb.py` prints a `rich` panel via `reporter.summary(...)`:
> ✅ Built `/dev/sdb` — Fedora 44 (x86_64) · profiles: full · offline-mirror: yes · +1 extra ISO
> Boot it: insert the USB → open the firmware boot menu → pick the USB → Fedora installs
> (auto/zero-touch or manual) → on first boot dev-boost installs your profiles. Bad update later?
> Reboot → GRUB "Fedora snapshots".

Update runs print the analogous "Updated `/dev/sdb` (Fedora 44 → binary vX, ISOs/secrets preserved)".

## 10. Error handling & testing

- **Errors:** reuse `UsbError`/`DeviceError`/`VentoyError`; probe failures (can't mount) degrade to
  `blank` with a warning (never block on a read-only probe); an unpinned OS/arch raises a clear
  `UsbError`.
- **Tests (hermetic, constitution gates):**
  - `catalog`: `supported()` friendly names; `iso_for` arch hit/miss; Fedora-44 sha256 is 64 hex.
  - `marker`: round-trip read/write.
  - `probe`: with a fake mounted dir containing the marker → `devboost`; VTOY without marker →
    `ventoy-other`; nothing → `blank`; all via `FakeExecutor` (mount is a recorded call; the temp dir
    is `tmp_path`).
  - `report`: `FakeReporter` records steps/summaries; `progress` increments are captured.
  - `preview`: `render_plan` contains the device, OS name, mode, profiles, and the offline note.
  - `update_stage`: re-stages binary/ks.cfg/marker and runs `ventoy -u` but **never** `ventoy -i`;
    leaves `ISO/`/`secrets.age` untouched.
  - `builder`: `mode="update"` calls `update_stage` (not `boot_artifacts`); `mode="build"` the reverse.
  - `download`: progress callback invoked with byte counts (FakeReporter).
- The wizard branches remain thin and are not unit-tested; the `probe`/`preview`/`reporter` they call
  are.

## 11. Constitution alignment

Typed Python + Typer; `rich`/`questionary` already deps; no new heavy deps. Privileged mount/ventoy
via the executor (argv + sudo). Catalog pins are in-repo data (Principle III). `mypy --strict` +
pytest + ruff gates. No bash added.

## 12. Resolved decisions (were open; locked in grilling)

- **Ventoy data-partition discovery:** enumerate the device's children with
  `lsblk -P -o NAME,LABEL <device>` and pick the child where `LABEL == "VTOY"` (no `blkid` dependency;
  one executor call, hermetically fakeable). Mount it `mount -o ro` to a `mkdtemp` dir and **unmount in
  a `finally`** (`umount`); any failure degrades to `blank` with a warning.
- **Update scope:** payload-only by default (re-stage binary/`ks.cfg`/`ventoy.json` + refresh marker;
  `ventoy -u`, never `ventoy -i`); `ISO/`, `secrets.age`, and the data partition are preserved.
  Refreshing the pinned ISO is an explicit opt-in `--refresh-iso` (and the analogous wizard prompt).
- **Estimated-download size:** HTTP `HEAD` `Content-Length` for the pinned ISO; if the blob is already
  in the cache show `"cached"`, and if `HEAD` fails or `--offline`/no network, show a static
  catalog-pinned size estimate (or `"unknown"`) rather than blocking the dry-run.
- **Catalog unit:** evolve `isos.py` → `catalog.py` (one `Os` entry per distro; `iso_for(os_id, arch)`
  retained); update importers + `test_isos.py`. (See §2 #8.)
- **Reporter injection:** constructor-injected into `UrllibDownloader`; `Downloader.fetch` signature
  unchanged; `build()`/stages take explicit `*, reporter`. (See §2 #4, §7.)
- **Fedora-44 sha256:** fetched and verified from Fedora's signed `CHECKSUM` during implementation —
  never invented. If the build environment has no network at impl time, the entry is flagged as a
  blocking pre-release TODO for the maintainer to fill, and tests assert only the 64-hex *shape*.
