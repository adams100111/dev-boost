# Implementation Plan: multimedia-codecs

**Branch**: `005-multimedia-codecs` | **Date**: 2026-06-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/005-multimedia-codecs/spec.md`

## Summary

Deliver the `multimedia` profile as **four escape-hatch modules over the existing engine**
+ one `profiles.toml` entry. `ffmpeg-full` swaps the limited `ffmpeg-free` for the full
RPM Fusion `ffmpeg`; `codecs` installs the `@multimedia` group; `va-hwaccel` detects the
GPU vendor(s) via `lspci` and installs the matching VA-API driver (Intel/AMD/NVIDIA, both
on hybrid), verifying with `vainfo`; `openh264` enables the Cisco repo and installs the
OpenH264 components. All verify on the END state (a re-run after a swap is a no-op). These
are Fedora/RPM-Fusion-specific: with only `[install].fedora` keys, the engine already
reports them **unsupported** on non-Fedora (no module guard needed). Zero engine/
`bin/devboost` change; GPU detection is inline in `va-hwaccel/install.sh` (no new lib).
Built test-first with bats, mocking `dnf`/`rpm`/`lspci`/`vainfo`/`dnf config-manager` — no
real installs, no real GPU, no network.

## Technical Context

**Language/Version**: Bash (engine + modules); python3/jq (existing).
**Primary Dependencies**: `dnf` (swap/update/config-manager), `rpm` (verify), `lspci` (GPU detect), `vainfo` (accel verify, from `libva-utils`). No new engine runtime dependency.
**Storage**: system packages + the Cisco repo toggle. No user config, no database.
**Testing**: `bats`; extend `tests/fixtures/base/stubs.bash` with `lspci` (vendor via knob), `vainfo` (working-driver via knob), and a `dnf swap`/`dnf config-manager` handler. No real installs/GPU/network (§V).
**Target Platform**: Fedora Workstation + RPM Fusion (reference). Non-Fedora → engine-reported unsupported (only fedora `[install]` keys).
**Project Type**: Single-project Bash bootstrap engine.
**Performance Goals**: Not latency-sensitive; correctness + idempotency.
**Constraints**: Unattended; idempotent (verify on end state); engine untouched; no secret in git.
**Scale/Scope**: 4 modules (`ffmpeg-full`, `codecs`, `va-hwaccel`, `openh264`) + 1 `profiles.toml` entry (`multimedia`) + ~4 bats files. No new lib (GPU detect inline). Reuses Spec-1/2 escape-hatch + `lib/pkg.sh` helpers.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Engine + Data Separation** — PASS (no engine touch). 4 modules (data + escape-hatch) + 1 `profiles.toml` entry. `run_install`/`depsort`/`module.sh`/`profile.sh`/`bin/devboost` unchanged. No new lib.
- **II. Idempotent & Verify-Guarded** — PASS. Each module verifies the END state (ffmpeg full installed / @multimedia present / vainfo working / openh264 present); a dnf swap re-run is guarded by the verify (skip). `dnf install -y`/`update` are idempotent.
- **III. Reproducible — Repo is Source of Truth** — PASS. Package choices + GPU→driver map live in the modules; no secret; no version churn introduced.
- **IV. Unattended by Default** — PASS. All `dnf -y`/swap/config-manager non-interactive; GPU detection is automatic (no prompt).
- **V. Test-First (NON-NEGOTIABLE)** — PASS. swap+verify, codec install, each GPU vendor + hybrid + unrecognized + vainfo-fails, openh264, unsupported-OS are failing-bats-first; all tooling stubbed.
- **VI. Cross-OS via Data** — PASS. Only `[install].fedora` keys ⇒ engine reports unsupported on other OS (FR-007 satisfied by data, no guard). GPU→driver mapping is data inside the module.

**Result: PASS** — proceed to Phase 0.

## Project Structure

### Documentation (this feature)
```text
specs/005-multimedia-codecs/
├── plan.md, research.md, data-model.md, quickstart.md
├── contracts/
│   ├── ffmpeg-and-codecs.md   # ffmpeg-full + codecs (US1)
│   ├── va-hwaccel.md          # GPU detect + per-vendor VA-API driver + vainfo verify (US2)
│   ├── openh264.md            # Cisco repo + OpenH264 (US3)
│   └── profiles.md            # multimedia profile entry
└── tasks.md
```

### Source Code (repository root)
```text
modules/                       # NEW multimedia modules
├── ffmpeg-full/{module.toml,install.sh}   # dnf swap ffmpeg-free ffmpeg --allowerasing
├── codecs/{module.toml,install.sh}        # dnf update @multimedia (no weak deps, exclude PackageKit-gstreamer-plugin)
├── va-hwaccel/{module.toml,install.sh}    # lspci detect → intel-media-driver / mesa-*-freeworld swap / libva-nvidia-driver; vainfo verify
└── openh264/{module.toml,install.sh}      # config-manager enable fedora-cisco-openh264 + install openh264/gstreamer1-plugin-openh264/mozilla-openh264
profiles.toml                  # EDIT — add `multimedia = ["ffmpeg-full","codecs","va-hwaccel","openh264"]`
tests/
├── ffmpeg-codecs.bats, va-hwaccel.bats, openh264.bats   # NEW
└── fixtures/base/stubs.bash   # EXTEND (backward-compatible): lspci (vendor knob), vainfo (working knob), dnf swap/config-manager
```

**Structure Decision**: Single-project Bash engine; fully additive. No engine/`bin/devboost`
or lib change. GPU detection is a small inline `lspci` parse in `va-hwaccel/install.sh`
(the only consumer) with the vendor→driver mapping as in-module data.

## Complexity Tracking

> No constitution violations — no engine touch, no new lib. Table empty.
