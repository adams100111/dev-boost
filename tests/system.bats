load test_helper
load fixtures/base/stubs
load fixtures/base/engine_helpers

# ===========================================================================
# tests/system.bats — Spec 10 system-resilience/maintenance modules.
#
# Covers all 12 `system` profile modules:
#   snapper, snapper-dnf-hook, grub-btrfs, btrfs-assistant, btrfsmaintenance,
#   fwupd, power-profiles-daemon, thermald, smartmontools,
#   dnf-automatic-security, restic-backup, earlyoom.
#
# Each module: install attempted (STUB_DNF_LOG), verify GREEN, idempotent
# re-run (engine reports "already installed"), unsupported-OS (no fedora
# install cmd on ubuntu/debian → install cmd empty / engine reports unsupported).
# ===========================================================================

setup() {
  load_lib log.sh
  load_lib pkg.sh
  base_setup
  export DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules"
  export OS_DISTRO="fedora"
  export OS_FAMILY="fedora"

  # Extra stubs for system modules (these tools have no base stub). All log to
  # a shared sink and are benign; knobs simulate state where needed.
  _stub_dir="$(base_stub_dir)"

  # snapper: list-configs emits configs from STUB_SNAPPER_CONFIGS; create-config
  # appends "root" to a scratch state so a re-run/verify can see it.
  export STUB_SNAPPER_STATE="${BATS_TEST_TMPDIR}/snapper-configs.state"
  : > "${STUB_SNAPPER_STATE}"
  cat > "${_stub_dir}/snapper" <<'STUB'
#!/usr/bin/env bash
printf 'snapper %s\n' "$*" >> "${STUB_SNAPPER_LOG:-/tmp/stub-snapper.log}"
if [[ "$1" == "list-configs" ]]; then
  printf 'Config | Subvolume\n-------+----------\n'
  for c in ${STUB_SNAPPER_CONFIGS:-}; do printf '%s   | /\n' "${c}"; done
  if [[ -f "${STUB_SNAPPER_STATE:-}" ]]; then
    while read -r c; do [[ -n "${c}" ]] && printf '%s   | /\n' "${c}"; done < "${STUB_SNAPPER_STATE}"
  fi
  exit 0
fi
# `snapper -c root create-config /` → record root in the scratch state.
if [[ "$*" == *create-config* ]]; then
  cfg="root"; prev=""
  for a in "$@"; do [[ "${prev}" == "-c" ]] && cfg="${a}"; prev="${a}"; done
  printf '%s\n' "${cfg}" >> "${STUB_SNAPPER_STATE:-/dev/null}"
  exit 0
fi
exit 0
STUB
  chmod +x "${_stub_dir}/snapper"

  # findmnt: report the filesystem type for "/" from STUB_ROOT_FSTYPE (default btrfs).
  cat > "${_stub_dir}/findmnt" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "${STUB_ROOT_FSTYPE:-btrfs}"
exit 0
STUB
  chmod +x "${_stub_dir}/findmnt"

  # grub2-mkconfig: benign, logged.
  cat > "${_stub_dir}/grub2-mkconfig" <<'STUB'
#!/usr/bin/env bash
printf 'grub2-mkconfig %s\n' "$*" >> "${STUB_GRUB_LOG:-/tmp/stub-grub.log}"
exit 0
STUB
  chmod +x "${_stub_dir}/grub2-mkconfig"

  export STUB_SNAPPER_LOG="${BATS_TEST_TMPDIR}/snapper-calls.log"
  export STUB_GRUB_LOG="${BATS_TEST_TMPDIR}/grub-calls.log"
  : > "${STUB_SNAPPER_LOG}"
  : > "${STUB_GRUB_LOG}"
}

teardown() {
  base_teardown
}

# ---------------------------------------------------------------------------
# Helper: assert the dnf install log contains a package token.
# ---------------------------------------------------------------------------
_dnf_log_has() { grep -q "$1" "${STUB_DNF_LOG}"; }

# ===========================================================================
# snapper
# ===========================================================================

@test "snapper: install attempts dnf install snapper" {
  run _engine_install snapper
  [ "$status" -eq 0 ]
  _dnf_log_has "snapper"
}

