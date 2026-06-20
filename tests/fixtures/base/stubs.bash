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
#   base_install_chezmoi          — install chezmoi stub (handles init + apply)
#   base_install_git              — install git stub
#   base_install_sudo             — install sudo stub (exec's its remaining args)
#   base_install_npm              — install npm stub (Spec 3: cli-and-shell)
#   base_install_cargo            — install cargo stub (Spec 3: cli-and-shell)
#   base_install_fc_list          — install fc-list stub (Spec 3: cli-and-shell)
#   base_install_fc_cache         — install fc-cache stub (Spec 3: cli-and-shell)
#   base_install_curl             — install curl stub (Spec 3: cli-and-shell, nerd-fonts download)
#   base_install_unzip            — install unzip stub (Spec 3: cli-and-shell, nerd-fonts extraction)
#
# Spec 4 (gnome-desktop) stubs and helpers:
#   base_install_gext             — install gext stub (Spec 4: gnome extension installer)
#   base_install_gnome_extensions — install gnome-extensions stub (Spec 4: benign list/info)
#   base_install_gnome_shell      — install gnome-shell stub (Spec 4: --version knob)
#   base_install_dconf            — install dconf stub (Spec 4: load records + scratch state)
#   base_install_gsettings        — install gsettings stub (Spec 4: get/set scratch key-value)
#   base_gnome_present_on         — enable gnome-shell on PATH (STUB_GNOME_PRESENT=1)
#   base_gnome_present_off        — remove gnome-shell from PATH (STUB_GNOME_PRESENT=0)
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
#   STUB_CHEZMOI_APPLY_FAIL   — if "1", chezmoi apply exits 1 (Spec 3)
#   STUB_GIT_LOG              — path to the git invocation log
#   STUB_SUDO_LOG             — path to the sudo invocation log
#   STUB_NVM_VERSION          — if set, creates ~/.nvm/alias/default with this version
#                               e.g. STUB_NVM_VERSION="18.20.0"
#   STUB_SDKMAN_VERSION       — if set, creates ~/.sdkman/candidates/java/current symlink dir
#                               e.g. STUB_SDKMAN_VERSION="21.0.1-tem"
#
# Spec 3 (cli-and-shell) additional knobs:
#   STUB_NPM_LOG              — path to the npm invocation log (default: $BATS_TEST_TMPDIR/npm-calls.log)
#   STUB_NPM_GLOBALS          — space-separated list of binaries to place on PATH after npm install -g
#                               e.g. STUB_NPM_GLOBALS="claude" creates a passthrough binary in the stub dir
#   STUB_CARGO_LOG            — path to the cargo invocation log (default: $BATS_TEST_TMPDIR/cargo-calls.log)
#   STUB_CURL_LOG             — path to the curl invocation log (default: $BATS_TEST_TMPDIR/curl-calls.log)
#   STUB_UNZIP_LOG            — path to the unzip invocation log (default: $BATS_TEST_TMPDIR/unzip-calls.log)
#   STUB_FONTS_INSTALLED      — newline-separated (or space-separated) font names fc-list emits
#                               e.g. STUB_FONTS_INSTALLED="JetBrainsMono Nerd Font:style=Regular"
#                               Leave empty/unset to simulate no fonts installed.
#   STUB_FC_LIST_LOG          — path to the fc-list invocation log
#   STUB_FC_CACHE_LOG         — path to the fc-cache invocation log
#   STUB_COPR_ENABLED         — space-separated list of COPR repos already enabled
#                               e.g. STUB_COPR_ENABLED="scottames/ghostty" — dnf copr enable is a no-op for these
#   STUB_ORDER_LOG            — shared chronological call-log that BOTH mise and npm stubs append to.
#                               Each line is tagged: "mise:<args>" or "npm:<args>".
#                               Use to assert cross-tool invocation ordering in a single file.
#
# Spec 4 (gnome-desktop) additional knobs:
#   STUB_GEXT_LOG             — path to the gext invocation log (default: $BATS_TEST_TMPDIR/gext-calls.log)
#   STUB_GEXT_MISMATCH_UUID   — if set, gext install writes metadata.json whose uuid= this value
#                               instead of the requested UUID (triggers author-mismatch failure test)
#   STUB_GNOME_EXTENSIONS_LOG — path to the gnome-extensions invocation log
#   STUB_GNOME_SHELL_VERSION  — version string gnome-shell --version prints
#                               (default: "GNOME Shell 47.0")
#   STUB_DCONF_LOG            — path to the dconf invocation log (default: $BATS_TEST_TMPDIR/dconf-calls.log)
#   STUB_DCONF_STATE_FILE     — path to the scratch dconf state file
#                               (default: $BATS_TEST_TMPDIR/dconf-state.ini)
#   STUB_GSETTINGS_STATE_FILE — path to the scratch gsettings key-value store
#                               (default: $BATS_TEST_TMPDIR/gsettings-state.kv)
#   STUB_GNOME_PRESENT        — if "1" (default), gnome-shell stub is on PATH;
#                               if "0", gnome-shell is absent from PATH
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
  # Spec 3 log defaults.
  export STUB_CURL_LOG="${STUB_CURL_LOG:-${BATS_TEST_TMPDIR}/curl-calls.log}"
  export STUB_UNZIP_LOG="${STUB_UNZIP_LOG:-${BATS_TEST_TMPDIR}/unzip-calls.log}"
  export STUB_NPM_LOG="${STUB_NPM_LOG:-${BATS_TEST_TMPDIR}/npm-calls.log}"
  export STUB_CARGO_LOG="${STUB_CARGO_LOG:-${BATS_TEST_TMPDIR}/cargo-calls.log}"
  export STUB_FC_LIST_LOG="${STUB_FC_LIST_LOG:-${BATS_TEST_TMPDIR}/fc-list-calls.log}"
  export STUB_FC_CACHE_LOG="${STUB_FC_CACHE_LOG:-${BATS_TEST_TMPDIR}/fc-cache-calls.log}"
  # Shared cross-tool chronological ordering log (mise + npm both append here).
  export STUB_ORDER_LOG="${STUB_ORDER_LOG:-${BATS_TEST_TMPDIR}/order-calls.log}"
  # Spec 4 log defaults.
  export STUB_GEXT_LOG="${STUB_GEXT_LOG:-${BATS_TEST_TMPDIR}/gext-calls.log}"
  export STUB_GNOME_EXTENSIONS_LOG="${STUB_GNOME_EXTENSIONS_LOG:-${BATS_TEST_TMPDIR}/gnome-extensions-calls.log}"
  export STUB_DCONF_LOG="${STUB_DCONF_LOG:-${BATS_TEST_TMPDIR}/dconf-calls.log}"
  export STUB_DCONF_STATE_FILE="${STUB_DCONF_STATE_FILE:-${BATS_TEST_TMPDIR}/dconf-state.ini}"
  export STUB_GSETTINGS_STATE_FILE="${STUB_GSETTINGS_STATE_FILE:-${BATS_TEST_TMPDIR}/gsettings-state.kv}"
  # STUB_GNOME_PRESENT defaults to 1 (gnome-shell present on PATH).
  export STUB_GNOME_PRESENT="${STUB_GNOME_PRESENT:-1}"

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
  # Spec 3 log initialisation.
  : > "${STUB_CURL_LOG}"
  : > "${STUB_UNZIP_LOG}"
  : > "${STUB_NPM_LOG}"
  : > "${STUB_CARGO_LOG}"
  : > "${STUB_FC_LIST_LOG}"
  : > "${STUB_FC_CACHE_LOG}"
  : > "${STUB_ORDER_LOG}"
  # Spec 4 log initialisation.
  : > "${STUB_GEXT_LOG}"
  : > "${STUB_GNOME_EXTENSIONS_LOG}"
  : > "${STUB_DCONF_LOG}"
  : > "${STUB_DCONF_STATE_FILE}"
  : > "${STUB_GSETTINGS_STATE_FILE}"

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
  # Spec 3 stubs.
  base_install_npm
  base_install_cargo
  base_install_fc_list
  base_install_fc_cache
  base_install_curl
  base_install_unzip
  # Spec 4 stubs (gnome-desktop).
  base_install_gext
  base_install_gnome_extensions
  base_install_gnome_shell
  base_install_dconf
  base_install_gsettings
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
# Stub: dnf — fake package manager for bats tests (handles install, upgrade, copr).
log_file="${STUB_DNF_LOG:-/tmp/stub-dnf-calls.log}"
printf 'dnf %s\n' "$*" >> "${log_file}"

