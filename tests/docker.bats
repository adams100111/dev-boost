load test_helper
load fixtures/base/stubs

# ---------------------------------------------------------------------------
# Setup / teardown
# ---------------------------------------------------------------------------
setup() {
  load_lib log.sh
  load_lib pkg.sh
  base_setup

  export DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules"
  export OS_DISTRO="fedora"
  export OS_FAMILY="fedora"
  export USER="${USER:-testuser}"

  # Install a minimal docker stub so `command -v docker` succeeds by default.
  cat > "$(base_stub_dir)/docker" <<'DOCKERSTUB'
#!/usr/bin/env bash
exit 0
DOCKERSTUB
  chmod +x "$(base_stub_dir)/docker"
}

teardown() {
  base_teardown
}

# ---------------------------------------------------------------------------
# Helper: run docker install.sh in a subshell with the full stub env.
# ---------------------------------------------------------------------------
_run_docker_install() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export USER='${USER:-testuser}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_SUDO_LOG='${STUB_SUDO_LOG}'
    export STUB_SYSTEMCTL_LOG='${STUB_SYSTEMCTL_LOG}'
    export STUB_USERMOD_LOG='${STUB_USERMOD_LOG}'
    export STUB_GETENT_LOG='${STUB_GETENT_LOG}'
    export STUB_SYSTEMCTL_ENABLED='${STUB_SYSTEMCTL_ENABLED:-}'
    export STUB_GETENT_DOCKER_USERS='${STUB_GETENT_DOCKER_USERS:-}'
    bash '${DEVBOOST_ROOT}/modules/docker/install.sh'
  " 2>&1
}

# ---------------------------------------------------------------------------
# Helper: run the engine against the docker module.
# ---------------------------------------------------------------------------
_engine_run_docker() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export USER='${USER:-testuser}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_DNF_LOG='${STUB_DNF_LOG}'
    export STUB_SUDO_LOG='${STUB_SUDO_LOG}'
    export STUB_SYSTEMCTL_LOG='${STUB_SYSTEMCTL_LOG}'
    export STUB_USERMOD_LOG='${STUB_USERMOD_LOG}'
    export STUB_GETENT_LOG='${STUB_GETENT_LOG}'
    export STUB_SYSTEMCTL_ENABLED='${STUB_SYSTEMCTL_ENABLED:-}'
    export STUB_GETENT_DOCKER_USERS='${STUB_GETENT_DOCKER_USERS:-}'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    source '${DEVBOOST_ROOT}/lib/depsort.sh'
    source '${DEVBOOST_ROOT}/lib/install.sh'
    summary_reset
    run_install -- docker
  " 2>&1
}

# ===========================================================================
# module.toml shape
# ===========================================================================

@test "docker: module.toml exists" {
  [ -f "${DEVBOOST_ROOT}/modules/docker/module.toml" ]
}

@test "docker: requires=[] (no deps)" {
  local req
  req="$(grep '^requires' "${DEVBOOST_ROOT}/modules/docker/module.toml" | sed 's/requires *= *//' | tr -d '"')"
  [[ "${req}" == "[]" ]]
}

@test "docker: verify field contains 'command -v docker'" {
  local vcmd
  vcmd="$(grep '^verify' "${DEVBOOST_ROOT}/modules/docker/module.toml")"
  [[ "${vcmd}" == *"command -v docker"* ]]
}

@test "docker: verify field checks systemctl is-enabled docker" {
  local vcmd
  vcmd="$(grep '^verify' "${DEVBOOST_ROOT}/modules/docker/module.toml")"
  [[ "${vcmd}" == *"systemctl is-enabled docker"* ]]
}

@test "docker: verify field checks getent group docker" {
  local vcmd
  vcmd="$(grep '^verify' "${DEVBOOST_ROOT}/modules/docker/module.toml")"
  [[ "${vcmd}" == *"getent group docker"* ]]
}

@test "docker: install command references install.sh" {
  grep -q "install.sh" "${DEVBOOST_ROOT}/modules/docker/module.toml"
}

# ===========================================================================
# T017 — install: docker-ce and compose plugin installed
# ===========================================================================

@test "docker: install exits 0" {
  run _run_docker_install
  [ "$status" -eq 0 ]
}

@test "docker: install — docker-ce installed via dnf" {
  run _run_docker_install
  [ "$status" -eq 0 ]
  grep -q "docker-ce" "${STUB_DNF_LOG}"
}

