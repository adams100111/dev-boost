#!/usr/bin/env bash
# RAM/disk gauges for the tmux status line — the persistent surface that stays visible
# while a full-screen app (fresh, vim, less, htop, lazygit) fills the pane, unlike the
# shell prompt. tmux interprets the #[...] style directives in this output (tmux >= 2.9).
#
# Same probes/thresholds as wezterm status.lua & starship:
#   RAM  󰍛 used%   green <60 · yellow 60-79 · red >=80
#   DISK 󰋊 free-G  teal, red at / >=80% used
# Critical (RAM >=80 or free <10G) flips the whole segment to a red badge, matching the
# alerts on the other surfaces. Linux /proc + df, cheap; refreshed on status-interval.
set -eu

ram=$(awk '/MemTotal/{t=$2}/MemAvailable/{a=$2}END{printf "%d",(t-a)/t*100}' /proc/meminfo)
read -r used free < <(df -P -BG / | awk 'NR==2{sub("%","",$5);sub("G","",$4);print $5, $4}')

green='#a6e3a1'; yellow='#f9e2af'; red='#f38ba8'; teal='#94e2d5'; base='#1e1e2e'

if [ "$ram" -ge 80 ] || [ "$free" -lt 10 ]; then
  # Critical → red badge (wezterm / Claude / starship parity).
  printf '#[fg=%s,bg=%s,bold] ⚠ 󰍛 %s%% 󰋊 %sG #[default]' "$base" "$red" "$ram" "$free"
else
  [ "$ram" -ge 60 ] && rc=$yellow || rc=$green
  [ "$used" -ge 80 ] && dc=$red || dc=$teal
  printf '#[fg=%s]󰍛 %s%%#[default]  #[fg=%s]󰋊 %sG#[default]' "$rc" "$ram" "$dc" "$free"
fi
