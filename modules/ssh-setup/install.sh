#!/usr/bin/env bash
# modules/ssh-setup/install.sh — generate ed25519 key and register with GitHub.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME, XDG_STATE_HOME.
# No prompts; idempotent (safe to re-run); non-blocking upload failure.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/secrets.sh"
source "${DEVBOOST_ROOT}/lib/github.sh"

# ---------------------------------------------------------------------------
# Step 1: generate ed25519 keypair if absent (never overwrite; FR-005)
# ---------------------------------------------------------------------------
if [[ ! -f "${HOME}/.ssh/id_ed25519" ]]; then
  log_info "ssh-setup: generating ed25519 keypair"
  mkdir -p "${HOME}/.ssh"
  chmod 700 "${HOME}/.ssh"
  ssh-keygen -t ed25519 -N "" -C "devboost:$(hostname)" -f "${HOME}/.ssh/id_ed25519"
else
  log_info "ssh-setup: existing key found, skipping keygen (FR-005)"
fi

# Ensure correct permissions regardless of how the key was created.
chmod 700 "${HOME}/.ssh"
chmod 600 "${HOME}/.ssh/id_ed25519"

# ---------------------------------------------------------------------------
# Step 2: ensure hardened, marker-delimited block in ~/.ssh/config
# ---------------------------------------------------------------------------
ssh_config="${HOME}/.ssh/config"
touch "${ssh_config}"

begin_marker="# BEGIN devboost-managed"
end_marker="# END devboost-managed"

devboost_block="${begin_marker}
Host *
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
  AddKeysToAgent yes
  HashKnownHosts yes
${end_marker}"

if grep -qF "${begin_marker}" "${ssh_config}" 2>/dev/null; then
  # Block already present — replace content between markers (idempotent).
  # Build a temp file with the block replaced.
  tmp_cfg="$(mktemp)"
  trap 'rm -f "${tmp_cfg}"' EXIT

  awk -v begin="${begin_marker}" -v end="${end_marker}" -v block="${devboost_block}" '
    $0 == begin { in_block=1; print block; next }
    in_block && $0 == end { in_block=0; next }
    in_block { next }
    { print }
  ' "${ssh_config}" > "${tmp_cfg}"
  mv "${tmp_cfg}" "${ssh_config}"
else
  # No managed block yet — append it.
  printf '\n%s\n' "${devboost_block}" >> "${ssh_config}"
fi

log_info "ssh-setup: ~/.ssh/config hardened block ensured"

# ---------------------------------------------------------------------------
# Step 3: upload public key to GitHub (non-blocking on failure; FR-007)
# ---------------------------------------------------------------------------
pat="$(secrets_pat)"
export GITHUB_PAT="${pat}"

title="devboost:$(hostname)"
pubkey_file="${HOME}/.ssh/id_ed25519.pub"

if gh_upload_ssh_key "${pubkey_file}" "${title}"; then
  # Success or already-registered — write the state marker.
  marker_dir="${XDG_STATE_HOME:-${HOME}/.local/state}/devboost"
  mkdir -p "${marker_dir}"
  touch "${marker_dir}/ssh-key-registered"
  log_ok "ssh-setup: state marker written"
else
  # Upload failed: warn and return 0 (non-blocking).
  # The engine will re-run verify after install; without the marker it will be
  # red, allowing --strict to abort or default mode to continue (FR-007).
  log_warn "ssh-setup: GitHub key upload failed — will retry on next run"
  return 0 2>/dev/null || exit 0
fi