@test "docker: install — docker-compose-plugin installed via dnf" {
  run _run_docker_install
  [ "$status" -eq 0 ]
  grep -q "docker-compose-plugin" "${STUB_DNF_LOG}"
}

# ===========================================================================
# T017 — systemctl enable --now docker
# ===========================================================================

@test "docker: install — systemctl enable --now docker is called" {
  run _run_docker_install
  [ "$status" -eq 0 ]
  grep -q "systemctl enable --now docker" "${STUB_SYSTEMCTL_LOG}"
}

# ===========================================================================
# T017 — usermod: group added only when user not already a member
# ===========================================================================

@test "docker: install — usermod -aG docker called when user not in group" {
  # STUB_GETENT_DOCKER_USERS not set → getent returns empty → user not in group
  export STUB_GETENT_DOCKER_USERS=""
  run _run_docker_install
  [ "$status" -eq 0 ]
  grep -q "usermod -aG docker" "${STUB_USERMOD_LOG}"
}

@test "docker: install — usermod NOT called when user already in docker group" {
  export STUB_GETENT_DOCKER_USERS="${USER:-testuser}"
  run _run_docker_install
  [ "$status" -eq 0 ]
  # usermod log must be empty (no call made)
  [ ! -s "${STUB_USERMOD_LOG}" ]
}

@test "docker: install — usermod NOT called when other users are in group but not current user" {
  # Some other user is in docker, but not $USER
  export STUB_GETENT_DOCKER_USERS="root alice"
  run _run_docker_install
  [ "$status" -eq 0 ]
  grep -q "usermod -aG docker" "${STUB_USERMOD_LOG}"
}

# ===========================================================================
# T017 — re-login warning emitted
# ===========================================================================

@test "docker: install — re-login warning is emitted in output" {
  run _run_docker_install
  [ "$status" -eq 0 ]
  # Must contain either [!] (warn) or [*] (info) mentioning re-login
  [[ "$output" == *"re-login"* ]] || [[ "$output" == *"log out"* ]] || [[ "$output" == *"logout"* ]]
}

# ===========================================================================
# T017 — verify via getent group docker
# ===========================================================================

@test "docker: verify is GREEN when docker on PATH, service enabled, and user in group" {
  export STUB_SYSTEMCTL_ENABLED="docker"
  export STUB_GETENT_DOCKER_USERS="${USER:-testuser}"
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export USER='${USER:-testuser}'
    export STUB_SYSTEMCTL_ENABLED='${STUB_SYSTEMCTL_ENABLED}'
    export STUB_GETENT_DOCKER_USERS='${STUB_GETENT_DOCKER_USERS}'
    command -v docker && systemctl is-enabled docker && getent group docker | grep -qw \"\${USER}\"
  " 2>&1
  [ "$status" -eq 0 ]
}

@test "docker: verify is RED when docker not on PATH" {
  export STUB_SYSTEMCTL_ENABLED="docker"
  export STUB_GETENT_DOCKER_USERS="${USER:-testuser}"
  rm -f "$(base_stub_dir)/docker"
  # Use only the stub dir (no real /usr/bin) so real docker binary is invisible.
  local stub_only_path
  stub_only_path="$(base_stub_dir)"
  run bash -c "
    export HOME='${HOME}'
    export PATH='${stub_only_path}'
    export USER='${USER:-testuser}'
    export STUB_SYSTEMCTL_ENABLED='${STUB_SYSTEMCTL_ENABLED}'
    export STUB_GETENT_DOCKER_USERS='${STUB_GETENT_DOCKER_USERS}'
    command -v docker && systemctl is-enabled docker && getent group docker | grep -qw \"\${USER}\"
  " 2>&1
  [ "$status" -ne 0 ]
}

@test "docker: verify is RED when service not enabled" {
  # STUB_SYSTEMCTL_ENABLED left empty → is-enabled docker fails
  export STUB_SYSTEMCTL_ENABLED=""
  export STUB_GETENT_DOCKER_USERS="${USER:-testuser}"
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export USER='${USER:-testuser}'
    export STUB_SYSTEMCTL_ENABLED=''
    export STUB_GETENT_DOCKER_USERS='${STUB_GETENT_DOCKER_USERS}'
    command -v docker && systemctl is-enabled docker && getent group docker | grep -qw \"\${USER}\"
  " 2>&1
  [ "$status" -ne 0 ]
}

