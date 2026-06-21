#!/usr/bin/env bash
# scripts/make-secrets.sh — build the age-encrypted secrets bundle for dev-boost.
#
# Produces (in --out DIR, default ./):
#   age-key.txt   the age IDENTITY (private key) — goes on the USB next to secrets.age (zero-touch),
#                 or pass it via DEVBOOST_SECRETS_KEY. NEVER commit it.
#   secrets.age   the encrypted JSON bundle { GIT_USER, GIT_EMAIL, GITHUB_PAT } that lib/secrets.sh decrypts.
#
# Inputs (env or interactive prompt): GIT_USER, GIT_EMAIL, GITHUB_PAT.
# The PAT is read silently and NEVER printed or logged.
set -Eeuo pipefail

die() { printf 'make-secrets: %s\n' "$*" >&2; exit 1; }
command -v age        >/dev/null 2>&1 || die "missing 'age' — sudo dnf install -y age"
command -v age-keygen >/dev/null 2>&1 || die "missing 'age-keygen' (ships with age)"
command -v jq         >/dev/null 2>&1 || die "missing 'jq' — sudo dnf install -y jq"

out="."
while (($#)); do case "$1" in --out) out="${2:?--out needs a dir}"; shift 2;; *) die "unknown option '$1'";; esac; done
mkdir -p "${out}"
key="${out}/age-key.txt"; bundle="${out}/secrets.age"

# Collect inputs (env wins; otherwise prompt). PAT is silent.
: "${GIT_USER:=}"; : "${GIT_EMAIL:=}"; : "${GITHUB_PAT:=}"
[[ -n "${GIT_USER}"  ]] || read -r  -p "GitHub username (GIT_USER): " GIT_USER
[[ -n "${GIT_EMAIL}" ]] || read -r  -p "Git email (GIT_EMAIL): " GIT_EMAIL
[[ -n "${GITHUB_PAT}" ]] || { read -rs -p "GitHub PAT (GITHUB_PAT, hidden): " GITHUB_PAT; echo; }
[[ -n "${GIT_USER}" && -n "${GIT_EMAIL}" && -n "${GITHUB_PAT}" ]] || die "all of GIT_USER, GIT_EMAIL, GITHUB_PAT are required"

# Generate the age identity only if absent (idempotent; never overwrite a key in use).
if [[ -f "${key}" ]]; then
  printf 'make-secrets: reusing existing identity %s\n' "${key}" >&2
else
  age-keygen -o "${key}" >/dev/null 2>&1 || die "age-keygen failed"
  chmod 600 "${key}"
fi
recipient="$(age-keygen -y "${key}")" || die "could not derive recipient from ${key}"

# Build the JSON bundle and encrypt to the recipient. The PAT only ever transits a pipe.
jq -n --arg u "${GIT_USER}" --arg e "${GIT_EMAIL}" --arg p "${GITHUB_PAT}" \
  '{GIT_USER:$u, GIT_EMAIL:$e, GITHUB_PAT:$p}' \
  | age -r "${recipient}" -o "${bundle}" || die "age encryption failed"
chmod 600 "${bundle}"

cat >&2 <<EOF
make-secrets: wrote ${bundle} (encrypted) + ${key} (identity).
  • Zero-touch USB: copy BOTH to the USB Bootstrap/ (the installer reads age-key.txt to decrypt).
  • Manual / testing: ./install.sh --secrets ${bundle}   (with DEVBOOST_SECRETS_KEY=${key})
  • NEVER commit age-key.txt or secrets.age — both are gitignored.
EOF
