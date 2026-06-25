# get.sh Public Bootstrap (Frozen-Binary Delivery) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a free `curl … | bash` public installer: `get.sh` downloads an arch-matched frozen `devboost` binary + a noarch data tarball from GitHub Releases `/latest/download/`, verifies SHA256, and runs `devboost install terminal` — no Python/clone/config on the target.

**Architecture:** A PyInstaller `--onefile` binary built from the typed engine + a `tar.gz` of the repo data (`modules/ lib/ dotfiles/ profiles.toml`). `scripts/build-bundle.sh` builds both (local + CI); `.github/workflows/release.yml` publishes them on a `v*` tag; `scripts/get.sh` (hosted on raw.githubusercontent) detects arch, downloads, verifies, installs to `~/.local/share/devboost`, and execs the binary with `DEVBOOST_ROOT` set.

**Tech Stack:** PyInstaller (onefile); bash (`get.sh`, `build-bundle.sh`); GitHub Actions; BATS (get.sh tests); pytest (engine env fallback).

## Global Constraints

- **Frozen binary is mandatory** (constitution v2.0.0): the on-target runtime is the PyInstaller binary; Python source MUST NOT be the runtime. Verify the binary runs with `python3` NOT on PATH.
- **Split Release assets:** `devboost-x86_64`, `devboost-aarch64`, `devboost-data.tar.gz`, `checksums.txt`. Data tarball contains exactly `modules/ lib/ dotfiles/ profiles.toml`.
- **Hosting:** `get.sh` URL is `https://raw.githubusercontent.com/adams100111/dev-boost/main/scripts/get.sh`; artifacts at `https://github.com/adams100111/dev-boost/releases/latest/download/<asset>`.
- **glibc base = ubuntu-22.04** for both arches (forward-compatible → runs Ubuntu 22.04→26.04 LTS, Fedora 38→44+). aarch64 on `ubuntu-22.04-arm` if available, else `ubuntu-24.04-arm`.
- **get.sh must SHA256-verify** every download against `checksums.txt` and abort on mismatch; must give a clear error if no Release exists (404).
- **Both suites stay green** (bats ≥1154 + engine pytest); new work is additive.
- **Commits:** Conventional Commits, NO Claude/Anthropic attribution.
- **CI workflow is not runnable in-session** — validated on push; in-session evidence is the local `build-bundle.sh` run + the `get.sh` bats.

**Out of scope:** Windows/macOS binaries; code-signing; custom domain; binary self-update.
**Prerequisites (user-actioned, not code):** repo public; a `v*` tag pushed to create the first Release.

---

## File Structure

```
engine/devboost/cli.py            # MODIFY — _DEFAULT_ROOT honors $DEVBOOST_ROOT
engine/devboost/__main__.py       # CREATE — PyInstaller/`python -m` entrypoint
engine/tests/test_cli.py          # MODIFY — DEVBOOST_ROOT fallback test
scripts/build-bundle.sh           # CREATE — PyInstaller build + data tarball + checksums + smoke
scripts/get.sh                    # CREATE — public bootstrap (download/verify/install/exec)
tests/getsh.bats                  # CREATE — hermetic get.sh tests
.github/workflows/release.yml     # CREATE — tag-triggered build + Release
README.md                         # MODIFY — real curl|bash one-liner + install section
docs/architecture.md              # MODIFY — frozen-binary delivery realized
```

---

## Task 1: Engine — `DEVBOOST_ROOT` fallback + `__main__.py`

**Files:** Modify `engine/devboost/cli.py`; Create `engine/devboost/__main__.py`; Test `engine/tests/test_cli.py`

**Interfaces:** Produces `python -m devboost` entrypoint; `_DEFAULT_ROOT` honors `$DEVBOOST_ROOT`.

- [ ] **Step 1: Write the failing test** — append to `engine/tests/test_cli.py`:

```python
def test_default_root_honors_devboost_root_env(monkeypatch, tmp_path) -> None:
    import importlib
    monkeypatch.setenv("DEVBOOST_ROOT", str(tmp_path))
    import devboost.cli as climod
    importlib.reload(climod)
    assert climod._DEFAULT_ROOT == tmp_path
    monkeypatch.delenv("DEVBOOST_ROOT")
    importlib.reload(climod)
    assert climod._DEFAULT_ROOT.name == "dev-boost" or climod._DEFAULT_ROOT.exists()
```

- [ ] **Step 2: Run — verify fail**