@test "docker: verify is RED when user not in docker group" {
  export STUB_SYSTEMCTL_ENABLED="docker"
  export STUB_GETENT_DOCKER_USERS=""
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export USER='${USER:-testuser}'
    export STUB_SYSTEMCTL_ENABLED='${STUB_SYSTEMCTL_ENABLED}'
    export STUB_GETENT_DOCKER_USERS=''
    command -v docker && systemctl is-enabled docker && getent group docker | grep -qw \"\${USER}\"
  " 2>&1
  [ "$status" -ne 0 ]
}

# ===========================================================================
# T017 — repo added once (add-if-absent idempotency)
# ===========================================================================

@test "docker: repo add-if-absent — repo file written on first install" {
  run _run_docker_install
  [ "$status" -eq 0 ]
  # The repo file should exist after install
  [ -f "${HOME}/.config/docker-ce.repo" ] || \
    grep -qE "config-manager|repo" "${STUB_DNF_LOG}"
}

@test "docker: repo add-if-absent — second install does not re-add repo" {
  # First install establishes the marker file.
  _run_docker_install >/dev/null 2>&1

  # The marker file must exist (proving first install ran the add step).
  local marker="${HOME}/.config/docker-ce.repo"
  [ -f "${marker}" ]

  # Clear logs for second run.
  : > "${STUB_DNF_LOG}"

  # Second install — marker exists, so repo-add step should be skipped.
  run _run_docker_install
  [ "$status" -eq 0 ]

  # config-manager must NOT appear in the second run's dnf log.
  ! grep -q "config-manager" "${STUB_DNF_LOG}"
}

# ===========================================================================
# T017 — idempotent re-run (engine verify-guard)
# ===========================================================================

@test "docker: idempotent — engine verify-guard skips install when fully verified" {
  # Seed docker stub on PATH, service enabled, user in group
  export STUB_SYSTEMCTL_ENABLED="docker"
  export STUB_GETENT_DOCKER_USERS="${USER:-testuser}"
  : > "${STUB_DNF_LOG}"

  run _engine_run_docker
  [ "$status" -eq 0 ]

  [[ "$output" == *"already installed"* ]]
  # dnf should not have been called for docker-ce
  ! grep -q "docker-ce" "${STUB_DNF_LOG}"
}

# ===========================================================================
# Debian/Ubuntu path — apt-repo install
# ===========================================================================

# Helper: run docker install.sh in debian mode with a scratch docker.list path
# so the idempotency guard and tee are fully exercisable without root.
_run_docker_install_debian() {
  local fake_os_release="${1}"
  local docker_list="${2}"
  local docker_keyrings="${3}"
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export USER='${USER:-testuser}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='ubuntu'
    export OS_FAMILY='debian'
    export OS_RELEASE_FILE='${fake_os_release}'
    export DOCKER_APT_SOURCES_FILE='${docker_list}'
    export DOCKER_APT_KEYRINGS_DIR='${docker_keyrings}'
    export STUB_APT_LOG='${STUB_APT_LOG}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    export STUB_SUDO_LOG='${STUB_SUDO_LOG}'
    export STUB_SYSTEMCTL_LOG='${STUB_SYSTEMCTL_LOG}'
    export STUB_USERMOD_LOG='${STUB_USERMOD_LOG}'
    export STUB_GETENT_LOG='${STUB_GETENT_LOG}'
    export STUB_SYSTEMCTL_ENABLED='${STUB_SYSTEMCTL_ENABLED:-}'
    export STUB_GETENT_DOCKER_USERS='${STUB_GETENT_DOCKER_USERS:-}'
    export STUB_DPKG_ARCH='amd64'
    bash '${DEVBOOST_ROOT}/modules/docker/install.sh'
  " 2>&1
}

@test "docker: debian — module.toml declares a debian install key" {
  grep -q '^debian' "${DEVBOOST_ROOT}/modules/docker/module.toml"
}

@test "docker: debian — apt-get install of docker-ce is invoked" {
  local fake_os_release="${BATS_TEST_TMPDIR}/os-release-ubuntu"
  printf 'ID=ubuntu\nID_LIKE=debian\nVERSION_ID=24.04\nVERSION_CODENAME=noble\n' > "${fake_os_release}"
  local docker_list="${BATS_TEST_TMPDIR}/docker.list"
  local docker_keyrings="${BATS_TEST_TMPDIR}/keyrings"
  mkdir -p "${docker_keyrings}"
  : > "${STUB_APT_LOG}"

  run _run_docker_install_debian "${fake_os_release}" "${docker_list}" "${docker_keyrings}"
  [ "$status" -eq 0 ]

  # Real assertion: apt-get must have been called with docker-ce
  grep -q "docker-ce" "${STUB_APT_LOG}"
  grep -q "docker-compose-plugin" "${STUB_APT_LOG}"
}

