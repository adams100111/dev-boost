# get.sh Public Bootstrap (Frozen-Binary Delivery) — Design

**Status:** Draft spec (approved in brainstorming; lands on the impl branch)
**Date:** 2026-06-25
**Builds on:** Plan 1 (typed engine), Plan 2 (portable tiers), config-enrichment — all merged to `main`
**Realizes:** the frozen-binary delivery the constitution (v2.0.0) mandates and the original two-tier spec deferred as "Plan 3".

---

## 1. Summary

Deliver a free, zero-config-per-user, always-latest public installer so any machine can become a configured dev box with one line:

```bash
curl -fsSL https://raw.githubusercontent.com/adams100111/dev-boost/main/scripts/get.sh | bash -s -- terminal
```

`get.sh` (hosted on raw.githubusercontent) detects the box's arch, downloads the matching **frozen single-file `devboost` binary** + a small **noarch data tarball** from the latest GitHub Release, verifies SHA256, and runs `devboost install terminal` — no Python, no clone, no config on the user's side. A GitHub Actions workflow builds + publishes the Release on every `v*` tag.

Constitution v2.0.0 mandates the frozen binary ("Pure-Python source MUST NOT be the on-target runtime"), so the delivery vehicle is fixed; this spec is about *building* and *shipping* it.

---

## 2. Decisions locked (brainstorming)

| # | Decision |
|---|----------|
| 1 | **Frozen single-file binary via PyInstaller `--onefile`** (zipapp/shiv would still need Python on-target → violates constitution; Nuitka heavier for no gain). |
| 2 | **Split Release artifacts:** per-arch binary (`devboost-x86_64`, `devboost-aarch64`) + one noarch `devboost-data.tar.gz` + `checksums.txt`. Data built once. |
| 3 | **Hosting (free):** `get.sh` on `raw.githubusercontent`; artifacts on GitHub Releases `/latest/download/` (always-newest); arch/distro detection client-side in `get.sh`. |
| 4 | **CI release workflow included** (`.github/workflows/release.yml`), triggered on `v*` tag. |
| 5 | **glibc base = ubuntu-22.04** for BOTH arches (glibc 2.35; forward-compatible → runs on Ubuntu 22.04 → 26.04 LTS and Fedora 38 → 44+). Use `ubuntu-22.04-arm` for aarch64 if the runner is available, else `ubuntu-24.04-arm` (ARM targets skew newer; acceptable). |
| 6 | **Engine tweak:** `--root` honors `$DEVBOOST_ROOT` so the frozen binary finds its extracted data. |

---

## 3. Component design

### 3.1 Engine: `DEVBOOST_ROOT` env fallback (`engine/devboost/cli.py`)
Today `_DEFAULT_ROOT = Path(__file__).resolve().parents[2]` — invalid inside a PyInstaller onefile (the source lives in a temp extraction dir, not the repo). Change to:
```python
import os
_DEFAULT_ROOT = (
    Path(os.environ["DEVBOOST_ROOT"]) if os.environ.get("DEVBOOST_ROOT")
    else Path(__file__).resolve().parents[2]
)
```
`--root` still overrides explicitly. Covered by a pytest (env set → that path; env unset → repo root). This is the only engine change.

### 3.2 `scripts/build-bundle.sh` (local + CI)
One script, runnable on any builder (this Fedora box AND the CI runners):
1. Resolve arch: `uname -m` → `x86_64` | `aarch64` (map `arm64`→`aarch64`).
2. Build a venv, `pip install ./engine pyinstaller`, then
   `pyinstaller --onefile --name devboost engine/devboost/__main__.py` (add a thin `engine/devboost/__main__.py` that calls `from devboost.cli import app; app()` so PyInstaller has a clean entrypoint).
   Output renamed to `dist/devboost-<arch>`.
3. Data tarball: `tar czf dist/devboost-data.tar.gz modules lib dotfiles profiles.toml`.
4. `sha256sum dist/devboost-* dist/devboost-data.tar.gz > dist/checksums.txt`.
5. Smoke: `DEVBOOST_ROOT=<extracted> dist/devboost-<arch> list terminal` resolves (proves the binary runs with NO python on PATH and finds the data).

