-- Server access. Every concrete `Host` in ~/.ssh/config becomes a WezTerm SSH
-- domain you can attach to from the launcher (LEADER d). We use a direct SSH
-- connection (multiplexing = "None") so no wezterm mux server is required on the
-- remote; panes/tabs work and close with the connection. Run tmux on the remote
-- if you want persistence across disconnects.
local wezterm = require("wezterm")
local caps = require("config.caps")

local M = {}

function M.apply(config)
  local ssh_domains = {}
  for host, _ in pairs(wezterm.enumerate_ssh_hosts()) do
    -- Skip pattern entries like `Host *`.
    if not host:match("[*?]") then
      table.insert(ssh_domains, {
        name = host,
        remote_address = host,
        multiplexing = "None",
        assume_shell = "Posix",
      })
    end
  end
  config.ssh_domains = ssh_domains

  -- Forward the local SSH agent into `wezterm ssh` / multiplexer domains so your
  -- keys reach the remote without per-host juggling. Nightly only.
  if caps.nightly then
    config.mux_enable_ssh_agent = true
  end
end

return M
