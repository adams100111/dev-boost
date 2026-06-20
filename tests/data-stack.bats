load test_helper
load fixtures/base/stubs
load fixtures/base/engine_helpers

setup() {
  load_lib log.sh
  load_lib pkg.sh
  base_setup
  export DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules"
  export COMPOSE="${DEVBOOST_ROOT}/templates/data/compose.yaml"
}

teardown() {
  base_teardown
}

# --- helpers ------------------------------------------------------------------

_run_data() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    bash '${DEVBOOST_ROOT}/modules/data-services/install.sh'
  " 2>&1
}

_run_verify_data() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    bash '${DEVBOOST_ROOT}/modules/data-services/verify.sh'
  " 2>&1
}

# ===========================================================================
# compose.yaml assets (containers-only persistence)
# ===========================================================================

@test "data: compose.yaml present and references pinned images" {
  [ -f "${COMPOSE}" ]
  grep -q 'postgres:18' "${COMPOSE}"
  grep -q 'valkey/valkey:8.1' "${COMPOSE}"
  grep -q 'dbgate/dbgate:7.2.0' "${COMPOSE}"
}

@test "data: compose.yaml declares the three named persistence volumes" {
  grep -q 'pgdata' "${COMPOSE}"
  grep -q 'valkeydata' "${COMPOSE}"
  grep -q 'dbgatedata' "${COMPOSE}"
}

@test "data: README documents docker compose up + dbgate :3000" {
  local readme="${DEVBOOST_ROOT}/templates/data/README.md"
  [ -f "${readme}" ]
  grep -q 'docker compose up -d' "${readme}"
  grep -q '3000' "${readme}"
}

# ===========================================================================
# install.sh — assets-only, no host database install
# ===========================================================================

@test "data: install succeeds and verify GREEN" {
  run _run_data
  [ "$status" -eq 0 ]
  run _run_verify_data
  [ "$status" -eq 0 ]
}

@test "data: install does NOT dnf-install a host postgres/redis service" {
  run _run_data
  [ "$status" -eq 0 ]
  ! grep -q 'postgresql-server' "${STUB_DNF_LOG}"
  ! grep -q 'redis' "${STUB_DNF_LOG}"
}

@test "data: install is idempotent — compose.yaml is not rewritten" {
  local h1; h1="$(sha256sum "${COMPOSE}")"
  run _run_data
  [ "$status" -eq 0 ]
  local h2; h2="$(sha256sum "${COMPOSE}")"
  [ "${h1}" = "${h2}" ]
}

# ===========================================================================
# Module metadata + engine gating
# ===========================================================================

@test "data: module requires docker" {
  grep -q 'requires' "${DEVBOOST_ROOT}/modules/data-services/module.toml"
  grep -Eq 'requires[[:space:]]*=.*"docker"' "${DEVBOOST_ROOT}/modules/data-services/module.toml"
}

@test "data: module [install] only targets fedora" {
  run _module_install_cmd data-services fedora fedora
  [ "$status" -eq 0 ]
  [[ "$output" == *"modules/data-services/install.sh"* ]]
}

@test "data: unsupported-OS — engine reports failure on non-fedora" {
  # --force bypasses the idempotency guard so the OS-gating (no [install].<os>)
  # path is exercised: data-services is fedora-only, so on ubuntu/debian the
  # engine has no install command and reports it unsupported.
  DEVBOOST_INSTALL_FLAGS="--force" run _engine_install data-services ubuntu debian
  [ "$status" -ne 0 ]
  [[ "$output" == *"unsupported"* ]]
}
