#!/usr/bin/env bash
# import-codex-config.sh — one-time seed of the repo from the live ~/.codex. Read-only on ~/.codex
# except the secret-scrub PREVIEW. Makes NO git commit. Safe to re-run.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CODEX="$HOME/.codex"
DOT="$REPO_ROOT/dotfiles/private_dot_codex"
mkdir -p "$DOT/hooks"

# 1. AGENTS.md — copy, then fix the copy-paste attribution artifact (Codex/OpenAI, dedup)
if [ -f "$CODEX/AGENTS.md" ]; then
  sed -e 's/reference to Codex, Codex, or Anthropic/reference to Codex or OpenAI/g' \
      -e 's/Codex\/Anthropic attribution/OpenAI\/Codex attribution/g' \
      -e 's/or any Codex\/Anthropic/or any OpenAI\/Codex/g' \
      "$CODEX/AGENTS.md" > "$DOT/AGENTS.md"
fi

# 2. hooks.json -> hooks.json.tmpl: replace the literal HOME with a chezmoi template var so the
#    hook-script paths resolve to the real HOME on every device (any username).
[ -f "$CODEX/hooks.json" ] && \
  sed "s|$HOME|{{ .chezmoi.homeDir }}|g" "$CODEX/hooks.json" > "$DOT/hooks.json.tmpl"
if [ -d "$CODEX/hooks" ]; then
  for f in "$CODEX/hooks"/*; do [ -f "$f" ] && cp "$f" "$DOT/hooks/executable_$(basename "$f")"; done
fi

# NOTE: Codex USER skills live in ~/.agents/skills (auto-discovered, shared with ~/.claude), NOT
# ~/.codex/skills (which holds only bundled .system skills). Vendored skills are seeded separately
# into dotfiles/private_dot_agents/skills below.

# 3. secret-scrub PREVIEW (read-only; does not modify ~/.codex)
echo "=== SECRET SCRUB (Codex) ==="
python3 - "$CODEX/config.toml" <<'PY'
import os, sys, tomllib
p = sys.argv[1]
if os.path.isfile(p):
    d = tomllib.loads(open(p, encoding="utf-8").read())
    if (d.get("shell_environment_policy", {}).get("set", {})).get("CLICKUP_API_TOKEN"):
        print("  config.toml CLICKUP_API_TOKEN present -> already in pass; codex-config re-supplies it")
    if "context7" in d.get("mcp_servers", {}):
        print("  context7 MCP (inline ctx7sk key) -> drop: `codex mcp remove context7`; plugin covers it")
PY
echo "=== DONE. Vendor chosen skills into dotfiles/private_dot_agents/skills/ (~/.agents/skills), then commit. ==="