Run: `cd engine && . .venv/bin/activate && pytest tests/test_cli.py::test_default_root_honors_devboost_root_env -v`
Expected: FAIL — `_DEFAULT_ROOT` ignores the env var.

- [ ] **Step 3: Edit `engine/devboost/cli.py`** — add `import os` at the top (with the other imports) and replace the `_DEFAULT_ROOT = ...` line with:

```python
_DEFAULT_ROOT = (
    Path(os.environ["DEVBOOST_ROOT"])
    if os.environ.get("DEVBOOST_ROOT")
    else Path(__file__).resolve().parents[2]
)
```

- [ ] **Step 4: Create `engine/devboost/__main__.py`**

```python
from devboost.cli import app

if __name__ == "__main__":
    app()
```

- [ ] **Step 5: Run — verify pass + types + module entry**

Run: `cd engine && . .venv/bin/activate && pytest tests/test_cli.py -v && mypy && python -m devboost --version`
Expected: tests PASS; mypy `Success`; `python -m devboost --version` prints the version.

- [ ] **Step 6: Commit**

```bash
git add engine/devboost/cli.py engine/devboost/__main__.py engine/tests/test_cli.py
git commit -m "feat(engine): DEVBOOST_ROOT env fallback for --root + python -m devboost entrypoint"
```

---

## Task 2: `scripts/build-bundle.sh` (+ local validation)

**Files:** Create `scripts/build-bundle.sh`; (validation only — no committed test)

**Interfaces:** Produces `dist/devboost-<arch>`, `dist/devboost-data.tar.gz`, `dist/checksums.txt`.

- [ ] **Step 1: Create `scripts/build-bundle.sh`**

```bash
#!/usr/bin/env bash
# scripts/build-bundle.sh — build the frozen devboost binary + data tarball + checksums.
# Runnable locally and in CI. Output in dist/.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
DIST="${ROOT}/dist"
rm -rf "${DIST}" build *.spec
mkdir -p "${DIST}"

# Resolve arch label.
case "$(uname -m)" in
  x86_64|amd64) ARCH=x86_64 ;;
  aarch64|arm64) ARCH=aarch64 ;;
  *) echo "build-bundle: unsupported arch $(uname -m)" >&2; exit 1 ;;
esac

# Build the frozen binary in an isolated venv.
python3 -m venv "${DIST}/.buildvenv"
# shellcheck disable=SC1091
. "${DIST}/.buildvenv/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet ./engine pyinstaller
pyinstaller --onefile --name devboost \
  --collect-all typer --collect-all click \
  "${ROOT}/engine/devboost/__main__.py"
mv "${ROOT}/dist/devboost" "${DIST}/devboost-${ARCH}"
deactivate

# Data tarball (noarch): exactly the data the engine reads at runtime.
tar -czf "${DIST}/devboost-data.tar.gz" -C "${ROOT}" modules lib dotfiles profiles.toml

# Checksums.
( cd "${DIST}" && sha256sum "devboost-${ARCH}" devboost-data.tar.gz > checksums.txt )

echo "build-bundle: wrote ${DIST}/devboost-${ARCH}, devboost-data.tar.gz, checksums.txt"
```

Note: PyInstaller writes `dist/devboost` at repo root by default; the script moves it into `dist/devboost-<arch>`. The `rm -rf ... dist` is scoped to `${ROOT}/dist`; PyInstaller's default `dist/` is the same dir.

- [ ] **Step 2: `chmod +x` and run it locally on this Fedora box**

Run: `chmod +x scripts/build-bundle.sh && ./scripts/build-bundle.sh`
Expected: produces `dist/devboost-x86_64`, `dist/devboost-data.tar.gz`, `dist/checksums.txt`. If PyInstaller errors on a missing import, the `--collect-all typer --collect-all click` flags should cover it; if a different module is missing, add `--collect-all <module>` and note it in the report.

- [ ] **Step 3: Validate the binary is standalone (no Python on PATH) + resolves data**

Run:
```bash
mkdir -p /tmp/dbtest && tar -xzf dist/devboost-data.tar.gz -C /tmp/dbtest
env -i HOME="$HOME" PATH=/usr/bin:/bin DEVBOOST_ROOT=/tmp/dbtest dist/devboost-x86_64 list terminal | head -3
env -i HOME="$HOME" PATH=/usr/bin:/bin DEVBOOST_ROOT=/tmp/dbtest dist/devboost-x86_64 --version
```
Expected: `--version` prints; `list terminal` prints module names (zoxide/fzf/…). The `env -i … PATH=/usr/bin:/bin` proves it runs without the venv/python3 on PATH. Record output in the report.