# Handle `dnf copr list`: emit enabled COPR repos from STUB_COPR_ENABLED.
if [[ "$1" == "copr" && "$2" == "list" ]]; then
  enabled="${STUB_COPR_ENABLED:-}"
  for r in ${enabled}; do
    printf '%s\n' "${r}"
  done
  exit 0
fi

# Handle `dnf copr enable -y <repo>`: record the COPR name; skip if already enabled.
if [[ "$1" == "copr" && "$2" == "enable" ]]; then
  # Extract the last non-flag argument as the repo name.
  copr_repo=""
  for arg in "$@"; do
    [[ "${arg}" == -* ]] && continue
    [[ "${arg}" == "copr" || "${arg}" == "enable" ]] && continue
    copr_repo="${arg}"
  done
  enabled="${STUB_COPR_ENABLED:-}"
  for r in ${enabled}; do
    if [[ "${r}" == "${copr_repo}" ]]; then
      printf 'Repository %s is already enabled.\n' "${copr_repo}"
      exit 0
    fi
  done
  exit 0
fi

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
# Also append to the shared ordering log (backward-compatible: no-op if unset).
if [[ -n "${STUB_ORDER_LOG:-}" ]]; then
  printf 'mise:%s\n' "$*" >> "${STUB_ORDER_LOG}"
