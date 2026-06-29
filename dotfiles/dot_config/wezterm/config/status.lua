-- Status bar. Left: LEADER indicator while the prefix is armed. Right: active
-- workspace · [remote host] · RAM · disk · clock. Colored with Catppuccin Mocha.
-- RAM/disk are read from a small shell probe, throttled so it doesn't spawn a
-- process on every status tick.
local wezterm = require("wezterm")

local M = {}

local C = {
  mauve = "#cba6f7",
  green = "#a6e3a1",
  yellow = "#f9e2af",
  red = "#f38ba8",
  teal = "#94e2d5",
  peach = "#fab387",
  blue = "#89b4fa",
  text = "#cdd6f4",
  surface = "#313244",
  base = "#1e1e2e",
}

-- Probe: prints "<ram_used%> <disk_used%> <disk_free_GB>" for /.
local PROBE = [[
ram=$(awk '/MemTotal/{t=$2}/MemAvailable/{a=$2}END{printf "%d",(t-a)/t*100}' /proc/meminfo)
read used free < <(df -P -BG / | awk 'NR==2{sub("%","",$5);sub("G","",$4);print $5, $4}')
printf '%s %s %s' "$ram" "$used" "$free"
]]

-- Throttled cache: refresh roughly every 8th status update.
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

local function ram_color(p)
  if p >= 80 then return C.red elseif p >= 60 then return C.yellow else return C.green end
end

function M.apply(config)
  wezterm.on("update-status", function(window, pane)
    -- Left: armed-leader indicator.
    if window:leader_is_active() then
      window:set_left_status(wezterm.format({
        { Background = { Color = C.mauve } },
        { Foreground = { Color = C.base } },
        { Attribute = { Intensity = "Bold" } },
        { Text = " ⌘ LEADER " },
      }))
    else
      window:set_left_status("")
    end

    tick = tick + 1
    if cache.ram == nil or tick % 8 == 0 then
      refresh_resources()
    end

    -- Right: workspace · [remote host] · RAM · disk · clock.
    local cells = {}
    local function sep()
      table.insert(cells, { Foreground = { Color = C.surface } })
      table.insert(cells, { Text = "  │ " })
    end

    table.insert(cells, { Foreground = { Color = C.green } })
    table.insert(cells, { Text = "  " .. window:active_workspace() })

    local domain = pane:get_domain_name()
    if domain and domain ~= "local" then
      sep()
      table.insert(cells, { Foreground = { Color = C.peach } })
      table.insert(cells, { Text = "󰣀 " .. domain })
    end

    if cache.ram ~= nil then
      sep()
      table.insert(cells, { Foreground = { Color = ram_color(cache.ram) } })
      table.insert(cells, { Text = "󰍛 " .. cache.ram .. "%" })
      table.insert(cells, { Foreground = { Color = (cache.disk_used >= 80) and C.red or C.teal } })
      table.insert(cells, { Text = "  󰋊 " .. cache.disk_free .. "G" })
    end

    sep()
    table.insert(cells, { Foreground = { Color = C.blue } })
    table.insert(cells, { Text = wezterm.strftime("%a %H:%M ") })

    window:set_right_status(wezterm.format(cells))
  end)
end

return M
