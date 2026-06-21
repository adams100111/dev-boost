# Contract: gpu-detect module + doctor --gpu (FR-005, FR-011)

## gpu-detect (in full)
- lspci → vendor (reuse va-hwaccel detection + STUB_GPU_VENDOR). NVIDIA present → log/select
  hardware-nvidia path (write a marker workstation-config/gpu.selected=nvidia); Intel/AMD → open path
  (selected=open); unrecognized → named report. verify: a selection was recorded.
- Tests: STUB_GPU_VENDOR=nvidia → selects nvidia; =intel/=amd → open, no nvidia pkgs; intel+nvidia →
  nvidia; unknown → reported.

## doctor --gpu (lib/gpu.sh gpu_doctor; bin/devboost cmd_doctor --gpu)
- checks: modprobe nvidia load test (STUB_MODPROBE_FAIL), nouveau blacklisted (file present),
  initramfs has nvidia (stub/knob), module signature present (stub), dmesg taint/lockdown/pkcs#7 scan
  (STUB_DMESG). Report each; non-zero if any fails.
- plain `devboost doctor` (no --gpu) behavior UNCHANGED.
- Tests (tests/gpu.bats + tests/cli.bats): healthy stubs → exit 0; nouveau-present/modprobe-fail → non-zero+names it.
