# lib/module.sh — module manifest model. Source-only.
declare -A _MOD_JSON

module_file() {
  local name="$1" base="${DEVBOOST_MODULES_DIR:-$DEVBOOST_ROOT/modules}"
  if   [[ -f "$base/$name.toml" ]];        then echo "$base/$name.toml"
  elif [[ -f "$base/$name/module.toml" ]]; then echo "$base/$name/module.toml"
  else die "module not found: $name"; fi
}

module_json() {
  local name="$1"
  [[ -n "${_MOD_JSON[$name]:-}" ]] && { printf '%s' "${_MOD_JSON[$name]}"; return; }
  local json; json="$(toml_to_json "$(module_file "$name")")"
  _MOD_JSON[$name]="$json"
  printf '%s' "$json"
}

module_field() {  # <name> <jq-filter>
  module_json "$1" | jq -r "$2 // empty"
}

module_requires() {  # newline list
  module_json "$1" | jq -r '(.requires // [])[]'
}

module_install_cmd() {
  local name="$1" cmd
  cmd="$(module_field "$name" ".install.\"$OS_DISTRO\"")"
  [[ -z "$cmd" ]] && cmd="$(module_field "$name" ".install.\"$OS_FAMILY\"")"
  [[ -z "$cmd" ]] && cmd="$(module_field "$name" '.install.default')"
  printf '%s' "$cmd"
}

module_verify_cmd() { module_field "$1" '.install.verify // .verify'; }
