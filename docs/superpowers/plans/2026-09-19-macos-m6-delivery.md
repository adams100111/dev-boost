# macOS M6 — Delivery Implementation Plan (plan-lite)

> **For agentic workers:** execute with `sdd-lanes` (parallel lanes in git worktrees, one
> implementer per lane). Format: `~/.claude/skills/sdd-lanes/plan-lite.md`. Tests first, from
> the **Tests** list of each task; no task in this plan ships full implementation code.

**Goal:** a fresh Apple Silicon Mac (macOS 27 Golden Gate primary, 26 Tahoe supported) becomes a
dev-boost workstation with one command,
`curl -fsSL https://raw.githubusercontent.com/adams100111/dev-boost/main/scripts/get.sh | bash -s -- macos`.
That command downloads a frozen `devboost-darwin-arm64` binary from a GitHub Release built by
CI. `devboost self-update` picks the asset by (os, arch). CI runs the full gate on macOS, and a
tart VM script rehearses the whole flow on 27 and 26. The M6 carry-over items close in this
milestone: the Linux vm-smoke list, root-owned files under `DemotingExecutor`, the SIGKILL
temp-key note, and M5-chip runner/image parity.

**Architecture:** delivery only; the engine gains no new concepts. Six surfaces change, no two
lanes share a file: (1) `build-bundle.sh` names the Darwin asset; (2) `get.sh` gains a Darwin
branch (arch/version gates, Homebrew bootstrap, no Ventoy archive, `/dev/tty` exec); (3)
`core/selfupdate.py` resolves a `ReleaseAsset` from `(system, machine)` and skips the archive on
Darwin; (4) the workflows gain macOS jobs; (5) new `vm-test-macos.sh` + `smoke-assert.sh` drive
tart VMs and Linux containers; (6) `accounts/bootstrap.py` hands root-owned files it created in
the user's HOME back to the user. Docs close the milestone; a `chore(release)` PR tags
**v0.2.0**, the first release with a Mac binary.

**Tech Stack:** Python ≥ 3.12, Typer, pytest (+ pytest-xdist), mypy `--strict`, ruff, `uv`,
PyInstaller 6.x (onefile), bash (`get.sh`, dev scripts), GitHub Actions, tart
(`cirruslabs/cli/tart`), shellcheck, actionlint.

**Spec:** `docs/superpowers/specs/2026-09-18-macos-support-design.md`, covering §0 (version
gates), §7 Delivery, the §9 CI and E2E bullets, §10 (the M6 docs rows) and the §11 M6 row.
Carry-over: `.superpowers/carryover/carryover.md`, the "M6" section plus every item tagged M6
elsewhere. The orchestration sketch is `.superpowers/research/speed/orchestration.md` §7
(D1–D7). This plan refines D1–D7 into T1–T13.

## Global Constraints

- **Commits:** Conventional Commits (`feat(delivery): …`, `ci: …`, `docs: …`,
  `chore(release): …`). **No `Co-Authored-By` trailer and no Claude/Anthropic/AI attribution** in
  commits or PR bodies.
- **Style:** lines ≤ 100 in Python, shell and YAML (ruff `line-length = 100`). `uv run mypy`
  (strict) and `uv run ruff check` must be clean. Shell scripts must be `shellcheck` clean
  (`-x`, default severity).
- **Hermetic tests:** no network, no real brew/tart/sudo/curl/codesign. Shell scripts are
  tested by running `bash` with a **stub directory first on `PATH`** (fake `uname`, `sw_vers`,
  `sysctl`, `curl`, `sudo`, `xcode-select`, `tart`, `codesign`) and `HOME=tmp_path`. Tests never
  read the host OS. A test that needs a real binary (`shellcheck`, `actionlint`) **skips**
  when it is absent.
- **Linux does not change.** The Linux asset names (`devboost-x86_64`, `devboost-aarch64`, their
  `.tar.gz`), the Linux `get.sh` flow and the Linux self-update flow stay byte-for-byte the same
  in behaviour. Each lane has a "Linux unchanged" test.
- **Free for commercial use only:** PyInstaller (GPL-2.0 with a bootloader exception, so the
  output may ship under any licence), tart (royalty-free on personal workstations; FSL-1.1-ALv2
  repo licence, see Verified facts), GitHub-hosted standard runners (free on this public repo),
  actionlint (MIT), shellcheck (GPL-3.0, a tool used unmodified). No Developer ID and no
  notarization (spec: out of scope).
- **No destructive git.** Subagents never run `reset --hard`, `checkout --`/`restore`, `clean`,
  `stash drop`, `branch -D` or a force-push, and never push or open PRs. The controller alone
  merges, pushes and runs `gh pr merge` (user-authorized for the macOS effort).
- Commands run from `engine/` unless a line says otherwise.

## Verified facts (checked 2026-09-19)