- [ ] **Step 4: Ensure `dist/` is gitignored** — confirm `dist/` and `*.spec` and `build/` are in `.gitignore` (add them if absent; do NOT commit build artifacts).

- [ ] **Step 5: Commit (script only, not artifacts)**

```bash
git add scripts/build-bundle.sh .gitignore
git commit -m "feat(release): build-bundle.sh — PyInstaller onefile binary + data tarball + checksums"
```

---

## Task 3: `scripts/get.sh` + hermetic bats

**Files:** Create `scripts/get.sh`; Test `tests/getsh.bats`

**Interfaces:** `get.sh` defines `gs_arch`, `gs_fetch`, `gs_verify`, `gs_main`; auto-runs `gs_main "$@"` only when executed (not when sourced).

- [ ] **Step 1: Write the failing bats** — create `tests/getsh.bats`:

```bash
load test_helper

setup() {
  GETSH="${BATS_TEST_DIRNAME}/../scripts/get.sh"
  STUB_DIR="$(mktemp -d)"
  export PATH="${STUB_DIR}:${PATH}"
}
teardown() { rm -rf "${STUB_DIR}"; }

@test "get.sh: gs_arch maps arm64 to aarch64" {
  printf '#!/usr/bin/env bash\necho arm64\n' > "${STUB_DIR}/uname"; chmod +x "${STUB_DIR}/uname"
  source "${GETSH}"
  run gs_arch
  [ "$status" -eq 0 ]
  [ "$output" = "aarch64" ]
}

@test "get.sh: gs_arch maps x86_64" {
  printf '#!/usr/bin/env bash\necho x86_64\n' > "${STUB_DIR}/uname"; chmod +x "${STUB_DIR}/uname"
  source "${GETSH}"
  run gs_arch
  [ "$output" = "x86_64" ]
}

@test "get.sh: gs_arch fails on unknown arch" {
  printf '#!/usr/bin/env bash\necho mips\n' > "${STUB_DIR}/uname"; chmod +x "${STUB_DIR}/uname"
  source "${GETSH}"
  run gs_arch
  [ "$status" -ne 0 ]
}

@test "get.sh: gs_verify fails on checksum mismatch" {
  source "${GETSH}"
  d="$(mktemp -d)"; echo "hello" > "${d}/file"
  echo "0000000000000000000000000000000000000000000000000000000000000000  file" > "${d}/checksums.txt"
  run gs_verify "${d}" file
  [ "$status" -ne 0 ]
  rm -rf "${d}"
}

@test "get.sh: gs_verify passes on matching checksum" {
  source "${GETSH}"
  d="$(mktemp -d)"; echo "hello" > "${d}/file"
  ( cd "${d}" && sha256sum file > checksums.txt )
  run gs_verify "${d}" file
  [ "$status" -eq 0 ]
  rm -rf "${d}"
}

@test "get.sh: sourcing does not auto-run gs_main" {
  # if gs_main ran on source, it would try to download and fail loudly
  run bash -c "source '${GETSH}'; echo SOURCED_OK"
  [ "$status" -eq 0 ]
  [[ "$output" == *"SOURCED_OK"* ]]
}
```

- [ ] **Step 2: Run — verify fail**

Run: `bats tests/getsh.bats`
Expected: FAIL — `scripts/get.sh` missing.

- [ ] **Step 3: Create `scripts/get.sh`**

