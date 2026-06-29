-- Per-project workspaces + a one-key "agent layout".
--
-- A workspace is a named set of tabs/panes. Each repo gets its own workspace so
-- you can jump between agent sessions without rebuilding context.
--
-- Exposes action builders consumed by config/keys.lua:
--   M.project_switcher()  fuzzy picker over project dirs -> switch/create workspace
--   M.agent_layout()      lay out the current pane into agent | run | logs
local wezterm = require("wezterm")
local act = wezterm.action

local M = {}

-- Directories scanned for projects. Each immediate subdirectory is a project.
local PROJECT_ROOTS = {
  wezterm.home_dir .. "/repos",
  wezterm.home_dir .. "/projects",
}

local function project_choices()
  local choices = {}
  local seen = {}
  for _, root in ipairs(PROJECT_ROOTS) do
    for _, path in ipairs(wezterm.glob(root .. "/*")) do
      local name = path:match("([^/]+)$")
      if name and not seen[name] then
        seen[name] = true
        table.insert(choices, { id = path, label = name })
      end
    end
  end
  table.sort(choices, function(a, b)
    return a.label:lower() < b.label:lower()
  end)
  return choices
end

-- Fuzzy project picker. Built fresh on each invocation so new repos appear
-- without reloading the config.
function M.project_switcher()
  return wezterm.action_callback(function(window, pane)
    window:perform_action(
      act.InputSelector({
        title = "Open project workspace",
        fuzzy = true,
        fuzzy_description = "project> ",
        choices = project_choices(),
        action = wezterm.action_callback(function(win, p, id, label)
          if not id then
            return
          end
          win:perform_action(
            act.SwitchToWorkspace({ name = label, spawn = { cwd = id } }),
            p
          )
        end),
      }),
      pane
    )
  end)
end

-- Drop a standard agentic layout into the current pane's directory:
--   +----------------+--------+
--   |                |  run   |   right-top : run commands / tests
--   |   agent (wide) +--------+
--   |                |  logs  |   right-bottom: git / logs / watch
--   +----------------+--------+
-- The original (left) pane is left for the agent itself.
function M.agent_layout()
  return wezterm.action_callback(function(_, pane)
    local right = pane:split({ direction = "Right", size = 0.4 })
    right:split({ direction = "Bottom", size = 0.5 })
    pane:activate()
  end)
end

function M.apply(config)
  config.default_workspace = "main"
end

return M
