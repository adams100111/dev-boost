# Quickstart: validate system-resilience (hermetic)

All stubbed — no real driver/btrfs/firmware/MOK/systemd mutation.

## Tests
```sh
cd /home/dev/repos/dev-boost
bats tests/system.bats        # snapper/dnf-hook/grub-btrfs/btrfs*/fwupd/ppd/thermald/smartd/dnf-auto/restic/earlyoom
bats tests/nvidia.bats        # nvidia-akmod (CRC/nouveau/dracut) + secureboot-mok (state machine) + resign + cuda/vaapi/ctk
bats tests/gpu.bats           # gpu-detect + doctor --gpu
bats tests/optional-editors.bats
bats tests/profiles.bats      # system/hardware-nvidia/optional-editors membership + depsort
bats tests/cli.bats           # doctor --gpu dispatch; plain doctor unchanged
```

## What "green" proves
- snapshot stack → "Fedora snapshots" boot menu + pre/post dnf snapshots (SC-001).
- maintenance services/timers enabled; dnf-automatic security-only (SC-002).
- earlyoom protects dev procs, prefers desktop hogs (SC-003).
- gpu-detect auto-selects NVIDIA vs open path, no flag (SC-004).
- nvidia chain: akmod+CRC32+nouveau-blacklist+resign+MOK state machine; SB-off skips signing (SC-005).
- doctor --gpu green on healthy / non-zero naming the failed check (SC-006).
- full suite green; all stub-only (SC-007).
