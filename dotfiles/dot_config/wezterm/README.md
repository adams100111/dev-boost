# WezTerm Config

Modular WezTerm config tuned for heavy agentic coding + multi-server access.

## Install

Copy the whole directory contents into your WezTerm config dir:

```sh
mkdir -p ~/.config/wezterm
cp -r wezterm.lua config ~/.config/wezterm/
```

(`wezterm.lua` requires the modules under `config/`, so both must be copied.)

### Recommended: nightly WezTerm

The last dated stable is `20240203`; all features since then ship on nightly.
The config detects the build and enables nightly-only niceties (SSH agent
forwarding through the mux, higher text contrast, smoother redraws) only when
present, so it also runs fine on stable.

Fedora:

```sh
sudo dnf copr enable wezfurlong/wezterm-nightly
sudo dnf install wezterm
```

Fonts: **JetBrainsMono Nerd Font** (theme is the built-in Catppuccin Mocha).

## Layout

| File | Responsibility |
| --- | --- |
| `wezterm.lua` | entry point; wires the modules together |
| `config/caps.lua` | stable-vs-nightly feature detection |
| `config/appearance.lua` | fonts, colors, window, readability |
| `config/domains.lua` | SSH domains auto-enumerated from `~/.ssh/config` |
| `config/workspaces.lua` | per-project workspaces + one-key agent layout |
| `config/keys.lua` | leader-driven keymap |
| `config/status.lua` | status bar (workspace, host, leader, clock) |

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
