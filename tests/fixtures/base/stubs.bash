# tests/fixtures/base/stubs.bash — shared bats stub harness for base-profile module tests.
#
# Source this file in a bats test file via:
#   load fixtures/base/stubs
#
# It provides:
#   base_setup       — call in bats setup()   : installs PATH stubs + scratch HOME + scratch root
#   base_teardown    — call in bats teardown() : cleans up temp dirs
#   base_stub_dir    — path to the temp bin directory prepended to PATH
#   base_home_dir    — path to the scratch HOME used by tests
#   base_root_dir    — path to the scratch root (fake /etc, etc.)
#
# Individual install helpers (called by base_setup; may be called independently):
#   base_install_dnf              — install dnf stub
#   base_install_rpm              — install rpm stub
#   base_install_flatpak          — install flatpak stub
#   base_install_fedora_third_party — install fedora-third-party stub
#   base_install_systemctl        — install systemctl stub
#   base_install_usermod          — install usermod stub
#   base_install_getent           — install getent stub
#   base_install_mise             — install mise stub
#   base_install_chezmoi          — install chezmoi stub
#   base_install_git              — install git stub
#   base_install_sudo             — install sudo stub (exec's its remaining args)
#
# State knobs (set before calling base_setup or the relevant install helper):
#   STUB_RPM_INSTALLED        — space-separated list of packages rpm reports as installed
#                               e.g. STUB_RPM_INSTALLED="rpmfusion-free-release pkg2"
#   STUB_DNF_LOG              — path to the dnf invocation log (default: $BATS_TEST_TMPDIR/dnf-calls.log)
#   STUB_RPM_LOG              — path to the rpm invocation log (default: $BATS_TEST_TMPDIR/rpm-calls.log)
#   STUB_FLATPAK_LOG          — path to the flatpak invocation log
#   STUB_FLATPAK_REMOTES      — space-separated list of already-present flatpak remotes
#                               e.g. STUB_FLATPAK_REMOTES="flathub" makes remote-add a no-op
#   STUB_FTP_ENABLED          — if "1", fedora-third-party query reports enabled
#   STUB_FTP_LOG              — path to the fedora-third-party invocation log
#   STUB_SYSTEMCTL_LOG        — path to the systemctl invocation log
#   STUB_SYSTEMCTL_ENABLED    — space-separated list of services systemctl reports as enabled
#                               e.g. STUB_SYSTEMCTL_ENABLED="docker"
#   STUB_USERMOD_LOG          — path to the usermod invocation log
#   STUB_GETENT_LOG           — path to the getent invocation log
#   STUB_GETENT_DOCKER_USERS  — space-separated list of users in the docker group
#                               e.g. STUB_GETENT_DOCKER_USERS="root alice"
#   STUB_MISE_LOG             — path to the mise invocation log
#   STUB_MISE_INSTALLED       — if "1", `command -v mise` succeeds (mise already present)
#   STUB_CHEZMOI_LOG          — path to the chezmoi invocation log
#   STUB_CHEZMOI_CLONE_FAIL   — if "1", chezmoi init --source=... exits 1 (clone failure)
#   STUB_GIT_LOG              — path to the git invocation log
#   STUB_SUDO_LOG             — path to the sudo invocation log
#   STUB_NVM_VERSION          — if set, creates ~/.nvm/alias/default with this version
#                               e.g. STUB_NVM_VERSION="18.20.0"
#   STUB_SDKMAN_VERSION       — if set, creates ~/.sdkman/candidates/java/current symlink dir
#                               e.g. STUB_SDKMAN_VERSION="21.0.1-tem"
#
# All stubs write no real network traffic or system changes; all temp files live under
# BATS_TEST_TMPDIR / scratch dirs and are cleaned up by bats or by base_teardown.

