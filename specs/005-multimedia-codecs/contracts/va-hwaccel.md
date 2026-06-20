# Contract: `va-hwaccel` (US2)

Escape-hatch module sourcing `lib/log.sh`+`lib/pkg.sh`. `category="multimedia"`,
`requires=["rpmfusion"]`, only `[install].fedora`.

## `install.sh`
1. install `libva-utils` (provides `vainfo`).
2. detect GPU vendor(s) from `lspci` (controller lines: `VGA`/`3D`/`Display`):
   - Intel → `sudo dnf install -y intel-media-driver` (older gens fallback `libva-intel-driver`).
   - AMD/ATI → `sudo dnf swap -y mesa-va-drivers mesa-va-drivers-freeworld` AND swap `mesa-vdpau-drivers mesa-vdpau-drivers-freeworld`.
   - NVIDIA → `sudo dnf install -y libva-nvidia-driver`.
   - ≥2 distinct vendors (hybrid/Optimus) → run ALL matched actions.
   - UNRECOGNIZED vendor → libva-utils only, then `die` naming the unmatched vendor (FR-009).
3. END-state check: `vainfo` exits 0 and reports a working driver. If NOT → `die` naming the
   GPU/driver (FR-004 — no silent success).
- `verify` (top-level): `vainfo >/dev/null 2>&1` succeeds (reports a working driver).

## Tests (`tests/va-hwaccel.bats`) — stubbed lspci/vainfo/dnf/rpm
- Intel (`STUB_GPU_VENDOR=intel`): `intel-media-driver` install attempted; verify GREEN when `STUB_VAINFO_OK=1`.
- AMD: the two mesa freeworld swaps attempted.
- NVIDIA: `libva-nvidia-driver` install attempted.
- Hybrid (`intel+nvidia`): BOTH the intel-media-driver AND libva-nvidia-driver actions attempted.
- Unrecognized (`unknown`): only libva-utils; module FAILS naming the unmatched vendor.
- vainfo-fails-after-install (`STUB_VAINFO_OK=0`): module FAILS naming the GPU/driver (not silent).
- idempotent re-run (verify GREEN ⇒ engine skip); unsupported-OS → engine failure.
