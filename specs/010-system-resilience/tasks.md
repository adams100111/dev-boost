# Tasks: system-resilience

**Input**: Design documents from `specs/010-system-resilience/`. TDD; design §6.3/§10 oracle.
Single-file tasks (`tests/fixtures/base/stubs.bash`, `bin/devboost`, `lib/gpu.sh`, `profiles.toml`,
`tests/profiles.bats`, `tests/cli.bats`) are NOT parallel. Keep prior 961 suite green.

## Phase 1: Setup
- [X] T001 [P] Create module dirs under `modules/` for the 21 modules (system + hardware + optional-editors).

## Phase 2: Foundational (Blocking)
- [X] T002 Extend `tests/fixtures/base/stubs.bash` (BACKWARD-COMPATIBLE — 961 must stay green): add stubs `akmods`, `mokutil` (--sb-state→STUB_SB_STATE; enrolled→STUB_MOK_ENROLLED; queued→STUB_MOK_QUEUED; --import logs), `kmodgenca`, `grubby`, `dracut`, `depmod`, `modprobe` (load test→STUB_MODPROBE_FAIL), `nvidia-ctk`, `unxz`/`xz`, `dmesg` (→STUB_DMESG); reuse lspci/STUB_GPU_VENDOR, dnf/rpm/systemctl. Knob+log defaults + truncation. Run `bats tests/` → 961 green.
- [X] T003 Add `system`/`hardware-nvidia`/`optional-editors` to `profiles.toml`; add `system` + `gpu-detect` to `full`; extend `tests/profiles.bats` membership (TOML-only). Depsort = Polish.

## Phase 3: US1 — snapshot recovery (P1) 🎯 MVP
- [X] T004 [P] [US1] `tests/system.bats` (RED) US1 cases per contracts/system-modules.md: snapper config root, snapper-dnf-hook pkg, grub-btrfs enabled, btrfs-assistant; idempotent; unsupported-OS; snapper non-Btrfs named fail.
- [X] T005 [US1] Implement `modules/{snapper,snapper-dnf-hook,grub-btrfs,btrfs-assistant}/` (module.toml + install.sh/verify where needed). GREEN.

## Phase 4: US2 — maintenance/health (P2)
- [X] T006 [US2] Add US2 cases to `tests/system.bats` (RED): each maintenance module installs+enables; dnf-automatic security-only; restic sample conf+timer (no secrets).
- [X] T007 [US2] Implement `modules/{btrfsmaintenance,fwupd,power-profiles-daemon,thermald,smartmontools,dnf-automatic-security,restic-backup}/`. GREEN.

## Phase 5: US3 — earlyoom (P3)
- [X] T008 [US3] Add US3 cases to `tests/system.bats` (RED): earlyoom config has --avoid (dev procs) + --prefer (desktop hogs), service enabled.
- [X] T009 [US3] Implement `modules/earlyoom/`. GREEN.

## Phase 6: US4 — gpu-detect (P4)
- [X] T010 [P] [US4] `tests/gpu.bats` (RED) US4 cases: STUB_GPU_VENDOR nvidia→selects nvidia; intel/amd→open (no nvidia pkgs); intel+nvidia→nvidia; unknown→reported.
- [X] T011 [US4] Create `lib/gpu.sh` (detection helpers) + `modules/gpu-detect/`. GREEN for T010.

## Phase 7: US5 — hardware-nvidia chain (P5)
- [X] T012 [P] [US5] `tests/nvidia.bats` (RED) per contracts/nvidia-chain.md: nvidia-akmod (pkgs, akmods --force, grubby nouveau args, CRC32 recompress, dracut --force; idempotent CRC); secureboot-mok state machine (sb-off skip / enrolled no-op / queued report / else import); nvidia-resign-service (script+unit+enable); cuda/libva-nvidia-driver/nvidia-container-toolkit (rpm/ctk configure); unsupported-OS.
- [X] T013 [US5] Implement `modules/{nvidia-akmod,cuda,libva-nvidia-driver,secureboot-mok,nvidia-resign-service,nvidia-container-toolkit}/`. GREEN.

## Phase 8: US6 — doctor --gpu (P6)
- [X] T014 [US6] Add `gpu_doctor` to `lib/gpu.sh` + `--gpu` branch to `bin/devboost` cmd_doctor; `tests/gpu.bats` + `tests/cli.bats` (RED→GREEN): healthy→0; nouveau-present/modprobe-fail→non-zero+named; plain doctor unchanged.

## Phase 9: US7 — optional-editors (P7)
- [X] T015 [P] [US7] `tests/optional-editors.bats` (RED): neovim + jetbrains-toolbox install+verify; NOT in full.
- [X] T016 [US7] Implement `modules/{neovim,jetbrains-toolbox}/`. GREEN.

## Phase 10: Polish
- [X] T017 Add depsort tests to `tests/profiles.bats` (system resolves; hardware-nvidia ordering rpmfusion→nvidia-akmod→{cuda,vaapi,mok,resign,ctk}; full includes system+gpu-detect). Run FULL `bats tests/` — green, no regression to 961.
- [X] T018 [P] Reconcile quickstart/research vs delivered; update `docs/roadmap.md` row 10 done.

**Total: 18 tasks.** MVP = US1 snapshots. US1–US3 share tests/system.bats; US4/US6 share tests/gpu.bats + lib/gpu.sh; US5 tests/nvidia.bats. Fan out independent module-impl tasks to subagents (disjoint module dirs) where a single shared test file isn't being co-edited.
