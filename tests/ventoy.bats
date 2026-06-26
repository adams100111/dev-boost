load test_helper
load fixtures/base/stubs

# Spec 11 — ventoy USB artifacts: make-usb.sh safety + ventoy.json + ks.cfg layout + firstboot service.
# Hermetic: lsblk/ventoy stubbed; no real disk/USB mutation.

setup() {
  load_lib log.sh
  base_setup
  base_install_usb_stubs
  export STUB_VENTOY_LOG="${BATS_TEST_TMPDIR}/ventoy-calls.log"; : > "${STUB_VENTOY_LOG}"
  V="${DEVBOOST_ROOT}/ventoy"
  # A fake block device the script will accept as -b (bats can't make a real one; shadow the -b test
  # by pointing at an existing char/file and relying on the lsblk stub — see _run_makeusb).
}
teardown() { base_teardown; }

# Run make-usb.sh with a fake "block device" by pre-creating a file and bind-checking via stubs.
# make-usb.sh uses `[[ -b dev ]]`; we use /dev/loopX-style path that the lsblk stub classifies via knobs.
_run_makeusb() {
  bash -c "
    export PATH='${PATH}'
    export USER='tester'
    export VTOY_MOUNT='${BATS_TEST_TMPDIR}/VTOY'
    export STUB_VENTOY_LOG='${STUB_VENTOY_LOG}'
    export STUB_LSBLK_TYPE='${STUB_LSBLK_TYPE:-disk}'
    export STUB_LSBLK_RM='${STUB_LSBLK_RM:-1}'
    export STUB_LSBLK_MOUNT='${STUB_LSBLK_MOUNT:-}'
    # neuter the [[ -b ]] check by providing a 'test' shim? No — use a real block dev if present, else
    # the script's -b guard runs first. We point at /dev/null-style; instead override with a wrapper.
    bash '${DEVBOOST_ROOT}/ventoy/make-usb.sh' $*
  " 2>&1
}

# Because `[[ -b ]]` needs a real block device, exercise the guard logic by sourcing the script's
# checks via a tiny harness is overkill; instead use an existing block device on the host if any,
# else skip the happy-path device check and assert on lsblk-driven refusals using a known block dev.
_blockdev() { ls /dev/loop0 /dev/sda /dev/vda /dev/nvme0n1 2>/dev/null | head -1; }

@test "make-usb: refuses a non-removable disk (no ventoy call)" {
  bd="$(_blockdev)"; [ -n "$bd" ] || skip "no block device available on host"
  STUB_LSBLK_RM=0 run _run_makeusb "$bd" --yes
  [ "$status" -ne 0 ]
  [[ "$output" == *"not a removable"* ]]
  ! grep -q 'ventoy' "${STUB_VENTOY_LOG}"
}

@test "make-usb: refuses a partition/loop (type != disk)" {
  bd="$(_blockdev)"; [ -n "$bd" ] || skip "no block device available on host"
  STUB_LSBLK_TYPE=part run _run_makeusb "$bd" --yes
  [ "$status" -ne 0 ]
  [[ "$output" == *"not a whole disk"* ]]
  ! grep -q 'ventoy' "${STUB_VENTOY_LOG}"
}

@test "make-usb: refuses a mounted (system) disk" {
  bd="$(_blockdev)"; [ -n "$bd" ] || skip "no block device available on host"
  STUB_LSBLK_MOUNT=/ run _run_makeusb "$bd" --yes
  [ "$status" -ne 0 ]
  [[ "$output" == *"mounted"* ]]
  ! grep -q 'ventoy' "${STUB_VENTOY_LOG}"
}

@test "make-usb: refuses a non-block path before touching anything" {
  run _run_makeusb "${BATS_TEST_TMPDIR}/notadev" --yes
  [ "$status" -ne 0 ]
  [[ "$output" == *"not a block device"* ]]
}

