# New to the Mac? Start here

This is the developer-facing tour of what `devboost install` sets up on macOS beyond the
base workstation (`docs/macos.md`): the desktop layer, the opt-in iOS toolchain, and
Voxtype dictation. Read `docs/macos.md` first for the base install; this page picks up
where it stops.

## 1. New to the Mac? Start here

A few keys behave differently from a PC keyboard, and Ghostty (M2) remaps some of them:

- **⌘ (Command)** is the app-shortcut key (⌘C copy, ⌘Tab switch apps, ⌘Space Raycast). It
  is *not* the terminal key — **Ctrl stays the terminal key** (Ctrl+C interrupts, Ctrl+R
  reverse-search, tmux/herdr prefixes).
- **⌥ (Option)** has two roles in Ghostty: **left ⌥ is Alt** (word jumps, fzf's Alt-C,
  herdr's Alt bindings), so Emacs/readline muscle memory keeps working. **Right ⌥ types
  accented characters** (⌥e then e → é), the macOS default — left it as-is so it never
  collides with a terminal binding.
- **fn / 🌐** switches to emoji picker / dictation / the function-key row (F1–F12 need fn
  held on some keyboards). It has no dev-boost meaning; Voxtype deliberately avoids it
  (see §8).

## 2. What `devboost install macos` set up

Every `macos-desktop` module is reversible or self-contained. "Undo" for a cask means
removing the app (`brew uninstall --cask <name>`); for `macos-defaults` it is the built-in
revert command.

| Module | What it does | See it | Undo it |
|---|---|---|---|
| `macos-defaults` | Keyboard repeat, Finder/Dock/screenshot/trackpad tweaks (§3) | System Settings, or `defaults read <domain> <key>` | `devboost revert macos-defaults [key…]` |
| `macos-limits` | Raises the open-files limit to 524288 | `launchctl limit maxfiles` | `sudo launchctl limit maxfiles 256 unlimited` (until reboot; the LaunchDaemon reapplies it) |
| `macos-firewall` | Turns on the application firewall | System Settings → Network → Firewall | `sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate off` |
| `timemachine-exclusions` | Excludes caches, VM disks and `node_modules`/`vendor` under `~/repos` from Time Machine, re-swept every 6 h | `tmutil isexcluded <path>` | `tmutil removeexclusion <path>`, then remove the `dev.devboost.tm-exclusions` agent |
| `stats` | Menu-bar CPU/RAM/disk/network monitor | menu bar | `brew uninstall --cask stats` |
| `raycast` | Launcher, clipboard history, window snapping | ⌘Space (once you hand it over, §5) | `brew uninstall --cask raycast` |
| `aerospace` | Tiling window manager, config via dotfiles | Ctrl+Alt+H/J/K/L (§4) | `brew uninstall --cask aerospace` |
| `alt-tab` | Windows-style ⌥⇥ switcher with previews | ⌥⇥ | `brew uninstall --cask alt-tab` |
| `thaw` | Menu-bar item manager (macOS 26+) | menu bar overflow | `brew uninstall --cask thaw` |
| `monitorcontrol` | External-display brightness/volume over DDC | menu bar | `brew uninstall --cask monitorcontrol` |
| `keka` | Archiver (7z, zip, rar, …) | Finder → right-click → Services, or open the app | `brew uninstall --cask keka` |
| `quicklook` | Quick Look previews for Markdown and source code | Space on a file in Finder (after enabling, §6) | `brew uninstall --cask qlmarkdown syntax-highlight` |
| `voxtype` (`base`, every OS) | Push-to-talk dictation | hold Right Option (§8) | remove its Login Item, then `rm -rf /Applications/Voxtype.app ~/.local/bin/voxtype` |

Example: `devboost revert macos-defaults tilesize` restores `com.apple.dock:tilesize` to
whatever it read before dev-boost first changed it (or deletes the key if it was unset).
With no keys, it restores everything dev-boost has changed.

**A plain `devboost install` re-applies a reverted key** the next time it runs, unless you
leave `macos-defaults` out of the profile you install. `devboost install --update` does
not: it refreshes only Homebrew-managed and self-updating modules, and `macos-defaults` is
neither, so a reverted key stays reverted until the next plain run.

## 3. The defaults, key by key

Every key is typed (`-bool`/`-int`/`-string`), snapshotted before its first write, and
reverted with `devboost revert macos-defaults [key…]` (§2). Ten keys need a **logout** to
take full effect (marked below); the rest restart Dock, Finder or SystemUIServer
immediately, only when the value actually changed and only when you run dev-boost in a
terminal. An unattended run (ssh, first boot) restarts nothing: the change applies at the
next login or restart, or right away with `killall Dock Finder SystemUIServer`.

| `<domain>:<key>` | Value | Effect | Takes effect |
|---|---|---|---|
| `NSGlobalDomain:KeyRepeat` | `2` | Faster key repeat | after logout |
| `NSGlobalDomain:InitialKeyRepeat` | `15` | Shorter delay before repeat starts | after logout |
| `NSGlobalDomain:ApplePressAndHoldEnabled` | `false` | Holding a key repeats it instead of showing accent picker | after logout |
| `NSGlobalDomain:AppleShowAllExtensions` | `true` | File extensions always shown | Finder restart |
| `NSGlobalDomain:NSAutomaticSpellingCorrectionEnabled` | `false` | No autocorrect while typing | after logout |
| `NSGlobalDomain:NSAutomaticQuoteSubstitutionEnabled` | `false` | Straight quotes, not curly — matters in code | after logout |
| `NSGlobalDomain:NSAutomaticDashSubstitutionEnabled` | `false` | No `--` → em-dash substitution | after logout |
| `com.apple.finder:AppleShowAllFiles` | `true` | Dotfiles visible in Finder | Finder restart |
| `com.apple.finder:ShowPathbar` | `true` | Path bar at the bottom of every window | Finder restart |
| `com.apple.finder:ShowStatusBar` | `true` | Item count / free space status bar | Finder restart |
| `com.apple.finder:FXPreferredViewStyle` | `Nlsv` | List view by default | Finder restart |
| `com.apple.desktopservices:DSDontWriteNetworkStores` | `true` | No `.DS_Store` on network shares | after logout |
| `com.apple.desktopservices:DSDontWriteUSBStores` | `true` | No `.DS_Store` on USB/external drives | after logout |
| `com.apple.dock:autohide` | `true` | Dock hides until you point at the edge | Dock restart |
| `com.apple.dock:tilesize` | `48` | Smaller Dock icons | Dock restart |
| `com.apple.dock:show-recents` | `false` | No "recent apps" section in the Dock | Dock restart |
| `com.apple.screencapture:target` | `clipboard` | Screenshots land on the clipboard (§7) | SystemUIServer restart |
| `com.apple.screencapture:type` | `png` | PNG screenshots | SystemUIServer restart |
| `com.apple.AppleMultitouchTrackpad:Clicking` | `true` | Tap-to-click (built-in trackpad) | after logout |
| `com.apple.driver.AppleBluetoothMultitouch.trackpad:Clicking` | `true` | Tap-to-click (Magic Trackpad over Bluetooth) | after logout |

A bare key name works when it is unique in the table (`devboost revert macos-defaults
tilesize`); `Clicking` is not unique, so use the full `<domain>:Clicking` form for either
trackpad row.

## 4. Windows: AeroSpace + AltTab

Every AeroSpace binding lives on a **Ctrl+Alt** layer, not plain Alt: AeroSpace's hotkeys
are global (they fire even when a terminal has focus), and a plain **Alt** layer would
swallow readline/fzf Alt bindings (Alt-C, Alt-B/F, …) inside the terminal itself.

| Keys | Action |
|---|---|
| Ctrl+Alt+H / J / K / L | Focus left / down / up / right |
| Ctrl+Alt+Shift+H / J / K / L | Move the focused window left / down / up / right |
| Ctrl+Alt+1…9 | Switch to workspace 1–9 |
| Ctrl+Alt+Shift+1…9 | Move the focused window to workspace 1–9 |
| Ctrl+Alt+/ | Layout: tiles, alternating horizontal/vertical |
| Ctrl+Alt+, | Layout: accordion, alternating horizontal/vertical |
| Ctrl+Alt+F | Toggle fullscreen |
| Ctrl+Alt+- / Ctrl+Alt+= | Resize smaller / larger |
| Ctrl+Alt+Tab | Jump back and forth between the last two workspaces |
| Ctrl+Alt+Shift+Tab | Move the current workspace to the next monitor |
| Ctrl+Alt+Shift+; | Enter **service mode** (a one-off mode for less common actions) |

Service mode (after Ctrl+Alt+Shift+;): `Esc` reloads the config and exits; `r` flattens
the workspace tree; `f` toggles floating/tiling; `Backspace` closes every window but the
current one; Ctrl+Alt+Shift+H/J/K/L joins the focused window with its neighbour. Any key
returns to the main mode afterwards.

**AltTab** is **⌥⇥** (hold Option, tap Tab) — the familiar Windows-style switcher, with
live window previews, independent of AeroSpace.

Validate a hand-edited AeroSpace config before reloading it for real:
`aerospace reload-config --dry-run --no-gui`.

## 5. Launcher, menu bar, monitors

**Raycast** replaces Spotlight as the launcher. It does not take over ⌘Space
automatically (dev-boost never rebinds a system shortcut without you watching) — open
Raycast once, then in System Settings → Keyboard → Keyboard Shortcuts → Spotlight, turn
off "Show Spotlight search", and set ⌘Space as Raycast's own hotkey in its preferences.

**Thaw** (macOS 26+ only — see §11) is a menu-bar item manager: drag icons into its
overflow drawer to declutter the menu bar. Not installed on macOS 15.

**Stats** is a menu-bar CPU/RAM/disk/network monitor; click its icon for the detail view.

**MonitorControl** puts brightness/volume control (over DDC) on external displays that
have no built-in keys for it, from the menu bar or the normal media keys.

**Why BetterDisplay is not installed.** BetterDisplay's licence requires a paid
subscription for business use, even for its free-tier features
(github.com/waydabber/BetterDisplay/discussions/739) — dev-boost only ships apps that are
free for commercial/employer work. MonitorControl (MIT) covers the DDC brightness/volume
case dev-boost needs. There is no free replacement for BetterDisplay's HiDPI
scaling-resolution feature: buy BetterDisplay yourself (betterdisplay.pro) if you need it.

## 6. Files

**Quick Look** (press Space on a selected file in Finder) gets Markdown and
syntax-highlighted source previews via two app extensions, `QLMarkdown` and `Syntax
Highlight`. **You may need to enable them once**: System Settings → General → Login
Items & Extensions → Quick Look, and toggle both on if they are not already.

**Keka** is the archive tool (7z, zip, rar, tar, …); right-click a file in Finder → Services
→ Keka, or drag files onto the Keka app/Dock icon.

**Code files open in Zed.** dev-boost's Zed setup (`data/macos/default-apps.tsv`, applied
through `utiluti`) makes Zed the default app for common code/text extensions (`.md`,
`.txt`, `.log`, `.json`, `.yaml`, …). macOS 26.4+ shows one confirmation dialog per file
type the first time; answer it once and dev-boost remembers your answer. To point a
different extension somewhere else by hand: look up its UTI with
`utiluti get-uti <ext> --show-dynamic`, then set the app with
`utiluti type set <uti> <bundle-id>` (e.g. `utiluti type set public.plain-text
dev.zed.Zed`).

