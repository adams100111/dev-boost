-- Smart CTRL+V paste that bridges the clipboard across SSH — one key, local or remote.
--
-- * LOCAL pane → forward the raw Ctrl+V (0x16) unchanged, so Claude Code's own native paste
--   runs exactly as it does today (it reads the laptop clipboard directly — text and images).
-- * SSH pane → the clipboard can't cross SSH, so wezterm bridges it:
--     - an IMAGE in the clipboard → scp it to the host THIS pane is ssh'd into and type the
--       remote path (Claude Code turns a path into an [Image]);
--     - otherwise → an ordinary text paste over the ssh pty.
--
-- The SSH host is AUTO-DETECTED from the pane's foreground `ssh` process — no env var needed.
-- Optional overrides: DEVBOOST_PASTE_HOST (force a host) / DEVBOOST_PASTE_DIR (remote dir,
-- default /tmp/wezterm-paste, absolute so Claude Code reads it without ~ expansion).
-- Requires wl-clipboard on the laptop (the `wl-clipboard` module) + a non-interactive ssh
-- (ssh-agent), so scp doesn't prompt. CTRL+SHIFT+V stays as an explicit always-text paste.

local wezterm = require("wezterm")
local act = wezterm.action

local M = {}

local REMOTE_DIR = os.getenv("DEVBOOST_PASTE_DIR") or "/tmp/wezterm-paste"

-- ssh flags that consume the FOLLOWING argument — skip their value when scanning for the host.
local SSH_TAKES_ARG = {
  b = true, c = true, D = true, E = true, e = true, F = true, I = true, i = true,
  J = true, L = true, l = true, m = true, O = true, o = true, p = true, Q = true,
  R = true, S = true, W = true, w = true,
}

-- Return the ssh destination for this pane (user@host or a Host alias from ~/.ssh/config —
-- used verbatim for scp so it resolves identically), or nil for a truly local pane.
local function ssh_destination(pane)
  -- 1. WezTerm SSH DOMAIN (the `LEADER d` launcher, multiplexing="None"): there is no local
  --    ssh process to inspect — the pane's DOMAIN is named after the ssh Host (config/
  --    domains.lua sets name = host), so the domain name IS the destination.
  local ok_d, domain = pcall(function()
    return pane:get_domain_name()
  end)
  if ok_d and domain and domain ~= "local" and domain ~= "unix" then
    return domain
  end
  -- 2. Plain `ssh host` running in a LOCAL pane: parse the foreground ssh argv.
  local ok, info = pcall(function()
    return pane:get_foreground_process_info()
  end)
  if not ok or not info or not info.argv then
    return nil
  end
  local argv = info.argv
  local exe = (argv[1] or ""):match("([^/]+)$")
  if exe ~= "ssh" then
    return nil
  end
  local i = 2
  while argv[i] do
    local a = argv[i]
    if a:sub(1, 1) == "-" then
      -- "-p 22" style: single-char flag that takes a separate value → skip the next token.
      -- "-p22" / bundled flags carry their value inline → no extra skip.
      local flag = a:sub(2, 2)
      if #a == 2 and SSH_TAKES_ARG[flag] then
        i = i + 1
      end
    else
      return a -- first bare token = the ssh destination
    end
    i = i + 1
  end
  return nil
end

-- The clipboard's image mime (e.g. "image/png") if it holds an image, else nil.
local function clipboard_image_mime()
  local ok, out = wezterm.run_child_process({ "wl-paste", "--list-types" })
  if not ok or not out then
    return nil
  end
  return out:match("image/%w+")
end

-- scp the clipboard image to `host`; return the remote path, or nil on failure. One shell,
-- non-interactive: stage locally → ensure remote dir → scp → clean up.
local function upload_image(host, mime)
  local ext = mime:match("image/(%w+)") or "png"
  local name = "paste-" .. wezterm.strftime("%Y%m%d-%H%M%S") .. "." .. ext
  local rpath = REMOTE_DIR .. "/" .. name
  local tmp = "/tmp/" .. name
  local script = string.format(
    "wl-paste --type %s > %q && ssh %s 'mkdir -p %q' && scp -q %q %s:%q && rm -f %q",
    mime, tmp, host, REMOTE_DIR, tmp, host, rpath, tmp
  )
  if wezterm.run_child_process({ "sh", "-c", script }) then
    return rpath
  end
  return nil
end

local function smart_paste(window, pane)
  local host = os.getenv("DEVBOOST_PASTE_HOST") or ssh_destination(pane)
  if not host then
    -- Local pane: forward Ctrl+V (0x16) so Claude Code's native paste handles it — identical
    -- to the current (unbound) behaviour, no regression for local shells or Claude Code.
    pane:send_text("\x16")
    return
  end
  local mime = clipboard_image_mime()
  if mime then
    local rpath = upload_image(host, mime)
    if rpath then
      pane:send_text(rpath .. " ") -- raw path (send_text, not paste) → Claude Code sees an image
      window:toast_notification("WezTerm", "Image → " .. host .. ":" .. rpath, nil, 3000)
      return
    end
    window:toast_notification("WezTerm", "Image upload failed — pasting text", nil, 4000)
  end
  -- SSH pane, text (or the upload failed): ordinary text paste over the ssh pty.
  window:perform_action(act.PasteFrom("Clipboard"), pane)
end

function M.apply(config)
  config.keys = config.keys or {}
  table.insert(config.keys, { key = "v", mods = "CTRL", action = wezterm.action_callback(smart_paste) })
  -- Explicit always-text paste (never image) — muscle-memory fallback.
  table.insert(config.keys, { key = "v", mods = "CTRL|SHIFT", action = act.PasteFrom("Clipboard") })
end

return M
