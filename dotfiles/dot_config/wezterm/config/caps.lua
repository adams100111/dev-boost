-- Feature detection so the config runs cleanly on both the 20240203 stable
-- build and the rolling nightly. Version strings look like
-- "20240203-110809-5046fc22"; anything dated after the last stable is nightly.
local wezterm = require("wezterm")

local M = {}

local ymd = tonumber((wezterm.version or ""):match("^(%d+)")) or 0

M.version_ymd = ymd
-- Last dated stable release is 20240203; newer builds are nightly.
M.nightly = ymd > 20240203

return M