### 3.3 `.github/workflows/release.yml`
- **Trigger:** `push: tags: ['v*']`.
- **Job `binary` (matrix):** `{os: ubuntu-22.04, arch: x86_64}` and `{os: ubuntu-22.04-arm | ubuntu-24.04-arm, arch: aarch64}`. Steps: checkout → setup-python 3.11+ → `bash scripts/build-bundle.sh` → upload `dist/devboost-<arch>` as a workflow artifact.
- **Job `data`:** builds `devboost-data.tar.gz` once (ubuntu-latest) → artifact.
- **Job `release`** (needs binary+data): download artifacts → generate combined `checksums.txt` → create/*update* the GitHub Release for the tag with all four assets (`softprops/action-gh-release` or `gh release create`). `/latest/download/<asset>` then resolves to these.

### 3.4 `scripts/get.sh` (public entry, hosted on raw.githubusercontent)
Structured as functions with a `main "$@"` guard at the bottom (so bats can source it without auto-running). Flow:
1. `_arch()`: `uname -m` → `x86_64`/`amd64`→`x86_64`, `aarch64`/`arm64`→`aarch64`; else fail with a clear message.
2. `_fetch URL OUT`: prefer `curl -fsSL`, fall back to `wget -qO`. Require `tar` + a sha256 tool (`sha256sum` or `shasum -a 256`).
3. Base URL: `https://github.com/adams100111/dev-boost/releases/latest/download`.
4. Download `devboost-<arch>`, `devboost-data.tar.gz`, `checksums.txt` to a temp dir.
5. **Verify SHA256** of both downloads against `checksums.txt`; abort on mismatch (integrity gate).
6. Install: `~/.local/share/devboost/` ← extract data tarball; `bin/devboost` ← the binary (`chmod +x`).
7. `export DEVBOOST_ROOT="$HOME/.local/share/devboost"`; `exec "$DEVBOOST_ROOT/bin/devboost" install "${@:-terminal}"`.

Usage: `curl -fsSL …/get.sh | bash -s -- terminal [devtools] [--dry-run]`.

### 3.5 `engine/devboost/__main__.py` (new, tiny)
```python
from devboost.cli import app
if __name__ == "__main__":
    app()
```
Gives PyInstaller a stable entrypoint and enables `python -m devboost`.

---

## 4. Testing

- **get.sh (hermetic bats, `tests/getsh.bats`):** put stub `curl`/`wget`/`uname`/`sha256sum`/`tar` on PATH; assert: arch mapping (`arm64`→`aarch64`, unknown→fail); correct `/latest/download/` URLs requested; **checksum mismatch → non-zero exit, no exec**; `DEVBOOST_ROOT` exported; final exec args pass through (`terminal` default; `terminal devtools` forwarded). Source get.sh's functions via the run-guard.
- **engine (pytest):** `DEVBOOST_ROOT` set → `_DEFAULT_ROOT` is that path; unset → repo root. (mypy --strict clean.)
- **build-bundle (local validation, not a unit test):** run `scripts/build-bundle.sh` on this Fedora box; confirm `dist/devboost-x86_64 --version` and `… list terminal` work with `python3` NOT on PATH (prove standalone). Record output.
- **CI workflow:** cannot run in-session — validated on push (a real `v*` tag). The plan notes this; local build-bundle + get.sh bats are the in-session evidence.
- **Both existing suites stay green** (bats ≥1154 + engine pytest); get.sh/build-bundle are additive.

---

## 5. Docs
- **README:** replace the "planned" bootstrap note with the real one-liner; a short "Install (any OS)" section; how `/latest/` tracks releases; the **repo-must-be-public** note.
- **docs/architecture.md:** mark the frozen-binary delivery as realized (was "sanctioned, not shipped").

---

## 6. Prerequisites (user-actioned, flagged — not code)
1. **Repo must be public** for the free `raw.githubusercontent` + Releases path. (Currently `github.com/adams100111/dev-boost`.)
2. A **`v*` tag** must be pushed to trigger the workflow and create the first Release that `/latest/download/` resolves to. (No Release ⇒ get.sh's download 404s — get.sh should surface that as a clear "no release yet" error.)

## 7. Out of scope
- Windows/macOS binaries (Linux x86_64/aarch64 only here; macOS schema exists but no frozen mac build).
- Code-signing / notarization.
- A custom domain (raw URL is the chosen $0 path; Pages/custom-domain is a later cosmetic option).
- Auto-update of an installed binary (get.sh re-run pulls latest; no self-update daemon).

## 8. Risks
- **PyInstaller onefile + bash subprocess:** the binary shells out to `bash -lc` for module installs; that's fine (bash is on every target). The binary itself needs no Python at runtime (tomllib is frozen in). Confirm via the python-not-on-PATH smoke.
- **glibc:** building on 22.04 covers 22.04→26.04+/Fedora 38→44+ by forward-compat; ancient LTS (20.04/RHEL8) unsupported — acceptable per §2.5.
- **aarch64 runner:** `ubuntu-22.04-arm` may not be a free label; fall back to `ubuntu-24.04-arm` (binaries then need glibc ≥2.39 on ARM — acceptable as ARM dev targets are recent).
- **No-release state:** get.sh must give a friendly error if `/latest/download/` 404s (no published Release yet).
- **CI not testable in-session:** mitigated by local build-bundle validation + get.sh bats; the workflow is reviewed as code.
- **Unauthenticated `checksums.txt` (accepted trust assumption):** get.sh fetches `checksums.txt` from the same Release as the binaries, so the SHA256 check guarantees *download integrity* (no corruption-in-transit, no partial/omitted asset) but NOT *provenance* — a compromise of the GitHub account/Release that rewrites the binaries AND `checksums.txt` together defeats it. This is inherent to self-hosted-checksum `curl | bash`; the mitigation (code-signing / a detached signature) is explicitly out of scope (§7). Trust rests on GitHub TLS + the repo owner's account integrity.

## 9. Decomposition
One cohesive plan, ordered: (A) engine `DEVBOOST_ROOT` fallback + `__main__.py` → (B) `build-bundle.sh` + local validation → (C) `get.sh` + bats → (D) `release.yml` → (E) docs.
