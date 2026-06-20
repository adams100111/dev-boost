# Phase 0 Research: multimedia-codecs

Spec clarifications settled in specify. Plan-level decisions below.

## D1. ffmpeg-full + codecs (exact, design §10c)
**Decision**: `ffmpeg-full/install.sh`: `sudo dnf swap ffmpeg-free ffmpeg --allowerasing`;
verify END state: `rpm -q ffmpeg` present AND `ffmpeg-free` absent (so a re-run after the
swap is a verify-green skip). `codecs/install.sh`: `sudo dnf update @multimedia
--setopt="install_weak_deps=False" --exclude=PackageKit-gstreamer-plugin`; verify a
representative codec component (e.g. `rpm -q gstreamer1-plugins-bad-freeworld` or a key
`@multimedia` member). Both `requires=["rpmfusion"]`.
**Rationale**: exact RPM Fusion Howto/Multimedia commands; verify-on-end-state makes the
swap idempotent.

## D2. GPU detection + per-vendor VA-API driver (inline, design §10c)
**Decision**: `va-hwaccel/install.sh` runs `gnome_require`-free; it:
1. installs `libva-utils` (provides `vainfo`).
2. detects GPU vendor(s) from `lspci` (lines matching `VGA`/`3D`/`Display` controller):
   `Intel` → `intel-media-driver` (recent; older gens fallback `libva-intel-driver`);
   `AMD`/`ATI` → `sudo dnf swap mesa-va-drivers mesa-va-drivers-freeworld` + swap
   `mesa-vdpau-drivers mesa-vdpau-drivers-freeworld`; `NVIDIA` → `libva-nvidia-driver`
   (renamed from nvidia-vaapi-driver). A HYBRID machine (≥2 vendors in lspci) installs ALL
   matched drivers.
3. verify END state: `vainfo` reports a working driver (exit 0 + a driver line). If after
   install `vainfo` shows none, the module FAILS naming the GPU/driver (FR-004 — not silent
   success). An UNRECOGNIZED vendor → `libva-utils` only + a named failure listing the
   unmatched vendor (FR-009 — not guessed).
**Rationale**: design §10c GPU-aware layer; lspci is the deterministic data source; vainfo
is the end-state oracle. `requires=["rpmfusion"]` (freeworld AMD drivers come from RPM Fusion).
**Scope note**: VA-API DRIVER layer only — the proprietary NVIDIA akmod/CUDA/Secure-Boot is
the later `hardware-nvidia` spec.

## D3. OpenH264 / Cisco (design §10c)
**Decision**: `openh264/install.sh`: `sudo dnf config-manager setopt
fedora-cisco-openh264.enabled=1` (enable add-if-not-enabled), then `sudo dnf install -y
openh264 gstreamer1-plugin-openh264 mozilla-openh264`. verify: the three packages present
(`rpm -q`). `requires=[]` (the Cisco repo is Fedora's own, not RPM Fusion).
**Rationale**: exact design commands; `rpm -q` end-state verify is idempotent.

## D4. Unsupported-OS via data (no guard)
**Decision**: each module declares ONLY an `[install].fedora` key. On a non-Fedora OS the
engine's `module_install_cmd` finds no match and reports the module **unsupported** (a
failure), satisfying FR-007/SC-006 purely by data — no in-module desktop/OS guard needed
(unlike the GNOME modules, the multimedia distinction IS an OS distinction the engine
already handles).

## D5. Testing (no installs/GPU/network)
**Decision**: extend `tests/fixtures/base/stubs.bash` (backward-compatible) with: `lspci`
(emits controller lines per a `STUB_GPU_VENDOR` knob — `intel`/`amd`/`nvidia`/`intel+nvidia`
hybrid/`unknown`), `vainfo` (exit + driver line per a `STUB_VAINFO_OK` knob), and a
`dnf swap`/`dnf config-manager setopt` handler in the existing dnf stub. `rpm -q` already
stubbed (`STUB_RPM_INSTALLED`). Tests assert: ffmpeg swap attempted + end-state verify;
codec update attempted; per-vendor driver install (intel/amd-swap/nvidia/hybrid-both),
unrecognized→named-fail, vainfo-fails-after-install→named-fail; openh264 repo enable +
install; unsupported-OS (non-fedora `OS_DISTRO`) → engine failure. No real installs/GPU.
**Rationale**: hermetic, §V real-behavior; mirrors Specs 1–4.

## Outcome
No unresolved NEEDS CLARIFICATION. Ready for Phase 1.
