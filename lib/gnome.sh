# lib/gnome.sh — shared GNOME helpers for gnome-desktop modules. Source-only.
# Depends on lib/log.sh and lib/pkg.sh (have/need_cmd). No side effects on source.
# All external commands (gnome-shell, gext, gsettings, dconf) are PATH-stubbable.

# ---------------------------------------------------------------------------
# gnome_require
#   Die "unsupported: not a GNOME desktop" (non-zero) unless GNOME is detected.
#   Detection: gnome-shell --version exits 0 OR $XDG_CURRENT_DESKTOP contains GNOME.
#   Uses these checks rather than `command -v gnome-shell` because the binary is
#   always on PATH in CI — only the --version exit code reflects real presence.
# ---------------------------------------------------------------------------
gnome_require() {
  if gnome-shell --version >/dev/null 2>&1 || [[ "${XDG_CURRENT_DESKTOP:-}" == *GNOME* ]]; then
    return 0
  fi
  die "unsupported: not a GNOME desktop"
}

# ---------------------------------------------------------------------------
# gnome_shell_version
#   Print the major GNOME Shell version integer (e.g. "47" from "GNOME Shell 47.0").
#   Used by ext_install to pass --shell-version to gext.
# ---------------------------------------------------------------------------
gnome_shell_version() {
  gnome-shell --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+' | head -1 | cut -d. -f1
}

# ---------------------------------------------------------------------------
# ext_install <UUID>
#   Install an extension via `gext install <UUID>`.
#   Idempotent: skips the gext call if the extension directory already exists.
# ---------------------------------------------------------------------------
ext_install() {
  local uuid="$1"
  local ext_dir="${HOME}/.local/share/gnome-shell/extensions/${uuid}"
  if [[ -d "${ext_dir}" ]]; then
    log_skip "ext_install: ${uuid} already installed (dir present)"
    return 0
  fi
  log_info "gnome: installing extension ${uuid}"
  gext install "${uuid}"
}

# ---------------------------------------------------------------------------
# ext_verify_author <UUID>
#   Read the installed metadata.json and confirm its "uuid" field equals <UUID>.
#   The UUID embeds the author domain, so a mismatch signals a tampered extension.
#   Non-zero + named error on mismatch.
# ---------------------------------------------------------------------------
ext_verify_author() {
  local uuid="$1"
  local metadata="${HOME}/.local/share/gnome-shell/extensions/${uuid}/metadata.json"
  if [[ ! -f "${metadata}" ]]; then
    log_error "ext_verify_author: metadata.json not found for ${uuid}"
    return 1
  fi
  local actual_uuid
  actual_uuid="$(grep -oP '"uuid"\s*:\s*"\K[^"]+' "${metadata}" 2>/dev/null \
    || sed -n 's/.*"uuid"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "${metadata}" | head -1)"
  if [[ "${actual_uuid}" != "${uuid}" ]]; then
    log_error "ext_verify_author: UUID mismatch for ${uuid} — got '${actual_uuid}' (author-verify failed)"
    return 1
  fi
  log_ok "gnome: extension ${uuid} author verified"
}

# ---------------------------------------------------------------------------
# ext_enable <UUID>
#   Append <UUID> to org.gnome.shell enabled-extensions via gsettings, deduplicating.
#   Reads the current list, appends only if absent, writes back. Idempotent.
#   No live GNOME session required; the next session will honor the updated list.
# ---------------------------------------------------------------------------
ext_enable() {
  local uuid="$1"
  # Read the current list — gsettings prints @as ['a','b'] or @as []
  local current
  current="$(gsettings get org.gnome.shell enabled-extensions 2>/dev/null || printf '@as []')"

  # Check if UUID is already present
  if [[ "${current}" == *"${uuid}"* ]]; then
    log_skip "ext_enable: ${uuid} already in enabled-extensions"
    return 0
  fi

  # Parse the existing list into a bash array of UUIDs
  # Input forms: @as [] or ['uuid1', 'uuid2'] or @as ['uuid1']
  local inner
  # Strip leading @as and brackets to get inner content
  inner="${current}"
  inner="${inner#@as }"                  # strip optional @as prefix
  inner="${inner#\[}"; inner="${inner%\]}"  # strip [ ]
  # Trim whitespace
  inner="$(printf '%s' "${inner}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

  local new_list
  if [[ -z "${inner}" ]]; then
    new_list="['${uuid}']"
  else
    # Append the new UUID to the existing list
    # inner already has 'uuid1', 'uuid2' format
    new_list="[${inner}, '${uuid}']"
  fi

  log_info "gnome: enabling extension ${uuid}"
  gsettings set org.gnome.shell enabled-extensions "${new_list}"
}

# ---------------------------------------------------------------------------
# dconf_load_managed <dump-file>
#   Load a dconf dump file into /org/gnome/ via `dconf load`.
#   Idempotent: dconf load sets exact values; re-running produces the same state.
# ---------------------------------------------------------------------------
dconf_load_managed() {
  local dump_file="$1"
  if [[ ! -f "${dump_file}" ]]; then
    log_error "dconf_load_managed: dump file not found: ${dump_file}"
    return 1
  fi
  log_info "gnome: loading dconf settings from ${dump_file}"
  dconf load /org/gnome/ < "${dump_file}"
}
