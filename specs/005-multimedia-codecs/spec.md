# Feature Specification: multimedia-codecs

**Feature Branch**: `005-multimedia-codecs`

**Created**: 2026-06-20

**Status**: Draft

**Input**: User description: "multimedia-codecs — the `multimedia` profile (design §10c + §6): full FFmpeg, the @multimedia codec set, GPU-aware hardware video acceleration (VA-API), and OpenH264 for Firefox."

## Overview

This feature makes media "just work" on a fresh machine: it replaces the limited default
media stack with the full one, installs the common codec set, enables **GPU-aware hardware
video acceleration** (so video decode is offloaded to the detected GPU), and turns on the
Cisco OpenH264 path so the browser plays H.264. It ships as self-contained modules over
the existing engine, reusing the escape-hatch + `lib/pkg.sh` + bats stub-harness patterns
(Specs 1–4) and building on the extra-repos foundation from base. These are
Fedora/RPM-Fusion-specific; on a non-Fedora host the modules report unsupported.

## Clarifications

### Session 2026-06-20 (self-answered from the design doc — source of truth; user "take over")

- Q: How is the VA-API driver chosen per GPU, and at what granularity? → A: a `lspci`-based detect step reads the GPU vendor and installs the matching VA-API driver: **Intel** (recent, incl. UHD 630) → the modern Intel media driver (older gens → the legacy Intel driver); **AMD** → swap to the freeworld Mesa VA/VDPAU drivers; **NVIDIA** → the libva NVIDIA driver. A multi-GPU / hybrid (Optimus) machine installs the discrete vendor's driver AND the integrated GPU's driver. This is the VA-API DRIVER layer only — the full proprietary NVIDIA kernel driver + CUDA + Secure-Boot signing is a separate later feature (hardware-nvidia).
- Q: How are the dnf swaps treated for idempotency? → A: verify on the END state (the target package installed / the old one absent), so a re-run with the swap already done is a no-op skip.
- Q: Are these in the default `full` set? → A: yes — `multimedia` is in `full` (design §5); the proprietary GPU driver layer is the part that is opt-in/auto-detected separately.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Full media stack + codecs (Priority: P1)

After the extra repos are in place, the operator's machine has the complete media
framework and the common codec set, so audio/video files and streams play without
"missing codec" errors.

**Why this priority**: The full framework + codecs is the core value (media plays); it is
independent of any GPU and is the MVP.

**Independent Test**: On a fixture host (package tooling mocked), run the framework and
codec modules and assert the full framework package is installed (the limited one
replaced) and representative codec components are present; re-run is a no-op.

**Acceptance Scenarios**:

1. **Given** the extra repos are present, **When** the framework module runs, **Then** the full media framework replaces the limited default (the limited package is gone, the full one installed).
2. **Given** the extra repos are present, **When** the codec module runs, **Then** the common codec set is installed.
3. **Given** the full stack is installed, **When** the modules run again, **Then** they report already-satisfied (idempotent — verify on the end state).
4. **Given** a non-Fedora host, **When** the modules run, **Then** they are reported unsupported, never silently skipped.

---

### User Story 2 - GPU-aware hardware video acceleration (Priority: P2)

The operator's machine offloads video decoding to its GPU automatically — the correct
acceleration driver for the detected graphics hardware is installed, so video playback is
smooth and power-efficient without the user choosing anything.

**Why this priority**: Big quality/efficiency win, but builds on the media stack (US1) and
is hardware-dependent.

**Independent Test**: With the GPU-detection and acceleration tooling mocked, run the
acceleration module against fixtures simulating each GPU vendor and assert the matching
driver is installed and the acceleration check reports a working driver; a hybrid-GPU
fixture installs both drivers; re-run is a no-op.

**Acceptance Scenarios**:

1. **Given** an Intel GPU is detected, **When** the acceleration module runs, **Then** the Intel acceleration driver is installed and the acceleration check reports a working driver.
2. **Given** an AMD GPU is detected, **When** the module runs, **Then** the freeworld AMD acceleration drivers are installed (replacing the limited ones).
3. **Given** an NVIDIA GPU is detected, **When** the module runs, **Then** the NVIDIA acceleration driver is installed.
4. **Given** a hybrid (discrete + integrated) machine, **When** the module runs, **Then** the drivers for BOTH GPUs are installed.
5. **Given** the acceleration is set up, **When** the module runs again, **Then** nothing changes (idempotent); **and** on a non-Fedora host it is reported unsupported.

---

### User Story 3 - Browser H.264 (OpenH264) (Priority: P3)

The operator's browser can play H.264 video (the most common web video codec) because the
Cisco OpenH264 source is enabled and its components are installed.

**Why this priority**: Important for everyday web video, but a small, independent add-on
on top of the media stack.