fi
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
# Stub: chezmoi — fake dotfile manager for bats tests (handles init + apply).
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

# Handle `chezmoi apply [--source <src>] [--destination <dest>]`
if [[ "$1" == "apply" ]]; then
  if [[ "${STUB_CHEZMOI_APPLY_FAIL:-0}" == "1" ]]; then
    printf 'chezmoi: error: apply failed\n' >&2
    exit 1
  fi

  # Parse --source and --destination from args.
  apply_source=""
  apply_dest="${HOME}"
  args=("$@")
  i=1
  while [[ $i -lt ${#args[@]} ]]; do
    arg="${args[$i]}"
    case "${arg}" in
      --source=*)  apply_source="${arg#--source=}" ;;
      --source)    (( i++ )); apply_source="${args[$i]}" ;;
      --destination=*) apply_dest="${arg#--destination=}" ;;
      --destination)   (( i++ )); apply_dest="${args[$i]}" ;;
    esac
    (( i++ ))
  done

  # Record parsed source and destination for test assertions.
  printf 'chezmoi apply --source %s --destination %s\n' "${apply_source}" "${apply_dest}" \
    >> "${log_file}.parsed"

  # Simulate applying: write deterministic managed files into the destination HOME.
  # Tests can inspect these to verify apply ran.
  mkdir -p "${apply_dest}/.config/starship"
  mkdir -p "${apply_dest}/.config/ghostty"
  mkdir -p "${apply_dest}/.config/atuin"
  mkdir -p "${apply_dest}/.tmux/plugins"

  # ~/.bashrc — contains dev-boost sentinel + representative init lines (single copy).
  # Only write if not already present, preserving idempotency (re-apply is a no-op).
  bashrc="${apply_dest}/.bashrc"
  if ! grep -q '# devboost managed' "${bashrc}" 2>/dev/null; then
    cat > "${bashrc}" <<'BASHRC'
