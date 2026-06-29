-- Visual + readability settings. Catppuccin Mocha, JetBrainsMono Nerd Font,
-- dimmed inactive panes (so the focused agent pane stands out), and high-contrast
-- text for dense, colorful agent/build output.
local wezterm = require("wezterm")
local caps = require("config.caps")

local M = {}

function M.apply(config)
  config.color_scheme = "Catppuccin Mocha"

  config.font = wezterm.font_with_fallback({
    "JetBrainsMono Nerd Font",
    "Symbols Nerd Font Mono",
    "Noto Color Emoji",
    "Noto Sans Mono",
  })
  config.font_size = 13.0
  config.adjust_window_size_when_changing_font_size = false

  -- Tab bar: fancy bar so each tab gets a clickable close (×) button and the
  -- window min/max/close render as proper Adwaita buttons (not glyph fallbacks).
  -- Always visible so workspace context is clear.
  config.enable_tab_bar = true
  config.use_fancy_tab_bar = true
  config.hide_tab_bar_if_only_one_tab = false
  config.tab_bar_at_bottom = false
  config.tab_max_width = 28

  -- Style the fancy tab bar to match Catppuccin Mocha.
  config.window_frame = {
    font = wezterm.font({ family = "JetBrainsMono Nerd Font", weight = "Bold" }),
    font_size = 11.0,
    active_titlebar_bg = "#181825",   -- mantle
    inactive_titlebar_bg = "#11111b", -- crust
  }
  config.colors = {
    tab_bar = {
      inactive_tab_edge = "#313244", -- surface0
    },
  }

  -- On GNOME/Mutter, "integrated-buttons-only with no compositor title bar" is a
  -- known, still-open WezTerm bug (wezterm/wezterm#4962, #6296): native Wayland
  -- always draws an sctk-adwaita CSD title bar, and INTEGRATED_BUTTONS just
  -- stacks a redundant second set on top. The one reliable clean result is a
  -- single GNOME title bar under XWayland (see enable_wayland below).
  config.window_decorations = "TITLE|RESIZE"

  config.window_padding = { left = 8, right = 8, top = 6, bottom = 4 }
  config.window_close_confirmation = "NeverPrompt"
  config.default_cursor_style = "BlinkingBar"
  config.audible_bell = "Disabled"
  config.scrollback_lines = 100000
  config.enable_scroll_bar = false

  -- XWayland gives a single, properly-styled GNOME title bar (move + min/max/
  -- close, no bottom overflow) — the only reliable clean decoration on Mutter.
  -- Trade-off: XWayland can render soft on fractional scaling. If so, enable
  -- Mutter's native XWayland scaling (sharp text, keeps this backend):
  --   gsettings set org.gnome.mutter experimental-features "['scale-monitor-framebuffer','xwayland-native-scaling']"
  config.enable_wayland = false

  -- Dim panes that aren't focused — keeps attention on the active agent.
  config.inactive_pane_hsb = { saturation = 0.9, brightness = 0.7 }

  -- Nightly-only readability + overlay polish. Gated so stable doesn't warn
  -- about unknown config keys.
  if caps.nightly then
    -- Lift the floor on text contrast so faint ANSI colors stay legible.
    config.text_min_contrast_ratio = 1.1
    -- Slightly smaller font for the command palette / selectors so long lists fit.
    config.command_palette_font_size = 12.0
    -- Smoother redraws for streaming agent output.
    config.max_fps = 120
    -- Show a clickable close (×) button on each tab in the fancy tab bar.
    config.show_close_tab_button_in_tabs = true
  end
end

return M
