# Design: use a local ISO instead of downloading it (`--iso-path`)

**Created**: 2026-07-17
**Status**: Draft — awaiting review
**Scope**: `devboost installer` only. Engine spec 014 (`specs/014-python-engine-core/`).

## Problem

`devboost installer` can only obtain its install ISO by downloading it from the URL pinned
in `catalog.toml`. If you already hold that exact ISO — from a colleague, a LAN mirror, an
earlier download, a DVD — there is no way to say so. You wait for ~2GB you already have.

The download cache removes the *repeat* cost — once the wizard's cache-dir answer is
actually honoured (commit `2910191`, unreleased at time of writing) — but only *after* one
successful download, and its default lives under `$TMPDIR`, so a reboot restores the
problem. Nothing covers "I already have the bytes; never fetch them."

## Goal

One flag and one wizard step that supply the **bytes** of the primary install ISO. Nothing
else changes: the catalog remains the source of truth for the id, URL, sha256, edition and
`os_family`, so `ks.cfg`, the netinst pairing, `ventoy.json` and zero-touch install are all
untouched.

## Non-goals (each is a separate feature; do not smuggle them in)

- A local **netinst/autoinstall** ISO (`--autoinstall-iso-path`).
- A local Ventoy tarball, or a fully offline/air-gapped build.
- **Off-catalog** distros or versions (`--iso-id`, `--os-family`). The catalog stays the
  only source of pins (Constitution Principle III).
- **Extra bootable ISOs** for multiboot (`--extra-iso`). `MediaConfig.extra_isos` and
  `.installers` already exist and are already staged by `stages.extra_isos()` /
  `stages.installers()`, but nothing populates them — a separate, easy feature.

## Decisions

### The ISO must match the catalog pin, or the build stops

The chosen ISO *is* the pinned catalog release, so its sha256 is already known and a local
file can be verified exactly as a downloaded one is. A mismatch is either a different
release or a corrupt file, and both must stop the build **before** it wipes a stick:

```
error: /home/dev/isos/f44.iso does not match the pinned fedora-44 ISO
         expected 1620295f…26ddf  (catalog.toml)
         got      9a3c1e77…0b412
       This is a different release or a corrupt file.
       Omit --iso-path to fetch the pinned ISO.
```

There is no `--no-verify` and no `--iso-sha256`. `ks.cfg`, `ventoy.json` and the netinst
pairing are all generated for the pinned release; an ISO that is not that release produces
a stick whose autoinstall does not match its media, and the failure would surface at boot,
far from its cause. Verification is not a tax here — see "Cost" below.

### Wrap the `Downloader` seam; do not branch in the staging code

`stages.py` obtains every artifact through the injected `Downloader` Protocol:

```python
class Downloader(Protocol):
    def fetch(self, url: str, name: str, sha256: str) -> Path: ...
```

A decorator serves one artifact from disk and delegates the rest:

```python
class LocalIsoDownloader:
    """Serves one user-supplied ISO in place; delegates every other artifact."""
    def __init__(self, inner: Downloader, name: str, path: Path, sha256: str) -> None
    def check(self) -> None                       # verify against the pin, or raise MediaError
    def fetch(self, url, name, sha256) -> Path    # name match -> local path; else -> inner
```

`fetch` receives a `sha256` of its own, and the constructor also takes one, so the contract
between them must be explicit rather than assumed: for the matched *name*, `fetch` requires
the requested `sha256` to equal the one `check()` verified, and raises if it does not. Both
values come from `cfg.iso.sha256` today, so they always agree — the guard exists so that a
future caller requesting a *different* pin under the same filename fails loudly instead of
silently receiving a file that was verified against something else.

`stages.py` needs **no changes**: all three ISO fetches already funnel through `dl`. This
mirrors how the engine already injects `Executor`, composes with the existing
`FakeDownloader` for hermetic tests, and keeps the sourcing decision in one class rather
than at three call sites.

The rejected alternatives:

- **Pre-seed the cache** (copy the file to `<cache>/fedora-44.iso` so `cache.has()`
  short-circuits): needs no download-path change at all, but either burns another 2GB on a
  copy or symlinks — and then `Cache.evict_stale()` unlinks *the user's own ISO*. It is
  also magic-by-side-effect: nothing in the code would say "local ISO".
- **`MediaConfig.iso_path` + a branch at each `dl.fetch` site**: spreads a sourcing concern
  through staging logic and duplicates it three times. Duplication at exactly this kind of
  site is what let the `VTOY` label bug and the Ventoy cwd bug each survive in two copies.

### Verify before anything destructive

`dl.fetch` for the primary ISO happens *inside* `_mounted_vtoy` — **after** the stick is
wiped and Ventoy is installed (`stages.py`, `boot_artifacts`). Verifying only there would
wipe the stick, install Ventoy, and *then* reject the ISO. That is the same late-validation
shape as the auto-mount refusal that made a user answer seven prompts for a device the
build could never honour.

So `installer()` calls `dl.check()` **before** `build()`. A bad path or a bad hash costs
seconds and zero data. `check()` memoises, so the later `fetch()` does not re-hash.

### Cost: verification is free relative to today

