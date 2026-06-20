# Tasks: multimedia-codecs

**Input**: Design documents from `specs/005-multimedia-codecs/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: REQUIRED — constitution §V + SC-007. Every module behavior is a failing bats
test before implementation.

**Organization**: by user story (US1 P1 → US2 P2 → US3 P3). Stub-harness extension +
profile entry are Foundational. Paths repo-root relative.

## Format: `[ID] [P?] [Story?] Description`

---

## Phase 1: Setup

- [ ] T001 [P] Create module folders under `modules/` for `ffmpeg-full`, `codecs`, `va-hwaccel`, `openh264` (with `.gitkeep`).
- [ ] T002 Extend `tests/fixtures/base/stubs.bash` (BACKWARD-COMPATIBLE — Specs 1–4 suite of 666 must stay green) with: `lspci` stub (emits GPU controller lines per `STUB_GPU_VENDOR` = `intel`/`amd`/`nvidia`/`intel+nvidia`/`unknown`), `vainfo` stub (exit + driver line per `STUB_VAINFO_OK`, default 1), and handlers in the existing `dnf` stub for `dnf swap <a> <b>` and `dnf config-manager setopt <repo>.enabled=1` (record to the dnf log; idempotent). Run `bats tests/` → 666 still green.

**Checkpoint**: scaffold + extended multimedia harness ready.

---

## Phase 2: Foundational (Blocking)

- [ ] T003 Add the `multimedia` entry to `profiles.toml` per `contracts/openh264.md` (do NOT touch base/cli/shell/gnome); extend `tests/profiles.bats` with `profile_expand multimedia` membership/count (4 modules, TOML-only). Full `list --profile multimedia` depsort test DEFERRED to T0XX (polish).

**Checkpoint**: profile resolves; stories can begin.

---

## Phase 3: User Story 1 — Full media stack + codecs (Priority: P1) 🎯 MVP

**Goal**: full ffmpeg replaces ffmpeg-free + the @multimedia codec set, idempotent (end-state verify); unsupported on non-Fedora.
**Independent test**: ffmpeg swap + codec install attempted; verify on end state; re-run no-op; non-Fedora → unsupported.

- [ ] T004 [P] [US1] Write `tests/ffmpeg-codecs.bats` (RED) per `contracts/ffmpeg-and-codecs.md`: ffmpeg-full dnf swap attempted + verify GREEN when `rpm -q ffmpeg` present AND `ffmpeg-free` absent (via `STUB_RPM_INSTALLED`) / RED when ffmpeg-free still present; codecs `dnf update @multimedia` attempted + verify maps to the codec component; idempotent skip; unsupported-OS (non-fedora `OS_DISTRO`) → engine failure.
- [ ] T005 [P] [US1] Implement `modules/ffmpeg-full/{module.toml,install.sh}` (`requires=["rpmfusion"]`; `dnf swap ffmpeg-free ffmpeg --allowerasing -y`; verify end state).
- [ ] T006 [US1] Implement `modules/codecs/{module.toml,install.sh}` (`requires=["rpmfusion"]`; `dnf update @multimedia --setopt=install_weak_deps=False --exclude=PackageKit-gstreamer-plugin -y`; verify a representative codec component). Reach GREEN for T004.

**Checkpoint**: US1 MVP — media plays.

---

## Phase 4: User Story 2 — GPU-aware hardware acceleration (Priority: P2)

**Goal**: detect GPU(s) + install matching VA-API driver(s), hybrid=both, vainfo end-state verify, named failures.
**Independent test**: per-vendor driver install; hybrid both; unrecognized→named-fail; vainfo-fails→named-fail; idempotent; unsupported-OS.

- [ ] T007 [US2] Write `tests/va-hwaccel.bats` (RED) per `contracts/va-hwaccel.md`: Intel→intel-media-driver; AMD→the two mesa freeworld swaps; NVIDIA→libva-nvidia-driver; hybrid (`intel+nvidia`)→BOTH; unrecognized (`unknown`)→module fails NAMING the unmatched vendor; `STUB_VAINFO_OK=0` after install→module fails NAMING the GPU/driver (no silent success); verify GREEN when vainfo works; idempotent; unsupported-OS → engine failure. Use `--force` where a test must reach install on a host with state.
- [ ] T008 [US2] Implement `modules/va-hwaccel/{module.toml,install.sh}` (`requires=["rpmfusion"]`; install `libva-utils`; inline `lspci` GPU detect → per-vendor driver action(s) per the data map; hybrid=all; unrecognized→`die` named; END-state `vainfo` check→`die` named on failure; verify = `vainfo` succeeds). Reach GREEN for T007.

**Checkpoint**: US2 — hardware video acceleration per detected GPU.

---

## Phase 5: User Story 3 — Browser H.264 / OpenH264 (Priority: P3)

**Goal**: Cisco source enabled + OpenH264 components installed, idempotent.
**Independent test**: config-manager enable + 3-package install; verify via rpm -q; idempotent; unsupported-OS.

- [ ] T009 [US3] Write `tests/openh264.bats` (RED) then implement `modules/openh264/{module.toml,install.sh}` (`requires=[]`; `dnf config-manager setopt fedora-cisco-openh264.enabled=1` + `dnf install -y openh264 gstreamer1-plugin-openh264 mozilla-openh264`; verify = `rpm -q` all 3; idempotent; unsupported-OS → engine failure). GREEN.

**Checkpoint**: US3 — browser H.264 works.

---

## Phase 6: Polish & Cross-Cutting

- [ ] T010 Add the deferred full-resolution test to `tests/profiles.bats`: `devboost list --profile multimedia` (real `profiles.toml` + all `modules/`) depsorts without cycle, `rpmfusion` before its multimedia dependents. Then run the FULL suite `bats tests/` — all green, NO regression to Specs 1–4 (666) or engine.
- [ ] T011 [P] Reconcile `quickstart.md` against delivered module names/commands; fix any drift.
- [ ] T012 [P] Update `docs/roadmap.md` Spec 5 row status (done at branch completion).

---

## Dependencies & Execution Order
- Setup (T001–T002) → Foundational (T003) → US1 (T004–T006) → US2 (T007–T008) → US3 (T009) → Polish (T010–T012).
- US1 is the MVP. US2 (va-hwaccel) and US3 (openh264) are independent of US1 (different modules) but tested after. All `requires` rpmfusion (US1/US2) — base provides it.
- TDD inside each story: RED test → implement → GREEN.

## Parallel Opportunities
- T001 ∥ (T002 after); T004 ∥ T005 (test vs ffmpeg module — different files); T011 ∥ T012.
- Same-file tasks (profiles.bats edited by T003 + T010; stubs.bash by T002) are NOT parallel.

## Implementation Strategy
- **MVP = US1** (Phases 1–3): full media stack — independently shippable.
- Then US2 (GPU accel), US3 (OpenH264), each a green increment. Whole-branch review + finishing after Polish.

**Total: 12 tasks** — Setup 2, Foundational 1, US1 3, US2 2, US3 1, Polish 3.