## 7. Screenshots go to the clipboard

`macos-defaults` sets `com.apple.screencapture:target = clipboard`, so the usual
shortcuts capture straight to the clipboard instead of writing a file to the Desktop:

- **⌘⇧3** — full screen
- **⌘⇧4** — a selected region
- **⌘⇧5** — the screenshot toolbar (choose window/selection, record video, or set a timer)

Paste the clipboard image straight into a remote agent session with **`herdr --remote`**'s
Ctrl+V image paste. If you do want a file on disk, use **⌘⇧5 → Options → Save to** and
pick a location for that capture (or every capture, from the same menu).

## 8. Dictation (Voxtype)

**Hold Right Option (⌥), speak, release.** Voxtype transcribes
locally (Whisper `small.en`, on-device, no network) and types the text wherever the
cursor is. Upstream defaults to the Globe/fn key on macOS, but macOS already binds that to
the emoji picker and system dictation, so dev-boost's default is **Right Option**
instead — left Option keeps its accent-character role (§1), and Right Option types
nothing on its own, so there is no collision.

**To use a different key**, edit the `[hotkey]` block in
`dotfiles/dot_config/voxtype/config.toml.tmpl` (in the dev-boost repo, not `~/.config`
directly — chezmoi rewrites that file), then run `devboost install dotfiles` to re-render
it onto every machine. macOS takes a single key (`RIGHTALT`, `FN`, `F13`, …) and ignores
`modifiers`; Linux takes evdev names (`SCROLLLOCK`, `PAUSE`, `F13`, …).

