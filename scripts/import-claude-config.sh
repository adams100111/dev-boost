#!/usr/bin/env bash
# import-claude-config.sh — one-time seed of the repo from the live ~/.claude.
# Mechanical parts are automated; skills classification is printed for human review.
# Safe to re-run. Makes NO git commit.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLAUDE="$HOME/.claude"
AGENTS="$HOME/.agents"
DOT_CLAUDE="$REPO_ROOT/dotfiles/private_dot_claude"
DOT_AGENTS="$REPO_ROOT/dotfiles/private_dot_agents"

mkdir -p "$DOT_CLAUDE/rules" "$DOT_CLAUDE/skills" "$DOT_AGENTS"

# 1. CLAUDE.md + rules (pure text, no secrets)
[ -f "$CLAUDE/CLAUDE.md" ] && cp "$CLAUDE/CLAUDE.md" "$DOT_CLAUDE/CLAUDE.md"
if [ -d "$CLAUDE/rules" ]; then cp -a "$CLAUDE/rules/." "$DOT_CLAUDE/rules/"; fi

# 2. commit-conventions rule (Conventional Commits + anti-attribution)
cat > "$DOT_CLAUDE/rules/commit-conventions.md" <<'EOF'
# Commit conventions

- Use Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, …
  with an optional scope, e.g. `feat(claude): add plugins module`.
- NEVER add a `Co-Authored-By: Claude …` trailer or any Claude/Anthropic attribution
  to commit messages or PR bodies.
EOF

# 3. skills lockfile (drop the .bak-* backups)
[ -f "$AGENTS/.skill-lock.json" ] && cp "$AGENTS/.skill-lock.json" "$DOT_AGENTS/.skill-lock.json"

# 4. skills classification report (upstream vs local-only) — for human review, no auto-vendor
echo "=== SKILLS CLASSIFICATION (review before vendoring) ==="
python3 - "$CLAUDE/skills" "$AGENTS/.skill-lock.json" <<'PY'
import json, os, sys
skills_dir, lock_path = sys.argv[1], sys.argv[2]
lock = set()
if os.path.isfile(lock_path):
    lock = set(json.load(open(lock_path)).get("skills", {}))
real, symlink, vendor = [], [], []
for name in sorted(os.listdir(skills_dir)) if os.path.isdir(skills_dir) else []:
    p = os.path.join(skills_dir, name)
    if os.path.islink(p):
        symlink.append(name)
    elif name in lock:
        real.append(name)          # upstream, reproduced by npx skills
    else:
        vendor.append(name)        # NOT in lock → candidate to VENDOR
print(f"symlinks (lockfile/plugin-managed): {len(symlink)}")
print(f"real + lock-tracked (reproduced):   {len(real)}")
print(f"VENDOR CANDIDATES (not in lock):    {len(vendor)}")
for n in vendor:
    print(f"  vendor? {n}")
PY

# 5. secret-scrub preview (does NOT modify ~/.claude; tells you what to move to pass)
echo "=== SECRET SCRUB (move these to pass; remove from committed config) ==="
python3 - "$CLAUDE/settings.json" <<'PY'
import json, os, sys
p = sys.argv[1]
if os.path.isfile(p):
    try:
        d = json.load(open(p))
    except ValueError:
        d = {}
    tok = (d.get("env") or {}).get("CLICKUP_API_TOKEN")
    if tok:
        print("  settings.json env.CLICKUP_API_TOKEN present -> `pass insert clickup/api-token`")
print("  standalone context7 MCP (inline ctx7sk key) -> drop; the context7 plugin covers it")
PY

echo "=== DONE. Review the vendor list, copy chosen dirs into $DOT_CLAUDE/skills/, then commit. ==="