# devboost managed — do not edit manually
eval "$(starship init bash)"
eval "$(atuin init bash)"
eval "$(zoxide init bash)"
eval "$(direnv hook bash)"
[ -f /usr/share/fzf/shell/key-bindings.bash ] && source /usr/share/fzf/shell/key-bindings.bash
BASHRC
  fi

  # ~/.config/starship.toml — placeholder starship config.
  starship_cfg="${apply_dest}/.config/starship.toml"
  if [[ ! -f "${starship_cfg}" ]]; then
    printf '# devboost managed starship config\nadd_newline = true\n' > "${starship_cfg}"
  fi

  # ~/.tmux.conf — placeholder tmux config.
  tmux_conf="${apply_dest}/.tmux.conf"
  if [[ ! -f "${tmux_conf}" ]]; then
    printf '# devboost managed tmux config\nset -g default-terminal "screen-256color"\n' > "${tmux_conf}"
  fi

  # ~/.config/ghostty/config — placeholder ghostty config.
  ghostty_cfg="${apply_dest}/.config/ghostty/config"
  if [[ ! -f "${ghostty_cfg}" ]]; then
    printf '# devboost managed ghostty config\nfont-family = JetBrainsMono Nerd Font\n' > "${ghostty_cfg}"
  fi

  # ~/.config/atuin/config.toml — placeholder atuin config.
  atuin_cfg="${apply_dest}/.config/atuin/config.toml"
  if [[ ! -f "${atuin_cfg}" ]]; then
    printf '# devboost managed atuin config\n[settings]\nsearch_mode = "fuzzy"\n' > "${atuin_cfg}"
  fi

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
# Spec 3 (cli-and-shell) stubs
# ---------------------------------------------------------------------------

# base_install_npm — write a fake `npm` binary to the stub bin dir.
#
# Behaviour:
#   npm install -g <pkg>  → logs invocation; if <pkg> name in STUB_NPM_GLOBALS, writes a
#                           passthrough stub binary named after the pkg's expected binary into
#                           the stub dir (so `command -v <binary>` succeeds after install).
#   (any other form)      → exits 0; logs invocation
base_install_npm() {
  cat > "${_base_bin_dir}/npm" <<'STUB'
#!/usr/bin/env bash
# Stub: npm — fake Node package manager for bats tests.
log_file="${STUB_NPM_LOG:-/tmp/stub-npm-calls.log}"
printf 'npm %s\n' "$*" >> "${log_file}"
# Also append to the shared ordering log (backward-compatible: no-op if unset).
if [[ -n "${STUB_ORDER_LOG:-}" ]]; then
  printf 'npm:%s\n' "$*" >> "${STUB_ORDER_LOG}"
fi

# Simulate placing a global binary on PATH for `npm install -g <pkg>`.
if [[ "$1" == "install" && "$2" == "-g" && -n "${3:-}" ]]; then
  pkg="$3"
  stub_bin_dir="$(dirname "$(command -v npm)")"
  for global in ${STUB_NPM_GLOBALS:-}; do
    # STUB_NPM_GLOBALS lists binary names (e.g. "claude") to create for the installed pkg.
    # Format: "pkgname:binary" or just "binary" (matched against the package name).
    if [[ "${global}" == "${pkg}:"* ]]; then
      bin_name="${global#${pkg}:}"
    elif [[ "${global}" == "${pkg}" ]]; then
      bin_name="${global}"
    else
      continue
    fi
    if [[ ! -f "${stub_bin_dir}/${bin_name}" ]]; then
      printf '#!/usr/bin/env bash\n# Stub: %s (placed by npm install -g stub)\nexit 0\n' \
        "${bin_name}" > "${stub_bin_dir}/${bin_name}"
      chmod +x "${stub_bin_dir}/${bin_name}"
    fi
  done
fi

exit 0
STUB
  chmod +x "${_base_bin_dir}/npm"
}