**If dictation types the word "you" and nothing else, the microphone captured silence.**
That is Whisper's output for an empty buffer, not a hotkey problem. The usual cause on
macOS is that capture follows the **system default input**, and the default moves on its
own:

- **A Bluetooth headset.** macOS cannot run A2DP (high-quality output) and the headset
  microphone at the same time, so opening the mic either fails or forces the whole device
  down to ~8–16 kHz mono. Connect earbuds and they silently become the default input.
- **A virtual device** — `ZoomAudioDevice`, Loopback, BlackHole — which has inputs but
  carries no live audio unless something is routing into it.

Pin a real device instead of following the default. Push-to-talk is held on a keyboard
key, so you are always within arm's reach of the built-in microphone anyway — a headset
buys nothing here and costs you the A2DP downgrade every time you speak:

```sh
voxtype info devices                      # names, exactly as they must be written
echo 'MacBook Pro Microphone' > ~/.config/devboost/voxtype-device
devboost install dotfiles                 # re-renders the config with the pin
```

dev-boost writes `audio.feedback.enabled = true`, so you hear a cue when recording starts
and stops. Without it a recording that captured nothing is indistinguishable from one that
worked, until the wrong text appears.

**Arabic dictation** is opt-in: `devboost install voxtype-arabic` downloads the larger
`large-v3-turbo` model (1.6 GB) and switches the config to a secondary model. Toggle it
with **Ctrl+Alt+D** on macOS (bound in the AeroSpace config, since Voxtype's
`model_modifier` key is ignored on macOS) — press once to start, again to stop. On Linux,
hold **Left Shift + the hotkey**. The secondary model loads only while you are dictating
Arabic and is evicted from memory after 60 s idle, so it costs **no RAM** the rest of the
time — only the primary `small.en` model (466 MB) stays resident.

