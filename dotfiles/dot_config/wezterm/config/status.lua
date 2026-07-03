-- Status bar + appearance-reactive theming + resource alert.
--
-- Follows the OS light/dark mode live (window:get_appearance): swaps the whole
-- palette between Catppuccin Mocha (dark) and Latte (light) — color scheme,
-- tab-bar frame, status colors, and the alert gradient/badge.
--
-- Left: LEADER indicator, or a bold alert badge when resources are critical.
-- Right: workspace · [remote host] · RAM · disk · clock.
-- Resource alert: RAM high or free disk low → designed dark/light→red gradient
-- background + a badge naming the cause; both clear on recovery.
local wezterm = require("wezterm")

local M = {}

-- Alert thresholds.
local RAM_CRITICAL = 80 -- percent used
local DISK_LOW_GB = 10  -- free GB on /

-- Routine RAM/disk gauges are opt-in via the shared prefs flag (also drives tab-bar
-- placement in appearance.lua). The critical alert below — left badge + red
-- background — is independent of it and always on; only the routine numbers gate.
local prefs = require("config.prefs")

local FRAME_FONT = wezterm.font({ family = "JetBrainsMono Nerd Font", weight = "Bold" })

-- Per-appearance theme: Catppuccin Mocha (dark) / Latte (light).
local THEME = {
  dark = {
    scheme = "Catppuccin Mocha",
    frame = { active = "#181825", inactive = "#11111b" },
    pal = {
      mauve = "#cba6f7", green = "#a6e3a1", yellow = "#f9e2af", red = "#f38ba8",
      teal = "#94e2d5", peach = "#fab387", blue = "#89b4fa", surface = "#313244",
      base = "#1e1e2e",
    },
    gradient = { colors = { "#1e1e2e", "#2a0d14", "#3a0d12" }, orientation = { Linear = { angle = -90.0 } } },
  },
  light = {
    scheme = "Catppuccin Latte",
    frame = { active = "#e6e9ef", inactive = "#dce0e8" },
    pal = {
      mauve = "#8839ef", green = "#40a02b", yellow = "#df8e1d", red = "#d20f39",
      teal = "#179299", peach = "#fe640b", blue = "#1e66f5", surface = "#ccd0da",
      base = "#eff1f5",
    },
    gradient = { colors = { "#eff1f5", "#f0d0d6", "#e6a9b3" }, orientation = { Linear = { angle = -90.0 } } },
  },
}

local function theme_for(window)
  local appearance = window:get_appearance() or "Dark"
  return appearance:find("Light") and THEME.light or THEME.dark
end

-- Probe: prints "<ram_used%> <disk_used%> <disk_free_GB>" for /.
local PROBE = [[
ram=$(awk '/MemTotal/{t=$2}/MemAvailable/{a=$2}END{printf "%d",(t-a)/t*100}' /proc/meminfo)
read used free < <(df -P -BG / | awk 'NR==2{sub("%","",$5);sub("G","",$4);print $5, $4}')
printf '%s %s %s' "$ram" "$used" "$free"
]]

local cache = { ram = nil, disk_used = nil, disk_free = nil }
local tick = 0

local function refresh_resources()
  local ok, stdout = wezterm.run_child_process({ "bash", "-c", PROBE })
  if not ok then
    return
  end
  local ram, used, free = stdout:match("(%d+)%s+(%d+)%s+(%d+)")
  if ram then
    cache.ram = tonumber(ram)
    cache.disk_used = tonumber(used)
    cache.disk_free = tonumber(free)
  end
end

local function ram_color(pal, p)
  if p >= 80 then return pal.red elseif p >= 60 then return pal.yellow else return pal.green end
end

local function alert_state()
  local critical, reason = false, nil
  if cache.ram and cache.ram >= RAM_CRITICAL then
    critical, reason = true, "RAM " .. cache.ram .. "%"
  end
  if cache.disk_free and cache.disk_free < DISK_LOW_GB then
    critical = true
    reason = (reason and (reason .. " · ") or "") .. "DISK " .. cache.disk_free .. "G"
  end
  return critical, reason
end

-- Apply scheme + frame (per appearance) and the alert gradient (when critical).
-- Keyed by an (appearance, critical) signature per window so set_config_overrides
-- only fires on a real change (each call re-evaluates the config).
local applied = {}

local function apply_overrides(window, th, critical)
  local sig = th.scheme .. (critical and "!" or "")
  local id = window:window_id()
  if applied[id] == sig then
    return
  end
  applied[id] = sig
  local o = window:get_config_overrides() or {}
  o.color_scheme = th.scheme
  o.window_frame = {
    font = FRAME_FONT,
    font_size = 11.0,
    active_titlebar_bg = th.frame.active,
    inactive_titlebar_bg = th.frame.inactive,
  }
  o.window_background_gradient = critical and th.gradient or nil
  window:set_config_overrides(o)
end

local registered = false

function M.apply(config)
  if registered then
    return
  end
  registered = true

  wezterm.on("update-status", function(window, pane)
    local th = theme_for(window)
    local pal = th.pal

    tick = tick + 1
    if cache.ram == nil or tick % 8 == 0 then
      refresh_resources()
    end

    local critical, reason = alert_state()

    -- Left: leader indicator, else alert badge, else empty.
    if window:leader_is_active() then
      window:set_left_status(wezterm.format({
        { Background = { Color = pal.mauve } },
        { Foreground = { Color = pal.base } },
        { Attribute = { Intensity = "Bold" } },
        { Text = " ⌘ LEADER " },
      }))
    elseif critical then
      window:set_left_status(wezterm.format({
        { Background = { Color = pal.red } },
        { Foreground = { Color = pal.base } },
        { Attribute = { Intensity = "Bold" } },
        { Text = " ⚠ " .. reason .. " " },
      }))
    else
      window:set_left_status("")
    end

    -- Right: workspace · [remote host] · RAM · disk · clock.
    local cells = {}
    local function sep()
      table.insert(cells, { Foreground = { Color = pal.surface } })
      table.insert(cells, { Text = "  │ " })
    end

    table.insert(cells, { Foreground = { Color = pal.green } })
    table.insert(cells, { Text = "  " .. window:active_workspace() })

    local domain = pane:get_domain_name()
    if domain and domain ~= "local" then
      sep()
      table.insert(cells, { Foreground = { Color = pal.peach } })
      table.insert(cells, { Text = "󰣀 " .. domain })
    end

    -- Routine gauges are opt-in (prefs.show_resource_gauges); the probe still runs
    -- every tick regardless, since the critical badge/background below depends on it.
    if prefs.show_resource_gauges and cache.ram ~= nil then
      sep()
      table.insert(cells, { Foreground = { Color = ram_color(pal, cache.ram) } })
      table.insert(cells, { Text = "󰍛 " .. cache.ram .. "%" })
      table.insert(cells, { Foreground = { Color = (cache.disk_used >= 80) and pal.red or pal.teal } })
      table.insert(cells, { Text = "  󰋊 " .. cache.disk_free .. "G" })
    end

    sep()
    table.insert(cells, { Foreground = { Color = pal.blue } })
    table.insert(cells, { Text = wezterm.strftime("%a %H:%M ") })

    window:set_right_status(wezterm.format(cells))

    apply_overrides(window, th, critical)
  end)
end

return M
