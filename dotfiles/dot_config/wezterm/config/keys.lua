-- Leader-driven keymap. Leader = CTRL+Space.
--
-- Panes
--   LEADER v        split left/right
--   LEADER s        split top/bottom
--   ALT  h/j/k/l    move between panes
--   LEADER H/J/K/L  resize pane (5 cells)
--   LEADER z        toggle pane zoom (focus one pane fullscreen)
--   LEADER o        rotate panes clockwise
--   LEADER w        close pane
--
-- Tabs
--   LEADER t        new tab
--   LEADER n        next tab
--   LEADER 1..9     jump to tab N
--   LEADER Tab      tab navigator
--
-- Workspaces / projects
--   LEADER f        fuzzy project switcher (open repo as a workspace)
--   LEADER a        drop the agent layout into the current pane
--   LEADER `        workspace launcher (jump to an existing workspace)
--   LEADER [ / ]    previous / next workspace
--
-- Servers
--   LEADER d        domain launcher (attach to an SSH host)
--   CTRL+SHIFT+D    detach current domain
--
-- Misc
--   LEADER p        command palette
--   LEADER e        quick-select (grab paths/hashes/URLs)
--   LEADER u        open a URL from the screen (quick-select → launch on the laptop)
--   LEADER c        copy mode
--   LEADER r        reload configuration
--   CTRL+SHIFT+f    search scrollback
--   CTRL+SHIFT+click  open the link under the mouse (SHIFT bypasses tmux's mouse grab)
local wezterm = require("wezterm")
local act = wezterm.action
local workspaces = require("config.workspaces")

local M = {}

function M.apply(config)
  config.leader = { key = "Space", mods = "CTRL", timeout_milliseconds = 1000 }

  -- Hyperlinks: WezTerm opens links on the LAPTOP (it runs the local URL handler), so
  -- this works over SSH. The catch is tmux with `mouse on` grabs the click before
  -- WezTerm sees it. SHIFT is WezTerm's mouse-reporting bypass, so CTRL+SHIFT+Click
  -- lets WezTerm handle the click and open the URL even inside tmux. (Default
  -- hyperlink_rules already auto-detect http/https URLs.)
  config.bypass_mouse_reporting_modifiers = "SHIFT"
  config.mouse_bindings = {
    {
      event = { Up = { streak = 1, button = "Left" } },
      mods = "CTRL|SHIFT",
      action = act.OpenLinkAtMouseCursor,
    },
  }

  local keys = {
    -- Panes
    { key = "v", mods = "LEADER", action = act.SplitHorizontal({ domain = "CurrentPaneDomain" }) },
    { key = "s", mods = "LEADER", action = act.SplitVertical({ domain = "CurrentPaneDomain" }) },
    { key = "h", mods = "ALT", action = act.ActivatePaneDirection("Left") },
    { key = "j", mods = "ALT", action = act.ActivatePaneDirection("Down") },
    { key = "k", mods = "ALT", action = act.ActivatePaneDirection("Up") },
    { key = "l", mods = "ALT", action = act.ActivatePaneDirection("Right") },
    { key = "H", mods = "LEADER", action = act.AdjustPaneSize({ "Left", 5 }) },
    { key = "J", mods = "LEADER", action = act.AdjustPaneSize({ "Down", 5 }) },
    { key = "K", mods = "LEADER", action = act.AdjustPaneSize({ "Up", 5 }) },
    { key = "L", mods = "LEADER", action = act.AdjustPaneSize({ "Right", 5 }) },
    { key = "z", mods = "LEADER", action = act.TogglePaneZoomState },
    { key = "o", mods = "LEADER", action = act.RotatePanes("Clockwise") },
    { key = "w", mods = "LEADER", action = act.CloseCurrentPane({ confirm = false }) },

    -- Tabs
    { key = "t", mods = "LEADER", action = act.SpawnTab("CurrentPaneDomain") },
    { key = "n", mods = "LEADER", action = act.ActivateTabRelative(1) },
    { key = "Tab", mods = "LEADER", action = act.ShowTabNavigator },

    -- Workspaces / projects
    { key = "f", mods = "LEADER", action = workspaces.project_switcher() },
    { key = "a", mods = "LEADER", action = workspaces.agent_layout() },
    { key = "`", mods = "LEADER", action = act.ShowLauncherArgs({ flags = "FUZZY|WORKSPACES" }) },
    { key = "[", mods = "LEADER", action = act.SwitchWorkspaceRelative(-1) },
    { key = "]", mods = "LEADER", action = act.SwitchWorkspaceRelative(1) },

    -- Servers / domains
    { key = "d", mods = "LEADER", action = act.ShowLauncherArgs({ flags = "FUZZY|DOMAINS" }) },
    { key = "D", mods = "CTRL|SHIFT", action = act.DetachDomain("CurrentPaneDomain") },

    -- Misc
    { key = "p", mods = "LEADER", action = act.ActivateCommandPalette },
    { key = "e", mods = "LEADER", action = act.QuickSelect },
    -- Open a URL without the mouse (works in tmux): quick-select over on-screen URLs,
    -- then launch the chosen one via the laptop's default handler.
    {
      key = "u",
      mods = "LEADER",
      action = act.QuickSelectArgs({
        label = "open url",
        patterns = { "https?://\\S+", "www\\.\\S+" },
        action = wezterm.action_callback(function(window, pane)
          local url = window:get_selection_text_for_pane(pane)
          if url and url ~= "" then
            if url:match("^www%.") then
              url = "https://" .. url
            end
            wezterm.open_with(url)
          end
        end),
      }),
    },
    { key = "c", mods = "LEADER", action = act.ActivateCopyMode },
    { key = "r", mods = "LEADER", action = act.ReloadConfiguration },
    { key = "f", mods = "CTRL|SHIFT", action = act.Search({ CaseInSensitiveString = "" }) },
  }

  -- LEADER 1..9 -> activate tab by index.
  for i = 1, 9 do
    table.insert(keys, {
      key = tostring(i),
      mods = "LEADER",
      action = act.ActivateTab(i - 1),
    })
  end

  config.keys = keys
end

return M
