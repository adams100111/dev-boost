# WezTerm Config

Modular WezTerm config tuned for heavy agentic coding + multi-server access.
Catppuccin theme that follows the OS light/dark preference, a **top** tab bar +
status (workspace · host · clock), and a background **resource alert** when RAM/disk
go critical. Routine RAM/disk gauges are opt-in via `config/prefs.lua`
(`show_resource_gauges`, default off — the starship prompt and Claude status line
show them instead); enabling it also moves the bar back to the bottom.

## Install

On a dev-boost machine this is automatic: the `wezterm` module installs WezTerm
(nightly) and the `dotfiles` module applies this config via chezmoi. Nothing to do.

Manual install — copy the tree into your WezTerm config dir:

```sh
mkdir -p ~/.config/wezterm
cp -r wezterm.lua config ~/.config/wezterm/
```

(`wezterm.lua` requires the modules under `config/`, so copy both.)

### WezTerm build

Use **nightly** — the last dated stable is `20240203` and all features since ship
on nightly. The config detects the build (`config/caps.lua`) and enables
nightly-only niceties (SSH-agent forwarding through the mux, higher text contrast,
per-tab close buttons, smoother redraws) only when present, so it also runs on stable.

dev-boost installs the nightly AppImage (extracted to `~/.local`, no FUSE/sudo) —
the reliable path on both Fedora and Ubuntu, since the COPR lacks builds for newer
Fedora releases. To do it by hand:

```sh
curl -fL -o /tmp/wez.AppImage \
  https://github.com/wezterm/wezterm/releases/download/nightly/WezTerm-nightly-Ubuntu20.04.AppImage
chmod +x /tmp/wez.AppImage && (cd /tmp && ./wez.AppImage --appimage-extract)
mv /tmp/squashfs-root ~/.local/wezterm-nightly
ln -sf ~/.local/wezterm-nightly/AppRun ~/.local/bin/wezterm
```

Fonts: **JetBrainsMono Nerd Font** (required for the status glyphs).

## Layout

| File | Responsibility |
| --- | --- |
| `wezterm.lua` | entry point; wires the modules together |
| `config/prefs.lua` | shared user prefs (`show_resource_gauges`) read by status + appearance |
| `config/caps.lua` | stable-vs-nightly feature detection |
| `config/appearance.lua` | fonts, colors, window decorations, OS light/dark scheme, tab-bar placement (top by default; bottom when `show_resource_gauges`) |
| `config/domains.lua` | SSH domains auto-enumerated from `~/.ssh/config` (+ agent forwarding) |
| `config/workspaces.lua` | per-project workspaces + one-key agent layout |
| `config/keys.lua` | leader-driven keymap |
| `config/status.lua` | status bar (workspace · host · clock), opt-in RAM/disk gauges, resource-critical alert |

## Appearance

- **Follows the OS light/dark preference live.** It reads `window:get_appearance()`
  and swaps the whole palette between **Catppuccin Mocha** (dark) and **Latte**
  (light) — color scheme, tab-bar frame, and status colors — at startup and when
  you toggle the OS appearance.
- **Window decorations:** on GNOME the config uses `TITLE|RESIZE` under XWayland
  (`enable_wayland = false`) — the one combination that yields a single, clean
  GNOME title bar (GNOME/Mutter can't render WezTerm's integrated buttons alone;
  see wezterm/wezterm#4962, #6296).
- **Tabs:** fancy tab bar with a per-tab close (`×`) button, on the **top** by
  default (tmux owns the bottom status line, nearer the prompt); it moves to the
  bottom when `show_resource_gauges` is enabled. Inactive panes dim so the focused
  agent pane stands out.

## Status bar

- **Left:** a `⌘ LEADER` indicator while the prefix is armed, or a resource **alert
  badge** when tripped.
- **Right:** `workspace · [ssh host when remote] · clock`, plus **opt-in** `RAM% ·
  disk-free` gauges when `show_resource_gauges` (`config/prefs.lua`) is set — off by
  default, since the starship prompt and Claude status line show them instead. When
  shown, RAM is green `<60` / yellow `60–79` / red `≥80`; disk is teal, red at `≥80%`
  used. Read from a throttled probe (no per-tick process spawn).

### Resource alert

Independent of the routine-gauge toggle and **always on**: when **RAM ≥ 80%** or
**free disk < 10 GB**, the window background gets a designed dark/light→red gradient
and the left status shows a bold badge naming the cause (`⚠ RAM 85%` / `⚠ DISK 8G`).
Both clear automatically on recovery. Applied via per-window config overrides, only on
a state change. Thresholds live at the top of `config/status.lua` (`RAM_CRITICAL`,
`DISK_LOW_GB`). The starship prompt and Claude status line carry the same alert
(a red badge / a red status row) so it reaches you even without WezTerm.

## Keybindings

Leader = **CTRL+Space**.

**Panes:** `LEADER v` split L/R · `LEADER s` split T/B · `ALT h/j/k/l` move ·
`LEADER H/J/K/L` resize · `LEADER z` zoom · `LEADER o` rotate · `LEADER w` close.

**Tabs:** `LEADER t` new · `LEADER n` next · `LEADER 1..9` jump · `LEADER Tab` navigator.

**Workspaces/projects:** `LEADER f` fuzzy project switcher · `LEADER a` agent layout ·
`LEADER \`` workspace launcher · `LEADER [` / `]` prev/next workspace.

**Servers:** `LEADER d` attach to an SSH host · `CTRL+SHIFT+D` detach domain.

**Misc:** `LEADER p` command palette · `LEADER e` quick-select · `LEADER c` copy mode ·
`LEADER r` reload · `CTRL+SHIFT+f` search.

## Servers

Every concrete `Host` in `~/.ssh/config` is auto-registered as an SSH domain.
`LEADER d` opens a fuzzy picker to attach to one in a tab; the local SSH agent is
forwarded (nightly). The status bar shows the remote host name while attached.

## Agent layout (`LEADER a`)

Splits the current pane into a wide left pane (the agent), a top-right pane (run
commands / tests), and a bottom-right pane (git / logs):

```
+----------------+--------+
|                |  run   |
|   agent (wide) +--------+
|                |  logs  |
+----------------+--------+
```