| # | Fact | Source |
|---|---|---|
| V1 | Arm64 macOS runner labels: `macos-15` / `macos-15-xlarge` (macOS 15 arm64, GA); `macos-26` / `macos-latest` / `macos-26-xlarge` (macOS 26 arm64, GA); `xcode-27` / `xcode-27-xlarge` (the macOS 27 image, arm64, **Preview**). `macos-latest` currently resolves to macOS 26 arm64. `macos-14` is deprecated. The `*-large` / `*-intel` labels are x64. | <https://github.com/actions/runner-images> (README image table) |
| V2 | Standard GitHub-hosted runners are **free and unlimited on public repositories**. Larger runners (`-xlarge`/`-large`) are billed even on public repos, so this plan uses only the standard labels. `adams100111/dev-boost` is public (`gh repo view` → `PUBLIC`). | <https://docs.github.com/en/billing/concepts/product-billing/github-actions>, <https://docs.github.com/en/actions/reference/runners/github-hosted-runners> |
| V3 | PyInstaller supports single-arch arm64, x86_64 and universal2 on macOS. It targets the running arch unless `--target-arch` is given. **By default it ad-hoc (re)signs all collected binaries and the executable**; `--codesign-identity` substitutes a real identity. | ctx7 `/websites/pyinstaller_en_stable`: feature-notes "macOS binary code signing", "macOS multi-arch support", pyi-makespec `--target-arch` |
| V4 | PyInstaller forward compatibility: collected binaries may not run on *older* macOS, so "the only way to ensure that your frozen application supports an older version of the OS is to freeze it on the oldest version … you wish to support". Building on `macos-15` therefore covers 15, 26 and 27. | ctx7 `/websites/pyinstaller_en_stable`: usage.html "Making macOS apps Forward-Compatible" |
| V5 | `curl` (and scp) do **not** set `com.apple.quarantine`, so Gatekeeper never assesses a binary fetched by `get.sh`. A browser download *is* quarantined; the fix is `xattr -d com.apple.quarantine <file>`. An arm64 binary must still carry a signature (ad-hoc is enough), which V3 provides. | Apple Community thread 256200611 (Apple's stated behaviour); homebrew-cask #22388; PyInstaller V3 |
| V6 | tart installs with `brew install cirruslabs/cli/tart` (a tap, not homebrew-core). Usage: `tart clone <image> <name>`, `tart run <name>` (`--no-graphics` flag exists), `ssh admin@$(tart ip <name>)`. Credentials are **admin/admin**. `tart exec [-i] [-t] <vm> <cmd…>` runs a command through the Tart Guest Agent, which every **non-vanilla** Cirrus image ships. | <https://tart.run/quick-start/>; ctx7 `/openai/tart` (Run.swift, Exec.swift, quick-start.md) |
| V7 | Image names: `ghcr.io/cirruslabs/macos-{golden-gate,tahoe,sequoia,sonoma}-{vanilla,base}`. **macOS 27 = `ghcr.io/cirruslabs/macos-golden-gate-base:latest`** (guest macOS 27.0, build 26A5416b at the time of issue #376). **macOS 26 = `ghcr.io/cirruslabs/macos-tahoe-base:latest`**. Known 27 image issue: Screen Sharing is enabled via `launchctl` only and has no TCC rights (#376), so use `tart run` with graphics, not VNC, for any GUI step. | <https://github.com/cirruslabs/macos-image-templates> README; issue #376 |
| V8 | tart licensing: "Usage on personal computers including personal workstations is royalty-free". The paid tiers only apply to organisations above 100 host CPU cores. The repo (now `openai/tart`) is FSL-1.1-ALv2, which forbids only *competing* commercial offerings. Internal testing on this Mac is allowed. | <https://tart.run/licensing/>; `openai/tart` LICENSE |
| V9 | Tart's published Linux images are `ubuntu:24.04`/`22.04` (arm64 + amd64), `debian:trixie` and `fedora:42`. There is **no Fedora 44 and no Arch**, so the Linux vm-smoke does not use tart (see D6). | `cirruslabs/linux-image-templates` `.github/workflows/images.yml` |
| V10 | The Homebrew installer with `NONINTERACTIVE=1` runs `sudo -n`, so it fails with "Failed during: /usr/bin/sudo -n …" unless sudo is already cached. It installs the CLT headlessly (the `/tmp/.com.apple.dt.CommandLineTools.installondemand.in-progress` + `softwareupdate -i <label>` trick), aborts "Don't run this as root!", and supports macOS 15.0 ≤ v < 28.0 (it warns but continues outside that range). | <https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh> |
| V11 | This Mac: Mac17,2, **Apple M5**, macOS 27.0 (26A428), arm64. It has `/sbin/sha256sum`, `/usr/bin/shasum`, `codesign`, `shellcheck`, `uv`. `tart` and `actionlint` are **not installed** (actionlint 1.7.12 is available in homebrew-core). | local `sw_vers`, `sysctl`, `command -v` |

## Decisions

| # | Decision | Why |
|---|---|---|
| D1 | Asset key `darwin-arm64` → `devboost-darwin-arm64`. **Darwin has no `.tar.gz`**: the Ventoy builder is Linux-only (`installer` is in `LINUX_ONLY`). `checksums.txt` gains one line. | Spec §7. Old Linux clients keep resolving their own names. |
| D2 | build-bundle **does not re-sign**. PyInstaller already ad-hoc signs (V3). The script only checks `codesign --verify --strict` and fails the build if that check fails. | Re-signing a onefile after the build cannot reach its embedded binaries (V3). |
| D3 | `get.sh` on Darwin: in a Rosetta-translated shell (`uname -m` = `x86_64`, `sysctl -n hw.optional.arm64` = `1`) the host counts as Apple Silicon. Only real Intel is refused. | `curl … \| bash` from an x86_64 terminal on an M-series Mac must not be mistaken for Intel. |
| D4 | `get.sh` bootstraps **only Homebrew** (which installs the CLT, V10). When brew is present and the CLT is missing, it leaves the CLT to the engine's `xcode-clt` module (M3). Before the Homebrew installer runs, it calls `sudo -v` once with its input read from the tty. | V10: `NONINTERACTIVE=1` needs cached sudo. One prompt, then unattended. |
| D5 | The `</dev/tty` exec and the Homebrew bootstrap are **Darwin-only**. On Linux the flow stays identical (Global Constraints). Linux `/dev/tty` becomes a follow-up in the carry-over list. | Keeps M6 from touching the Linux bootstrap. |
| D6 | Linux vm-smoke (carry-over): **containers on GitHub runners** (`fedora:44`, `archlinux:latest`) plus the **`ubuntu-24.04` runner host itself** for the snap leg (real systemd + snapd). This lives in `vm-smoke.yml` (`workflow_dispatch` + nightly, non-blocking). A libvirt run on a Linux host (`scripts/vm-test.sh`) stays the documented manual fallback. | There is no libvirt on the Mac (M3 Step 11), tart has no Fedora 44 or Arch (V9), and a snap needs systemd, which a container lacks. |
| D7 | macOS CI: `checks` on `ubuntu-22.04` + `macos-15` (both blocking) and `xcode-27` (`continue-on-error`, Preview). A `binary-compat` job runs the **macos-15-built** binary on `macos-26` (blocking) and `xcode-27` (non-blocking). | Spec §9, V1, V4. This covers the carry-over "runner parity (macos-latest arm64)" without paid runners. |
| D8 | `vm-test-macos.sh` drives the guest with **`tart exec`** (V6). There is no sshpass or key setup. `ssh admin@$(tart ip)` is printed only as the interactive hint. A snapshot is a `tart clone` of the stopped VM named `<vm>--<snap>`. | `tart exec` needs no password tooling. tart has no native snapshots. |
| D9 | For pre-release rehearsal, `get.sh` honours **`DEVBOOST_RELEASE_BASE`** (default `https://github.com/adams100111/dev-boost/releases/latest/download`). `file://` URLs work because curl handles them. The tart script shares `dist/` into the VM with `tart run --dir=dist:<path>`. | Lets T11 prove a fresh-Mac `curl \| bash` **before** tagging, then T13 repeats it against the real release. |
| D10 | Root-owned files: `bootstrap_user` hands back every root-owned path created under the target HOME since the run started (`lchown` to the user's uid/gid). It does this in a `finally`, after the run, and never follows symlinks. The in-process writers stay untouched. | The carry-over asks for "chown or run as the user". There are 25+ in-process writers (grep), so one post-pass in the only root path (`accounts`, Linux-only via `LINUX_ONLY`) is smaller and complete. The root guard in `cli/host.py` already refuses root on macOS. |
| D11 | `bash-config` on an unknown Linux family: `families = ()` plus `provided_by = ("macos",)`. An unknown distro (family = its own id) keeps bash-config. macOS reports `provided-by-macos` (zsh-config) where today it silently drops it. | Carry-over (M2 final review). A one-line data change; the contract test already accepts `provided_by`. |
| D12 | Release version **v0.2.0**: the first Mac binary is a new platform. The PR `chore(release): v0.2.0 — macOS support (M1–M6)` follows the v0.1.80 pattern (CHANGELOG roll, `pyproject.toml`, `__init__.py`, `uv.lock`). | The user can override it at T13; one line changes. |
| D13 | Version gates in get.sh use `sw_vers -productVersion`, major part: `<15` refuse; `15` warn; `26`/`27` ok; `≥28` warn "newer than tested". | Spec §0 + V10 (Homebrew's own range stops at < 28). |

## File Structure

| Path | Change | Lane |
|---|---|---|
| `scripts/build-bundle.sh` | Modify: `bb_arch`, `bb_sha256`, source guard, Darwin branch | A |
| `scripts/release.sh` | Modify: `sed -nE` version parse, Darwin arch, sha fallback | A |
| `engine/tests/scripts/test_build_bundle_sh.py` | Create | A |
| `engine/tests/scripts/test_release_sh.py` | Create | A |
| `scripts/get.sh` | Modify: Darwin branch, `DEVBOOST_RELEASE_BASE`, `GS_BREW_PREFIX`, `GS_TTY` | B |
| `engine/tests/scripts/test_get_sh.py` | Create | B |
| `engine/src/devboost/core/selfupdate.py` | Modify: `ReleaseAsset`, `release_asset`, `update_frozen` | C |
| `engine/tests/core/test_selfupdate.py` | Modify: new tests; existing tests keep passing | C |
| `.github/workflows/ci.yml` | Modify: macOS checks + frozen-smoke matrix | D |
| `.github/workflows/release.yml` | Modify: checks matrix, darwin binary, `binary-compat`, combine | D |
| `engine/tests/scripts/test_workflows.py` | Create | D |
| `scripts/vm-test-macos.sh` | Create | E |
| `scripts/smoke-assert.sh` | Create | E |
| `.github/workflows/vm-smoke.yml` | Modify: add `linux-smoke` job (kickstart job untouched) | E |
| `engine/tests/scripts/test_vm_test_macos.py`, `test_smoke_assert.py` | Create | E |
| `engine/src/devboost/accounts/bootstrap.py` | Modify: `reclaim_home` + call in `finally` | F |
| `engine/tests/accounts/test_bootstrap_reclaim.py` | Create | F |
| `engine/src/devboost/modules/shell.py` | Modify: `BashConfig.families`/`provided_by` only | F |
| `engine/tests/core/test_unknown_distro.py` | Create | F |
| `README.md`, `CLAUDE.md`, `CHANGELOG.md`, `docs/macos.md`, `docs/vm-testing.md`, `docs/credentials.md`, `docs/maintenance.md`, spec §9 line | Modify | G |
| `engine/tests/scripts/__init__.py`, `engine/tests/scripts/conftest.py` (stub-PATH fixture), `engine/pyproject.toml` + `engine/uv.lock` (pytest-xdist if absent) | Create/Modify | T0 (controller) |
| `CHANGELOG.md` roll, `engine/pyproject.toml`, `engine/src/devboost/__init__.py`, `engine/uv.lock` | Modify (release) | T13 (controller) |

## Lanes

| Wave | Lane | Tasks | Owns files | Consumes (from) |
|---|---|---|---|---|
| 0 | ctl | T0 pre-flight | `tests/scripts/{__init__,conftest}.py`, pyproject/uv.lock | M3–M5 merged on `main` |
| 1 | A build | T1, T2 | build-bundle.sh, release.sh, their tests | T0 fixture |
| 1 | B bootstrap | T3 | get.sh, test_get_sh.py | T0 fixture |
| 1 | C selfupdate | T4 | selfupdate.py, test_selfupdate.py | — |
| 1 | D CI | T5 | ci.yml, release.yml, test_workflows.py | asset names (D1) only, not code |
| 1 | E VM | T6, T7 | vm-test-macos.sh, smoke-assert.sh, vm-smoke.yml, their tests | T0 fixture; `DEVBOOST_RELEASE_BASE` name (D9) |
| 1 | F root/data | T8, T9 | accounts/bootstrap.py, modules/shell.py, their tests | — |
| 2 | G docs | T10 | the docs row above | names from T1–T9 |
| 3 | ctl + user | T11 CI iteration, T12 rehearsal (tart + Linux smoke) | none (fix-ups go back to the owning lane) | merged W1+W2 |
| 4 | ctl + user | T13 release + acceptance | release files | green T11/T12 |

Merge order within Wave 1: C, F, A, B, E, D. Code before workflows, so the first CI run on the
branch sees every script.

---

### Task 0: Pre-flight   (Lane ctl, risk: normal)

**Files:** Create `engine/tests/scripts/__init__.py` (empty) and `engine/tests/scripts/conftest.py`.
If `pytest-xdist` is absent, modify `engine/pyproject.toml` (dev group) and `engine/uv.lock`.
**Interfaces:** Produces the fixture
`stub_path(tmp_path) -> StubPath`, where `StubPath.add(name: str, script: str) -> Path` writes
an executable `#!/bin/sh` stub and `StubPath.env(**extra: str) -> dict[str, str]` returns
`PATH=<stubdir>:/usr/bin:/bin`, `HOME=<tmp_path/home>` and the extras. It also produces the
helper `run_bash(script: Path, *args: str, env: dict[str, str], source_fn: str | None = None)
-> subprocess.CompletedProcess[str]`: with `source_fn` it runs `bash -c 'source <script>;
<source_fn> "$@"'`.
**Exact values:** `pytest-xdist>=3.6`; milestone gate `uv run pytest -n 4`.
**Behaviour:**
- Base branch `feat/macos-m6-delivery` from `main` **after M3, M4 and M5 are merged**. If they
  are not, stop and report.
- Check that each "M3:/M5:" carry-over item filed under the M6 heading actually landed. That
  covers: nvm/sdkman init-block migration on macOS; Time Machine exclusion using the resolved
  Colima dir; the Linux chezmoi assertion that `.config/aerospace` is absent; lazy sudo; the
  OS-aware `--update` filter; `record_rc_digests` warn-not-fail. Anything missing is added to the
  final fix wave with its owning file, and the lane table is updated.
- User at the Mac, in the background from the start: `brew install cirruslabs/cli/tart
  actionlint`, then `tart pull ghcr.io/cirruslabs/macos-golden-gate-base:latest` and
  `tart pull ghcr.io/cirruslabs/macos-tahoe-base:latest` (tens of GB each).
**Tests (write first):** `test_stub_path_shadows_uname` — add a `uname` stub that prints
`Darwin`, run `uname` through `run_bash` → stdout `Darwin`.
**Task gate:** `uv run pytest tests/scripts -q && uv run pytest -n 4 -q` (xdist is usable).

### Task 1: build-bundle names the Darwin asset   (Lane A, risk: high)

**Files:** Modify `scripts/build-bundle.sh`; Test `engine/tests/scripts/test_build_bundle_sh.py`.
**Interfaces:** Produces the shell functions `bb_arch` (prints the asset key) and `bb_sha256
<files…>` (`sha256sum`, else `shasum -a 256`). Guard main with
`if ! (return 0 2>/dev/null); then bb_main "$@"; fi`, the same idiom as get.sh.
**Exact values:** `uname -s`/`uname -m` → key: `Linux x86_64|amd64` → `x86_64`;
`Linux aarch64|arm64` → `aarch64`; `Darwin arm64` → `darwin-arm64`; `Darwin x86_64` → exit 1
with `build-bundle: Intel Macs are not supported (Apple Silicon only)`; anything else →
`build-bundle: unsupported platform <s>/<m>`. Darwin checksums file:
`dist/checksums-darwin-arm64.txt` with one line. Signature check:
`codesign --verify --strict "${DIST}/devboost-darwin-arm64"`. Smoke on Darwin:
`--version` and then `list macos` (both exit 0).
**Behaviour:**
- Linux output is unchanged: the binary, the `.tar.gz` Ventoy archive, and a checksums file
  with two lines.
- On Darwin: no Ventoy staging, no tar; the checksums file lists only the binary.
- It never passes `--codesign-identity` and never re-signs (D2). A failed verify fails the build.
- `--add-data` still bundles `ventoy/` on Darwin (it is harmless and keeps one bundle layout).
  Record this in a comment.
- `rm -rf` targets stay the same.
**Tests (write first):**
- `test_bb_arch_linux_x86_64`: stub `uname` (`-s`→Linux, `-m`→x86_64), source + call
  `bb_arch` → `x86_64`.
- `test_bb_arch_linux_aarch64_and_arm64`: `aarch64` and `arm64` → `aarch64`.
- `test_bb_arch_darwin_arm64`: `Darwin`/`arm64` → `darwin-arm64`.
- `test_bb_arch_intel_mac_refused`: `Darwin`/`x86_64` → rc 1 and the exact message on stderr.
- `test_bb_arch_unknown_platform`: `Linux`/`riscv64` → rc 1, `unsupported platform`.
- `test_bb_sha256_falls_back_to_shasum`: PATH has only a `shasum` stub (logs argv) → the stub is
  called with `-a 256 <file>`.
- `test_script_is_shellcheck_clean`: skip if `shellcheck` is missing; `shellcheck -x` → rc 0.
**Implementation notes:** keep `set -Eeuo pipefail` at the top. Move the body into `bb_main`
so sourcing it for tests has no side effects. `uname -s` must be read once (`BB_OS`).
**Task gate:** `uv run pytest tests/scripts/test_build_bundle_sh.py -q`

### Task 2: release.sh portable to macOS   (Lane A, risk: normal)

**Files:** Modify `scripts/release.sh`; Test `engine/tests/scripts/test_release_sh.py`.
**Interfaces:** Consumes `bb_arch`, using the same mapping. release.sh keeps its own copy, named
`rl_arch`: it is a standalone script and does not source build-bundle.sh. Produces
`rl_version <file> <regex-name>` via `sed -nE`.
**Exact values:** `sed -nE 's/^version = "([^"]+)".*/\1/p' engine/pyproject.toml | head -n1`;
`sed -nE 's/^__version__ = "([^"]+)".*/\1/p' engine/src/devboost/__init__.py | head -n1`.
Darwin upload list: `dist/devboost-darwin-arm64` only. Checksums regeneration:
`sha256sum devboost-*` with a `shasum -a 256` fallback.
**Behaviour:**
- `--dry-run` on a Darwin stub prints `+ gh release upload v<ver> dist/devboost-darwin-arm64
  --clobber` and no `.tar.gz`.
- A version mismatch still exits 1 with the existing message.
- `grep -oP` no longer appears anywhere in `scripts/` (BSD grep has no `-P`).
**Tests (write first):**
- `test_release_version_parse_without_grep_P`: fixture repo tree (tmp) with pyproject 1.2.3
  and `__init__` 1.2.3; stub `gh` (auth ok, `release view` rc 1), `uname` Darwin/arm64,
  `bash scripts/release.sh --dry-run` from a copy of the script → stdout contains
  `release: v1.2.3 (host arch: darwin-arm64)`.
- `test_release_dry_run_darwin_uploads_binary_only`: the same setup → no `devboost-darwin-arm64.tar.gz`
  in stdout.
- `test_release_version_mismatch_exits_1`: 1.2.3 vs 1.2.4 → rc 1, `version mismatch`.
- `test_no_grep_P_in_scripts`: reading `scripts/*.sh` → no `grep` line with `-oP`/`-P`.
**Task gate:** `uv run pytest tests/scripts/test_release_sh.py -q`

### Task 3: get.sh on Darwin   (Lane B, risk: high)

**Files:** Modify `scripts/get.sh`; Test `engine/tests/scripts/test_get_sh.py`.
**Interfaces:** Produces the functions `gs_os` (`linux`|`darwin`), `gs_arch` (asset key),
`gs_macos_check_version`, `gs_macos_prereqs` and `gs_main`. Env inputs:
`DEVBOOST_RELEASE_BASE` (D9), `GS_BREW_PREFIX` (default `/opt/homebrew`, for tests only),
`GS_TTY` (default `/dev/tty`, for tests only). Consumes the asset names from D1.
**Exact values:**
- Default base `https://github.com/adams100111/dev-boost/releases/latest/download`.
- Homebrew installer: `https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh`, run
  as `NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL <url>)"` after `sudo -v <"$GS_TTY"`.
- Shellenv: `eval "$("${GS_BREW_PREFIX}/bin/brew" shellenv)"`.
- Rosetta probe: `sysctl -n hw.optional.arm64` (prints `1` on Apple Silicon).
- Messages (stderr, each prefixed `get.sh: `):
  - `Intel Macs are not supported — dev-boost needs Apple Silicon (arm64)`
  - `macOS <v> is not supported — dev-boost needs macOS 15 or newer (27 recommended)`
  - `macOS 15 is best-effort (untested); 27 and 26 are supported`
  - `macOS <v> is newer than tested (27) — continuing`
  - `don't run this as root on macOS — Homebrew refuses root. Run it as your user.`
  - `the USB builder is Linux-only`
  - PATH hint: `echo 'export PATH="<bindir>:$PATH"' >> ~/.zshrc` followed by
    `(dev-boost's shell config adds it for you once installed)`.
**Behaviour:**
- On Linux the function flow, URLs, files and messages stay as they are today. The only
  addition is that `DEVBOOST_RELEASE_BASE` overrides the base on every OS.
- On Darwin, the order is: root refusal (`id -u` = 0) → arch (D3) → version gate (D13) →
  `gs_macos_prereqs` → fetch `checksums.txt` + `devboost-darwin-arm64` → verify → install to
  `~/.local/share/devboost/bin/devboost` → link `~/.local/bin/devboost`.
- `gs_macos_prereqs` does nothing when `${GS_BREW_PREFIX}/bin/brew` exists. It only runs
  `shellenv` in that case.
- On Darwin get.sh never fetches or installs any `.tar.gz` and never runs `sudo ln` into
  `/usr/local/bin`.
- On Darwin, profile `usb` → rc 1 with the Linux-only message; `none` → binary only, rc 0.
- The Darwin exec is `exec … install <profiles> <"$GS_TTY"` when stdin is not a tty **and**
  `( : <"$GS_TTY" ) 2>/dev/null` succeeds. Otherwise it is a plain exec.
- The default profile stays `terminal` on every OS.
- On a failed download or checksum, the existing messages apply, with `devboost-darwin-arm64`
  in them.
**Tests (write first):** the stub `curl` writes canned files from a fixture dir keyed by the URL
basename and appends every URL to `curl.log`. The canned `devboost-darwin-arm64` is a shell
script that writes `"$@"` and `[ -t 0 ]` status to `exec.log`, and `checksums.txt` is computed by
the test.
- `test_linux_x86_64_flow_unchanged`: `uname` Linux/x86_64 → curl.log = [checksums.txt,
  devboost-x86_64, devboost-x86_64.tar.gz]; exec.log = `install terminal`.
- `test_darwin_arm64_fetches_binary_only`: Darwin/arm64, `sw_vers` 27.0, brew present →
  curl.log has no `.tar.gz`; the binary is installed and linked.
- `test_darwin_rosetta_shell_counts_as_arm64`: Darwin/x86_64 + `sysctl` → `1` → proceeds with
  `darwin-arm64`.
- `test_darwin_intel_refused`: Darwin/x86_64 + `sysctl` → `0` → rc 1, exact message, no curl.
- `test_darwin_macos_14_refused`: `sw_vers` 14.7 → rc 1, exact message.
- `test_darwin_macos_15_warns`: 15.6 → the warning, then proceeds.
- `test_darwin_macos_26_and_27_quiet`: both → no version message.
- `test_darwin_macos_28_warns_newer`: 28.0 → the "newer than tested" message.
- `test_darwin_root_refused`: `id` stub `-u` → `0` → rc 1, the exact message.
- `test_darwin_bootstraps_homebrew_when_missing`: no brew under `GS_BREW_PREFIX`; the curl stub
  for `install.sh` returns a script that creates `${GS_BREW_PREFIX}/bin/brew` and logs
  `NONINTERACTIVE=$NONINTERACTIVE` → the sudo stub log has `-v` **before** the installer ran;
  the installer saw `NONINTERACTIVE=1`.
- `test_darwin_skips_homebrew_when_present`: brew exists → install.sh never fetched, sudo never
  called.
- `test_darwin_exec_reads_tty_under_pipe`: stdin is a pipe, `GS_TTY` = a tmp file → the exec
  stdin is the file (exec.log shows the file content was read).
- `test_darwin_usb_profile_refused` / `test_darwin_none_installs_only`: as in Behaviour.
- `test_release_base_override`: `DEVBOOST_RELEASE_BASE=file:///x` → every curl.log URL starts
  with `file:///x/`.
- `test_checksum_mismatch_darwin`: bad checksum → rc 1,
  `checksum mismatch: devboost-darwin-arm64`, nothing installed.
- `test_get_sh_shellcheck_clean`: skip if absent.
**Implementation notes:** only `bash` 3.2 features on macOS, because `curl | bash` on a fresh Mac
runs `/bin/bash` 3.2: no `${var,,}`, no associative arrays, no `mapfile`. The fixture runs the
script with `/bin/bash`. The existing `profiles=("$@")` with `"${#profiles[@]}"` must stay
`set -u` safe on 3.2, where an empty array trips `set -u`, so guard it with
`${profiles[@]+"${profiles[@]}"}`.
**Task gate:** `uv run pytest tests/scripts/test_get_sh.py -q`

### Task 4: self-update keyed by (os, arch)   (Lane C, risk: high)

**Files:** Modify `engine/src/devboost/core/selfupdate.py`; Test
`engine/tests/core/test_selfupdate.py`.
**Interfaces:** Produces:
- `@dataclass(frozen=True) class ReleaseAsset: key: str; binary: str; archive: str | None`
- `def release_asset(system: str | None = None, machine: str | None = None) -> ReleaseAsset`,
  where `None` means `platform.system()` / `platform.machine()`
- `def _arch() -> str`, kept for the existing tests, which returns `release_asset().key`
- `update_frozen(fetch_url=…, fetch_file=…)` keeps its signature and return value.
**Exact values:** `("Linux","x86_64"|"amd64")` → `ReleaseAsset("x86_64","devboost-x86_64",
"devboost-x86_64.tar.gz")`; `("Linux","aarch64"|"arm64")` → the aarch64 trio;
`("Darwin","arm64"|"aarch64")` → `ReleaseAsset("darwin-arm64","devboost-darwin-arm64",None)`;
`("Darwin","x86_64")` → `RuntimeError("Intel Macs are not supported (Apple Silicon only)")`;
other → `RuntimeError(f"unsupported platform: {system}/{machine}")`. The machine match is
case-insensitive.
**Behaviour:**
- When `archive is None`, `update_frozen` downloads and verifies only `checksums.txt` and the
  binary. It never calls `injection_archive_path` and never writes any archive.
- The Linux path is unchanged: it downloads, verifies and replaces both files.
- A missing checksum entry or a mismatch raises the existing messages.
- A frozen Darwin binary replaces itself through the existing `_atomic_replace` (same
  directory, `os.replace`). A comment notes that the new file inherits no quarantine xattr
  because urllib is not a quarantine-aware downloader (V5).
**Tests (write first):**
- `test_release_asset_linux_x86_64` / `_linux_aarch64` / `_linux_arm64_alias`: exact dataclass.
- `test_release_asset_darwin_arm64`: `("Darwin","arm64")` → key `darwin-arm64`, archive `None`.
- `test_release_asset_intel_mac_rejected`: raises with the exact message.
- `test_release_asset_unknown_platform`: `("Linux","riscv64")` → `unsupported platform`.
- `test_update_frozen_darwin_skips_archive`: monkeypatch `release_asset` → darwin; the fake
  `fetch_file` records names; `sys.executable` → a tmp file; `injection_archive_path` patched to
  raise → downloads = [checksums.txt, devboost-darwin-arm64]; the tmp exe holds the new bytes.
- `test_update_frozen_darwin_ignores_missing_archive_checksum`: checksums lists only the
  binary → success.
- `test_update_frozen_linux_unchanged`: the Linux asset still requires the tar entry (the
  existing `test_update_frozen_missing_checksum_entry_raises` stays green when forced to Linux).
- The existing tests that call `selfupdate._arch()` monkeypatch `release_asset` to a Linux
  asset, so they stay hermetic on a Mac host.
**Task gate:** `uv run pytest tests/core/test_selfupdate.py -q`

### Task 5: CI matrix and release workflow   (Lane D, risk: high)

**Files:** Modify `.github/workflows/ci.yml` and `.github/workflows/release.yml`; Test
`engine/tests/scripts/test_workflows.py`.
**Interfaces:** Consumes the asset names from D1 and the build-bundle output paths from T1:
`dist/devboost-<key>`, `dist/devboost-<key>.tar.gz` (Linux only),
`dist/checksums-<key>.txt`.
**Exact values:**
- ci.yml `engine` job → matrix `os: [ubuntu-22.04, macos-15, xcode-27]`, with
  `continue-on-error: ${{ matrix.os == 'xcode-27' }}`. The apt `pass` and chezmoi `.deb` steps
  get `if: runner.os == 'Linux'`. The macOS steps
  `brew install pass chezmoi` get `if: runner.os == 'macOS'`. Run `uv run pytest -n 4` on
  macOS, where the runners have 3 vCPU; `-n 4` stays for parity with the local gate.
- ci.yml `frozen-smoke` → matrix `{os: ubuntu-22.04, key: x86_64}`, `{os: macos-15, key:
  darwin-arm64}`; the last step is `./dist/devboost-${{ matrix.key }} --version`.
- release.yml `checks` → matrix `[ubuntu-22.04, macos-15]`. `binary` matrix adds
  `- runner: macos-15` / `arch: darwin-arm64`. The tag check uses the `sed -nE` expressions
  from T2.
- `upload-artifact` path: `dist/devboost-${{ matrix.arch }}*` and
  `dist/checksums-${{ matrix.arch }}.txt`.
- New job `binary-compat`: `needs: [binary]`; matrix `os: [macos-26, xcode-27]`;
  `continue-on-error: ${{ matrix.os == 'xcode-27' }}`; downloads the `devboost-darwin-arm64`
  artifact, `chmod +x`, runs `--version` and `list macos`, then
  `codesign --verify --strict`.
- `release` job: `needs: [binary, binary-compat]`; also copies
  `artifacts/devboost-darwin-arm64/devboost-darwin-arm64`; `sha256sum` covers the five
  files; `files:` adds `out/devboost-darwin-arm64`.
- Action versions stay as they are (`checkout@v7`, `setup-uv@v7`, `upload-artifact@v7`,
  `download-artifact@v8`, `softprops/action-gh-release@v3`).
**Behaviour:**
- The Linux jobs and assets are unchanged (the same names, the same five-then-six file list, with
  checksums.txt lines only added).
- No larger runners (`-xlarge`/`-large`) appear anywhere (V2).
- `grep -oP` is gone from the workflows.
**Tests (write first):** text/regex assertions over the YAML files; no YAML dependency.
- `test_ci_runs_checks_on_macos_15`: `macos-15` appears in the `engine` matrix.
- `test_ci_xcode_27_non_blocking`: `continue-on-error` references `xcode-27`.
- `test_release_binary_matrix_has_darwin`: `arch: darwin-arm64` sits under the `macos-15` runner.
- `test_release_checksums_include_darwin`: the combine step names `devboost-darwin-arm64` in
  both `sha256sum` and `files:`.
- `test_release_linux_assets_unchanged`: all four Linux asset names are still present.
- `test_no_grep_P_in_workflows`, `test_no_paid_runner_labels`: no `-xlarge`/`-large`/`-intel`.
- `test_actionlint_clean`: skip if `actionlint` is absent; rc 0 over `.github/workflows`.
**Task gate:** `uv run pytest tests/scripts/test_workflows.py -q && (cd .. && actionlint)`

### Task 6: tart VM script and the guest smoke assertions   (Lane E, risk: normal)

**Files:** Create `scripts/vm-test-macos.sh` and `scripts/smoke-assert.sh`; Test
`engine/tests/scripts/test_vm_test_macos.py` and `engine/tests/scripts/test_smoke_assert.py`.
**Interfaces:**
- `vm-test-macos.sh [--dry-run] <verb> [opts]`. Verbs: `create --os 27|26 [--name N] [--cpu
  4] [--memory 8192] [--disk 80]`, `snapshot <snap>`, `revert <snap>`, `list`,
  `destroy`, `run [--local DIR] [--profiles "macos"]`, `shell`. VM name
  default `devboost-mac<os>`.
- `smoke-assert.sh <profiles…>` (POSIX `sh`, any guest; exit 0/1, prints each failed check):
  `devboost verify <profiles>` exits 0; `herdr --version` matches `0.9.1`; `command -v glow`;
  `devboost verify herdr-plugins`; login-shell stderr empty (`bash -lic exit` on Linux,
  `zsh -lic exit` on Darwin, stderr captured with `2>&1 >/dev/null`).
**Exact values:**
- Images: 27 → `ghcr.io/cirruslabs/macos-golden-gate-base:latest`; 26 →
  `ghcr.io/cirruslabs/macos-tahoe-base:latest`.
- argv (the `--dry-run` output, one `+ `-prefixed line each):
  - create: `tart clone <image> <vm>`, `tart set <vm> --cpu 4 --memory 8192 --disk-size 80`
  - run: `tart run --no-graphics <vm>` (in the background), `tart ip --wait 120 <vm>`, then
    `tart exec -i <vm> /bin/bash -lc '<cmd>'`
  - `--local DIR`: `tart run --no-graphics --dir=dist:<abs DIR> <vm>` and
    `DEVBOOST_RELEASE_BASE=file:///Volumes/My\ Shared\ Files/dist`
  - snapshot: `tart stop <vm>`, `tart clone <vm> <vm>--<snap>`
  - revert: `tart stop <vm>`, `tart delete <vm>`, `tart clone <vm>--<snap> <vm>`
  - destroy: `tart stop <vm>`, `tart delete <vm>`
  - list: `tart list`
  - shell hint: `ssh admin@$(tart ip <vm>)   # password: admin`
- The guest command for `run`:
  `curl -fsSL https://raw.githubusercontent.com/adams100111/dev-boost/main/scripts/get.sh | bash
  -s -- <profiles> && sh smoke-assert.sh <profiles>`. With `--local`, it is get.sh from the
  shared dir.
**Behaviour:**
- It refuses a non-Darwin host or a non-arm64 host with a clear message.
- A missing `tart` fails with `vm-test-macos: missing 'tart' — install with: brew install
  cirruslabs/cli/tart`.
- `create` refuses an existing VM unless `--recreate` is given, the same rule as vm-test.sh.
- `--local` needs `DIR/checksums.txt`. When only `checksums-darwin-arm64.txt` exists, the
  script copies it to `checksums.txt` in a staging dir, never in `dist/`.
- `run` streams the guest output and exits with the guest's exit code.
**Tests (write first):**
- `test_dry_run_create_27_argv`, `test_dry_run_create_26_argv`: exact `+ tart …` lines.
- `test_dry_run_snapshot_revert_destroy_argv`: exact sequences.
- `test_dry_run_run_local_sets_release_base`: contains `--dir=dist:` and the
  `DEVBOOST_RELEASE_BASE=file://` line.
- `test_refuses_linux_host`: stub `uname` Linux → rc 1.
- `test_missing_tart_message`: no tart on PATH, not dry-run → rc 1 and the exact message.
- `test_local_without_checksums_refused`: an empty dir → rc 1.
- `test_smoke_assert_all_pass`: stubs `devboost` (rc 0), `herdr` (`herdr 0.9.1`), `glow`, and
  `bash` (prints nothing) → rc 0.
- `test_smoke_assert_reports_each_failure`: `herdr 0.9.0`, no glow, bash writes to stderr →
  rc 1; the output names all three.
- `test_scripts_shellcheck_clean`: both scripts; skip if absent.
**Task gate:** `uv run pytest tests/scripts/test_vm_test_macos.py tests/scripts/test_smoke_assert.py -q`

### Task 7: Linux vm-smoke job   (Lane E, risk: normal)

**Files:** Modify `.github/workflows/vm-smoke.yml`, adding a job and leaving `kickstart-smoke`
as it is; Test: extend `engine/tests/scripts/test_smoke_assert.py` with workflow text checks.
**Interfaces:** Consumes `scripts/smoke-assert.sh` (T6).
**Exact values:**
- Job `linux-smoke`, `continue-on-error: true`, matrix:
  - `{name: fedora, runs-on: ubuntu-24.04, container: "fedora:44"}`
  - `{name: arch, runs-on: ubuntu-24.04, container: "archlinux:latest"}`
  - `{name: ubuntu-host, runs-on: ubuntu-24.04, container: ""}`
- Each leg: create user `dev` with `NOPASSWD` sudo (containers only) → `uv sync` in `engine/`
  → as `dev`, `uv run devboost install cli ghostty` → `sh scripts/smoke-assert.sh cli ghostty`.
- Extra asserts: Fedora `dnf copr list` includes `scottames/ghostty`; Ubuntu host
  `snap list ghostty` exits 0; Arch `pacman -Q ghostty` exits 0.
- Triggers: the existing `workflow_dispatch` + nightly cron.
**Behaviour:**
- The kickstart job stays byte-identical.
- The container legs run the engine from source, so no release is needed.
- The Ubuntu leg runs on the runner host, where systemd and snapd are real (D6).
**Tests (write first):**
- `test_vm_smoke_has_linux_legs`: fedora:44, archlinux:latest and the host leg are all present.
- `test_vm_smoke_asserts_ghostty_sources`: `scottames/ghostty`, `snap list ghostty` and
  `pacman -Q ghostty` are present.
- `test_kickstart_job_unchanged`: the kickstart job block is byte-equal to a fixture snapshot
  taken at T0.
**Task gate:** `uv run pytest tests/scripts/test_smoke_assert.py -q && (cd .. && actionlint)`

### Task 8: Root-owned files under DemotingExecutor   (Lane F, risk: high)

**Files:** Modify `engine/src/devboost/accounts/bootstrap.py`; Test
`engine/tests/accounts/test_bootstrap_reclaim.py`.
**Interfaces:** Produces:
```python
def reclaim_home(home: Path, *, uid: int, gid: int, since: float,
                 lstat: Callable[[Path], os.stat_result] = os.lstat,
                 lchown: Callable[[Path, int, int], None] = os.lchown) -> list[Path]
```
It returns the paths it chowned, sorted. `bootstrap_user` records `since = time.time()` before
`_run_profiles`, and in its `finally` (before HOME is restored) calls
`reclaim_home(Path(home_of(user)), uid=pw.pw_uid, gid=pw.pw_gid, since=since)` with
`pw = pwd.getpwnam(user.name)`, but only when `os.geteuid() == 0` and `not ctx.dry_run`.
**Exact values:** the log line per run is `accounts: reclaimed <n> root-owned path(s) in <home>`
(printed only when n > 0).
**Behaviour:**
- It walks `home` with `os.walk(followlinks=False)`, including `home` itself. It chowns an
  entry only when `st_uid == 0` **and** `st_mtime >= since` **or** `st_ctime >= since`.
- It uses `lchown`, so a symlink is never followed and its target outside HOME is never touched.
- A root-owned file older than `since` (for example one the admin placed on purpose) is left
  alone.
- An error on one path (`PermissionError`/`FileNotFoundError`, for instance when the file
  vanished) is logged and skipped. It never raises out of `finally`.
- It never runs on macOS: `accounts` is in `LINUX_ONLY`, and the root guard refuses root.
  A comment records this.
- The carry-over's audit question is answered in the test docstring: the root path does write
  user config in-process (`jsonc_merge_deep`, `_atomic_write`, `_zed.seed_files`, `fs.write`,
  `shell.py` rc writes …). This task fixes that for all of them at once.
**Tests (write first):** fakes: an `lstat` that returns a `SimpleNamespace`-like
`os.stat_result` built from a dict `{path: (uid, mtime)}`, and an `lchown` recorder.
- `test_reclaims_new_root_owned_files`: a tmp tree with 3 files and a nested dir; fake uid 0
  and mtime ≥ since for 2 of them → exactly those 2 are chowned to (1000, 1000).
- `test_leaves_old_root_files`: uid 0 but mtime < since → not chowned.
- `test_leaves_user_owned_files`: uid 1000 → not chowned.
- `test_never_follows_symlinks`: a symlink to a file outside home → `lchown` is called with the
  link path and the target is never visited.
- `test_error_on_one_path_continues`: `lchown` raises `PermissionError` on the first path →
  the second is still chowned; nothing is raised.
- `test_bootstrap_user_calls_reclaim_as_root`: monkeypatch `os.geteuid` → 0, `pwd.getpwnam`,
  `_run_profiles` (which raises), and `reclaim_home` (a recorder) → `reclaim_home` is called
  once with the user's home, even though the run raised.
- `test_bootstrap_user_skips_reclaim_when_not_root_or_dry_run`: euid 1000 → not called;
  dry_run → not called.
**Task gate:** `uv run pytest tests/accounts -q`

### Task 9: bash-config on unknown Linux distros   (Lane F, risk: normal)

**Files:** Modify `engine/src/devboost/modules/shell.py` (only the `BashConfig` class
attributes and comment); Test `engine/tests/core/test_unknown_distro.py`.
**Interfaces:** `BashConfig.families = ()` and `BashConfig.provided_by = ("macos",)` (D11).
**Behaviour:**
- On an unknown distro (`OsInfo(distro="gentoo", family="gentoo", …)`) the plan keeps
  `bash-config` with no skip reason.
- On macOS the plan reports `bash-config` with skip reason `provided-by-macos`.
- On Fedora, Ubuntu and Arch the plan is unchanged: `bash-config` is planned and not skipped.
- `tests/core/test_macos_contract.py` stays green.
**Tests (write first):**
- `test_unknown_distro_keeps_bash_config`: `build_plan` over the `shell` profile → a
  `bash-config` entry with `skip_reason is None`.
- `test_macos_reports_bash_config_provided`: `skip_reason == "provided-by-macos"`.
- `test_known_linux_families_unchanged`: fedora/debian/arch → `None`.
**Task gate:** `uv run pytest tests/core/test_unknown_distro.py tests/core/test_macos_contract.py -q`

### Task 10: Final docs   (Lane G, risk: normal)

**Files:** Modify `README.md`, `CLAUDE.md`, `CHANGELOG.md` (`[Unreleased]`), `docs/macos.md`,
`docs/vm-testing.md`, `docs/credentials.md`, `docs/maintenance.md`, and the spec §9 E2E bullet.
**Interfaces:** Consumes the names from T1–T9 verbatim: `devboost-darwin-arm64`,
`DEVBOOST_RELEASE_BASE`, the `vm-test-macos.sh` verbs, `smoke-assert.sh`, the image names
(V7), and the `bash-config` behaviour.
**Exact values:**
- README install line for Macs:
  `curl -fsSL https://raw.githubusercontent.com/adams100111/dev-boost/main/scripts/get.sh | bash -s -- macos`.
- Quarantine fix line: `xattr -d com.apple.quarantine ~/Downloads/devboost-darwin-arm64`.
**Behaviour:**
- **README:** a macOS install section (the line above; Apple Silicon; 27/26 supported, 15
  best-effort). It says that `curl` sets no quarantine and that a browser download needs the
  `xattr` line (V5). The regenerated profile tables come from `scripts/gen_profiles_table.py`.
  The "lands in M6" note is removed.
- **CLAUDE.md:** the mission line names macOS as a first-class family delivered by `get.sh` +
  a frozen binary.
- **docs/macos.md:** Status → "M1–M6 complete"; Requirements: get.sh installs Homebrew + the
  CLT (D4); "Install" puts `curl | bash` first, clone second; a self-update note (`(os, arch)`
  asset, no archive); a Gatekeeper/quarantine troubleshooting row; "Coming next" removed; the
  "Linux gate" section points to `vm-smoke.yml` `linux-smoke`.
- **docs/vm-testing.md:** a "macOS (tart)" section: install/pull, every verb with an example,
  the `--local` pre-release rehearsal, admin/admin, the V7 Screen Sharing caveat, and the
  **only accepted non-green items in a macOS guest** (no nested virtualization for a Colima VM
  inside a macOS guest, so the Docker runtime start fails; TCC grants need the GUI). A "Linux
  smoke (CI)" section covers `linux-smoke` and the libvirt fallback.
- **docs/credentials.md:** a note that the keychain age key is materialized as a 0600 `mkstemp`
  file only during a decrypt. A `SIGKILL` (or power loss) between write and unlink can leave it
  in `$TMPDIR`, which on macOS is a per-user `/var/folders/…` directory. Risk is low. The
  cleanup line: `find "$TMPDIR" -maxdepth 1 -name 'devboost-age-*' -user "$USER" -delete`
  (prefix verified in `modules/secrets.py`: `mkstemp(prefix="devboost-age-")`).
- **docs/maintenance.md:** the release checklist covers three binaries plus `checksums.txt`,
  the `binary-compat` job, and the tart rehearsal before tagging.
- **CHANGELOG `[Unreleased]`:** one "macOS delivery (M6)" entry covering the darwin binary,
  get.sh on Mac, self-update by (os, arch), the macOS CI, tart `vm-test-macos.sh`, the Linux
  vm-smoke, root-owned-file reclaim, and bash-config on unknown distros.
- **Spec §9:** "exact 27 image name confirmed at M6" becomes
  `ghcr.io/cirruslabs/macos-golden-gate-base`.
**Tests (write first):** none. The docs are checked by the gate below.
**Task gate:** regenerate the README tables with `scripts/gen_profiles_table.py` → the diff
shows only intended rows; `grep -n "lands in M6\|Coming next" README.md docs/macos.md` → empty.

### Task 11: CI iteration on real runners   (Lane ctl, risk: high)

**Files:** none new. A red job goes back to the owning lane (A–F) as a fix task in that lane's
files.
**Behaviour:**
- Push `feat/macos-m6-delivery` and open a draft PR (the controller does both). The `ci`
  workflow must go green on `ubuntu-22.04` + `macos-15` (engine + frozen-smoke), and `xcode-27`
  may be red but must not block.
- Rehearse the release workflow without publishing, using `workflow_dispatch` on a branch copy
  or a fork tag. Do not create a `v*` tag on the main repo before T13. Check that
  `binary-compat` passes on `macos-26`.
- Budget: 2–3 iterations at about 10–15 min each (orchestration §7).
**Task gate:** `gh pr checks <pr> --watch` green on the blocking jobs.

### Task 12: Rehearsal: tart (27 + 26) and Linux smoke   (Lane ctl + user, risk: high)

**Files:** none. Findings become fix tasks in the owning lane, and doc gaps go to Lane G.
**Behaviour (the user at the Mac):**
1. On the M5 host: `bash scripts/build-bundle.sh` → `dist/devboost-darwin-arm64`.
   `codesign --verify --strict` passes, and `./dist/devboost-darwin-arm64 list macos` exits 0.
2. `scripts/vm-test-macos.sh create --os 27`, then `snapshot fresh`, then `run --local dist
   --profiles terminal`, then `revert fresh`, then `run --local dist --profiles macos`. The run
   reaches the end, and the only failures are the documented ones (T10).
3. Repeat step 2 with `--os 26`.
4. Trigger `gh workflow run vm-smoke.yml`. All three `linux-smoke` legs must pass
   `smoke-assert.sh`. That closes the carry-over vm-smoke list: glow, herdr 0.9.1 and
   herdr-plugins on Fedora/Ubuntu/Arch; Ghostty via COPR on Fedora and via snap on Ubuntu; a
   clean login shell after `install cli`.
5. The unknown-distro `bash-config` item is closed by T9's hermetic test plus the Arch leg.
**Task gate:** all of the above recorded in the SDD ledger with the VM exit codes.

### Task 13: Release v0.2.0 and fresh-Mac acceptance   (Lane ctl + user, risk: high)

**Files:** `CHANGELOG.md` (roll `[Unreleased]` → `[0.2.0] — <date>`),
`engine/pyproject.toml`, `engine/src/devboost/__init__.py`, `engine/uv.lock` (bump via
`uv lock`).
**Exact values:**
- Commit `chore(release): v0.2.0 — macOS support (M1–M6)` on `release/v0.2.0`, following the
  v0.1.80 PR (#30) pattern.
- Tag `v0.2.0` (annotated) on the merge commit.
- Assets: `devboost-x86_64`, `devboost-aarch64`, `devboost-x86_64.tar.gz`,
  `devboost-aarch64.tar.gz`, `devboost-darwin-arm64`, `checksums.txt`.
**Behaviour:**
- Merge the M6 PR first (`gh pr merge --merge --delete-branch`), then the release PR, then push
  the tag. `release.yml` publishes.
- Fresh-Mac acceptance: `vm-test-macos.sh revert fresh` (27), then `run --profiles macos` with
  **no** `--local`, which uses the published release and `main`'s get.sh. The same documented
  items as T12 are the only failures.
- Linux self-update: on a Linux box/VM with v0.1.80, `devboost self-update` → `0.2.0`, with the
  archive replaced.
- Mac self-update: there is no earlier Mac release. Build a scratch binary from `v0.2.0` with
  `__version__` patched to `0.1.99` in an uncommitted scratch worktree, run its
  `self-update` → it replaces itself with the published 0.2.0 and fetches no archive. The first
  real Mac-to-Mac update is checked at the next patch release.
- On the real Mac: `curl … | bash -s -- macos` over the existing install, where every module
  skips or upgrades.
**Task gate:** `gh release view v0.2.0 --json assets` lists the 6 assets; both self-updates
report `0.2.0`.

---

## Gates

| Tier | When | Command(s) |
|---|---|---|
| Task | after each task | the task's **Task gate** line |
| Lane | before the lane's branch merges | `uv run ruff check && uv run mypy && uv run pytest <lane test paths> -q` + `shellcheck -x <lane scripts>` + (D, E) `actionlint` |
| Milestone | after each wave merge and before the PR | from `engine/`: `uv run ruff check && uv run mypy && uv run pytest -n 4`; from the root: `shellcheck -x scripts/*.sh && actionlint`; then T11 CI green; then T12/T13 on the Mac |

Reviews: `risk: high` tasks (T1, T3, T4, T5, T8, T11–T13) get a spec reviewer plus a
Linux-unchanged reviewer. The others get one reviewer.

## Needs the user at the Mac

- T0: `brew install cirruslabs/cli/tart actionlint`, and start both `tart pull`s early (tens of
  GB).
- T12: the build on the M5, the tart runs on 27 and 26, and any GUI/TCC click inside the VM (use
  `tart run` with graphics; VNC is broken on the 27 image, V7). Also the sudo password `admin`
  when get.sh's `sudo -v` prompts inside the VM.
- T13: approve the v0.2.0 version (D12), the fresh-VM acceptance against the published
  release, a Linux host with v0.1.80 for the Linux self-update, and the re-run on the real
  Mac.

## Risks

- uv-managed (python-build-standalone) Python + PyInstaller on macOS: the Linux build already
  uses the same combination. T1's gate on the real Mac and T11's `frozen-smoke` on `macos-15`
  catch a missing `libpython` early. The fallback is `setup-uv` with
  `python-version: '3.12'` and `UV_PYTHON_PREFERENCE=only-system` on the runner.
- `xcode-27` is a Preview image and can change or vanish, so it stays non-blocking (D7).
- The golden-gate image is new (27.0 build 26A5416b). If `tart exec` misbehaves, fall back
  to the ssh line that `shell` prints. A onefile start extracts to `$TMPDIR` each run (slower
  than onedir); accepted.

## Self-review

- **Spec coverage:**
  - §7: T1 (asset, shasum fallback, no tarball, smoke `list macos`), T5 (the `macos-15` matrix,
    `sed -nE`, checks on macos-15, combine), T3 (all get.sh bullets incl. `</dev/tty` and the
    `~/.zshrc` hint), T4 (`_arch`, archive skip).
  - §9: CI on ubuntu-22.04 + macos-15 + non-blocking xcode-27 (T5); tart E2E for 27 and 26
    with verbs mirroring vm-test.sh (T6, T12).
  - §10: README, CLAUDE.md, CHANGELOG, macos.md, vm-testing.md, maintenance.md (T10).
  - §11 M6 outcome: T13.
- **Carry-over:**
  - selfupdate by (os, arch): T4.
  - DemotingExecutor root-owned files: T8.
  - SIGKILL temp key: T10 credentials.md.
  - vm-smoke list: glow, herdr 0.9.1, herdr-plugins, Ghostty COPR and snap, clean login shell
    (T6, T7, T12).
  - Unknown distros and bash-config: T9.
  - Tart 27 image on the M5 host and runner parity: V7, T6, T12, D7.
  - The "M3:/M5:"-tagged items under the M6 heading: T0 verification.
  - The plan-writing rule (default promotions re-proven per OS): Ghostty, glow and
    herdr-plugins in T7/T12.
- **Interface names across lanes:** `devboost-darwin-arm64`, `darwin-arm64`,
  `DEVBOOST_RELEASE_BASE`, `checksums-<key>.txt`, `smoke-assert.sh`, `ReleaseAsset` /
  `release_asset`, `reclaim_home`. Each is spelled the same in T1–T13.
- **File ownership:** each file row in File Structure has exactly one lane. `CHANGELOG.md` is
  Lane G in Wave 2 and T13 in Wave 4. These are sequential waves, not concurrent lanes.