# _base_fixture_dir resolves the absolute path to this stubs directory.
_base_fixture_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# base_setup — main entry point; creates scratch dirs and installs all stubs.
# ---------------------------------------------------------------------------
base_setup() {
  # Create a temp bin directory for stub executables.
  _base_bin_dir="$(mktemp -d)"
  # Create a scratch HOME so tests never touch the real home.
  _base_home_dir="$(mktemp -d)"
  # Create a scratch root for fake /etc tree.
  _base_root_dir="$(mktemp -d)"

  # Prepend stub bin dir to PATH so our fakes shadow real tools.
  export PATH="${_base_bin_dir}:${PATH}"

  # Export scratch HOME and XDG dirs for isolation.
  export HOME="${_base_home_dir}"
  export XDG_STATE_HOME="${_base_home_dir}/.local/state"
  export XDG_CONFIG_HOME="${_base_home_dir}/.config"
  mkdir -p "${_base_home_dir}/.local/state/devboost"
  mkdir -p "${_base_home_dir}/.config"

  # Create scratch /etc/dnf under the scratch root.
  mkdir -p "${_base_root_dir}/etc/dnf"

  # Default log paths (tests may override before calling base_setup).
  export STUB_DNF_LOG="${STUB_DNF_LOG:-${BATS_TEST_TMPDIR}/dnf-calls.log}"
  export STUB_RPM_LOG="${STUB_RPM_LOG:-${BATS_TEST_TMPDIR}/rpm-calls.log}"
  export STUB_FLATPAK_LOG="${STUB_FLATPAK_LOG:-${BATS_TEST_TMPDIR}/flatpak-calls.log}"
  export STUB_FTP_LOG="${STUB_FTP_LOG:-${BATS_TEST_TMPDIR}/ftp-calls.log}"
  export STUB_SYSTEMCTL_LOG="${STUB_SYSTEMCTL_LOG:-${BATS_TEST_TMPDIR}/systemctl-calls.log}"
  export STUB_USERMOD_LOG="${STUB_USERMOD_LOG:-${BATS_TEST_TMPDIR}/usermod-calls.log}"
  export STUB_GETENT_LOG="${STUB_GETENT_LOG:-${BATS_TEST_TMPDIR}/getent-calls.log}"
  export STUB_MISE_LOG="${STUB_MISE_LOG:-${BATS_TEST_TMPDIR}/mise-calls.log}"
  export STUB_CHEZMOI_LOG="${STUB_CHEZMOI_LOG:-${BATS_TEST_TMPDIR}/chezmoi-calls.log}"
  export STUB_GIT_LOG="${STUB_GIT_LOG:-${BATS_TEST_TMPDIR}/git-calls.log}"
  export STUB_SUDO_LOG="${STUB_SUDO_LOG:-${BATS_TEST_TMPDIR}/sudo-calls.log}"

  # Initialise all log files as empty.
  : > "${STUB_DNF_LOG}"
  : > "${STUB_RPM_LOG}"
  : > "${STUB_FLATPAK_LOG}"
  : > "${STUB_FTP_LOG}"
  : > "${STUB_SYSTEMCTL_LOG}"
  : > "${STUB_USERMOD_LOG}"
  : > "${STUB_GETENT_LOG}"
  : > "${STUB_MISE_LOG}"
  : > "${STUB_CHEZMOI_LOG}"
  : > "${STUB_GIT_LOG}"
  : > "${STUB_SUDO_LOG}"

  # Set up optional fake ~/.nvm / ~/.sdkman for migration tests.
  if [[ -n "${STUB_NVM_VERSION:-}" ]]; then
    mkdir -p "${_base_home_dir}/.nvm/alias"
    printf '%s\n' "${STUB_NVM_VERSION}" > "${_base_home_dir}/.nvm/alias/default"
  fi
  if [[ -n "${STUB_SDKMAN_VERSION:-}" ]]; then
    mkdir -p "${_base_home_dir}/.sdkman/candidates/java"
    mkdir -p "${_base_home_dir}/.sdkman/candidates/java/${STUB_SDKMAN_VERSION}"
    ln -sfn "${_base_home_dir}/.sdkman/candidates/java/${STUB_SDKMAN_VERSION}" \
            "${_base_home_dir}/.sdkman/candidates/java/current"
  fi

  # Install all stubs.
  base_install_dnf
  base_install_rpm
  base_install_flatpak
  base_install_fedora_third_party
  base_install_systemctl
  base_install_usermod
  base_install_getent
  base_install_mise
  base_install_chezmoi
  base_install_git
  base_install_sudo
}

# ---------------------------------------------------------------------------
# base_teardown — remove temp dirs created by base_setup.
# ---------------------------------------------------------------------------
base_teardown() {
  [[ -n "${_base_bin_dir:-}"  && -d "${_base_bin_dir}"  ]] && rm -rf "${_base_bin_dir}"
  [[ -n "${_base_home_dir:-}" && -d "${_base_home_dir}" ]] && rm -rf "${_base_home_dir}"
  [[ -n "${_base_root_dir:-}" && -d "${_base_root_dir}" ]] && rm -rf "${_base_root_dir}"
}

# ---------------------------------------------------------------------------
# Accessors — return the paths to scratch directories for use in assertions.
# ---------------------------------------------------------------------------
base_stub_dir() { printf '%s\n' "${_base_bin_dir}"; }
base_home_dir()  { printf '%s\n' "${_base_home_dir}"; }
base_root_dir()  { printf '%s\n' "${_base_root_dir}"; }

