#!/usr/bin/env bash
set -Eeuo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ensure_dep() {  # <cmd> <fedora-pkg>
  if [[ "${DEVBOOST_DRYRUN:-0}" == 1 ]]; then
    if command -v "$1" >/dev/null; then
      echo "dep ok: $1"
    else
      echo "would install dep: $1 ($2)"
    fi
    return 0
  fi
  command -v "$1" >/dev/null && return 0
  if command -v sudo >/dev/null && command -v dnf >/dev/null; then
    sudo dnf install -y "$2"
  else
    echo "ERROR: missing $1 and cannot auto-install" >&2; exit 1
  fi
}

ensure_dep python3 python3
ensure_dep jq jq

if [[ "${DEVBOOST_DRYRUN:-0}" == 1 ]]; then
  printf 'would run: bin/devboost install %s\n' "$*"; exit 0
fi
exec "$HERE/bin/devboost" install "$@"
