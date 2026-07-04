-- Smart paste (CTRL+SHIFT+V): if the laptop clipboard holds an IMAGE, upload it to the
-- VPS and type the remote file path — Claude Code turns an image path into an [Image],
-- and there is no escape sequence that can carry a clipboard image across SSH. Anything
-- else (or no target configured) → an ordinary text paste, unchanged.
--
-- Requires: wl-clipboard on the laptop (the `wl-clipboard` module installs it) and an
-- ssh-agent so scp is non-interactive. Configure the destination via env:
--   DEVBOOST_PASTE_HOST  a Host from ~/.ssh/config or a Tailscale MagicDNS name (e.g. myvps)
--   DEVBOOST_PASTE_DIR   remote dir for pasted images (default /tmp/wezterm-paste, absolute
--                        so Claude Code can read it without ~ expansion)
-- Unset DEVBOOST_PASTE_HOST → image branch is skipped and CTRL+SHIFT+V is a normal paste.

local wezterm = require("wezterm")
local act = wezterm.action

local M = {}

local REMOTE = os.getenv("DEVBOOST_PASTE_HOST")
local REMOTE_DIR = os.getenv("DEVBOOST_PASTE_DIR") or "/tmp/wezterm-paste"

-- Return the clipboard's image mime (e.g. "image/png") if it holds one, else nil.
local function clipboard_image_mime()
  local ok, out = wezterm.run_child_process({ "wl-paste", "--list-types" })
  if not ok or not out then
    return nil
  end
  return out:match("image/%w+")
end

function M.apply(config)
  config.keys = config.keys or {}
  table.insert(config.keys, {
    key = "v",
    mods = "CTRL|SHIFT",
    action = wezterm.action_callback(function(window, pane)
      local mime = REMOTE and clipboard_image_mime() or nil
      if mime then
        local ext = mime:match("image/(%w+)") or "png"
        local name = "paste-" .. wezterm.strftime("%Y%m%d-%H%M%S") .. "." .. ext
        local rpath = REMOTE_DIR .. "/" .. name
        local tmp = "/tmp/" .. name
        -- stage locally → ensure remote dir → scp → clean up. One shell, non-interactive.
        local script = string.format(
          "wl-paste --type %s > %q && ssh %s 'mkdir -p %q' && scp -q %q %s:%q && rm -f %q",
          mime, tmp, REMOTE, REMOTE_DIR, tmp, REMOTE, rpath, tmp
        )
        local ok = wezterm.run_child_process({ "sh", "-c", script })
        if ok then
          -- send_text (not send_paste): raw path, so Claude Code detects it as an image.
          pane:send_text(rpath .. " ")
          window:toast_notification("WezTerm", "Image → " .. REMOTE .. ":" .. rpath, nil, 3000)
          return
        end
        window:toast_notification("WezTerm", "Image upload failed — pasting text", nil, 4000)
      end
      window:perform_action(act.PasteFrom("Clipboard"), pane)
    end),
  })
end

return M
