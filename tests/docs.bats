load test_helper

# Spec 12 — docs-and-readme: README drift gate (profiles + verbs) + docs presence + generator.

@test "gen-profiles-table.sh runs and emits a markdown table row per profile" {
  run bash "${DEVBOOST_ROOT}/scripts/gen-profiles-table.sh"
  [ "$status" -eq 0 ]
  [[ "$output" == *"| Profile | Installs"* ]]
  # one row per profile in profiles.toml
  local n_profiles n_rows
  n_profiles="$(bash -c 'source "$DEVBOOST_ROOT/lib/log.sh"; source "$DEVBOOST_ROOT/lib/toml.sh"; source "$DEVBOOST_ROOT/lib/profile.sh"; DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_names | wc -l')"
  n_rows="$(printf '%s\n' "$output" | grep -cE '^\| `')"
  [ "$n_rows" -eq "$n_profiles" ]
}

@test "README lists EVERY profile in profiles.toml (no drift)" {
  local p
  while IFS= read -r p; do
    [[ -n "$p" ]] || continue
    grep -qF "\`${p}\`" "${DEVBOOST_ROOT}/README.md" || { echo "README missing profile: ${p}"; return 1; }
  done < <(bash -c 'source "$DEVBOOST_ROOT/lib/log.sh"; source "$DEVBOOST_ROOT/lib/toml.sh"; source "$DEVBOOST_ROOT/lib/profile.sh"; DEVBOOST_PROFILES="$DEVBOOST_ROOT/profiles.toml" profile_names')
}

@test "README documents every CLI verb" {
  for v in install verify list doctor add export diff update self-update dev; do
    grep -qE "devboost ${v}\b|\`${v}\`|\\b${v}\\b" "${DEVBOOST_ROOT}/README.md" || { echo "README missing verb: ${v}"; return 1; }
  done
}

@test "README has quick start + recovery + add-a-tool sections" {
  grep -q '## Quick start' "${DEVBOOST_ROOT}/README.md"
  grep -qiE 'install.sh|curl .* bash' "${DEVBOOST_ROOT}/README.md"
  grep -qi 'Recovery' "${DEVBOOST_ROOT}/README.md"
  grep -qi 'Adding a tool' "${DEVBOOST_ROOT}/README.md"
}

@test "all six docs/ files exist with substantive content" {
  for d in architecture recovery-runbook adding-a-module maintenance obsidian-sync ventoy; do
    f="${DEVBOOST_ROOT}/docs/${d}.md"
    [ -f "$f" ] || { echo "missing docs/${d}.md"; return 1; }
    [ "$(wc -l < "$f")" -ge 20 ] || { echo "docs/${d}.md too short"; return 1; }
  done
}
