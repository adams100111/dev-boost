#!/usr/bin/env bash
# modules/pass-store/install.sh — provision GPG + initialize the pass store for unattended use.
# Analogous to how `secrets` provisions `age`. No prompts; idempotent (key/init seed-if-absent).
set -Eeuo pipefail
source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

have pass || die "pass-store: pass CLI not installed"

store="${PASSWORD_STORE_DIR:-${HOME}/.password-store}"
gpg_uid="${DEVBOOST_PASS_GPG_UID:-devboost-pass}"

# 1. GPG key for unattended decrypt — generate (passphrase-less) only if none exists.
if gpg --list-secret-keys >/dev/null 2>&1; then
  log_skip "pass-store: a GPG secret key already exists — not regenerating"
else
  log_info "pass-store: generating a passphrase-less GPG key (${gpg_uid})"
  gpg --batch --pinentry-mode loopback --passphrase '' \
    --quick-generate-key "${gpg_uid}" default default never \
    || die "pass-store: GPG key generation failed"
fi

# 2. Clone an existing password-store repo if configured and the store is absent.
if [[ -n "${DEVBOOST_PASS_REPO:-}" && ! -d "${store}" ]]; then
  log_info "pass-store: cloning password store from ${DEVBOOST_PASS_REPO}"
  git clone "${DEVBOOST_PASS_REPO}" "${store}" || die "pass-store: clone failed"
fi

# 3. Initialize the store (idempotent; writes ${store}/.gpg-id).
if [[ -f "${store}/.gpg-id" ]]; then
  log_skip "pass-store: store already initialized (${store})"
else
  log_info "pass-store: pass init ${gpg_uid}"
  pass init "${gpg_uid}" || die "pass-store: 'pass init' failed"
fi

log_ok "pass-store: password store ready (${store})"