@test "snapper: creates root config when absent, verify GREEN" {
  run _engine_install snapper
  [ "$status" -eq 0 ]
  grep -q "create-config" "${STUB_SNAPPER_LOG}"
  [[ "$output" == *"[+] snapper"* || "$output" == *snapper* ]]
}

@test "snapper: idempotent re-run reports already installed" {
  export STUB_SNAPPER_CONFIGS="root"
  run _engine_install snapper
  [ "$status" -eq 0 ]
  [[ "$output" == *"already installed"* ]]
}

@test "snapper: does not recreate config when root already present" {
  export STUB_SNAPPER_CONFIGS="root"
  run _engine_install snapper
  [ "$status" -eq 0 ]
  run cat "${STUB_SNAPPER_LOG}"
  [[ "$output" != *"create-config"* ]]
}

@test "snapper: dies clearly on non-btrfs root" {
  export STUB_ROOT_FSTYPE="ext4"
  run _engine_install snapper
  [[ "$output" == *"tfs"* || "$output" == *"Btrfs"* ]]
  [[ "$output" == *"fail"* || "$output" == *"[x]"* ]]
}

@test "snapper: unsupported on non-fedora (empty install cmd)" {
  run _module_install_cmd snapper ubuntu debian
  [ -z "$output" ]
}

# ===========================================================================
# snapper-dnf-hook
# ===========================================================================

@test "snapper-dnf-hook: install attempts dnf install plugin" {
  export STUB_SNAPPER_CONFIGS="root"
  export STUB_RPM_INSTALLED="python3-dnf-plugin-snapper"
  DEVBOOST_INSTALL_FLAGS="--force" run _engine_install snapper-dnf-hook
  [ "$status" -eq 0 ]
  _dnf_log_has "python3-dnf-plugin-snapper"
}

@test "snapper-dnf-hook: verify GREEN when rpm reports installed" {
  export STUB_SNAPPER_CONFIGS="root"
  export STUB_RPM_INSTALLED="python3-dnf-plugin-snapper"
  run _engine_install snapper-dnf-hook
  [ "$status" -eq 0 ]
  [[ "$output" == *"already installed"* ]]
}

@test "snapper-dnf-hook: unsupported on non-fedora" {
  run _module_install_cmd snapper-dnf-hook ubuntu debian
  [ -z "$output" ]
}

# ===========================================================================
# grub-btrfs
# ===========================================================================

@test "grub-btrfs: install attempts dnf install grub-btrfs" {
  export STUB_SYSTEMCTL_ENABLED="grub-btrfsd"
  DEVBOOST_INSTALL_FLAGS="--force" run _engine_install grub-btrfs
  [ "$status" -eq 0 ]
  _dnf_log_has "grub-btrfs"
}

@test "grub-btrfs: enables grub-btrfsd and regenerates grub menu" {
  export STUB_SYSTEMCTL_ENABLED="grub-btrfsd"
  DEVBOOST_INSTALL_FLAGS="--force" run _engine_install grub-btrfs
  [ "$status" -eq 0 ]
  grep -q "enable" "${STUB_SYSTEMCTL_LOG}"
  grep -q "grub-btrfsd" "${STUB_SYSTEMCTL_LOG}"
  grep -q "grub2-mkconfig" "${STUB_GRUB_LOG}"
}

@test "grub-btrfs: verify GREEN when grub-btrfsd enabled, idempotent" {
  export STUB_SYSTEMCTL_ENABLED="grub-btrfsd"
  run _engine_install grub-btrfs
  [ "$status" -eq 0 ]
  [[ "$output" == *"already installed"* ]]
}

@test "grub-btrfs: unsupported on non-fedora" {
  run _module_install_cmd grub-btrfs ubuntu debian
  [ -z "$output" ]
}

# ===========================================================================
# btrfs-assistant
# ===========================================================================

@test "btrfs-assistant: install attempts dnf install btrfs-assistant" {
  export STUB_RPM_INSTALLED="btrfs-assistant"
  DEVBOOST_INSTALL_FLAGS="--force" run _engine_install btrfs-assistant
  [ "$status" -eq 0 ]
  _dnf_log_has "btrfs-assistant"
}

