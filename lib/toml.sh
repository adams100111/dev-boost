# lib/toml.sh — TOML→JSON using python3 stdlib tomllib (>=3.11). Source-only.
toml_to_json() {
  local file="$1"
  command -v python3 >/dev/null || die "python3 required for TOML parsing"
  python3 - "$file" <<'PY' || die "invalid TOML: $1"
import sys, json, tomllib
with open(sys.argv[1], "rb") as fh:
    data = tomllib.load(fh)
json.dump(data, sys.stdout, separators=(",", ":"))
PY
}
