#!/usr/bin/env bash
# Minimal, responsive Claude Code status line — self-contained, Catppuccin Mocha.
# Layout: left (dir · git) hugs left; right (model · context% · cost) is justified
# to the right edge. As the window narrows, items drop lowest-first:
# cost → model → branch, always keeping directory and the context %.
# Context % is color-thresholded: green <50 · yellow 50–79 · red ≥80.
# (RAM/disk live in the WezTerm top status bar, not here.)
input=$(cat)
cols=${COLUMNS:-80}
dir=$(printf '%s' "$input" | jq -r '.workspace.current_dir // .cwd // ""')
branch=$(git -C "$dir" branch --show-current 2>/dev/null)

INPUT="$input" COLS="$cols" BRANCH="$branch" python3 - <<'PY'
import json, os, re, unicodedata, sys

d = json.loads(os.environ.get("INPUT") or "{}")
cw_cols = int(os.environ.get("COLS") or 80)
branch  = os.environ.get("BRANCH") or ""

model = (d.get("model") or {}).get("display_name") or "?"
ctx   = int((d.get("context_window") or {}).get("used_percentage") or 0)
cost  = float((d.get("cost") or {}).get("total_cost_usd") or 0)
ws    = d.get("workspace") or {}
name  = (ws.get("repo") or {}).get("name") or os.path.basename(ws.get("current_dir") or d.get("cwd") or "") or "?"

# Catppuccin Mocha
BLUE="137;180;250"; MAUVE="203;166;247"; GREEN="166;227;161"
YELLOW="249;226;175"; RED="243;139;168"; TEXT="205;214;244"; DIM="108;112;134"
cc = RED if ctx >= 80 else YELLOW if ctx >= 50 else GREEN
def c(rgb, s): return f"\x1b[38;2;{rgb}m{s}\x1b[0m"

# Display (terminal cell) width: Nerd Font PUA glyphs render as 2 cells in WezTerm.
def width(s):
    s = re.sub(r"\x1b\[[0-9;]*m", "", s)
    w = 0
    for ch in s:
        o = ord(ch)
        if 0xE000 <= o <= 0xF8FF or 0xF0000 <= o <= 0xFFFFD or 0x100000 <= o <= 0x10FFFD:
            w += 2
        elif unicodedata.combining(ch):
            w += 0
        elif unicodedata.east_asian_width(ch) in ("W", "F"):
            w += 2
        else:
            w += 1
    return w

dir_s    = " " + c(BLUE, f" {name}")
branch_s = "  " + c(MAUVE, f" {branch}") if branch else ""
model_s  = c(TEXT, f"󰚩 {model}")
ctx_s    = c(cc,   f"󰧑 {ctx}%")
cost_s   = c(DIM,  f"${cost:.2f}")

def join(parts): return "  ".join(p for p in parts if p)

# Richest→leanest; first that fits wins. Drop cost→model→branch; dir & ctx survive.
candidates = [
    (dir_s + branch_s, [model_s, ctx_s, cost_s]),
    (dir_s + branch_s, [model_s, ctx_s]),
    (dir_s + branch_s, [ctx_s]),
    (dir_s,            [ctx_s]),
    (dir_s,            []),
]
left, right_parts = candidates[-1]
for L, R in candidates:
    if width(L) + width(join(R)) + 1 <= cw_cols:
        left, right_parts = L, R
        break

right = join(right_parts)
gap = cw_cols - width(left) - width(right) - 1
sys.stdout.write(left + " " * gap + right if right and gap >= 1 else left)
PY
