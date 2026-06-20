#!/usr/bin/env bash
# modules/gnome-settings/install.sh — apply reference GNOME look-and-feel via dconf.
# Requires a GNOME desktop session environment (gnome-shell present).
# Mechanism: dconf load /org/gnome/ < gnome.dconf (single declarative load, idempotent).
# No prompts. No secrets. enabled-extensions is NOT managed here (owned by gnome-extensions).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"
source "${DEVBOOST_ROOT}/lib/gnome.sh"

# ---------------------------------------------------------------------------
# Guard: fail fast on non-GNOME systems (FR-010/SC-005).
# gnome_require dies "unsupported: not a GNOME desktop" if GNOME is absent.
# ---------------------------------------------------------------------------
gnome_require

# ---------------------------------------------------------------------------
# Load the reference dconf dump into /org/gnome/.
# Declarative and idempotent: re-running dconf load produces the same state.
# ---------------------------------------------------------------------------
_dump="${DEVBOOST_ROOT}/modules/gnome-settings/gnome.dconf"

dconf_load_managed "${_dump}"

log_ok "gnome-settings: reference look-and-feel applied"