# base_install_cargo — write a fake `cargo` binary to the stub bin dir.
#
# Behaviour:
#   cargo install <pkg>  → logs invocation; exits 0
#   (any other form)     → exits 0; logs invocation
base_install_cargo() {
  cat > "${_base_bin_dir}/cargo" <<'STUB'
#!/usr/bin/env bash
# Stub: cargo — fake Rust package manager for bats tests.
log_file="${STUB_CARGO_LOG:-/tmp/stub-cargo-calls.log}"
printf 'cargo %s\n' "$*" >> "${log_file}"
exit 0
STUB
  chmod +x "${_base_bin_dir}/cargo"
}

# base_install_fc_list — write a fake `fc-list` binary to the stub bin dir.
#
# Behaviour:
#   fc-list  → emits the contents of STUB_FONTS_INSTALLED (newline-separated font descriptors)
#              or nothing if unset (simulates no fonts installed); logs invocation
base_install_fc_list() {
  cat > "${_base_bin_dir}/fc-list" <<'STUB'
#!/usr/bin/env bash
# Stub: fc-list — fake fontconfig list command for bats tests.
log_file="${STUB_FC_LIST_LOG:-/tmp/stub-fc-list-calls.log}"
printf 'fc-list %s\n' "$*" >> "${log_file}"

# Emit the configured font list (empty = no fonts installed).
if [[ -n "${STUB_FONTS_INSTALLED:-}" ]]; then
  printf '%s\n' "${STUB_FONTS_INSTALLED}"
fi

exit 0
STUB
  chmod +x "${_base_bin_dir}/fc-list"
}

# base_install_fc_cache — write a fake `fc-cache` binary to the stub bin dir.
#
# Behaviour:
#   fc-cache [-f]  → exits 0; logs invocation
base_install_fc_cache() {
  cat > "${_base_bin_dir}/fc-cache" <<'STUB'
#!/usr/bin/env bash
# Stub: fc-cache — fake fontconfig cache rebuild command for bats tests.
log_file="${STUB_FC_CACHE_LOG:-/tmp/stub-fc-cache-calls.log}"
printf 'fc-cache %s\n' "$*" >> "${log_file}"
exit 0
STUB
  chmod +x "${_base_bin_dir}/fc-cache"
}

# base_install_unzip — write a fake `unzip` binary to the stub bin dir.
#
# Behaviour (Spec 3: nerd-fonts extraction):
#   unzip -o -j <zip> '*.ttf' -d <dir>  → writes a placeholder <stem>.ttf file into <dir>;
#                                          logs the invocation to STUB_UNZIP_LOG
#   (any other form)                     → exits 0; logs invocation
#
# This simulates font archive extraction so tests can assert that a real .ttf
# file results from the install (catching the "raw ZIP written as .ttf" bug).
#
# State knobs:
#   STUB_UNZIP_LOG   — path to the unzip invocation log (default: $BATS_TEST_TMPDIR/unzip-calls.log)
base_install_unzip() {
  cat > "${_base_bin_dir}/unzip" <<'STUB'
#!/usr/bin/env bash
# Stub: unzip — fake archive extractor for bats tests (simulates ttf extraction).
log_file="${STUB_UNZIP_LOG:-/tmp/stub-unzip-calls.log}"
printf 'unzip %s\n' "$*" >> "${log_file}"

# Parse -d <dir> from args to find the output directory.
# Also detect a .zip source file so we can derive a placeholder name.
dest_dir=""
zip_file=""
args=("$@")
i=0
while [[ $i -lt ${#args[@]} ]]; do
  arg="${args[$i]}"
  case "${arg}" in
    -d)
      (( i++ ))
      dest_dir="${args[$i]}"
      ;;
    -d*)
      dest_dir="${arg#-d}"
      ;;
    *.zip)
      zip_file="${arg}"
      ;;
  esac
  (( i++ ))
done

# If we have a destination directory, write a placeholder .ttf into it so the
# test can assert a real font file resulted from extraction.
if [[ -n "${dest_dir}" ]]; then
  mkdir -p "${dest_dir}"
  # Derive a stem from the zip filename (e.g. JetBrainsMono.zip → JetBrainsMono.ttf).
  if [[ -n "${zip_file}" ]]; then
    stem="$(basename "${zip_file}" .zip)"
  else
    stem="placeholder"
  fi
  : > "${dest_dir}/${stem}NerdFont-Regular.ttf"
fi

exit 0
STUB
  chmod +x "${_base_bin_dir}/unzip"
}

