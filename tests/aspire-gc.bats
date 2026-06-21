load test_helper
load fixtures/base/stubs
load fixtures/base/engine_helpers

# Spec 9 US6 — aspire-gc module: hourly `devboost dev gc` systemd --user timer.

setup() {
  load_lib log.sh
  load_lib pkg.sh
  base_setup
  export DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules"
}
teardown() { base_teardown; }

_run_install() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export STUB_SYSTEMCTL_LOG='${STUB_SYSTEMCTL_LOG}'
    export STUB_LOGINCTL_LOG='${STUB_LOGINCTL_LOG}'
    bash '${DEVBOOST_ROOT}/modules/aspire-gc/install.sh'
  " 2>&1
}
_run_verify() {
  bash -c "export HOME='${HOME}'; export DEVBOOST_ROOT='${DEVBOOST_ROOT}'; bash '${DEVBOOST_ROOT}/modules/aspire-gc/verify.sh'" 2>&1
}

@test "aspire-gc: installs hourly timer + oneshot service running 'devboost dev gc'" {
  run _run_install
  [ "$status" -eq 0 ]
  ud="${HOME}/.config/systemd/user"
  grep -q 'OnCalendar=hourly' "${ud}/aspire-gc.timer"
  grep -q 'Persistent=true' "${ud}/aspire-gc.timer"
  grep -q 'Type=oneshot' "${ud}/aspire-gc.service"
  grep -q 'dev gc' "${ud}/aspire-gc.service"
}

@test "aspire-gc: enables timer + linger" {
  _run_install
  grep -q 'enable --now aspire-gc.timer' "${STUB_SYSTEMCTL_LOG}"
  grep -q 'enable-linger' "${STUB_LOGINCTL_LOG}"
}

@test "aspire-gc: verify RED before install, GREEN after; idempotent" {
  run _run_verify
  [ "$status" -ne 0 ]
  _run_install
  run _run_verify
  [ "$status" -eq 0 ]
  _run_install   # idempotent re-run
  [ -f "${HOME}/.config/systemd/user/aspire-gc.timer" ]
}

@test "aspire-gc: unsupported-OS — no install command on non-fedora" {
  run _module_install_cmd aspire-gc ubuntu debian
  [ -z "$output" ]
}

@test "aspire-gc: module metadata — category dev-hygiene, requires docker" {
  grep -q 'category    = "dev-hygiene"' "${DEVBOOST_ROOT}/modules/aspire-gc/module.toml"
  grep -q 'requires    = \["docker"\]' "${DEVBOOST_ROOT}/modules/aspire-gc/module.toml"
}
