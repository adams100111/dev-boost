-- Shared user-facing preferences read by more than one config module.
local M = {}

-- Show the routine RAM/disk gauges in WezTerm's status bar. Default OFF: the
-- starship prompt and Claude status line already show them, so this avoids showing
-- the same gauges twice inside WezTerm. Flip to true if you don't use starship.
--
-- This also drives layout (appearance.lua): when the gauges are ON, WezTerm's bar
-- carries useful always-on content and earns the BOTTOM (attention) spot; when OFF,
-- the bar is just tabs + workspace/clock, so tabs move to the TOP and tmux owns the
-- bottom (nearer the prompt). The critical alert (badge + red bg) is always on
-- regardless of this flag.
--
-- NOTE: tmux's status-position (dot_tmux.conf) is the inverse of this — bottom when
-- false, top when true — but tmux is a separate process (and runs outside WezTerm
-- too), so that pairing is set by hand there, not from this flag. If you change this
-- to true, also set tmux `status-position top`.
M.show_resource_gauges = false

return M
