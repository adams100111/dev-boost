-- WezTerm configuration entry point.
--
-- Tuned for heavy agentic coding + multi-server access. The config is split into
-- focused modules under `config/`; this file just wires them together.
--
--   config/caps.lua        feature detection (stable vs nightly)
--   config/appearance.lua  fonts, colors, window, readability
--   config/domains.lua     SSH domains (auto-enumerated) + agent forwarding
--   config/keys.lua        leader-driven keymap (panes/tabs/workspaces/servers)
--   config/workspaces.lua  per-project workspaces + one-key agent layout
--   config/status.lua      status bar (workspace, host, leader indicator, clock)
--
-- WezTerm adds this file's directory to package.path, so `require("config.x")`
-- resolves to `<config-dir>/config/x.lua`.

local wezterm = require("wezterm")

-- config_builder gives clearer error messages for unknown/typo'd keys.
local config = wezterm.config_builder and wezterm.config_builder() or {}

require("config.appearance").apply(config)
require("config.domains").apply(config)
require("config.workspaces").apply(config)
require("config.keys").apply(config)
require("config.status").apply(config)

return config