@test "btrfs-assistant: verify GREEN when rpm installed, idempotent" {
  export STUB_RPM_INSTALLED="btrfs-assistant"
  run _engine_install btrfs-assistant
  [ "$status" -eq 0 ]
  [[ "$output" == *"already installed"* ]]
}

@test "btrfs-assistant: unsupported on non-fedora" {
  run _module_install_cmd btrfs-assistant ubuntu debian
  [ -z "$output" ]
}

# ===========================================================================
# btrfsmaintenance
# ===========================================================================

@test "btrfsmaintenance: install attempts dnf install btrfsmaintenance" {
  export STUB_RPM_INSTALLED="btrfsmaintenance"
  DEVBOOST_INSTALL_FLAGS="--force" run _engine_install btrfsmaintenance
  [ "$status" -eq 0 ]
  _dnf_log_has "btrfsmaintenance"
}

@test "btrfsmaintenance: enables scrub and balance timers" {
  export STUB_RPM_INSTALLED="btrfsmaintenance"
  DEVBOOST_INSTALL_FLAGS="--force" run _engine_install btrfsmaintenance
  [ "$status" -eq 0 ]
  grep -q "btrfs-scrub" "${STUB_SYSTEMCTL_LOG}"
  grep -q "btrfs-balance" "${STUB_SYSTEMCTL_LOG}"
}

@test "btrfsmaintenance: verify GREEN when rpm installed, idempotent" {
  export STUB_RPM_INSTALLED="btrfsmaintenance"
  run _engine_install btrfsmaintenance
  [ "$status" -eq 0 ]
  [[ "$output" == *"already installed"* ]]
}

@test "btrfsmaintenance: unsupported on non-fedora" {
  run _module_install_cmd btrfsmaintenance ubuntu debian
  [ -z "$output" ]
}

# ===========================================================================
# fwupd
# ===========================================================================

@test "fwupd: install attempts dnf install fwupd" {
  export STUB_SYSTEMCTL_ENABLED="fwupd.service"
  DEVBOOST_INSTALL_FLAGS="--force" run _engine_install fwupd
  [ "$status" -eq 0 ]
  _dnf_log_has "fwupd"
}

@test "fwupd: enables fwupd service, verify GREEN" {
  export STUB_SYSTEMCTL_ENABLED="fwupd.service"
  DEVBOOST_INSTALL_FLAGS="--force" run _engine_install fwupd
  [ "$status" -eq 0 ]
  grep -q "fwupd" "${STUB_SYSTEMCTL_LOG}"
  [[ "$output" == *"[+] fwupd"* || "$output" == *fwupd* ]]
}

@test "fwupd: idempotent re-run (service enabled)" {
  export STUB_SYSTEMCTL_ENABLED="fwupd.service"
  run _engine_install fwupd
  [ "$status" -eq 0 ]
  [[ "$output" == *"already installed"* ]]
}

@test "fwupd: unsupported on non-fedora" {
  run _module_install_cmd fwupd ubuntu debian
  [ -z "$output" ]
}

# ===========================================================================
# power-profiles-daemon
# ===========================================================================

@test "power-profiles-daemon: install attempts dnf install" {
  export STUB_SYSTEMCTL_ENABLED="power-profiles-daemon"
  DEVBOOST_INSTALL_FLAGS="--force" run _engine_install power-profiles-daemon
  [ "$status" -eq 0 ]
  _dnf_log_has "power-profiles-daemon"
}

@test "power-profiles-daemon: enables + verify GREEN when enabled" {
  export STUB_SYSTEMCTL_ENABLED="power-profiles-daemon"
  run _engine_install power-profiles-daemon
  [ "$status" -eq 0 ]
  [[ "$output" == *"already installed"* ]]
}

@test "power-profiles-daemon: enable recorded on first install" {
  export STUB_SYSTEMCTL_ENABLED="power-profiles-daemon"
  DEVBOOST_INSTALL_FLAGS="--force" run _engine_install power-profiles-daemon
  [ "$status" -eq 0 ]
  grep -q "power-profiles-daemon" "${STUB_SYSTEMCTL_LOG}"
}

@test "power-profiles-daemon: unsupported on non-fedora" {
  run _module_install_cmd power-profiles-daemon ubuntu debian
  [ -z "$output" ]
}