# ---------------------------------------------------------------------------
# base_install_dnf — write a fake `dnf` binary to the stub bin dir.
#
# Behaviour:
#   dnf install -y <pkg...>    → exits 0; logs the invocation
#   dnf upgrade --refresh -y   → exits 0; logs the invocation
#   (any other form)           → exits 0; logs the invocation
# ---------------------------------------------------------------------------
base_install_dnf() {
  cat > "${_base_bin_dir}/dnf" <<'STUB'
#!/usr/bin/env bash
# Stub: dnf — fake package manager for bats tests.
log_file="${STUB_DNF_LOG:-/tmp/stub-dnf-calls.log}"
printf 'dnf %s\n' "$*" >> "${log_file}"
exit 0
STUB
  chmod +x "${_base_bin_dir}/dnf"
}

# ---------------------------------------------------------------------------
# base_install_rpm — write a fake `rpm` binary to the stub bin dir.
#
# Behaviour:
#   rpm -q <pkg>    → exits 0 if pkg is listed in STUB_RPM_INSTALLED; else exits 1
#   rpm -E %fedora  → prints "44" (the reference Fedora release number)
#   (any other form) → exits 0
# ---------------------------------------------------------------------------
base_install_rpm() {
  cat > "${_base_bin_dir}/rpm" <<'STUB'
#!/usr/bin/env bash
# Stub: rpm — fake RPM query tool for bats tests.
log_file="${STUB_RPM_LOG:-/tmp/stub-rpm-calls.log}"
printf 'rpm %s\n' "$*" >> "${log_file}"

# Handle rpm -E %fedora (macro expansion used in install URLs).
if [[ "$*" == *"-E"* && "$*" == *"%fedora"* ]]; then
  printf '44\n'
  exit 0
fi

# Handle rpm -q (package query): succeed only if ALL queried packages are installed.
if [[ "$1" == "-q" ]]; then
  shift
  installed="${STUB_RPM_INSTALLED:-}"
  for pkg in "$@"; do
    found=0
    for ipkg in ${installed}; do
      if [[ "${ipkg}" == "${pkg}" ]]; then
        found=1
        break
      fi
    done
    if [[ "${found}" -eq 0 ]]; then
      printf 'package %s is not installed\n' "${pkg}" >&2
      exit 1
    fi
  done
  exit 0
fi

exit 0
STUB
  chmod +x "${_base_bin_dir}/rpm"
}

# ---------------------------------------------------------------------------
# base_install_flatpak — write a fake `flatpak` binary to the stub bin dir.
#
# Behaviour:
#   flatpak remotes         → prints each name in STUB_FLATPAK_REMOTES (one per line)
#   flatpak remote-add ...  → exits 0 (already guarded by the caller; logs invocation)
#   flatpak remote-modify ...→ exits 0; logs invocation
#   (any other form)        → exits 0; logs invocation
# ---------------------------------------------------------------------------
base_install_flatpak() {
  cat > "${_base_bin_dir}/flatpak" <<'STUB'
#!/usr/bin/env bash
# Stub: flatpak — fake Flatpak client for bats tests.
log_file="${STUB_FLATPAK_LOG:-/tmp/stub-flatpak-calls.log}"
printf 'flatpak %s\n' "$*" >> "${log_file}"

if [[ "$1" == "remotes" ]]; then
  for remote in ${STUB_FLATPAK_REMOTES:-}; do
    printf '%s\n' "${remote}"
  done
  exit 0
fi

exit 0
STUB
  chmod +x "${_base_bin_dir}/flatpak"
}

# ---------------------------------------------------------------------------
# base_install_fedora_third_party — write a fake `fedora-third-party` binary.
#
# Behaviour:
#   fedora-third-party enable  → exits 0; logs invocation
#   fedora-third-party query   → prints "enabled" if STUB_FTP_ENABLED=1; else "disabled"
#   (any other form)           → exits 0; logs invocation
# ---------------------------------------------------------------------------
base_install_fedora_third_party() {
  cat > "${_base_bin_dir}/fedora-third-party" <<'STUB'
#!/usr/bin/env bash
# Stub: fedora-third-party — fake third-party enablement tool for bats tests.
log_file="${STUB_FTP_LOG:-/tmp/stub-ftp-calls.log}"
printf 'fedora-third-party %s\n' "$*" >> "${log_file}"

if [[ "$1" == "query" ]]; then
  if [[ "${STUB_FTP_ENABLED:-0}" == "1" ]]; then
    printf 'enabled\n'
  else
    printf 'disabled\n'
  fi
  exit 0
fi

exit 0
STUB
  chmod +x "${_base_bin_dir}/fedora-third-party"
}