**`Voxtype.app` holds a copy of the binary, not a symlink.** `devboost install` rebuilds
it (`voxtype setup app-bundle`) only when its version differs from the installed
`voxtype --version` — but upstream's own setup step **resets the Accessibility and Input
Monitoring grants** whenever it rebuilds the bundle, so a `brew upgrade`-driven Voxtype
update means re-granting both permissions afterwards (run `devboost permissions` to be
walked through it again). That rebuild adds a Login Item and opens Voxtype.app, which
asks for permissions, so an unattended run (over ssh, first boot, or
`DEVBOOST_NONINTERACTIVE=1`) installs the binary and model but reports Voxtype as
`blocked` until you run `devboost install voxtype` in a terminal.

## 9. Privacy permissions

macOS never lets a script grant a privacy permission — a human has to click "Allow" in
System Settings. dev-boost opens the exact settings pane for you and remembers what you
confirmed.

| App | Permission(s) needed |
|---|---|
| AeroSpace | Accessibility |
| Raycast | Accessibility |
| MonitorControl | Accessibility |
| LinearMouse (extras) | Accessibility |
| Maccy (extras) | Accessibility |
| AltTab | Accessibility, Screen Recording |
| Thaw | Accessibility, Screen Recording |
| KeyCastr (extras) | Input Monitoring, Accessibility |
| Voxtype | Microphone, Input Monitoring, Accessibility |