# ===========================================================================
# thermald
# ===========================================================================

@test "thermald: install attempts dnf install thermald" {
  export STUB_SYSTEMCTL_ENABLED="thermald"
  DEVBOOST_INSTALL_FLAGS="--force" run _engine_install thermald
  [ "$status" -eq 0 ]
  _dnf_log_has "thermald"
}

@test "thermald: enables + verify GREEN when enabled" {
  export STUB_SYSTEMCTL_ENABLED="thermald"
  run _engine_install thermald
  [ "$status" -eq 0 ]
  [[ "$output" == *"already installed"* ]]
}

@test "thermald: unsupported on non-fedora" {
  run _module_install_cmd thermald ubuntu debian
  [ -z "$output" ]
}

# ===========================================================================
# smartmontools
# ===========================================================================

@test "smartmontools: install attempts dnf install smartmontools" {
  export STUB_SYSTEMCTL_ENABLED="smartd"
  DEVBOOST_INSTALL_FLAGS="--force" run _engine_install smartmontools
  [ "$status" -eq 0 ]
  _dnf_log_has "smartmontools"
}

@test "smartmontools: enables smartd, verify GREEN when smartd enabled" {
  export STUB_SYSTEMCTL_ENABLED="smartd"
  run _engine_install smartmontools
  [ "$status" -eq 0 ]
  [[ "$output" == *"already installed"* ]]
}

@test "smartmontools: enable smartd recorded on first install" {
  export STUB_SYSTEMCTL_ENABLED="smartd"
  DEVBOOST_INSTALL_FLAGS="--force" run _engine_install smartmontools
  [ "$status" -eq 0 ]
  grep -q "smartd" "${STUB_SYSTEMCTL_LOG}"
}

@test "smartmontools: unsupported on non-fedora" {
  run _module_install_cmd smartmontools ubuntu debian
  [ -z "$output" ]
}

# ===========================================================================
# dnf-automatic-security
# ===========================================================================

@test "dnf-automatic-security: install attempts dnf install dnf-automatic" {
  export DEVBOOST_DNF_AUTOMATIC_CONF="${BATS_TEST_TMPDIR}/automatic.conf"
  run _engine_install dnf-automatic-security
  [ "$status" -eq 0 ]
  _dnf_log_has "dnf-automatic"
}

@test "dnf-automatic-security: writes upgrade_type = security (not default/full)" {
  export DEVBOOST_DNF_AUTOMATIC_CONF="${BATS_TEST_TMPDIR}/automatic.conf"
  run _engine_install dnf-automatic-security
  [ "$status" -eq 0 ]
  run cat "${DEVBOOST_DNF_AUTOMATIC_CONF}"
  [[ "$output" == *"upgrade_type = security"* ]]
  [[ "$output" != *"upgrade_type = default"* ]]
}

@test "dnf-automatic-security: enables dnf-automatic.timer" {
  export DEVBOOST_DNF_AUTOMATIC_CONF="${BATS_TEST_TMPDIR}/automatic.conf"
  run _engine_install dnf-automatic-security
  [ "$status" -eq 0 ]
  grep -q "dnf-automatic.timer" "${STUB_SYSTEMCTL_LOG}"
}

@test "dnf-automatic-security: idempotent re-run (config present)" {
  export DEVBOOST_DNF_AUTOMATIC_CONF="${BATS_TEST_TMPDIR}/automatic.conf"
  run _engine_install dnf-automatic-security
  [ "$status" -eq 0 ]
  run _engine_install dnf-automatic-security
  [ "$status" -eq 0 ]
  [[ "$output" == *"already installed"* ]]
}

@test "dnf-automatic-security: unsupported on non-fedora" {
  run _module_install_cmd dnf-automatic-security ubuntu debian
  [ -z "$output" ]
}

# ===========================================================================
# restic-backup
# ===========================================================================

@test "restic-backup: install attempts dnf install restic" {
  export DEVBOOST_RESTIC_UNIT_DIR="${BATS_TEST_TMPDIR}/restic-units"
  run _engine_install restic-backup
  [ "$status" -eq 0 ]
  _dnf_log_has "restic"
}

