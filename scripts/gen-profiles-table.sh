#!/usr/bin/env bash
# scripts/gen-profiles-table.sh — emit the README profiles table from profiles.toml (design §9b).
# Generated, not hand-maintained, so docs never drift. Run: bash scripts/gen-profiles-table.sh
set -Eeuo pipefail
DEVBOOST_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/toml.sh"
source "${DEVBOOST_ROOT}/lib/profile.sh"
export DEVBOOST_PROFILES="${DEVBOOST_PROFILES:-${DEVBOOST_ROOT}/profiles.toml}"

printf '| Profile | Installs (resolved modules) |\n'
printf '|---------|------------------------------|\n'
while IFS= read -r p; do
  [[ -n "$p" ]] || continue
  mods="$(profile_expand "$p" | LC_ALL=C sort | tr '\n' ' ')"
  mods="${mods%% }"; mods="$(printf '%s' "$mods" | sed 's/  */, /g; s/, $//')"
  printf '| `%s` | %s |\n' "$p" "$mods"
done < <(profile_names | LC_ALL=C sort)
