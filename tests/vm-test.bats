load test_helper
load fixtures/base/stubs

# scripts/vm-test.sh — hermetic: virt-install/virsh/virt-viewer stubbed; no real VM created.

setup() {
  load_lib log.sh
  base_setup
  # libvirt tool stubs in the stub bin dir (on PATH via base_setup).
  cat > "$(base_stub_dir)/virt-install" <<'STUB'
#!/usr/bin/env bash
printf 'virt-install %s\n' "$*" >> "${STUB_VI_LOG:?}"
exit 0
STUB
  cat > "$(base_stub_dir)/virsh" <<'STUB'
#!/usr/bin/env bash
printf 'virsh %s\n' "$*" >> "${STUB_VIRSH_LOG:?}"
for a in "$@"; do
  if [[ "$a" == "dominfo" ]]; then
    [[ "${STUB_VM_EXISTS:-0}" == "1" ]] && exit 0 || exit 1
  fi
done
exit 0
STUB
  cat > "$(base_stub_dir)/virt-viewer" <<'STUB'
#!/usr/bin/env bash
printf 'virt-viewer %s\n' "$*" >> "${STUB_VIRSH_LOG:?}"; exit 0
STUB
  chmod +x "$(base_stub_dir)"/virt-install "$(base_stub_dir)"/virsh "$(base_stub_dir)"/virt-viewer
  export STUB_VI_LOG="${BATS_TEST_TMPDIR}/vi.log"; : > "${STUB_VI_LOG}"
  export STUB_VIRSH_LOG="${BATS_TEST_TMPDIR}/virsh.log"; : > "${STUB_VIRSH_LOG}"
  export VM_NAME="bats-vm"
}
teardown() { base_teardown; }

_vm() {
  bash -c "
    export HOME='${HOME}'; export PATH='${PATH}'; export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export STUB_VI_LOG='${STUB_VI_LOG}'; export STUB_VIRSH_LOG='${STUB_VIRSH_LOG}'
    export VM_NAME='${VM_NAME}'; export STUB_VM_EXISTS='${STUB_VM_EXISTS:-0}'
    bash '${DEVBOOST_ROOT}/scripts/vm-test.sh' $*
  " 2>&1
}

# --- engine mode ---------------------------------------------------------------
@test "engine: requires --iso" {
  run _vm engine
  [ "$status" -ne 0 ]; [[ "$output" == *"--iso"* ]]
}
@test "engine: builds a UEFI virtio session VM from the Live ISO" {
  iso="${BATS_TEST_TMPDIR}/Fedora-Live.iso"; : > "$iso"
  run _vm engine --iso "$iso"
  [ "$status" -eq 0 ]
  grep -q -- '--boot uefi' "${STUB_VI_LOG}"
  grep -q -- '--connect qemu:///session' "${STUB_VI_LOG}"
  grep -q -- "--cdrom ${iso}" "${STUB_VI_LOG}"
  grep -q 'bus=virtio' "${STUB_VI_LOG}"
  grep -q -- '--name bats-vm' "${STUB_VI_LOG}"
}
@test "engine: refuses an existing VM unless --recreate" {
  iso="${BATS_TEST_TMPDIR}/i.iso"; : > "$iso"
  STUB_VM_EXISTS=1 run _vm engine --iso "$iso"
  [ "$status" -ne 0 ]; [[ "$output" == *"already exists"* ]]
  ! grep -q 'virt-install' "${STUB_VI_LOG}"
}
@test "engine: --recreate destroys then recreates" {
  iso="${BATS_TEST_TMPDIR}/i.iso"; : > "$iso"
  STUB_VM_EXISTS=1 run _vm engine --iso "$iso" --recreate
  [ "$status" -eq 0 ]
  grep -q 'undefine --nvram bats-vm' "${STUB_VIRSH_LOG}"
  grep -q 'virt-install' "${STUB_VI_LOG}"
}

# --- usb mode ------------------------------------------------------------------
@test "usb: errors when neither --device nor --kickstart given" {
  run _vm usb
  [ "$status" -ne 0 ]; [[ "$output" == *"--device"* && "$output" == *"--kickstart"* ]]
}
@test "usb --device: rejects a non-block path" {
  run _vm usb --device "${BATS_TEST_TMPDIR}/notadev"
  [ "$status" -ne 0 ]; [[ "$output" == *"not a block device"* ]]
}
@test "usb --kickstart: drives ventoy/ks.cfg on a SATA disk (device-less zero-touch)" {
  iso="${BATS_TEST_TMPDIR}/netinst.iso"; : > "$iso"
  run _vm usb --kickstart "$iso"
  [ "$status" -eq 0 ]
  grep -q -- "--location ${iso}" "${STUB_VI_LOG}"
  grep -q 'initrd-inject .*ventoy/ks.cfg' "${STUB_VI_LOG}"
  grep -q 'inst.ks=file:/ks.cfg' "${STUB_VI_LOG}"
  grep -q 'bus=sata' "${STUB_VI_LOG}"
}
@test "usb --kickstart: rejects a missing ISO" {
  run _vm usb --kickstart "${BATS_TEST_TMPDIR}/missing.iso"
  [ "$status" -ne 0 ]; [[ "$output" == *"not found"* ]]
}

# --- lifecycle -----------------------------------------------------------------
@test "destroy: undefines with storage removal" {
  STUB_VM_EXISTS=1 run _vm destroy
  [ "$status" -eq 0 ]
  grep -q 'undefine --nvram --remove-all-storage bats-vm' "${STUB_VIRSH_LOG}"
}
@test "help: usage lists engine + usb" {
  run _vm help
  [ "$status" -eq 0 ]; [[ "$output" == *"engine"* && "$output" == *"usb"* ]]
}