`UrllibDownloader.fetch` calls `cache.has(name, sha256)` → `Cache.verify` → a **full
sha256 of the ISO on every run**, cached or not. Hashing a local ISO is therefore the same
work the cached path already does, not a new cost.

### One shared hashing implementation

`Cache.verify` owns the only sha256 loop today. Extract it to a module-level
`sha256_of(path: Path) -> str` in `media/cache.py`; `Cache.verify` and `LocalIsoDownloader`
both call it. Two copies of "what verification means" is precisely the shape of the bugs
this component is meant to avoid.

### Expand `~` explicitly

Nothing in `media/` or `cli/installer.py` calls `expanduser()` today, so `--iso-path
~/isos/f44.iso` would look for a literal `~` directory, and the wizard's path prompt has
the same gap. `iso_path` is normalised with `.expanduser().resolve()` at the boundary
(CLI option and wizard answer).

> Adjacent, out of scope: `secrets_path` / `secrets_key_path` have the same latent gap and
> should get the same treatment in their own change.

### The wizard asks, with blank meaning "download"

The wizard already asks 10 questions; this adds an eleventh whose default is blank, so it
costs one Enter — the same shape as the existing "Path to secrets.age (blank to skip)".
It is placed immediately after the OS select, because it is about *that* OS's ISO.

```
? Operating system: Fedora 44 — Workstation (Live)
? Local ISO for Fedora 44 (blank to download): ~/isos/Fedora-Workstation-Live-44-1.7.x86_64.iso
```

### `MediaConfig.iso_path` is config, not behaviour

`MediaConfig` gains `iso_path: Path | None = None`. It is the wizard → `installer()`
contract, so the answer has to travel in it. It is read **only** in `installer()`, to build
the downloader; `stages.py` never sees it. The field is data about where bytes come from;
the behaviour lives in the seam.

### The update path gets it for free

`update_stage` re-fetches the ISO only when `cfg.refresh_iso`, using the same
`f"{cfg.iso.id}.iso"` name, so `--iso-path --refresh-iso` on a dev-boost stick is served
from disk with no extra code.

### `--dry-run` stays inert

Dry-run reports `local: <path>` and checks only that the file exists (a `stat`). It does
not hash — dry-run's contract is "resolve and print the plan; touch nothing", and a 2GB
hash would make it slow for no gain. A wrong path is caught by the existing existence
check; a wrong *hash* is caught on the real run, before the wipe.

> Adjacent finding, out of scope: `_iso_note()` in `cli/installer.py` is **dead code** —
> defined, documented (with a warning about dry-run behaviour that cannot occur) and never
> called. Two tests monkeypatch it, which is coverage of nothing. It should be deleted or
> wired up in its own change.

## Data flow

```
--iso-path PATH  /  wizard "Local ISO … (blank to download)"
        │  .expanduser().resolve()
        ▼
MediaConfig.iso_path
        │
        ▼
installer():
    dl = UrllibDownloader(cache, reporter)
    if cfg.iso_path:
        dl = LocalIsoDownloader(dl, f"{cfg.iso.id}.iso", cfg.iso_path, cfg.iso.sha256)
        dl.check()                    # ← before build(); before any wipe
    build(ctx, cfg, dl, cache, …)
        │
        ▼
stages.boot_artifacts / update_stage:          (unchanged)
    dl.fetch(cfg.iso.url, "fedora-44.iso", pin_sha)
        ├─ name matches      → the user's file, in place
        └─ "fedora-44-netinst.iso", "ventoy-1.1.16-linux.tar.gz" → downloaded as today
        │
        ▼
    shutil.copyfile(iso_path, mnt/"ISO"/"fedora-44.iso")   (unchanged)
```

## Errors

All raise `MediaError`, which `installer()` already converts to a clean `exit 1` with no
traceback:

| Condition | Message |
|---|---|
| Path missing / not a file / unreadable | names the path and the flag |
| sha256 mismatch | names both hashes and points at `catalog.toml` (see above) |

`--iso-path` with a Fedora file while `--iso ubuntu-26.04` is selected fails as a hash
mismatch. That is correct and desirable: it is not the pinned ISO for the chosen OS.

## Testing

Hermetic, no network, no device:

1. `LocalIsoDownloader` delegates a non-matching name (netinst, Ventoy tarball) to the
   inner downloader.
2. Returns the local path when the name matches, and does **not** copy it into the cache.
3. `check()` raises `MediaError` naming both hashes on a mismatch.
4. `check()` raises on a missing/unreadable file.
5. `fetch()` does not re-hash after `check()` (memoised).
6. **Ordering — the one that guards the bug class**: a bad `--iso-path` fails *before*
   `build()` is called, so nothing is wiped.
7. CLI: `--iso-path` serves the file with no network access.
8. Wizard: blank → `iso_path is None`; a path → `cfg.iso_path` set and `~` expanded.

## Acceptance

- `devboost installer --device /dev/sdb --iso-path <pinned fedora-44 iso> --yes` builds a
  working stick with no ISO download (the netinst and Ventoy tarball still download).
- The same command with a non-pinned or corrupt ISO exits 1, names both hashes, and leaves
  the stick untouched.
- The wizard's new prompt, left blank, behaves exactly as today.
- `mypy --strict`, `ruff`, and the full suite stay green.