# ---------------------------------------------------------------------------
# base_install_systemctl — write a fake `systemctl` binary to the stub bin dir.
#
# Behaviour:
#   systemctl enable --now <svc>  → exits 0; logs invocation
#   systemctl is-enabled <svc>    → exits 0 if svc in STUB_SYSTEMCTL_ENABLED; else exits 1
#   (any other form)              → exits 0; logs invocation
# ---------------------------------------------------------------------------
base_install_systemctl() {
  cat > "${_base_bin_dir}/systemctl" <<'STUB'
#!/usr/bin/env bash
# Stub: systemctl — fake systemd control for bats tests.
log_file="${STUB_SYSTEMCTL_LOG:-/tmp/stub-systemctl-calls.log}"
printf 'systemctl %s\n' "$*" >> "${log_file}"

if [[ "$1" == "is-enabled" ]]; then
  svc="$2"
  enabled="${STUB_SYSTEMCTL_ENABLED:-}"
  for s in ${enabled}; do
    if [[ "${s}" == "${svc}" ]]; then
      printf 'enabled\n'
      exit 0
    fi
  done
  printf 'disabled\n'
  exit 1
fi

exit 0
STUB
  chmod +x "${_base_bin_dir}/systemctl"
}

# ---------------------------------------------------------------------------
# base_install_usermod — write a fake `usermod` binary to the stub bin dir.
#
# Behaviour:
#   usermod -aG <group> <user> → exits 0; logs invocation
#   (any other form)           → exits 0; logs invocation
# ---------------------------------------------------------------------------
base_install_usermod() {
  cat > "${_base_bin_dir}/usermod" <<'STUB'
#!/usr/bin/env bash
# Stub: usermod — fake user modification tool for bats tests.
log_file="${STUB_USERMOD_LOG:-/tmp/stub-usermod-calls.log}"
printf 'usermod %s\n' "$*" >> "${log_file}"
exit 0
STUB
  chmod +x "${_base_bin_dir}/usermod"
}

# ---------------------------------------------------------------------------
# base_install_getent — write a fake `getent` binary to the stub bin dir.
#
# Behaviour:
#   getent group docker → prints "docker:x:999:<users>" where <users> is
#                         STUB_GETENT_DOCKER_USERS (comma-separated); exits 0 if
#                         STUB_GETENT_DOCKER_USERS is set, else exits 2 (not found)
#   (any other form)    → exits 0; logs invocation
# ---------------------------------------------------------------------------
base_install_getent() {
  cat > "${_base_bin_dir}/getent" <<'STUB'
#!/usr/bin/env bash
# Stub: getent — fake NSS database query tool for bats tests.
log_file="${STUB_GETENT_LOG:-/tmp/stub-getent-calls.log}"
printf 'getent %s\n' "$*" >> "${log_file}"

if [[ "$1" == "group" && "$2" == "docker" ]]; then
  if [[ -n "${STUB_GETENT_DOCKER_USERS:-}" ]]; then
    # Convert space-separated list to comma-separated for /etc/group format.
    users="${STUB_GETENT_DOCKER_USERS// /,}"
    printf 'docker:x:999:%s\n' "${users}"
    exit 0
  else
    exit 2
  fi
fi

exit 0
STUB
  chmod +x "${_base_bin_dir}/getent"
}

# ---------------------------------------------------------------------------
# base_install_mise — write a fake `mise` binary to the stub bin dir.
#
# Behaviour:
#   mise use -g <tool>@<version>  → exits 0; logs invocation
#   (any other form)              → exits 0; logs invocation
# Note: `command -v mise` presence is controlled by whether this stub exists on PATH.
# Set STUB_MISE_INSTALLED=0 and remove/skip stub install to simulate mise absent.
# ---------------------------------------------------------------------------
base_install_mise() {
  cat > "${_base_bin_dir}/mise" <<'STUB'
#!/usr/bin/env bash
# Stub: mise — fake runtime manager for bats tests.
log_file="${STUB_MISE_LOG:-/tmp/stub-mise-calls.log}"
printf 'mise %s\n' "$*" >> "${log_file}"
exit 0
STUB
  chmod +x "${_base_bin_dir}/mise"
}