```bash
#!/usr/bin/env bash
# scripts/get.sh — dev-boost public bootstrap.
# Usage: curl -fsSL https://raw.githubusercontent.com/adams100111/dev-boost/main/scripts/get.sh | bash -s -- terminal
# Downloads the arch-matched frozen devboost binary + data tarball from the latest
# GitHub Release, verifies SHA256, installs to ~/.local/share/devboost, and runs install.
set -Eeuo pipefail

GS_REPO="adams100111/dev-boost"
GS_BASE="https://github.com/${GS_REPO}/releases/latest/download"
GS_PREFIX="${HOME}/.local/share/devboost"

gs_err() { echo "get.sh: $*" >&2; }

gs_arch() {
  case "$(uname -m)" in
    x86_64|amd64) echo x86_64 ;;
    aarch64|arm64) echo aarch64 ;;
    *) gs_err "unsupported architecture: $(uname -m) (x86_64/aarch64 only)"; return 1 ;;
  esac
}

# gs_fetch URL OUTFILE — download via curl or wget.
gs_fetch() {
  local url="$1" out="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" -o "$out"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$out" "$url"
  else
    gs_err "need curl or wget"; return 1
  fi
}

gs_sha256() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@";
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$@";
  else gs_err "need sha256sum or shasum"; return 1; fi
}

# gs_verify DIR FILE — verify FILE in DIR against DIR/checksums.txt.
gs_verify() {
  local dir="$1" file="$2"
  ( cd "$dir" && grep -E "  ${file}\$" checksums.txt | gs_sha256 -c - ) >/dev/null 2>&1
}

gs_main() {
  local arch tmp bin profiles
  arch="$(gs_arch)" || return 1
  command -v tar >/dev/null 2>&1 || { gs_err "need tar"; return 1; }
  profiles=("$@"); [ "${#profiles[@]}" -eq 0 ] && profiles=(terminal)

  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN

  gs_err "downloading devboost-${arch} + data from the latest release…"
  gs_fetch "${GS_BASE}/checksums.txt" "${tmp}/checksums.txt" \
    || { gs_err "no published release yet (or network error). See README for releasing."; return 1; }
  gs_fetch "${GS_BASE}/devboost-${arch}" "${tmp}/devboost-${arch}" || return 1
  gs_fetch "${GS_BASE}/devboost-data.tar.gz" "${tmp}/devboost-data.tar.gz" || return 1

  gs_verify "$tmp" "devboost-${arch}"     || { gs_err "checksum mismatch: devboost-${arch}"; return 1; }
  gs_verify "$tmp" "devboost-data.tar.gz" || { gs_err "checksum mismatch: data tarball"; return 1; }

  mkdir -p "${GS_PREFIX}/bin"
  tar -xzf "${tmp}/devboost-data.tar.gz" -C "${GS_PREFIX}"
  install -m 0755 "${tmp}/devboost-${arch}" "${GS_PREFIX}/bin/devboost"

  gs_err "installed to ${GS_PREFIX}; running: devboost install ${profiles[*]}"
  export DEVBOOST_ROOT="${GS_PREFIX}"
  exec "${GS_PREFIX}/bin/devboost" install "${profiles[@]}"
}

# Run only when executed (incl. via `curl | bash`), not when sourced for tests.
if ! (return 0 2>/dev/null); then
  gs_main "$@"
fi
```

- [ ] **Step 4: Run — verify pass**

Run: `chmod +x scripts/get.sh && bats tests/getsh.bats`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/get.sh tests/getsh.bats
git commit -m "feat(release): get.sh public bootstrap (arch-detect, download, SHA256-verify, install, exec)"
```

---

## Task 4: `.github/workflows/release.yml`

**Files:** Create `.github/workflows/release.yml`

**Interfaces:** On a `v*` tag, publishes the 4 Release assets so `/latest/download/` resolves.

- [ ] **Step 1: Create `.github/workflows/release.yml`**

```yaml
name: release
on:
  push:
    tags: ['v*']

permissions:
  contents: write

