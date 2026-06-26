---
description: "Task list for the bash → Python migration (014)"
---

# Tasks: Bash → Python Migration (typed engine, modules, and tests)

**Input**: Design documents from `/specs/014-python-engine-core/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: REQUIRED. The constitution (Principle V — Test-First, NON-NEGOTIABLE) and spec FR-016
mandate comprehensive, test-first pytest. Every implementation cluster is preceded by its tests,
written to fail first against a `FakeExecutor`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no incomplete dependencies)
- **[Story]**: the user story (US1–US6 from spec.md) the task primarily advances
- Paths are repo-relative; the typed project lives under `engine/` until M10 (then hoisted to root)

## Organization note (read first)

This is one greenfield deliverable, built as a **direct incremental rewrite** across internal
milestones **M0–M10** (plan.md / design §10) — *not* shippable per-phase. The phases below ARE the
milestones. The spec's user stories are cross-cutting quality outcomes satisfied progressively, so
each task is tagged with the story it advances:

- **US1** Fedora parity · **US2** whole-platform debuggability · **US3** one typed file + type-checked graph
- **US4** OS-ready seams · **US5** hermetic tests + strict typing · **US6** cold-start frozen binary

The bash engine, ~55 modules, and 1,104 bats tests are the **behavioral spec** — ported to pytest and
deleted group-by-group. No intermediate release; the single release point is M10.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: scaffold the typed `uv` project and the quality gates.

- [X] T001 Create the src-layout skeleton `engine/src/devboost/{cli,core,exec/primitives,modules}/` + `engine/tests/{core,exec,primitives,modules,cli}/` per plan.md
- [X] T002 Write `engine/pyproject.toml` (uv_build backend, `requires-python>=3.12`; deps: typer, pydantic, pydantic-settings, loguru, tenacity; dev: pytest, pytest-mock, mypy, ruff) and `engine/.python-version` (3.12); bump the stale `typer<0.22` pin to current (research R7)
- [X] T003 [P] Configure `mypy` (`strict = true`, files = src) and `ruff` (line-length 100) in `engine/pyproject.toml`, and pytest options (markers `unit`/`integration`, `pythonpath=src`, `strict_markers`)
- [X] T004 [P] Create `engine/tests/conftest.py` with the `FakeExecutor` and `fake_ctx` fixtures (fedora + headless + ubuntu-os variants) used by every unit test
- [X] T005 Retarget CI: update `.github/workflows/` to run `uv run pytest`, `mypy --strict`, `ruff check` against `engine/`, gating merges (US5)

**Checkpoint**: `uv sync` + `uv run pytest` run (empty-green) under strict typing/lint.

---

## Phase 2: Foundational — M0 Engine core + tracer (Blocking Prerequisites) 🎯 KEYSTONE

**Purpose**: build the stable contract (`Ctx`/`Executor`/`Module`/`Installer`/registry/engine flow),
prove it end-to-end with two tracer modules, stand up the CLI + delivery, and rewrite the boot path.
Everything else depends on this. (Serves US2/US3/US4/US5/US6 foundationally.)

**⚠️ CRITICAL**: No module-group milestone (Phase 3+) may begin until M0 is complete.

- [X] T006 [P] Implement the `DevbootError` exception hierarchy in `engine/src/devboost/core/errors.py`
- [X] T007 [P] Implement loguru config (`info/ok/skip/error` semantics) in `engine/src/devboost/core/log.py`
- [X] T008 [P] [US4] Tests then impl: `OsInfo` + `detect()` (distro→family table, arch, headless; `/etc/os-release` path injectable) in `engine/tests/core/test_osinfo.py` + `engine/src/devboost/core/osinfo.py` (crib `engine/devboost/osinfo.py`)
- [X] T009 [US5] Tests then impl: `Executor` Protocol + `Result` + `RealExecutor` (argv-only, `sudo`, `env`, `dry_run`-honoring) + `FakeExecutor` (records `calls`) in `engine/tests/exec/test_executor.py` + `engine/src/devboost/exec/executor.py`
- [X] T010 [US3] Tests then impl: `Ctx`, `Installer` Protocol, `Module` base (`per_os`/`_strategy`/`verify`/`install`), `OsMap[T]`, `DnfRepo`/`Script` value objects in `engine/tests/core/test_model.py` + `engine/src/devboost/model.py`
- [X] T011 [US3] Tests then impl: registry `@register` + `load()` auto-scan of `devboost.modules.*` + graph validation (unique names, `requires` resolve, `profiles` exist, no cycles, gui rules) in `engine/tests/core/test_registry.py` + `engine/src/devboost/core/registry.py`
- [X] T012 [P] [US1] Tests then impl: Kahn `toposort` in `engine/tests/core/test_graph.py` + `engine/src/devboost/core/graph.py` (crib `engine/devboost/graph.py`)
- [X] T013 [US1] Tests then impl: pydantic `profiles.toml` loader + `expand()` (transitive profile/module) in `engine/tests/core/test_profiles.py` + `engine/src/devboost/core/profiles.py`
- [X] T014 [US1] Add the `full` profile (production aggregate, research R2 membership) to `profiles.toml`
- [X] T015 [US1] Tests then impl: `PlannedModule` + `build_plan` (headless-gui + unsupported-os skips) in `engine/tests/core/test_plan.py` + `engine/src/devboost/core/plan.py`
- [X] T016 [US1] Tests then impl: `run_plan` verify-guarded loop (skip/install/re-verify, `force`, `dry_run`, failure names module + command) in `engine/tests/core/test_runner.py` + `engine/src/devboost/core/runner.py`
- [X] T017 [US4] Tests then impl: `pkg` primitive — `PackageManager` Protocol, `Dnf` impl, `manager_for(os)`, `install/installed/add_repo`, `OsMap`/`Source` resolution in `engine/tests/primitives/test_pkg.py` + `engine/src/devboost/exec/primitives/pkg.py`
- [X] T018 [P] [US1] Tests then impl: `config` + `fs` primitives (`json_merge`, `ensure_line`, `write`, `exists`) in `engine/tests/primitives/` + `engine/src/devboost/exec/primitives/{config,fs}.py`
- [X] T019 [US3] Tracer A — trivial module: tests then `engine/src/devboost/modules/ripgrep.py` (single `pkg.install`), proving registry→plan→run→primitive→FakeExecutor end-to-end
- [X] T020 [US1] Tracer B — per-OS `Source` module: tests then `engine/src/devboost/modules/{docker,ddev}.py` (`ddev` uses `DnfRepo` + `mkcert`), proving layer-3 dispatch (`requires=(Docker,)`)
- [X] T021 [US2] Tests then impl: Typer app + `install`/`verify`/`list` verbs **and the `terminal`/`devtools` tier verbs** (thin wrappers that run `install` with the matching profile; `devtools` is fully exercisable once its member modules land in M2/M6, but the verb ships in M0) in `engine/tests/cli/` (`CliRunner`) + `engine/src/devboost/cli/{app,install,verify,list,tiers}.py`
- [X] T022 [US1] Tests then impl: `doctor` Python preflight (OS detect, deps `jq`/`age`, modules dir, secrets-state + mise-drift hooks as stubs to fill in M2/M1) in `engine/src/devboost/cli/doctor.py` — replaces `install.sh` dep-ensure
- [X] T023 [P] [US6] Tests then impl: `Settings` (pydantic-settings, `DEVBOOST_*`) + `resources` resolver (paths work from source and frozen) in `engine/src/devboost/core/settings.py` + `engine/src/devboost/exec/resources.py`
- [X] T024 [US6] Retarget delivery: update `scripts/build-bundle.sh` + `.github/workflows/release.yml` to PyInstaller-freeze `engine/` (`--onefile`, x86_64 + aarch64, bundle `data/`); add a frozen-binary smoke test (`--version`/`list`)
- [ ] T025 [US1] Rewrite the boot path: `get.sh` + `ventoy/ks.cfg` `%post` + `devboost-firstboot.service` call the binary directly; delete `bin/devboost` and `install.sh`'s logic (move dep-ensure into `doctor`); update `tests/ventoy.bats` references (or port to pytest)

**Checkpoint (M0)**: `devboost install --profile <tracer>` installs ripgrep + ddev end-to-end on a
Fedora VM; `list`/`verify`/`doctor` work; `mypy --strict` + ruff + pytest green; frozen binary smoke
passes on both arches. **The architecture is proven — bulk porting can begin.**

---

## Phase 3: M1 — secrets + github (Priority: US1)

**Goal**: typed secrets/age + GitHub API **first**, so credential-dependent modules (`chezmoi-repo`, `obsidian-sync`, private dev-stack repos) can rely on it; fill `doctor`'s secrets preflight.

**Independent Test**: `secrets`/`ssh-setup` provision identity + upload key on a VM with a test bundle; `doctor` reports secrets state.

- [ ] T026 [P] [US1] Port secrets/github bats → pytest (test-first) in `engine/tests/modules/` and `engine/tests/primitives/`
- [ ] T027 [US1] Tests then impl: `age` primitive (decrypt the `secrets.age` bundle via the `age` CLI through `Executor`; parse JSON with stdlib) in `engine/src/devboost/exec/primitives/age.py`
- [ ] T028 [US1] Tests then impl: `github` primitive (SSH-key upload via stdlib HTTP, not the `gh` CLI) in `engine/src/devboost/exec/primitives/github.py`
- [ ] T029 [US1] [US3] Port `secrets` + `ssh-setup` modules; complete `doctor`'s secrets-state branch (T022 stub); delete `lib/secrets.sh` + `lib/github.sh` + their bats; VM-verify

**Checkpoint**: secrets/ssh-setup green; `doctor` secrets preflight real; `lib/secrets.sh`/`lib/github.sh` gone.

---

## Phase 4: M2 — base profile (Priority: US1)

**Goal**: port the `base` foundation modules into typed Python; establish the core install primitives. Runs **after** secrets (M1) so `chezmoi-repo`'s credential-store clone works.

**Independent Test**: `devboost install base && devboost verify base` is fully green on a clean Fedora VM.

- [ ] T030 [P] [US1] Port base-group bats → pytest as the behavioral spec (test-first), in `engine/tests/modules/` (rpmfusion, dnf-tune, fedora-third-party, flatpak, build-tools, mise, chezmoi, chezmoi-repo, docker)
- [ ] T031 [US1] Tests then impl: `copr`, `mise`, `flatpak` primitives in `engine/src/devboost/exec/primitives/{copr,mise,flatpak}.py`
- [ ] T032 [US1] [US3] Port base modules to `engine/src/devboost/modules/` (rpmfusion, dnf-tune, fedora-third-party, flatpak, build-tools, mise, chezmoi, chezmoi-repo) — one typed file each (`docker` already done by the M0 tracer, T020)
- [ ] T033 [US1] [US3] Port the CLI-tools clusters to `engine/src/devboost/modules/` (`base`: coreutils, git, curl, wget, unzip, jq, htop, ripgrep✓, fd, fzf, tmux; `cli`: eza, bat, btop, zoxide, atuin, direnv, delta, lazygit, lazydocker, dust, duf, sd, yq, gh, tealdeer, tpm, fastfetch, claude-code)
- [ ] T034 [US1] Wire base/cli into `profiles.toml`; delete `lib/pkg.sh` + the ported modules' bash + their bats; run `install base` + `verify base` on a Fedora VM

**Checkpoint**: base + cli install/verify green; `lib/pkg.sh` gone.

---

## Phase 5: M3 — cli + shell profiles (Priority: US1)

**Goal**: shell/prompt/dotfiles experience in typed Python.

**Independent Test**: `install shell && verify shell` green; starship/ghostty/nerd-fonts/dotfiles applied.

- [ ] T035 [P] [US1] Port cli/shell bats → pytest (test-first)
- [ ] T036 [US1] [US3] Port `shell` modules (starship, bash-config, ghostty, nerd-fonts, dotfiles) to `engine/src/devboost/modules/`; reuse `config`/`fs`/`mise` primitives (extend as needed)
- [ ] T037 [US1] Delete the ported modules' bash + bats; VM-verify `cli`+`shell`

**Checkpoint**: terminal experience green.

---

## Phase 6: M4 — gnome (Priority: US1)

**Goal**: GNOME settings/extensions via typed `dconf`.

**Independent Test**: `install gnome && verify gnome` green on a GNOME VM (dark/scaling/extensions applied).

- [ ] T038 [P] [US1] Port gnome bats → pytest (test-first)
- [ ] T039 [US1] Tests then impl: `dconf` primitive (`load` schema dumps via `dconf` CLI through `Executor`) in `engine/src/devboost/exec/primitives/dconf.py`
- [ ] T040 [US1] [US3] Port gnome modules (gnome-settings, gnome-extensions, gnome-manager-apps; opt-in aesthetics/theme bundles) ; delete `lib/gnome.sh` + bash + bats; VM-verify

**Checkpoint**: gnome green; `lib/gnome.sh` gone.

---

## Phase 7: M5 — multimedia + editors (Priority: US1)

**Goal**: codecs/va-hwaccel + VS Code + `fresh` editor & LSP wiring.

**Independent Test**: `install multimedia editors && verify …` green; `vainfo` works; `fresh` config has base LSPs.

- [ ] T041 [P] [US1] Port multimedia + editors bats → pytest (test-first)
- [ ] T042 [US1] [US3] Port multimedia modules (ffmpeg-full, codecs, va-hwaccel [GPU-aware], openh264)
- [ ] T043 [US1] [US3] Port editors modules (vscode, fresh, fresh-lsp) + the `fresh` config-merge logic (replaces `lib/fresh.sh`) using the `config` primitive
- [ ] T044 [US1] Delete `lib/fresh.sh` + ported bash + bats; VM-verify

**Checkpoint**: multimedia + editors green; `lib/fresh.sh` gone.

---

## Phase 8: M6 — dev-stacks (Priority: US1)

**Goal**: the buildable dev stacks (the mission's "production builds out of the box").

**Independent Test**: each stack profile installs+verifies; sample projects build (Laravel/.NET+Aspire/Python/web/RN).

- [ ] T045 [P] [US1] Port dev-stacks bats → pytest (test-first) for laravel/dotnet/python/web/data/devops/react-native
- [ ] T046 [US1] [US3] Port `python` (uv, python-lsp) + `web` (web-runtimes, web-lsp) modules + templates
- [ ] T047 [US1] [US3] Port `laravel` (ddev✓, laravel-lsp) + `dotnet` (dotnet-sdk, aspire, dotnet-lsp) modules + templates
- [ ] T048 [US1] [US3] Port `data` (data-services) + `devops` (devops-tools, devops-lsp) + `react-native` (android-sdk, expo) modules + templates
- [ ] T049 [US1] Delete ported dev-stack bash + bats; VM-verify each stack builds a sample project

**Checkpoint**: all dev stacks green and buildable.

---

## Phase 9: M7 — apps + obsidian (Priority: US1)

**Goal**: Flathub GUI apps + obsidian-sync (deploy key, systemd user timer).

**Independent Test**: `install apps && verify apps` green; Obsidian opens `~/Vault`, round-trips to GitHub.

- [ ] T050 [P] [US1] Port apps + obsidian-sync bats → pytest (test-first)
- [ ] T051 [US1] Tests then impl: `systemd` primitive (enable a `--user` unit/timer) in `engine/src/devboost/exec/primitives/systemd.py`
- [ ] T052 [US1] [US3] Port `apps` modules (obsidian, bruno, bitwarden, flameshot, localsend, vlc) + `obsidian-sync` (reuses `github`/`age` primitives; replaces `lib/vault.sh`)
- [ ] T053 [US1] Delete `lib/vault.sh` + ported bash + bats; VM-verify

**Checkpoint**: apps + obsidian-sync green; `lib/vault.sh` gone.

---

## Phase 10: M8 — lifecycle + dev-hygiene CLI verbs (Priority: US1)

**Goal**: the remaining CLI verbs in typed Python.

**Independent Test**: `add`/`export`/`diff`/`update`/`self-update` and `dev status|gc|down` behave per contracts/cli.md.

- [ ] T054 [P] [US1] Port lifecycle + devhygiene bats → pytest (test-first)
- [ ] T055 [US1] [US2] Tests then impl: `cli/lifecycle.py` (`add` scaffolds a typed module file, `export`, `diff`, `update` + `devboost.lock` writer, `self-update`)
- [ ] T056 [US1] [US2] Tests then impl: `cli/devhygiene.py` (`dev status|gc|down`; precise orphan GC) + the `aspire-gc` user-timer module
- [ ] T057 [US1] Delete `lib/lifecycle.sh` + `lib/devhygiene.sh` + their bash + bats; VM-verify the verbs

**Checkpoint**: full CLI surface (contracts/cli.md) implemented; lifecycle/devhygiene bash gone.

---

## Phase 11: M9 — system + gpu (Priority: US1)

**Goal**: system-resilience modules + GPU/MOK state machine + `doctor --gpu`.

**Independent Test**: `install system && verify system` green; `gpu-detect` selects the right driver path; `doctor --gpu` reports the NVIDIA stack.

- [ ] T058 [P] [US1] Port system + gpu/nvidia bats → pytest (test-first)
- [ ] T059 [US1] Tests then impl: `gpu` primitive + MOK state machine (lspci detect, resign service, CRC fix) in `engine/src/devboost/exec/primitives/gpu.py`; complete `doctor --gpu` (T022)
- [ ] T060 [US1] [US3] Port `system` modules (snapper, grub-btrfs, btrfsmaintenance, fwupd, tuned/thermald, earlyoom, smartmontools, dnf-automatic-security, restic-backup, gpu-detect) + `hardware-nvidia` modules (nvidia-akmod, cuda, libva-nvidia-driver, secureboot-mok, nvidia-resign-service, nvidia-container-toolkit) + `optional-editors` + `security-cli` (pass, pass-store)
- [ ] T061 [US1] Delete `lib/gpu.sh` + ported bash + bats; VM-verify (stubbed MOK per design §10 oracle)

**Checkpoint**: every module ported; only `lib/`-remnants + entrypoints remain to clean.

---

## Phase 12: M10 — Finish, hoist, and acceptance (Polish & Cross-Cutting)

**Purpose**: remove the last bash, finalize structure, and validate the whole deliverable.

- [ ] T062 [US3] Delete any remaining `lib/*.sh`, per-module `*.sh`, `module.toml`, and `tests/*.bats`; confirm only `get.sh` + Kickstart `%post` remain as bash (quickstart Scenario 6 / SC-003)
- [ ] T063 [P] [US2] Hoist the project from `engine/` to the repository root (root `pyproject.toml`, `src/devboost`, `tests/`); update CI/build paths and `CLAUDE.md`
- [ ] T064 [P] Rewrite the README profiles-table generator to read the typed registry (category/description from classes) + `profiles.toml` membership (research R5); replace `scripts/gen-profiles-table.sh`
- [ ] T065 [P] Apply the scheduled constitution PATCH: reword Principle I's TOML "manifest/`[install]` key" language to typed-Python modules (design §12)
- [ ] T066 [US6] Final release build: PyInstaller per-arch (x86_64 + aarch64) + frozen-binary smoke (`--version`/`list`); publish via `release.yml` on a `v*` tag (the single release point)
- [ ] T067 [US1] Full acceptance on a clean Fedora VM: `devboost install full` then `verify full` fully green; second `install full` is an idempotent no-op (quickstart Scenario 4 / SC-001, SC-002)
- [ ] T068 [P] [US5] Final gate sweep: `mypy --strict` + ruff clean; full pytest suite green; 0 `.bats` files remain (SC-004, SC-005)
- [ ] T069 Run all quickstart.md scenarios end-to-end as the deliverable's definition-of-done

**Checkpoint**: single-deliverable acceptance met — ship.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies — start immediately.
- **M0 Foundational (Phase 2)**: depends on Setup — **BLOCKS all module-group milestones**.
- **M1–M9 (Phases 3–11)**: each depends on M0. Ordered by the roadmap dependency chain
  (base → secrets → cli/shell → gnome → multimedia/editors → dev-stacks → apps → lifecycle → system),
  but a given milestone only truly needs M0 + the primitives it introduces; later milestones reuse
  earlier primitives. **`secrets` is M1 — placed before `base` (M2)** because `base`'s `chezmoi-repo`
  (and later `obsidian-sync`, private dev-stack repos) clone via the credential store that `secrets`
  provisions.
- **M10 (Phase 12)**: depends on M1–M9 all complete — the single release point.

### Within each milestone

- **Tests first** (port the group's bats → pytest, confirm they fail), then primitives, then modules,
  then delete the corresponding bash + bats, then VM-verify. (Constitution Principle V.)
- Build primitives before the modules that compose them.

### Parallel Opportunities

- Setup tasks marked [P] run in parallel.
- Within M0, the independent leaves marked [P] (errors, log, osinfo, graph, config/fs primitives,
  settings) run in parallel; `model`/`registry`/`runner`/`pkg`/CLI are sequential on their inputs.
- Within a module-group milestone, the bats→pytest port [P] and independent module files can be
  written in parallel once that milestone's primitives exist.
- M10 cleanup tasks marked [P] (hoist, table generator, constitution PATCH, gate sweep) parallelize.

---

## Implementation Strategy

### Keystone first (M0)

1. Phase 1 Setup → 2. Phase 2 (M0) foundation + **both tracer modules** → **STOP and VALIDATE**:
the engine installs ripgrep + ddev end-to-end on a Fedora VM, CLI verbs work, frozen binary smoke
passes, all gates green. This proves the architecture before any bulk porting (the riskiest design
is validated by real callers).

### Incremental rewrite (M1 → M9)

Port one milestone at a time: bats→pytest (spec) → primitives → typed modules → delete bash →
VM-verify. `main` stays green at each checkpoint; nothing is released. Reuse primitives across
milestones; add new ones only when a module needs them.

### Finish (M10)

Delete the last bash, hoist to root, regenerate docs, apply the constitution PATCH, build + smoke the
per-arch binary, and run the full-`full` Fedora VM acceptance + quickstart scenarios. This is the
single release point.

---

## Notes

- [P] = different files, no incomplete dependencies. [Story] tags trace each task to the spec's user
  stories (US1 parity · US2 debuggability · US3 one-file/typed-graph · US4 OS-ready · US5 tests · US6 binary).
- TDD is mandatory (Principle V): write the group's pytest from its bats spec and see it fail first.
- Only `get.sh` + Kickstart `%post` may remain bash at completion (SC-003).
- Commit after each task or logical cluster (Conventional Commits, no attribution).
- Fedora is the only implemented target; `Apt`/`Pacman` and per-OS entries are seams for a later spec.
