# lib/profile.sh — expand profile tokens to a flat module set. Source-only.
_profiles_json() { toml_to_json "${DEVBOOST_PROFILES:-$DEVBOOST_ROOT/profiles.toml}"; }

profile_names() { _profiles_json | jq -r '.profiles // {} | keys[]'; }

_profile_is() { # is token a profile name?
  _profiles_json | jq -e --arg k "$1" '(.profiles // {}) | has($k)' >/dev/null
}

profile_expand() {
  local -A seen=() out=() ; local -a stack=("$@")
  while ((${#stack[@]})); do
    local t="${stack[0]}"; stack=("${stack[@]:1}")
    [[ -n "${seen[$t]:-}" ]] && continue
    seen[$t]=1
    if _profile_is "$t"; then
      local m
      while IFS= read -r m; do [[ -n "$m" ]] && stack+=("$m"); done \
        < <(_profiles_json | jq -r --arg k "$t" '.profiles[$k][]')
    else
      out[$t]=1
    fi
  done
  printf '%s\n' "${!out[@]}"
}