# base_install_curl — write a fake `curl` binary to the stub bin dir.
#
# Behaviour (Spec 3: nerd-fonts download):
#   curl ... -o <file> <url>   → creates a zero-byte placeholder at <file>; logs invocation
#   curl ... --output <file> <url> → same
#   curl ... -o <file>         → same (url may come before -o)
#   (any other form)           → exits 0; logs invocation
#
# This allows nerd-fonts/install.sh to run to completion in tests without
# real network access; font file presence is detected by `find`, not content.
base_install_curl() {
  cat > "${_base_bin_dir}/curl" <<'STUB'
#!/usr/bin/env bash
# Stub: curl — fake HTTP client for bats tests (places placeholder output files).
log_file="${STUB_CURL_LOG:-/tmp/stub-curl-calls.log}"
printf 'curl %s\n' "$*" >> "${log_file}"

# Parse -o / --output <file> to create a placeholder at the destination.
output_file=""
args=("$@")
i=0
while [[ $i -lt ${#args[@]} ]]; do
  arg="${args[$i]}"
  case "${arg}" in
    -o|--output)
      (( i++ ))
      output_file="${args[$i]}"
      ;;
    -o*)
      output_file="${arg#-o}"
      ;;
    --output=*)
      output_file="${arg#--output=}"
      ;;
  esac
  (( i++ ))
done

if [[ -n "${output_file}" ]]; then
  mkdir -p "$(dirname "${output_file}")"
  : > "${output_file}"
fi

exit 0
STUB
  chmod +x "${_base_bin_dir}/curl"
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

# ===========================================================================
# Spec 4 (gnome-desktop) stubs
# ===========================================================================

# ---------------------------------------------------------------------------
# base_install_gext — write a fake `gext` binary to the stub bin dir.
#
# Behaviour:
#   gext install <UUID>  → logs invocation; creates a fake extension dir with a
#                          metadata.json whose "uuid" field matches the requested UUID
#                          (so ext_verify_author passes); idempotent (skips if dir exists).
#                          If STUB_GEXT_MISMATCH_UUID is set, writes that value instead
#                          (triggers the author-mismatch failure test).
#   (any other form)     → exits 0; logs invocation
# ---------------------------------------------------------------------------
base_install_gext() {
  cat > "${_base_bin_dir}/gext" <<'STUB'
#!/usr/bin/env bash
# Stub: gext — fake gnome-extensions-cli for bats tests (Spec 4).
log_file="${STUB_GEXT_LOG:-/tmp/stub-gext-calls.log}"
printf 'gext %s\n' "$*" >> "${log_file}"

if [[ "$1" == "install" && -n "${2:-}" ]]; then
  uuid="$2"
  ext_dir="${HOME}/.local/share/gnome-shell/extensions/${uuid}"
  # Idempotent: skip creating metadata if the extension dir already exists.
  if [[ ! -d "${ext_dir}" ]]; then
    mkdir -p "${ext_dir}"
    # Use STUB_GEXT_MISMATCH_UUID to inject a wrong uuid for failure tests.
    metadata_uuid="${STUB_GEXT_MISMATCH_UUID:-${uuid}}"
    printf '{"uuid":"%s","name":"Stub Extension","description":"test stub"}\n' \
      "${metadata_uuid}" > "${ext_dir}/metadata.json"
  fi
fi

exit 0
STUB
  chmod +x "${_base_bin_dir}/gext"
}

# ---------------------------------------------------------------------------
# base_install_gnome_extensions — write a fake `gnome-extensions` binary.
#
# Behaviour (benign):
#   gnome-extensions list   → exits 0; logs invocation
#   gnome-extensions info   → exits 0; logs invocation
#   (any other form)        → exits 0; logs invocation
# ---------------------------------------------------------------------------
base_install_gnome_extensions() {
  cat > "${_base_bin_dir}/gnome-extensions" <<'STUB'
#!/usr/bin/env bash
# Stub: gnome-extensions — fake GNOME extension manager CLI for bats tests (Spec 4).
log_file="${STUB_GNOME_EXTENSIONS_LOG:-/tmp/stub-gnome-extensions-calls.log}"
printf 'gnome-extensions %s\n' "$*" >> "${log_file}"
exit 0
STUB
  chmod +x "${_base_bin_dir}/gnome-extensions"
}

# ---------------------------------------------------------------------------
# base_install_gnome_shell — write a fake `gnome-shell` binary to the stub bin dir.
#
# Behaviour (STUB_GNOME_PRESENT=1, default):
#   gnome-shell --version  → prints STUB_GNOME_SHELL_VERSION (default: "GNOME Shell 47.0")
#   (any other form)       → exits 0
#
# Behaviour (STUB_GNOME_PRESENT=0):
#   gnome-shell (any args) → exits 1 (simulates a non-functional / absent GNOME shell)
#   XDG_CURRENT_DESKTOP is set to "" so command-presence checks also fail by convention.
# ---------------------------------------------------------------------------
base_install_gnome_shell() {
  if [[ "${STUB_GNOME_PRESENT:-1}" == "0" ]]; then
    # Write a stub that always exits 1 so --version checks fail; also clear XDG_CURRENT_DESKTOP.
    cat > "${_base_bin_dir}/gnome-shell" <<'STUB'
#!/usr/bin/env bash
# Stub: gnome-shell ABSENT — simulates non-GNOME environment (STUB_GNOME_PRESENT=0).
exit 1
STUB
    chmod +x "${_base_bin_dir}/gnome-shell"
    export XDG_CURRENT_DESKTOP=""
  else
    cat > "${_base_bin_dir}/gnome-shell" <<'STUB'
#!/usr/bin/env bash
# Stub: gnome-shell — fake GNOME Shell for bats tests (Spec 4).
if [[ "$1" == "--version" ]]; then
  printf '%s\n' "${STUB_GNOME_SHELL_VERSION:-GNOME Shell 47.0}"
fi
exit 0
STUB
    chmod +x "${_base_bin_dir}/gnome-shell"
    export XDG_CURRENT_DESKTOP="${XDG_CURRENT_DESKTOP:-GNOME}"
  fi
}

# ---------------------------------------------------------------------------
# base_install_dconf — write a fake `dconf` binary to the stub bin dir.
#
# Behaviour:
#   dconf load /org/gnome/  → reads stdin (the dump); records the dump content to
#                             STUB_DCONF_LOG; appends to STUB_DCONF_STATE_FILE
#   (any other form)        → exits 0; logs invocation
# ---------------------------------------------------------------------------
base_install_dconf() {
  cat > "${_base_bin_dir}/dconf" <<'STUB'
#!/usr/bin/env bash
# Stub: dconf — fake dconf settings tool for bats tests (Spec 4).
log_file="${STUB_DCONF_LOG:-/tmp/stub-dconf-calls.log}"
state_file="${STUB_DCONF_STATE_FILE:-/tmp/stub-dconf-state.ini}"
printf 'dconf %s\n' "$*" >> "${log_file}"

# Handle `dconf load <path>`: read stdin dump; record it in log and state file.
if [[ "$1" == "load" ]]; then
  dump="$(cat)"
  printf '%s\n' "${dump}" >> "${log_file}"
  printf '%s\n' "${dump}" >> "${state_file}"
fi

exit 0
STUB
  chmod +x "${_base_bin_dir}/dconf"
}

# ---------------------------------------------------------------------------
# base_install_gsettings — write a fake `gsettings` binary to the stub bin dir.
#
# Behaviour (scratch key-value store backed by STUB_GSETTINGS_STATE_FILE):
#   gsettings get <schema> <key>   → reads the value for "schema key" from the state file;
#                                    prints "@as []" if the key is absent (empty list default
#                                    for enabled-extensions)
#   gsettings set <schema> <key> <value> → writes/updates "schema key=value" in state file
#   (any other form)               → exits 0
#
# Supports list-typed values (e.g. the enabled-extensions array) transparently.
# ---------------------------------------------------------------------------
base_install_gsettings() {
  cat > "${_base_bin_dir}/gsettings" <<'STUB'
#!/usr/bin/env bash
# Stub: gsettings — fake GSettings CLI for bats tests (Spec 4); scratch key-value store.
state_file="${STUB_GSETTINGS_STATE_FILE:-/tmp/stub-gsettings-state.kv}"

if [[ "$1" == "get" && -n "${2:-}" && -n "${3:-}" ]]; then
  schema="$2"
  key="$3"
  lookup="${schema} ${key}"
  # Search state file for a matching "schema key=value" line.
  value=""
  while IFS= read -r line; do
    if [[ "${line}" == "${lookup}="* ]]; then
      value="${line#${lookup}=}"
      break
    fi
  done < "${state_file}"
  if [[ -n "${value}" ]]; then
    printf '%s\n' "${value}"
  else
    # Default empty list for enabled-extensions; empty string for other keys.
    if [[ "${key}" == "enabled-extensions" ]]; then
      printf '@as []\n'
    else
      printf '\n'
    fi
  fi
  exit 0
fi

if [[ "$1" == "set" && -n "${2:-}" && -n "${3:-}" && -n "${4:-}" ]]; then
  schema="$2"
  key="$3"
  shift 3
  value="$*"
  lookup="${schema} ${key}"
  tmp_file="${state_file}.tmp"
  # Remove any existing entry for this key, then append the new value.
  grep -v "^${lookup}=" "${state_file}" > "${tmp_file}" 2>/dev/null || true
  printf '%s=%s\n' "${lookup}" "${value}" >> "${tmp_file}"
  mv "${tmp_file}" "${state_file}"
  exit 0
fi

exit 0
STUB
  chmod +x "${_base_bin_dir}/gsettings"
}

# ---------------------------------------------------------------------------
# base_gnome_present_on — make gnome-shell stub work normally (STUB_GNOME_PRESENT=1).
# Call after base_setup when a test needs to re-enable GNOME presence.
# Reinstalls the working stub and sets XDG_CURRENT_DESKTOP=GNOME.
# ---------------------------------------------------------------------------
base_gnome_present_on() {
  export STUB_GNOME_PRESENT=1
  base_install_gnome_shell
}

# ---------------------------------------------------------------------------
# base_gnome_present_off — replace gnome-shell stub with an always-exit-1 version (STUB_GNOME_PRESENT=0).
# Call after base_setup when a test needs `gnome-shell --version` (and presence checks) to fail.
# Also clears XDG_CURRENT_DESKTOP so env-based GNOME detection also fails.
# ---------------------------------------------------------------------------
base_gnome_present_off() {
  export STUB_GNOME_PRESENT=0
  base_install_gnome_shell
}