Run **`devboost permissions`** to list every outstanding grant for apps that are already
installed; it opens each System Settings pane in turn and asks about **one switch at a
time** — "Is Voxtype switched ON under Microphone?" — recording only what you say yes to.
You can also record a whole module's grants at once with **`devboost permissions
--confirm <module>`**. Scripts cannot flip the switches themselves: Apple's TCC database
has no supported API for a script to grant these.

**Why one prompt per switch.** The prompt used to be one question per *module* —
"Granted everything for voxtype?" — covering Microphone, Input Monitoring and
Accessibility together. Answer yes having flipped two of three and the third was marked
done forever. That is how a machine ended up reporting `permissions: all granted` while
Voxtype's microphone was off, and dictation silently transcribed the word "you" from an
empty buffer for hours.

**Why a grant can expire.** macOS binds a privacy grant to the app's **code signature**.
Rebuild the bundle and macOS sees a different app, so the grant stops applying — and a
background daemon cannot show a prompt, so it gets silence instead of an error. dev-boost
records the signature (`codesign -d --verbose=4` → `CandidateCDHash`) alongside each
confirmation and asks again when it changes. Apps signed ad-hoc (`TeamIdentifier=not
set`) are re-signed on every rebuild, so this is routine, not rare. If dev-boost cannot
read an app's signature it says nothing rather than nagging — no opinion is not evidence
that a permission was lost.

## 10. Launch at login

Stats, Raycast, AltTab, Thaw, MonitorControl, Maccy and LinearMouse each have their own
"Launch at login" checkbox in their own Preferences/Settings window — dev-boost opens each
app once after installing it (so it can request its permissions), but never touches macOS
Login Items itself (doing that through `osascript`/System Events would trigger its own
Automation permission prompt). Open the app, find its menu-bar icon → Settings/Preferences
→ General, and flip the switch there if you want it to start automatically.

**AeroSpace is already set**: `start-at-login = true` is baked into the dotfiles-managed
`aerospace.toml`, so it starts itself without any manual step.

## 11. Safety net

- **Firewall.** `macos-firewall` turns on the application firewall
  (`socketfilterfw --setglobalstate on`). Check it any time: System Settings → Network →
  Firewall.
- **Time Machine exclusions.** Caches and regenerable data never eat your backup budget:
  `~/Library/Caches`, `~/.colima` and `~/.config/colima` (Docker VM disks, whichever
  Colima uses), `~/.orbstack`, `~/Library/Containers/com.docker.docker`, `~/.gradle`,
  `~/.npm`, `~/.cache`, `~/.nuget/packages`, `~/Library/Developer/Xcode/DerivedData` — plus
  every `node_modules`/`vendor` directory found under `~/repos` (up to 6 levels deep). A
  login agent re-sweeps `~/repos` every **6 hours** and once at login, so a project you
  clone later gets excluded automatically once its dependencies are installed.
- **Open-files limit.** `macos-limits` raises `kern.maxfiles`/`kern.maxfilesperproc` to
  **524288** (from the macOS defaults, which are too low for some dev tooling — file
  watchers, big monorepos) via a root LaunchDaemon, applied immediately (no reboot
  needed).
- **`devboost doctor`** reports the desktop's health: firewall (fails the check if it's
  off after `macos-firewall` turned it on; a WARN if you never installed that module —
  everything else here is informational), FileVault, System Integrity Protection,
  whether a Time Machine destination is configured, iCloud Desktop & Documents sync (a
  hint to keep repos out of `~/Desktop`/`~/Documents` if it's on — cloud sync fights with
  `node_modules` churn), the battery charge limit (macOS 26.4+, GUI-only, no CLI),
  Raycast/Maccy hotkey reminders, and which modules are gated off by your macOS version.

## 12. iOS (opt-in)

`devboost install ios` (not part of `macos` or `full` by default — it is a 10 GB+
download) installs `xcodes`, then Xcode itself, then CocoaPods, watchman and the pinned
iOS simulator runtime.

Xcode needs an Apple ID sign-in. Either export `XCODES_USERNAME` and `XCODES_PASSWORD`
beforehand, or just run `devboost install ios` **in a terminal** — a person there can
answer a 2FA prompt if one appears. With neither, the module reports itself blocked
rather than hanging on an invisible prompt. **xcodes saves the Apple ID password in your
login keychain** after the first successful sign-in, so later runs on the same machine
don't need the environment variables again.

The Xcode and iOS runtime versions are pinned in `catalog.toml` under `[xcode]`
(currently Xcode 27.0, iOS runtime 27.0, requiring macOS ≥ 26.6). Bump the pin there when
a new Xcode ships — `version`, `ios_runtime` and `min_macos` all live in that one table.

## 13. Extras (opt-in)

`devboost install macos-extras` installs every app below at once; each one is also
installable on its own (e.g. `devboost install maccy`).

| App | What it is |
|---|---|
| Maccy | Clipboard history |
| Ollama | Run local LLMs |
| LM Studio | Local LLM app with a chat UI |
| Pearcleaner | App uninstaller (removes an app's leftover files too) |
| KeyCastr | Shows your keystrokes on screen — handy for demos/screencasts |
| LinearMouse | Per-device mouse/trackpad tuning (speed, scroll direction, …) |
| Android Studio | Full Android IDE (react-native already gets the SDK without it) |
| Expo Orbit | Launch Expo builds on simulators/emulators from the menu bar |
| Herd | Native PHP/Laravel environment (an alternative to ddev for Laravel work) |
| WezTerm | Alternative terminal with its own multiplexer/SSH domains (Ghostty + herdr are the default; WezTerm is deprecated but kept for people who rely on it) |

`android-emulator` is a separate opt-in module (not part of `macos-extras`, no profile at
all): `devboost install android-emulator` provisions the emulator binary, one Android 35
system image (`arm64-v8a` on Apple Silicon), and a `devboost-pixel` AVD (Pixel 8). Boot it
by hand: `emulator -avd devboost-pixel`.

## 14. Licences

Every app dev-boost installs on macOS is free for commercial/employer/client work — this
was checked deliberately, because this Mac is used for paid work:

| App | Licence | Why it's OK for work |
|---|---|---|
| Raycast | Free plan | Explicitly allowed for commercial use (raycast.com/pricing) |
| AeroSpace | MIT | No restriction |
| AltTab | GPL-3.0 | No restriction |
| Thaw | GPL-3.0 | No restriction |
| MonitorControl | MIT | No restriction |
| Keka | Freeware (keka.io) | Terms have a warranty disclaimer only, no use restriction; the App Store listing is an optional paid tip, not a licence (D4) |
| Stats | MIT | No restriction |
| QLMarkdown / Syntax Highlight | GPL-3.0 | No restriction |
| Maccy | MIT | No restriction |
| Ollama (app) | MIT | No restriction |
| LM Studio | Free for work since 2025-07-08 (lmstudio.ai/blog/free-for-work) | Explicitly allowed |
| Pearcleaner | Apache-2.0 + Commons Clause | Commons Clause only bans *reselling* Pearcleaner itself |
| KeyCastr | BSD-3-Clause | No restriction |
| LinearMouse | MIT | No restriction |
| Android Studio | Apache-2.0 + Google SDK terms | Standard Google SDK terms, no business restriction |
| Expo Orbit | MIT | No restriction |
| Herd | Free tier, EULA (herd.laravel.com/eula) | No business restriction on the free tier; Pro is optional |
| Voxtype | MIT | No restriction |
| Xcode / xcodes | Apple SLA / MIT (xcodes tool) | Standard Apple developer terms |

**BetterDisplay is deliberately not installed** — its licence requires a paid
subscription for business use even on its free-tier features. See §5 for the
MonitorControl alternative and where to buy BetterDisplay if you want its HiDPI feature.
