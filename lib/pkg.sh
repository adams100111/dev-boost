# lib/pkg.sh — shared package-management helpers for escape-hatch modules.
# Source-only; no side effects on source. Depends on lib/log.sh.
# All external commands (dnf, rpm, flatpak, sudo) are PATH-stubbable in tests.

# ---------------------------------------------------------------------------
# have <cmd>
#   Returns 0 if <cmd> is found on PATH. Identical body to lib/secrets.sh::have;
#   redefinition is harmless because the bodies are identical.
# ---------------------------------------------------------------------------
have() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------------------
# need_cmd <cmd> <pkg>
#   Ensure <cmd> exists on PATH, installing <pkg> via dnf only when absent.
# ---------------------------------------------------------------------------
need_cmd() {
  local cmd="$1" pkg="$2"
  if ! have "${cmd}"; then
    log_info "pkg: installing ${pkg} (${cmd} not found)"
    dnf_install "${pkg}"
  fi
}

# ---------------------------------------------------------------------------
# dnf_install <pkg...>
#   Run `sudo dnf install -y <pkg...>`. Safe with no-op args.
# ---------------------------------------------------------------------------
dnf_install() {
  sudo dnf install -y "$@"
}

# ---------------------------------------------------------------------------
# rpm_q <pkg...>
#   Returns 0 iff ALL listed packages are installed (rpm -q).
# ---------------------------------------------------------------------------
rpm_q() {
  rpm -q "$@" >/dev/null 2>&1
}

# ---------------------------------------------------------------------------
# flatpak_remote_add <name> <url>
#   Add a Flatpak remote if it is not already present. Idempotent.
# ---------------------------------------------------------------------------
flatpak_remote_add() {
  local name="$1" url="$2"
  if flatpak remotes | awk '{print $1}' | grep -qxF "${name}"; then
    log_skip "flatpak remote '${name}' already present"
    return 0
  fi
  log_info "pkg: adding flatpak remote '${name}'"
  flatpak remote-add --if-not-exists "${name}" "${url}"
}

# ---------------------------------------------------------------------------
# write_kv_conf <file> <key> <value>
#   Ensure `key=value` is present in <file> (ini-style).
#   Reconciles an existing `key=` line (replace) rather than appending a
#   duplicate. Creates the file if missing. Never corrupts unrelated lines.
# ---------------------------------------------------------------------------
write_kv_conf() {
  local file="$1" key="$2" value="$3"

  # Create the file if it does not exist.
  if [[ ! -f "${file}" ]]; then
    log_info "pkg: creating ${file}"
    touch "${file}" || { log_error "write_kv_conf: cannot create ${file}"; return 1; }
  fi

  # If the key already exists with the correct value, nothing to do.
  # Use a fixed-string first-field check so keys/values with regex metacharacters
  # are safe: awk splits on the first '=' and compares both fields literally.
  if awk -F= 'NR==1{found=0} $1==key && substr($0, length($1)+2)==val{found=1} END{exit !found}' \
        key="${key}" val="${value}" "${file}"; then
    log_skip "write_kv_conf: ${key}=${value} already set in ${file}"
    return 0
  fi

  # If the key exists with a different value, replace it in-place using awk so
  # that neither key nor value is interpolated into a regex or sed delimiter.
  if awk -F= '$1==key{found=1} END{exit !found}' key="${key}" "${file}"; then
    log_info "pkg: reconciling ${key} in ${file}"
    local tmp
    tmp="$(mktemp)" || { log_error "write_kv_conf: mktemp failed"; return 1; }
    awk -F= -v key="${key}" -v val="${value}" \
      '$1==key { print key "=" val; next } { print }' \
      "${file}" > "${tmp}" \
      && mv "${tmp}" "${file}" \
      || { log_error "write_kv_conf: failed to update ${key} in ${file}"; rm -f "${tmp}"; return 1; }
    return 0
  fi

  # Key not present — append it.
  log_info "pkg: appending ${key}=${value} to ${file}"
  printf '%s=%s\n' "${key}" "${value}" >> "${file}" \
    || { log_error "write_kv_conf: failed to append to ${file}"; return 1; }
}

# ---------------------------------------------------------------------------
# comment_block <file> <begin-marker> <end-marker>
#   Prefix `# ` to each non-empty, non-already-commented line within a
#   delimited block. Idempotent: already-commented lines are untouched.
#   Lines outside the block are preserved unchanged.
# ---------------------------------------------------------------------------
comment_block() {
  local file="$1" begin="$2" end="$3"

  if [[ ! -f "${file}" ]]; then
    log_error "comment_block: file not found: ${file}"
    return 1
  fi

  local tmp
  tmp="$(mktemp)" || { log_error "comment_block: mktemp failed"; return 1; }

  local inside=0
  while IFS= read -r line || [[ -n "${line}" ]]; do
    if [[ "${line}" == "${begin}" ]]; then
      inside=1
      printf '%s\n' "${line}" >> "${tmp}"
      continue
    fi
    if [[ "${line}" == "${end}" ]]; then
      inside=0
      printf '%s\n' "${line}" >> "${tmp}"
      continue
    fi
    if [[ "${inside}" -eq 1 ]]; then
      # Comment the line if not already commented and not empty.
      if [[ -n "${line}" && "${line}" != "# "* ]]; then
        printf '# %s\n' "${line}" >> "${tmp}"
      else
        printf '%s\n' "${line}" >> "${tmp}"
      fi
    else
      printf '%s\n' "${line}" >> "${tmp}"
    fi
  done < "${file}"

  mv "${tmp}" "${file}" \
    || { log_error "comment_block: failed to update ${file}"; rm -f "${tmp}"; return 1; }
}

# ---------------------------------------------------------------------------
# mise_drift
#   Detect whether both mise and a legacy manager are active simultaneously.
#   Prints one of:
#     both       — mise on PATH AND an uncommented nvm/sdkman init line exists in ~/.bashrc
#     mise-only  — mise on PATH, no uncommented legacy init hook in ~/.bashrc
#     neither    — mise not on PATH
#   Exits 0 always (read-only probe; used by cmd_doctor for FR-008).
#
#   "Legacy active" means an UNCOMMENTED shell-hook line is still present in
#   ~/.bashrc that would cause nvm or sdkman to activate on login.  Mere
#   directory presence (~/.nvm, ~/.sdkman) is NOT sufficient — the migration
#   deliberately leaves those dirs intact and only comments out the hooks.
#   Patterns matched (tolerant of leading whitespace, not starting with '#'):
#     nvm   — line containing NVM_DIR or nvm.sh not starting with optional-ws '#'
#     sdkman — line containing SDKMAN_DIR or sdkman-init.sh not starting with optional-ws '#'
# ---------------------------------------------------------------------------
mise_drift() {
  local has_mise=0 has_legacy=0
  local bashrc="${HOME}/.bashrc"

  have mise && has_mise=1

  if [[ -f "${bashrc}" ]]; then
    # An uncommented line (not starting with optional-whitespace then '#') that
    # references an nvm or sdkman hook.  grep -E; two separate patterns ORed.
    if grep -qE '^[[:space:]]*[^#[:space:]][^#]*((NVM_DIR|nvm\.sh)|(SDKMAN_DIR|sdkman-init\.sh))' \
         "${bashrc}" 2>/dev/null; then
      has_legacy=1
    fi
  fi

  if [[ "${has_mise}" -eq 1 && "${has_legacy}" -eq 1 ]]; then
    printf 'both\n'
  elif [[ "${has_mise}" -eq 1 ]]; then
    printf 'mise-only\n'
  else
    printf 'neither\n'
  fi
}