# ---------------------------------------------------------------------------
# base_install_chezmoi — write a fake `chezmoi` binary to the stub bin dir.
#
# Behaviour:
#   chezmoi init ...            → exits 0 normally; exits 1 if STUB_CHEZMOI_CLONE_FAIL=1
#   (any other form)            → exits 0; logs invocation
# ---------------------------------------------------------------------------
base_install_chezmoi() {
  cat > "${_base_bin_dir}/chezmoi" <<'STUB'
#!/usr/bin/env bash
# Stub: chezmoi — fake dotfile manager for bats tests.
log_file="${STUB_CHEZMOI_LOG:-/tmp/stub-chezmoi-calls.log}"
printf 'chezmoi %s\n' "$*" >> "${log_file}"

if [[ "$1" == "init" ]]; then
  if [[ "${STUB_CHEZMOI_CLONE_FAIL:-0}" == "1" ]]; then
    printf 'chezmoi: error: failed to clone dotfiles repository\n' >&2
    exit 1
  fi
  # Create the chezmoi source directory to simulate a successful init+clone.
  mkdir -p "${HOME}/.local/share/chezmoi"
  exit 0
fi

exit 0
STUB
  chmod +x "${_base_bin_dir}/chezmoi"
}

# ---------------------------------------------------------------------------
# base_install_git — write a fake `git` binary to the stub bin dir.
#
# Behaviour:
#   git clone ...  → exits 0; logs invocation
#   (any other form) → exits 0; logs invocation
# ---------------------------------------------------------------------------
base_install_git() {
  cat > "${_base_bin_dir}/git" <<'STUB'
#!/usr/bin/env bash
# Stub: git — fake version control client for bats tests.
log_file="${STUB_GIT_LOG:-/tmp/stub-git-calls.log}"
printf 'git %s\n' "$*" >> "${log_file}"
exit 0
STUB
  chmod +x "${_base_bin_dir}/git"
}

# ---------------------------------------------------------------------------
# base_install_sudo — write a fake `sudo` binary to the stub bin dir.
#
# sudo transparently exec's its remaining args so `sudo dnf …` reaches the
# dnf stub. Also logs each top-level invocation (without re-logging the
# delegated command's own log entry).
# ---------------------------------------------------------------------------
base_install_sudo() {
  cat > "${_base_bin_dir}/sudo" <<'STUB'
#!/usr/bin/env bash
# Stub: sudo — passes through to the next command so sudo dnf/systemctl/etc hit their stubs.
log_file="${STUB_SUDO_LOG:-/tmp/stub-sudo-calls.log}"
printf 'sudo %s\n' "$*" >> "${log_file}"
exec "$@"
STUB
  chmod +x "${_base_bin_dir}/sudo"
}

# ---------------------------------------------------------------------------
# base_remove_mise — remove the mise stub from PATH (simulates mise not installed).
# Call after base_setup when a test needs `command -v mise` to fail.
# ---------------------------------------------------------------------------
base_remove_mise() { rm -f "${_base_bin_dir}/mise"; }

# ---------------------------------------------------------------------------
# base_scratch_dnf_conf — return the path to the scratch dnf.conf file.
# Tests that exercise write_kv_conf should pass this path instead of /etc/dnf/dnf.conf.
# ---------------------------------------------------------------------------
base_scratch_dnf_conf() { printf '%s/etc/dnf/dnf.conf\n' "${_base_root_dir}"; }

# ---------------------------------------------------------------------------
# base_scratch_bashrc — return the path to the scratch ~/.bashrc file.
# Creates the file (empty) on first call if it does not yet exist.
# ---------------------------------------------------------------------------
base_scratch_bashrc() {
  local f="${_base_home_dir}/.bashrc"
  [[ -f "${f}" ]] || touch "${f}"
  printf '%s\n' "${f}"
}

# ---------------------------------------------------------------------------
# base_add_nvm_block — write a fake nvm init block into ~/.bashrc.
# Tests that exercise comment_block can call this to seed the block.
# ---------------------------------------------------------------------------
base_add_nvm_block() {
  local bashrc
  bashrc="$(base_scratch_bashrc)"
  cat >> "${bashrc}" <<'NVM_BLOCK'
# BEGIN NVM
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"
# END NVM
NVM_BLOCK
}

# ---------------------------------------------------------------------------
# base_add_sdkman_block — write a fake sdkman init block into ~/.bashrc.
# Tests that exercise comment_block can call this to seed the block.
# ---------------------------------------------------------------------------
base_add_sdkman_block() {
  local bashrc
  bashrc="$(base_scratch_bashrc)"
  cat >> "${bashrc}" <<'SDKMAN_BLOCK'
# BEGIN SDKMAN
export SDKMAN_DIR="$HOME/.sdkman"
[[ -s "$HOME/.sdkman/bin/sdkman-init.sh" ]] && source "$HOME/.sdkman/bin/sdkman-init.sh"
# END SDKMAN
SDKMAN_BLOCK
}
