# The macOS desktop apps

What `macos-desktop` installs, what each one is for, and the keys that make them
useful. Keys are written the way your keyboard is labelled — **⌃** Control, **⌥**
Option, **⌘** Command, **⇧** Shift. AeroSpace's config file spells the same keys
`ctrl`, `alt`, `cmd`, `shift`, because that is its syntax.

| App | Licence | What it is for |
|---|---|---|
| `aerospace` | MIT | i3-style tiling window manager |
| `alt-tab` | GPL-3.0 | Window switcher with previews |
| `raycast` | free plan, commercial use allowed | Launcher, clipboard history, window commands |
| `stats` | MIT | Menu-bar disk/RAM/CPU/GPU monitor |
| `thaw` | GPL-3.0 | Menu-bar item manager (macOS 26+) |
| `monitorcontrol` | MIT | Brightness/volume for external displays over DDC |
| `keka` | free | Archiver (7z, zip, rar) |
| `quicklook` | GPL-3.0 | Space-bar previews for Markdown and source |

Everything here is free for commercial use. Where a category's best tool is not —
OrbStack and Docker Desktop, for instance — dev-boost picks the one that is.

## AeroSpace

A tiling window manager: windows fill the screen side by side instead of overlapping,
and you move between them with the keyboard.

### The keys

| Do this | Press |
|---|---|
| Focus left / down / up / right | **⌃⌥H / J / K / L** |
| Move the window left / down / up / right | **⌃⌥⇧H / J / K / L** |
| Go to workspace 1–9 | **⌃⌥1** … **⌃⌥9** |
| Send the window to workspace 1–9 | **⌃⌥⇧1** … **⌃⌥⇧9** |
| Back to the previous workspace | **⌃⌥Tab** |
| Fullscreen this window | **⌃⌥F** |
| Flip the split horizontal ⇄ vertical | **⌃⌥/** |
| Accordion layout (one large, rest collapsed) | **⌃⌥,** |
| Shrink / grow | **⌃⌥−** / **⌃⌥=** |
| **Make every window the same size again** | **⌃⌥0** |
| Move this workspace to the next monitor | **⌃⌥⇧Tab** |
| Service mode | **⌃⌥⇧;** then `R` flatten · `F` float/tile · `⌫` close all but this · `Esc` exit |

`⌃⌥D` is Arabic dictation, on machines with the voxtype-arabic marker.

### Nothing works at all

AeroSpace cannot move a window until macOS grants it **Accessibility**, and it fails
silently — the app runs, the keys do nothing. Grant it, then **restart AeroSpace**:
macOS only hands the permission to a fresh process.

```sh
devboost permissions                      # what is still missing, with links
open 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility'
devboost permissions --confirm aerospace  # record it once granted
```

### Two windows, unreadable slivers

Almost always too many windows on one workspace: four windows means four columns.
**Two per workspace** is the rule of thumb.

```sh
aerospace list-windows --workspace focused   # what is actually here
```

That list is the diagnosis — windows you had forgotten are still tiled and taking
width. Send them elsewhere with **⌃⌥⇧2**, then **⌃⌥Tab** to flip back and forth.

If the proportions are skewed rather than crowded, **⌃⌥0** (`balance-sizes`) makes them
equal again. Service mode's `R` (`flatten-workspace-tree`) is the bigger hammer: it
rebuilds the layout tree from scratch, discarding any nesting you meant to keep.

### Windows land where they belong

`~/.config/aerospace/aerospace.toml` places the apps dev-boost installs: Ghostty on 1,
Zed on 4, Obsidian on 5, and System Settings floated (fixed-size windows tile badly).
Workspaces 2 and 3 are deliberately free — dev-boost installs no browser and no chat
app and will not guess which you use. Add your own:

```sh
osascript -e 'id of app "Safari"'   # -> com.apple.Safari
```

```toml
[[on-window-detected]]
if.app-id = 'com.apple.Safari'
run = 'move-node-to-workspace 2'
```

The file is yours once chezmoi has applied it.

### What it will never do

macOS gives no compositor access, so AeroSpace moves windows rather than rendering
them: no Hyprland-style animations, no blur, no shape transitions. Workspaces are
faked by moving windows off-screen. It is the closest thing on a Mac, not an equal.

## The others

- **AltTab** — switches *windows*, not apps, so it reaches a second window of the same
  app that `⌘Tab` cannot. Previews need **Screen Recording** as well as Accessibility.
- **Raycast** — `⌘Space`. Clipboard history is the feature people stay for. The free
  plan is enough; the Pro trial it offers on first run is optional and needs no sign-in.
- **Stats** — dev-boost sets disk, RAM, CPU and GPU and nothing else; click a readout
  for detail. See docs/macos.md for how those defaults are seeded and changed.
- **Thaw** — hides and reorders menu-bar icons, which matters once Stats adds four.
- **MonitorControl** — only useful with an external display; it drives DDC.
- **Keka**, **QuickLook** — no setup, no keys.

Raycast, MonitorControl and Thaw only appear in the Accessibility list **after their
first launch** — macOS lists an app once it has asked. Open each one, then grant.

## The Dock

The Dock is macOS's own; no app here manages it. `macos-defaults` sets it to hide,
with a deliberate reveal:

```
autohide                = true
autohide-delay          = 0.25
autohide-time-modifier  = 0.3
tilesize                = 48
show-recents            = false
```

A hidden Dock only feels right if revealing it is intentional. macOS waits about half a
second and animates slowly; zero delay is worse, not better, because a tiling WM sends
the pointer to screen edges constantly and the Dock then flies out mid-work. A short
delay with a quick animation reveals on purpose.

Magnification is deliberately left off: icons that move as you approach hurt aim.

`devboost revert macos-defaults` restores whatever the machine had before.