@test "docker: debian — docker.list repo file is written on first install" {
  local fake_os_release="${BATS_TEST_TMPDIR}/os-release-ubuntu"
  printf 'ID=ubuntu\nID_LIKE=debian\nVERSION_ID=24.04\nVERSION_CODENAME=noble\n' > "${fake_os_release}"
  local docker_list="${BATS_TEST_TMPDIR}/docker.list"
  local docker_keyrings="${BATS_TEST_TMPDIR}/keyrings"
  mkdir -p "${docker_keyrings}"
  : > "${STUB_APT_LOG}"

  run _run_docker_install_debian "${fake_os_release}" "${docker_list}" "${docker_keyrings}"
  [ "$status" -eq 0 ]

  # The docker.list file must have been created by tee.
  [ -f "${docker_list}" ]
  # It must contain docker's apt repo URL.
  grep -q "download.docker.com/linux/ubuntu" "${docker_list}"
}

@test "docker: debian — repo add is idempotent (no apt-get update on second run)" {
  local fake_os_release="${BATS_TEST_TMPDIR}/os-release-ubuntu"
  printf 'ID=ubuntu\nID_LIKE=debian\nVERSION_ID=24.04\nVERSION_CODENAME=noble\n' > "${fake_os_release}"
  local docker_list="${BATS_TEST_TMPDIR}/docker.list"
  local docker_keyrings="${BATS_TEST_TMPDIR}/keyrings"
  mkdir -p "${docker_keyrings}"

  # First install creates the docker.list file.
  _run_docker_install_debian "${fake_os_release}" "${docker_list}" "${docker_keyrings}" >/dev/null 2>&1

  # Verify docker.list was created.
  [ -f "${docker_list}" ]

  # Clear the apt log for the second run.
  : > "${STUB_APT_LOG}"

  # Second install — docker.list already exists, so the repo-add block must be skipped.
  run _run_docker_install_debian "${fake_os_release}" "${docker_list}" "${docker_keyrings}"
  [ "$status" -eq 0 ]

  # On the second run, apt-get update (for the repo setup) must NOT appear;
  # only the final apt-get install of docker-ce should appear.
  # Count the apt-get update invocations: must be 0 on the second pass.
  local update_count
  update_count="$(grep -c "apt-get update" "${STUB_APT_LOG}" || true)"
  [ "${update_count}" -eq 0 ]

  # But docker-ce install must still be called (packages may need upgrading).
  grep -q "docker-ce" "${STUB_APT_LOG}"
}

@test "docker: debian — systemctl enable --now docker is called" {
  local fake_os_release="${BATS_TEST_TMPDIR}/os-release-ubuntu"
  printf 'ID=ubuntu\nID_LIKE=debian\nVERSION_ID=24.04\nVERSION_CODENAME=noble\n' > "${fake_os_release}"
  local docker_list="${BATS_TEST_TMPDIR}/docker.list"
  local docker_keyrings="${BATS_TEST_TMPDIR}/keyrings"
  mkdir -p "${docker_keyrings}"

  run _run_docker_install_debian "${fake_os_release}" "${docker_list}" "${docker_keyrings}"
  [ "$status" -eq 0 ]

  grep -q "systemctl enable --now docker" "${STUB_SYSTEMCTL_LOG}"
}

@test "docker: debian — usermod -aG docker called when user not in group" {
  local fake_os_release="${BATS_TEST_TMPDIR}/os-release-ubuntu"
  printf 'ID=ubuntu\nID_LIKE=debian\nVERSION_ID=24.04\nVERSION_CODENAME=noble\n' > "${fake_os_release}"
  local docker_list="${BATS_TEST_TMPDIR}/docker.list"
  local docker_keyrings="${BATS_TEST_TMPDIR}/keyrings"
  mkdir -p "${docker_keyrings}"
  export STUB_GETENT_DOCKER_USERS=""

  run _run_docker_install_debian "${fake_os_release}" "${docker_list}" "${docker_keyrings}"
  [ "$status" -eq 0 ]

  grep -q "usermod -aG docker" "${STUB_USERMOD_LOG}"
}