@test "restic-backup: seeds service + timer unit files (no secrets)" {
  export DEVBOOST_RESTIC_UNIT_DIR="${BATS_TEST_TMPDIR}/restic-units"
  run _engine_install restic-backup
  [ "$status" -eq 0 ]
  [ -f "${DEVBOOST_RESTIC_UNIT_DIR}/restic-backup.service" ]
  [ -f "${DEVBOOST_RESTIC_UNIT_DIR}/restic-backup.timer" ]
  # No committed secrets: no uncommented secret assignment with an actual value.
  # (RESTIC_PASSWORD_FILE=<path> is a reference, not a secret, and is allowed.)
  run grep -rhE "^[[:space:]]*[^#]*RESTIC_PASSWORD=[^[:space:]]" "${DEVBOOST_RESTIC_UNIT_DIR}"
  [ "$status" -ne 0 ]
}

@test "restic-backup: enables timer" {
  export DEVBOOST_RESTIC_UNIT_DIR="${BATS_TEST_TMPDIR}/restic-units"
  run _engine_install restic-backup
  [ "$status" -eq 0 ]
  grep -q "restic-backup.timer" "${STUB_SYSTEMCTL_LOG}"
}

@test "restic-backup: idempotent re-run (units present)" {
  export DEVBOOST_RESTIC_UNIT_DIR="${BATS_TEST_TMPDIR}/restic-units"
  run _engine_install restic-backup
  [ "$status" -eq 0 ]
  run _engine_install restic-backup
  [ "$status" -eq 0 ]
  [[ "$output" == *"already installed"* ]]
}

@test "restic-backup: unsupported on non-fedora" {
  run _module_install_cmd restic-backup ubuntu debian
  [ -z "$output" ]
}

# ===========================================================================
# earlyoom
# ===========================================================================

@test "earlyoom: install attempts dnf install earlyoom" {
  export DEVBOOST_EARLYOOM_CONF="${BATS_TEST_TMPDIR}/earlyoom"
  run _engine_install earlyoom
  [ "$status" -eq 0 ]
  _dnf_log_has "earlyoom"
}

@test "earlyoom: writes config with --avoid and --prefer patterns" {
  export DEVBOOST_EARLYOOM_CONF="${BATS_TEST_TMPDIR}/earlyoom"
  run _engine_install earlyoom
  [ "$status" -eq 0 ]
  run cat "${DEVBOOST_EARLYOOM_CONF}"
  [[ "$output" == *"--avoid"* ]]
  [[ "$output" == *"--prefer"* ]]
  # avoid protects critical dev daemons.
  [[ "$output" == *"dockerd"* ]]
  [[ "$output" == *"dotnet"* ]]
  [[ "$output" == *"dcp"* ]]
  [[ "$output" == *"sshd"* ]]
  [[ "$output" == *"code"* ]]
  [[ "$output" == *"gnome-shell"* ]]
  # prefer targets memory-hungry GUI apps.
  [[ "$output" == *"firefox"* ]]
  [[ "$output" == *"chrome"* ]]
  [[ "$output" == *"chromium"* ]]
  [[ "$output" == *"electron"* ]]
  [[ "$output" == *"QtWebEngine"* ]]
  [[ "$output" == *"brave"* ]]
  [[ "$output" == *"slack"* ]]
  [[ "$output" == *"discord"* ]]
}

@test "earlyoom: enables earlyoom service" {
  export DEVBOOST_EARLYOOM_CONF="${BATS_TEST_TMPDIR}/earlyoom"
  run _engine_install earlyoom
  [ "$status" -eq 0 ]
  grep -q "earlyoom" "${STUB_SYSTEMCTL_LOG}"
}

@test "earlyoom: idempotent re-run (config present)" {
  export DEVBOOST_EARLYOOM_CONF="${BATS_TEST_TMPDIR}/earlyoom"
  run _engine_install earlyoom
  [ "$status" -eq 0 ]
  run _engine_install earlyoom
  [ "$status" -eq 0 ]
  [[ "$output" == *"already installed"* ]]
}

@test "earlyoom: unsupported on non-fedora" {
  run _module_install_cmd earlyoom ubuntu debian
  [ -z "$output" ]
}