jobs:
  binary:
    strategy:
      matrix:
        include:
          - runner: ubuntu-22.04
            arch: x86_64
          - runner: ubuntu-24.04-arm
            arch: aarch64
    runs-on: ${{ matrix.runner }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Build frozen binary
        run: bash scripts/build-bundle.sh
      - uses: actions/upload-artifact@v4
        with:
          name: devboost-${{ matrix.arch }}
          path: dist/devboost-${{ matrix.arch }}

  data:
    runs-on: ubuntu-22.04
    steps:
      - uses: actions/checkout@v4
      - name: Package data tarball
        run: tar -czf devboost-data.tar.gz modules lib dotfiles profiles.toml
      - uses: actions/upload-artifact@v4
        with:
          name: devboost-data
          path: devboost-data.tar.gz

  release:
    needs: [binary, data]
    runs-on: ubuntu-22.04
    steps:
      - uses: actions/download-artifact@v4
        with:
          path: artifacts
      - name: Collect assets + checksums
        run: |
          mkdir -p out
          cp artifacts/devboost-x86_64/devboost-x86_64 out/
          cp artifacts/devboost-aarch64/devboost-aarch64 out/
          cp artifacts/devboost-data/devboost-data.tar.gz out/
          ( cd out && sha256sum devboost-x86_64 devboost-aarch64 devboost-data.tar.gz > checksums.txt )
      - name: Publish release
        uses: softprops/action-gh-release@v2
        with:
          files: |
            out/devboost-x86_64
            out/devboost-aarch64
            out/devboost-data.tar.gz
            out/checksums.txt
```

Note: `build-bundle.sh` also builds the data tarball + checksums locally, but in CI the `data`/`release` jobs build the data tarball once and the combined checksums across both arches — that's why `release` regenerates `checksums.txt` over all three assets (the per-runner `checksums.txt` from build-bundle is not uploaded).

- [ ] **Step 2: Validate the YAML parses**

Run: `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/release.yml')); print('yaml ok')"`
Expected: `yaml ok`. (The workflow itself only runs on GitHub — note in the report that end-to-end validation happens on the first `v*` tag push.)

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "ci(release): build x86_64+aarch64 binaries + data tarball, publish on v* tag"
```

---

## Task 5: Docs — real install one-liner

**Files:** Modify `README.md`, `docs/architecture.md`

**Interfaces:** Prose only; the profiles drift-gate stays green.

- [ ] **Step 1: README — add an "Install (any OS)" section** near the top / Quick start:

```markdown
## Install (any OS)

```bash
curl -fsSL https://raw.githubusercontent.com/adams100111/dev-boost/main/scripts/get.sh | bash -s -- terminal
```

Detects your architecture, downloads the matching frozen `devboost` binary + config
data from the latest GitHub Release, verifies SHA256, and runs `devboost install
terminal` — no Python, no clone. Add `devtools` for language runtimes/frameworks, or
`--dry-run` to preview:

```bash
curl -fsSL https://raw.githubusercontent.com/adams100111/dev-boost/main/scripts/get.sh | bash -s -- terminal devtools
```

Releases are published automatically on each `v*` tag; `/latest/` always tracks the
newest. (Requires this repo to be public.)
```

- [ ] **Step 2: README — replace the prior "planned" bootstrap note** (added in the config-enrichment docs) so it points at the section above instead of saying a bootstrap is "planned".

- [ ] **Step 3: docs/architecture.md — mark delivery realized.** In the dual-engine section, change the frozen-binary description from "sanctioned, not yet shipped" to note it is built by `.github/workflows/release.yml` (PyInstaller onefile) and delivered by `scripts/get.sh`.

- [ ] **Step 4: Verify both suites still green**

Run: `bats tests/ 2>&1 | tail -2` then `cd engine && . .venv/bin/activate && pytest -q 2>&1 | tail -1 && mypy 2>&1 | tail -1`
Expected: bats all green (now includes `getsh.bats`); engine pytest green incl. the new env-fallback test; mypy clean.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/architecture.md
git commit -m "docs: real curl|bash install one-liner + frozen-binary delivery realized"
```

---

## Self-Review

**Spec coverage:**
- §3.1 engine DEVBOOST_ROOT fallback + __main__.py → Task 1. ✅
- §3.2 build-bundle.sh + local standalone validation → Task 2. ✅
- §3.3 release.yml (matrix, ubuntu-22.04 glibc, split assets, checksums) → Task 4. ✅
- §3.4 get.sh (arch-detect, download, SHA256-verify, install, exec, DEVBOOST_ROOT) → Task 3. ✅
- §3.5 __main__.py → Task 1. ✅
- §4 tests: get.sh bats (arch map, checksum-mismatch-abort, no-auto-run-on-source), engine env pytest, local standalone smoke → Tasks 1–3. ✅
- §5 docs → Task 5. ✅
- §2.5 glibc base ubuntu-22.04 both arches → Task 4 matrix. ✅
- §8 no-release friendly error → get.sh `gs_main` checksums fetch failure message (Task 3). ✅

**Placeholder scan:** The PyInstaller "add `--collect-all <module>` if an import is missing" (Task 2 Step 2) is a concrete contingency with the exact flag, not a TBD. The CI "validated on push" caveat is stated, not deferred work.

**Type/name consistency:** `gs_arch`/`gs_fetch`/`gs_verify`/`gs_main` used identically in get.sh and `tests/getsh.bats`. Asset names (`devboost-<arch>`, `devboost-data.tar.gz`, `checksums.txt`) identical across build-bundle.sh, get.sh, release.yml. `DEVBOOST_ROOT` consistent (engine reads it; get.sh exports it; build-bundle smoke sets it). `~/.local/share/devboost` consistent (get.sh install + DEVBOOST_ROOT).

**Ordering:** Task 1 (engine, enables the binary to find data) → Task 2 (build + prove standalone) → Task 3 (get.sh consumes the asset names) → Task 4 (CI produces those assets) → Task 5 (docs). Each ends testable in-session except the CI workflow (parses + reviewed as code; runs on tag push).
