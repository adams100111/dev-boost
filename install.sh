#!/usr/bin/env bash
set -Eeuo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ensure_dep() {  # <cmd> <fedora-pkg> [<debian-pkg>] [<brew-formula>]
  local cmd="$1" fedora_pkg="$2" debian_pkg="${3:-$2}" brew_formula="${4:-$1}"
  if [[ "${DEVBOOST_DRYRUN:-0}" == 1 ]]; then
    if command -v "${cmd}" >/dev/null; then
      echo "dep ok: ${cmd}"
    else
      echo "would install dep: ${cmd} (${fedora_pkg})"
    fi
    return 0
  fi
  command -v "${cmd}" >/dev/null && return 0
  if command -v sudo >/dev/null && command -v dnf >/dev/null; then
    sudo dnf install -y "${fedora_pkg}"
  elif command -v sudo >/dev/null && command -v apt-get >/dev/null; then
    sudo apt-get install -y "${debian_pkg}"
  elif command -v brew >/dev/null; then
    brew install "${brew_formula}"
  else
    echo "ERROR: missing ${cmd} and cannot auto-install" >&2; exit 1
  fi
}

ensure_dep python3 python3
ensure_dep jq jq
ensure_dep age age age age

if [[ "${DEVBOOST_DRYRUN:-0}" == 1 ]]; then
  printf 'would run: bin/devboost install %s\n' "$*"; exit 0
fi
exec "$HERE/bin/devboost" install "$@"