@test "make-usb: removable + --yes → installs ventoy and lays out the USB tree" {
  bd="$(_blockdev)"; [ -n "$bd" ] || skip "no block device available on host"
  STUB_LSBLK_TYPE=disk STUB_LSBLK_RM=1 STUB_LSBLK_MOUNT="" run _run_makeusb "$bd" --yes
  [ "$status" -eq 0 ]
  grep -q "ventoy -i ${bd}" "${STUB_VENTOY_LOG}"
  for d in ISO Bootstrap Installers Backups ventoy; do [ -d "${BATS_TEST_TMPDIR}/VTOY/${d}" ]; done
  [ -f "${BATS_TEST_TMPDIR}/VTOY/ventoy/ventoy.json" ]
  [ -f "${BATS_TEST_TMPDIR}/VTOY/Bootstrap/ks.cfg" ]
}

@test "make-usb: --update uses ventoy -u (no wipe path)" {
  bd="$(_blockdev)"; [ -n "$bd" ] || skip "no block device available on host"
  run _run_makeusb "$bd" --update --yes
  [ "$status" -eq 0 ]
  grep -q "ventoy -u ${bd}" "${STUB_VENTOY_LOG}"
}

# --- ventoy.json ---------------------------------------------------------------
@test "ventoy.json: valid JSON binding ks.cfg + injection to the Fedora ISO" {
  run jq -e . "${DEVBOOST_ROOT}/ventoy/ventoy.json"
  [ "$status" -eq 0 ]
  [ "$(jq -r '.auto_install[0].template' "${DEVBOOST_ROOT}/ventoy/ventoy.json")" = "/Bootstrap/ks.cfg" ]
  [ "$(jq -r '.injection[0].archive' "${DEVBOOST_ROOT}/ventoy/ventoy.json")" = "/Bootstrap/devboost.tar.gz" ]
  jq -e '.control[] | select(.VTOY_MENU_TIMEOUT)' "${DEVBOOST_ROOT}/ventoy/ventoy.json" >/dev/null
}

# --- ks.cfg §10c layout --------------------------------------------------------
@test "ks.cfg: §10c subvolumes incl. mandatory var/lib/gdm + non-snapshot set" {
  k="${DEVBOOST_ROOT}/ventoy/ks.cfg"
  grep -qE 'btrfs / .*--name=root' "$k"
  grep -qE 'btrfs /home .*--name=home' "$k"
  grep -q '/var/lib/gdm' "$k"
  for s in /opt /var/cache /var/log /var/spool /var/tmp /var/lib/containers /var/lib/flatpak /var/lib/libvirt; do
    grep -q "$s" "$k" || { echo "missing subvol $s"; return 1; }
  done
}
@test "ks.cfg: compress=zstd:1 on btrfs mounts and NO swap partition" {
  k="${DEVBOOST_ROOT}/ventoy/ks.cfg"
  grep -q 'compress=zstd:1' "$k"
  ! grep -qE '^part swap|^swap ' "$k"
  grep -qE 'part /boot/efi' "$k"
}
@test "ks.cfg: minimal %packages (git+python3+jq) and %post enables firstboot" {
  k="${DEVBOOST_ROOT}/ventoy/ks.cfg"
  grep -q '^git$' "$k"; grep -q '^python3$' "$k"; grep -q '^jq$' "$k"
  grep -q 'systemctl enable devboost-firstboot.service' "$k"
}

# --- firstboot service ---------------------------------------------------------
@test "devboost-firstboot.service: oneshot running the devboost binary, self-disabling" {
  s="${DEVBOOST_ROOT}/ventoy/devboost-firstboot.service"
  grep -q 'Type=oneshot' "$s"
  grep -q '/opt/dev-boost/devboost install full' "$s"
  grep -q 'DEVBOOST_SECRETS=' "$s"
  grep -q '/var/log/devboost-firstboot.log' "$s"
  grep -q 'systemctl disable devboost-firstboot.service' "$s"
}