**Independent Test**: With package tooling mocked, run the OpenH264 module and assert the
Cisco source is enabled and the OpenH264 components are installed; re-run is a no-op.

**Acceptance Scenarios**:

1. **Given** a fresh machine, **When** the OpenH264 module runs, **Then** the Cisco source is enabled and the OpenH264 components are installed.
2. **Given** OpenH264 is set up, **When** the module runs again, **Then** it reports already-satisfied (idempotent).

### Edge Cases

- The full framework is already installed (swap already done) → verify passes on the end state; no re-swap.
- No GPU detected / an unrecognized GPU vendor → the acceleration module installs the generic acceleration utilities and reports which GPUs it could (not) match, failing clearly rather than installing a wrong driver.
- A hybrid machine where one driver is already installed → only the missing one is added.
- The acceleration check reports no working driver after install → the module fails naming the GPU/driver (not a silent success).
- A non-Fedora / non-RPM-Fusion host → all modules reported unsupported.
- The Cisco source is already enabled → not re-enabled; components installed only if missing.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST replace the limited default media framework with the full one (the limited package absent, the full one installed afterward), idempotently.
- **FR-002**: The system MUST install the common codec set, idempotently.
- **FR-003**: The system MUST detect the GPU vendor(s) present and install the matching hardware-acceleration driver(s) for the detected hardware, including BOTH drivers on a hybrid machine.
- **FR-004**: The system MUST verify hardware acceleration on the END state — the acceleration check reports a working driver for the detected GPU — and MUST fail (named) if no working driver results, rather than reporting silent success.
- **FR-005**: The system MUST enable the browser H.264 source and install its components, idempotently.
- **FR-006**: Every module MUST be idempotent and verify-guarded: a top-level verify determines already-satisfied state (the END state of a swap/install) and is evaluated before any install action.
- **FR-007**: These modules MUST be reported UNSUPPORTED on a non-Fedora / non-RPM-Fusion host, never silently skipped; OS differences MUST be expressed as data.
- **FR-008**: Dependency ordering MUST be expressed via `requires` (the framework/codec/acceleration modules after the extra-repos module), reusing the engine's existing ordering — no engine control-flow change.
- **FR-009**: GPU detection MUST be a deterministic data step (read the hardware inventory), with each vendor → driver mapping expressed as data; an unrecognized vendor MUST be reported, not guessed.
- **FR-010**: A failure in any module MUST name the module and the exact operation that failed.
- **FR-011**: No module may write secrets into version control (carried platform rule).

### Key Entities *(include if feature involves data)*

- **Media framework**: the full framework package replacing the limited default.
- **Codec set**: the common audio/video codec components.
- **GPU inventory + driver map**: detected GPU vendor(s) and the vendor→acceleration-driver mapping (Intel/AMD/NVIDIA, incl. hybrid).
- **Acceleration check**: the tool that reports whether a working acceleration driver is present for the detected GPU.
- **Browser H.264 source + components**: the Cisco source toggle and the OpenH264 components.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Running the multimedia profile on a base machine completes with **zero interactive prompts** and ends with all modules verifying green.
- **SC-002**: Re-running the multimedia profile is a **no-op** — every module reports already-satisfied (verify on the end state).
- **SC-003**: After the run, a common video file plays with the full framework (no "missing codec"), and the acceleration check reports a **working driver for the detected GPU**.
- **SC-004**: On each simulated GPU vendor (and a hybrid machine), the **correct** driver(s) are installed; an unrecognized vendor is reported, not mis-driven.
- **SC-005**: After the run, the browser can play H.264 (the Cisco source is enabled + components installed).
- **SC-006**: On a non-Fedora host, the modules report **unsupported** (a failure), never a silent skip.
- **SC-007**: Automated tests cover framework swap + codec install + idempotency, each GPU vendor + hybrid + unrecognized + acceleration-check-fails paths, OpenH264, and the unsupported-OS path — with no real installs, no real GPU, and no network (mocked).

## Assumptions

- Base (Spec 2) is present: the extra free/non-free repos and the tuned package manager are available; the framework/codec/freeworld-driver packages come from the extra repos.
- The reference OS is Fedora Workstation; non-Fedora hosts are unsupported (reported).
- GPU detection reads the machine's hardware inventory; the vendor→driver mapping is the design-doc set (Intel/AMD/NVIDIA, hybrid = both); exact package names are pinned in the plan.
- This feature provides the VA-API DRIVER layer only; the full proprietary NVIDIA kernel driver + CUDA + Secure-Boot signing is a separate later feature (hardware-nvidia) and is out of scope here.
- `multimedia` is part of the default `full` set; the proprietary GPU driver layer is the separately-handled part.
- Built test-first with the project's existing harness, mocking the package/GPU/acceleration tooling so no real installs, GPU, or network occur.
