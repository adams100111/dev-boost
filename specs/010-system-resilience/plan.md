# Implementation Plan: system-resilience

**Branch**: `010-system-resilience` | **Date**: 2026-06-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/010-system-resilience/spec.md`

## Summary

Deliver the `system` resilience/maintenance profile (snapper snapshots + grub-btrfs + dnf hook,
btrfsmaintenance, fwupd, power-profiles-daemon, thermald, smartmontools, dnf-automatic-security,
restic-backup, dev-protecting earlyoom), `gpu-detect` auto-selection (in `full`), the `hardware-nvidia`
chain (akmod + CUDA + VA-API + MOK state machine + CRC64→CRC32 fix + per-kernel resign service +
container toolkit), a `doctor --gpu` engine diagnostic, and an opt-in `optional-editors` profile.
Almost all data modules (Principle I); `doctor --gpu` + `lib/gpu.sh` are an additive engine flag
(Principle V TDD). Reuses Spec 5 lspci detection. All system calls stubbed.

## Technical Context

**Language/Version**: Bash (`set -Eeuo pipefail`); existing engine/module conventions.
**Primary Dependencies**: dnf/rpm, systemctl, snapper, grub-btrfs, akmods, mokutil, kmodgenca, grubby,
dracut, depmod, modprobe, xz/unxz, nvidia-ctk, lspci, dmesg — all PATH-stubbable.
**Storage**: filesystem (configs under /etc, units, /usr/local/sbin, workstation-config/gpu marker).
**Testing**: bats; tests/system.bats, tests/nvidia.bats, tests/gpu.bats, tests/optional-editors.bats +
cli/profiles; new stubs akmods/mokutil/kmodgenca/grubby/dracut/depmod/modprobe/nvidia-ctk/unxz/xz/dmesg;
reuse lspci/STUB_GPU_VENDOR, dnf/rpm/systemctl. No real hardware/driver/btrfs/MOK mutation.
**Target Platform**: Fedora reference; all `[install]` Fedora-only.
**Project Type**: dev-boost data modules + small engine doctor extension.
**Constraints**: unattended except one-time NVIDIA MOK enrollment (SB on); idempotent; verify-guarded;
NVIDIA fixes verbatim from design §10; dnf-automatic security-only; earlyoom protects dev procs.
**Scale/Scope**: ~20 modules + 3 profiles + 1 engine flag + lib/gpu.sh.

## Constitution Check

- **I. Engine + Data Separation** — PASS. Modules are data; the only engine change is the additive
  `doctor --gpu` flag + `lib/gpu.sh` (feature-local), justified as an engine *feature*, existing
  `doctor` behavior unchanged.
- **II. Idempotent & Verify-Guarded** — PASS. Snapshot/maintenance/nvidia steps skip-if-present; MOK +
  CRC + resign are idempotent; each module has verify; failures name module + command.
- **III. Reproducible** — PASS. Package/driver set pinned in module data; no secrets (restic sample
  conf only); nothing auto-commits.
- **IV. Unattended** — PASS. Only the one-time NVIDIA MOK enrollment is interactive (SB on), by design.
- **V. Test-First (TDD)** — PASS (binding). Every module + the doctor flag built RED→GREEN on stub logs.
- **VI. Cross-OS via Data** — PASS. Fedora-only `[install]` ⇒ unsupported elsewhere.

**Result: PASS.** Re-checked post-Phase-1: still PASS.

## Project Structure
```text
profiles.toml                # + system, hardware-nvidia, optional-editors; full gains system + gpu-detect
lib/gpu.sh                   # NEW — gpu_doctor + detection helpers (feature-local)
bin/devboost                 # cmd_doctor gains --gpu branch (plain doctor unchanged)
modules/{snapper,snapper-dnf-hook,grub-btrfs,btrfs-assistant,btrfsmaintenance,fwupd,
         power-profiles-daemon,thermald,smartmontools,dnf-automatic-security,restic-backup,earlyoom}/
modules/{gpu-detect,nvidia-akmod,cuda,libva-nvidia-driver,secureboot-mok,
         nvidia-resign-service,nvidia-container-toolkit}/
modules/{neovim,jetbrains-toolbox}/
tests/{system,nvidia,gpu,optional-editors}.bats  + tests/{cli,profiles}.bats additions
tests/fixtures/base/stubs.bash  # + akmods/mokutil/kmodgenca/grubby/dracut/depmod/modprobe/nvidia-ctk/unxz/xz/dmesg (backward-compatible)
```

## Phase 0 — Research
See [research.md](./research.md). No open unknowns.

## Phase 1 — Design & Contracts
[data-model.md](./data-model.md) + contracts/{system-modules,nvidia-chain,gpu-detect-and-doctor}.md +
[quickstart.md](./quickstart.md). CLAUDE.md SPECKIT pointer → this plan.

## Phase 2 — Tasks
`/speckit-tasks` → tasks.md (Setup → Foundational stubs + profiles → US1 snapshots → US2 maintenance →
US3 earlyoom → US4 gpu-detect → US5 nvidia chain → US6 doctor --gpu → US7 optional-editors → Polish).
