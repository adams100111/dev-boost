#!/usr/bin/env bash
# Minimal, responsive Claude Code status line — self-contained, Catppuccin Mocha.
# Layout: left = environment (dir · git branch · RAM · disk) hugs left; right =
# Claude session (model · context% · cost) is justified to the right edge. Machine
# gauges live with dir/branch, kept out of the session metrics you actively watch.
# As the window narrows, items drop: cost → disk → ram → model → branch; directory
# and context % always survive.
# Context % is color-thresholded: green <50 · yellow 50–79 · red ≥80.
# RAM/disk gauges mirror the WezTerm status bar / starship prompt, for headless &
# SSH sessions (and inside Claude) where WezTerm's top bar isn't running.
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
TEAL="148;226;213"
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

# System resources — RAM used% (green<60·yellow60–79·red≥80) and free disk on /
# (teal, red when / is ≥80% used); same probes/thresholds as status.lua/starship.
# Linux /proc + statvfs; blanks out on failure or non-Linux so the layout omits them.
ram = None
try:
    mt = ma = 0
    with open("/proc/meminfo") as _fh:
        for _ln in _fh:
            if _ln.startswith("MemTotal:"):       mt = int(_ln.split()[1])
            elif _ln.startswith("MemAvailable:"): ma = int(_ln.split()[1])
    if mt:
        ram = round((mt - ma) / mt * 100)
except OSError:
    pass
dfree = dpct = None
try:
    _st = os.statvfs("/")
    _used  = _st.f_blocks - _st.f_bfree
    _denom = _used + _st.f_bavail
    dpct  = round(_used * 100 / _denom) if _denom else 0
    dfree = round(_st.f_bavail * _st.f_frsize / (1024 ** 3))
except OSError:
    pass
ram_s  = c(RED if ram >= 80 else YELLOW if ram >= 60 else GREEN, f"󰍛 {ram}%") if ram is not None else ""
disk_s = c(RED if (dpct or 0) >= 80 else TEAL, f"󰋊 {dfree}G") if dfree is not None else ""
# Critical thresholds mirror WezTerm status.lua (RAM_CRITICAL=80, DISK_LOW_GB=10).
critical = (ram is not None and ram >= 80) or (dfree is not None and dfree < 10)
# Left-side variants: RAM/disk group with dir/branch as "environment" context, so
# leading separators are baked in here (the right side gets them from join()).
ram_l  = ("  " + ram_s)  if ram_s  else ""
disk_l = ("  " + disk_s) if disk_s else ""

def join(parts): return "  ".join(p for p in parts if p)

# Richest→leanest; first that fits wins. Left = environment (dir · branch · RAM ·
# disk); right = Claude session (model · ctx% · cost) — keeps machine gauges out of
# the session metrics you actively watch. Drop order: cost → disk → ram → model →
# branch; dir & ctx% always survive.
candidates = [
    (dir_s + branch_s + ram_l + disk_l, [model_s, ctx_s, cost_s]),
    (dir_s + branch_s + ram_l + disk_l, [model_s, ctx_s]),
    (dir_s + branch_s + ram_l,          [model_s, ctx_s]),
    (dir_s + branch_s,                  [model_s, ctx_s]),
    (dir_s + branch_s,                  [ctx_s]),
    (dir_s,                             [ctx_s]),
    (dir_s,                             []),
]
left, right_parts = candidates[-1]
for L, R in candidates:
    # +2 = 1 trailing column kept free (avoid last-cell wrap) + ≥1 space between
    # left and right. Must match the writer below, else a candidate can "fit" with
    # gap==0 and the writer drops the entire right side (blank status at that width).
    if width(L) + width(join(R)) + 2 <= cw_cols:
        left, right_parts = L, R
        break

right = join(right_parts)
gap = cw_cols - width(left) - width(right) - 1
line = left + " " * gap + right if right and gap >= 1 else left

if critical:
    # Resource alert — WezTerm floods the window bg via window_background_gradient;
    # the shell/Claude can't repaint the terminal, but it owns THIS row, so flood the
    # whole row red instead. Flatten the per-segment fg colors to dark-on-red and pad
    # to full width. Repainted every render, so it clears itself on recovery.
    plain = re.sub(r"\x1b\[[0-9;]*m", "", line)
    plain += " " * max(0, (cw_cols - 1) - width(plain))
    sys.stdout.write(f"\x1b[48;2;{RED};38;2;30;30;46m{plain}\x1b[0m")
else:
    sys.stdout.write(line)
PY
