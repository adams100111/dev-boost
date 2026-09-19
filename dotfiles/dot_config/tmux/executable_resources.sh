#!/bin/sh
# RAM/disk gauges for the tmux status line — the persistent surface that stays visible
# while a full-screen app (fresh, vim, less, htop, lazygit) fills the pane, unlike the
# shell prompt. tmux interprets the #[...] style directives in this output (tmux >= 2.9).
#
# Same probe and thresholds as the starship prompt, WezTerm's status.lua and the Claude
# status line — all read ~/.local/bin/devboost-resources (Linux and macOS):
#   RAM  󰍛 used%   green <60 · yellow 60-79 · red >=80
#   DISK 󰋊 free-G  teal, red at >=80% used
# Critical (RAM >=80 or free <10G) flips the whole segment to a red badge, matching the
# alerts on the other surfaces. Refreshed on status-interval.
set -u

# shellcheck disable=SC2046 # splitting the probe's three numbers into $1 $2 $3 is the point
set -- $("${HOME}/.local/bin/devboost-resources" 2>/dev/null)
[ "$#" -eq 3 ] || exit 0
ram=$1 used=$2 free=$3

green='#a6e3a1'; yellow='#f9e2af'; red='#f38ba8'; teal='#94e2d5'; base='#1e1e2e'

if [ "$ram" -ge 80 ] || [ "$free" -lt 10 ]; then
  # Critical → red badge (wezterm / Claude / starship parity).
  printf '#[fg=%s,bg=%s,bold] ⚠ 󰍛 %s%% 󰋊 %sG #[default]' "$base" "$red" "$ram" "$free"
else
  if [ "$ram" -ge 60 ]; then rc=$yellow; else rc=$green; fi
  if [ "$used" -ge 80 ]; then dc=$red; else dc=$teal; fi
  printf '#[fg=%s]󰍛 %s%%#[default]  #[fg=%s]󰋊 %sG#[default]' "$rc" "$ram" "$dc" "$free"
fi
