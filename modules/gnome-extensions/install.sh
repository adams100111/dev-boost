#!/usr/bin/env bash
# modules/gnome-extensions/install.sh — install + enable the 6 curated functional GNOME
# extensions by pinned UUID via gext, author-verified, session-free, idempotent.
#
# Each UUID embeds the author domain — author-verify guards against tampered packages.
# Enabling uses gsettings (no live session required); the next session honors the list.
# Idempotent: gext skips already-installed; enable deduplicates.
# No secrets. No prompts.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"
source "${DEVBOOST_ROOT}/lib/gnome.sh"

# ---------------------------------------------------------------------------
# Guard: fail fast on non-GNOME systems (FR-010/SC-005).
# ---------------------------------------------------------------------------
gnome_require

# ---------------------------------------------------------------------------
# Ensure gext (gnome-extensions-cli) is available.
# ---------------------------------------------------------------------------
if ! have gext; then
  log_info "gnome-extensions: installing gext (gnome-extensions-cli)"
  pipx install gnome-extensions-cli --include-deps >/dev/null 2>&1 \
    || dnf_install python3-gnome-extensions-cli
fi

# ---------------------------------------------------------------------------
# Pinned functional UUID set (spec §D5 / contracts/gnome-extensions.md).
# Order is stable; each UUID embeds the author's domain.
# ---------------------------------------------------------------------------
_FUNCTIONAL_UUIDS=(
  "appindicatorsupport@rgcjonas.gmail.com"
  "clipboard-indicator@tudmotu.com"
  "caffeine@patapon.info"
  "gsconnect@andyholmes.github.io"
  "dash-to-dock@micxgx.gmail.com"
  "emoji-copy@felipeftn"
)

# ---------------------------------------------------------------------------
# Verify-only mode: check all UUIDs present + enabled.
# Used by module.toml verify expression.
# ---------------------------------------------------------------------------
if [[ "${1:-}" == "--verify-only" ]]; then
  enabled="$(gsettings get org.gnome.shell enabled-extensions 2>/dev/null || printf '@as []')"
  for uuid in "${_FUNCTIONAL_UUIDS[@]}"; do
    ext_dir="${HOME}/.local/share/gnome-shell/extensions/${uuid}"
    if [[ ! -d "${ext_dir}" ]]; then
      log_error "gnome-extensions verify: extension dir absent for ${uuid}"
      exit 1
    fi
    if [[ "${enabled}" != *"${uuid}"* ]]; then
      log_error "gnome-extensions verify: ${uuid} not in enabled-extensions"
      exit 1
    fi
  done
  log_ok "gnome-extensions: all 6 functional extensions present and enabled"
  exit 0
fi

# ---------------------------------------------------------------------------
# Install + author-verify + enable each pinned UUID.
# ---------------------------------------------------------------------------
for uuid in "${_FUNCTIONAL_UUIDS[@]}"; do
  # Step 1: install via gext (idempotent — skips if dir already present).
  ext_install "${uuid}"

  # Step 2: author-verify — UUID in metadata.json must match pinned value.
  # A mismatch signals a tampered extension; we fail named and stop.
  if ! ext_verify_author "${uuid}"; then
    log_error "gnome-extensions: author-verify failed for ${uuid} — aborting"
    exit 1
  fi

  # Step 3: enable (dedup — adds to enabled-extensions only if absent).
  ext_enable "${uuid}"
done

log_ok "gnome-extensions: all 6 functional extensions installed, verified, and enabled"
