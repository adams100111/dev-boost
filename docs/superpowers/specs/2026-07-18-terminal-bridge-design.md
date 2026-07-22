# Design: a "feels-local" terminal bridge — clipboard, links, open-URL, notify over SSH

**Created**: 2026-07-18
**Status**: Draft — awaiting review
**Scope**: Chezmoi dotfiles only (`dotfiles/`). No engine module, no `profiles.toml` change, no
installer/media changes. Makes a remote SSH+tmux session driven from a wezterm laptop *feel*
local: copied text reaches the laptop clipboard, printed links are clickable, programs that
open a URL pop the **laptop** browser, and long-job/agent notifications toast on the laptop.

## Problem

Our fleet is split by role (see [remote-profile spec](2026-07-18-remote-profile-design.md)):
**Fedora laptops** are the workstations (wezterm + tmux, a real GUI), and **Ubuntu VPS/servers**
are the headless boxes where agents and long builds run. Day to day you `ssh` from the laptop's
wezterm into a VPS and live inside tmux there.

In that session the remote box is a black box for anything GUI-shaped:

- Copying text in a remote app does not reach the laptop clipboard (only partially solved today).
- A URL printed by a remote tool (`gh pr create`, `vite`, an OAuth device flow) is inert — you
  hand-copy it into a local browser.
- A tool that calls `xdg-open`/`$BROWSER` on the VPS opens nothing (headless), instead of the
  laptop browser.
- A long build or agent that finishes while you're in another window notifies no one.

We want the remote session to behave like a local terminal for these four things, with **no new
network path, no new listening port, no credentials**, and no dependency beyond the SSH+tmux+
wezterm stack we already run.

## Goal

A small set of dotfiles that, layered on the existing `ssh → tmux → wezterm` session, deliver:

1. **Clipboard remote→local** — copy on the VPS lands in the laptop clipboard.
2. **Clickable links** — http/https URLs printed on the VPS are CTRL-click-openable in the laptop
   browser.
3. **Open-URL** — a program calling `$BROWSER`/`xdg-open` on the VPS opens the **laptop** browser.
4. **Desktop notifications** — a VPS command can pop a toast on the laptop.

All four ride the **existing terminal byte stream** (escape sequences carried up through tmux into
wezterm). Nothing opens a second connection, so nothing new needs Tailscale, keys, or a daemon —
the bridge simply inherits the security of the SSH session it rides in.

## Verified mechanics (sources)

Confirmed this session against live docs via context7 (Constitution III — verify, don't recall):

- **wezterm user variables (OSC 1337 `SetUserVar`).** A shell emits
  `\033]1337;SetUserVar=<name>=<base64(value)>\007`; wezterm decodes it and fires the
  `user-var-changed(window, pane, name, value)` Lua event with the **decoded** value. Through tmux
  the sequence must be wrapped in the passthrough form `\033Ptmux;\033<seq>\033\\` **and**
  `set -g allow-passthrough on` must be set. (wezterm.org/shell-integration,
  config/lua/window-events/user-var-changed, recipes/passing-data)
- **`wezterm.open_with(url)`** opens a URL/file with the OS default handler — already used in this
  repo at `dotfiles/dot_config/wezterm/config/keys.lua:108`.
- **OSC 777 / OSC 9 notifications.** `printf "\033]777;notify;%s;%s\033\\" title body` (title+body)
  and `\033]9;%s\033\\` (message) generate native wezterm toasts. Through tmux they need the same
  `allow-passthrough` wrapping. (wezterm.org/escape-sequences)
- **tmux `set-clipboard` / `allow-passthrough`.** `set-clipboard on` lets an application's OSC 52
  create paste buffers *and* set the outer terminal's clipboard (default is `external`, which
  **ignores** application OSC 52). `allow-passthrough` (default **off**) gates the `\ePtmux;…\e\\`
  DCS bypass used to smuggle sequences tmux doesn't natively forward. (tmux wiki/Clipboard,
  `options-table.c`, `input.c`)
- **Already shipped in these dotfiles** (so out of build scope, in verify scope):
  - `dot_tmux.conf:14` `set -g set-clipboard on` + `terminal-features … :clipboard` — clipboard
    remote→local already works over SSH.
  - `dot_config/wezterm/config/keys.lua` `hyperlink_rules` (auto http/https) +
    `OpenLinkAtMouseCursor` mouse binding — clickable links already work.
  - `wezterm.lua` composes focused modules via `require("config.<x>").apply(config)`.
  - `~/.local/bin` is already on `PATH` (`dot_bashrc:21`); `executable_browser-mcp` is the
    precedent for a shim there.

## Non-goals (stated so they are not smuggled in)

- **No SSH backhaul in v1.** No VPS→laptop connection, no OpenSSH forced-command, no bridge key,
  no alternate sshd port, no GUI-session (`DBUS`/`WAYLAND_DISPLAY`) discovery. Deferred to
  "Future" for the detached/headless-firing case only.
- **No engine module and no `profiles.toml` change.** There is nothing to install; it is dotfiles.
- **No dependency on Tailscale or the `remote` profile.** The bridge rides the existing pty. It is
  most useful over a Tailscale-secured SSH session (which the `remote`/`server` profiles already
  provision), but adds nothing to them and needs none of their machinery.
- **Not native wezterm-mux panes.** That needs `wezterm-mux-server` on every VPS and is existing
  wezterm-domain territory (`config/domains.lua`), not this bridge.
- **Not a non-wezterm-terminal path.** If the laptop viewer is not wezterm (e.g. a phone SSH app),
  open-URL/notify degrade to no-ops; clipboard/links degrade per that terminal's support.

## Decisions

### Transport: in-band wezterm user-vars, not an SSH backhaul

Programmatic "open this URL on the laptop" has no standard escape sequence, so it needs *some*
out-of-terminal signal. Two shapes were considered:

- **In-band (chosen)** — the VPS emits an OSC 1337 `SetUserVar` carrying the URL; a `wezterm.lua`
  handler opens it locally. wezterm already runs **inside** the laptop's GUI session, so it opens
  the browser with zero extra plumbing.
- **SSH backhaul (rejected for v1)** — VPS `ssh`es back to the laptop to run `xdg-open`. Because
  the platform enables **Tailscale SSH** (`server.py`: `tailscale up --ssh`), tailscaled owns
  `:22`, so an OpenSSH `authorized_keys` forced-command would not fire — the backhaul would need a
  **separate** OpenSSH port bound to `tailscale0`, a dedicated key provisioned via the age bundle,
  a forced-command dispatcher, discovery of the logged-in session's `DBUS`/`WAYLAND_DISPLAY`, and a
  scoped `accept` ACL. Large surface for one capability the in-band path already covers whenever a
  wezterm client is attached — i.e. exactly when you are looking.

**Cost of the in-band choice:** it only fires while a wezterm client is attached to the pane. For
"feels local while I'm working," that is the target scenario; detached/headless firing is the sole
reason to add the backhaul later (see Future).

### Structure: pure dotfiles, no engine module

With the in-band transport there is nothing to install — no package, no secret, no systemd unit,
no ACL. The whole feature is: one tmux option, one wezterm handler, three small shims, one env
var. All are chezmoi dotfiles applied to both OSes; each is harmless on the machine where it is not
the active side (the wezterm handler only matters where wezterm runs; the shims only forward when
inside an SSH session). An engine module would have nothing to do, so there is none.

Alternative rejected: a Fedora-only `remote`-profile module (as RDP/browser-mcp use). It would add
process and gates for a feature that installs no software.

### Security: scheme-restricted auto-open, no prompt

`allow-passthrough on` means **any process in the VPS session can emit these sequences** — auto-open
trades away the click that makes OSC 8 links safe. Bounded by:

- The handler opens **`http`/`https` only** (`value:match("^https?://")`); everything else
  (`file://`, `javascript:`, custom schemes — the code-exec / local-file vectors) is ignored and
  logged. Navigating to an http(s) URL cannot execute anything; worst case is an unwanted tab.
- Open via **`wezterm.open_with(url)`** (default browser, navigation only) — never a shell command.
- **No confirmation prompt** — scheme-restriction removes the dangerous cases, and a per-open prompt
  would defeat "feels local." A prompt/allowlist can be an opt-in toggle later.

Residual risk consciously accepted: a process in your VPS session can open an arbitrary http(s) tab
in your laptop browser (with your session/cookies). Acceptable for a personal dev box.

### Notify: OSC 777 native toast, no handler code

`notify` emits OSC 777 `notify;title;body`; wezterm renders the toast itself — no Lua needed, and it
degrades to any OSC-9/777-aware terminal. open-URL *must* be `SetUserVar` (no standard open escape
exists), but notify has a standard escape, so it uses it. Rejected: routing notify through the
handler — more code, wezterm-only, and no requirement justifies the extra control (YAGNI).

### Open interception: `$BROWSER` + a context-aware `xdg-open` shim

`export BROWSER=~/.local/bin/open-url` catches tools that honor `$BROWSER` (gh, many CLIs); a lot of
tools call `xdg-open` directly, so a shim on `~/.local/bin` (ahead of `/usr/bin` on `PATH`) catches
those too. The shim is context-aware to stay transparent:

- `$SSH_CONNECTION` set **and** arg is `http(s)` → forward via `open-url`.
- otherwise (local laptop, or a non-URL arg like a file / `mailto:`) → `exec /usr/bin/xdg-open`.

Same local-vs-remote detection `paste.lua` and `browser-mcp` already use. Pure upside on the VPS: a
headless server's `xdg-open` fails today anyway, so intercepting http(s) only ever adds capability.

## Architecture / data flow

```
VPS (Ubuntu, inside tmux):
  gh / OAuth / vite ──$BROWSER──▶ open-url <url> ─────────────┐
  arbitrary tool ──▶ xdg-open <url> ──($SSH_CONNECTION+http)──┤─▶ OSC 1337 SetUserVar=open_url=<b64>
  long-job / agent ──▶ notify "title" "body" ─────────────────▶ OSC 777 notify;title;body
        │  when $TMUX: wrapped \033Ptmux;\033<seq>\033\\   (needs allow-passthrough on)
        ▼  up through tmux ──▶ over ssh ──▶ into wezterm (laptop, in the GUI session)
laptop (Fedora, wezterm):
  config/bridge.lua:  on('user-var-changed', name=='open_url')
                        → value matches ^https?://  → wezterm.open_with(value)   (else ignore+log)
  OSC 777             → wezterm native toast
  [already present]   OSC 52 → laptop clipboard ;  OSC 8 hyperlink_rules → CTRL-click opens browser
```

## Files

**New**

- `dot_config/wezterm/config/bridge.lua` — exports `apply(config)`; registers
  `wezterm.on('user-var-changed', …)`. On `name == "open_url"`: if `value:match("^https?://")` →
  `wezterm.open_with(value)`, else `wezterm.log_warn(...)` and drop. (wezterm hands the handler the
  **decoded** value, so no base64 in Lua.)
- `dot_local/bin/executable_open-url` — the core primitive. `url="$1"`; base64-encode it; emit
  `SetUserVar=open_url=<b64>`; when `$TMUX` is set, wrap in the `\033Ptmux;…` passthrough form.
  Exit 0 regardless (a detached/non-wezterm viewer simply ignores the bytes).
- `dot_local/bin/executable_notify` — `notify "title" "body"`; emit OSC 777 `notify;title;body`,
  tmux-wrapped when `$TMUX`.
- `dot_local/bin/executable_xdg-open` — context-aware wrapper (see decision above); delegates to
  `/usr/bin/xdg-open` for the local / non-http cases.

**Edit**

- `dot_config/wezterm/wezterm.lua` — add `require("config.bridge").apply(config)` to the module
  wiring block.
- `dot_tmux.conf` — add `set -g allow-passthrough on` (companion to the existing
  `set -g set-clipboard on`).
- `dot_bashrc` — `export BROWSER="${HOME}/.local/bin/open-url"`.

## Errors / degraded behavior (documented, not failures)

| Condition | Behaviour |
|---|---|
| Viewer is not wezterm, or tmux is detached (no client) | Escape sequences are ignored by the terminal; shims still exit 0. No error. |
| `allow-passthrough` not yet applied (stale tmux) | Sequences are swallowed by tmux; open-URL/notify silently no-op until `dot_tmux.conf` is reloaded. Clipboard/links unaffected. |
| Non-http(s) URL reaches the handler | Ignored and logged by `bridge.lua`; nothing opens. |
| `xdg-open` shim on the laptop, or with a file/`mailto:` arg | Delegates to real `/usr/bin/xdg-open` — fully transparent. |
| `base64` missing (shim) | open-url no-ops with a stderr note; `base64` is present on both OSes, so this is defensive only. |

## Testing

Pure dotfiles, so no engine `pytest`. Two layers:

1. **Shell-logic assertions** on the only branches that carry logic (hermetic, no GUI):
   - `xdg-open` shim: `$SSH_CONNECTION` set + `http(s)` arg → invokes `open-url` (assert via a stub
     on `PATH`); local (no `$SSH_CONNECTION`) or a `file://`/path arg → invokes `/usr/bin/xdg-open`.
   - `open-url` / `notify`: `$TMUX` set → output contains the `\033Ptmux;` wrapper and terminator;
     unset → bare OSC. (Assert on captured stdout; no terminal needed.)
2. **Manual on-hardware acceptance** (laptop wezterm ⇄ VPS tmux), the checklist below.

## Acceptance

From a wezterm pane SSH'd into a VPS, inside tmux, after `chezmoi apply` on both ends and a tmux
reload:

- `open-url https://example.com` opens example.com in the **laptop** browser.
- A `gh`-printed / OAuth-device URL opens the laptop browser (via `$BROWSER`).
- A tool calling `xdg-open https://…` on the VPS opens the laptop browser (via the shim).
- `open-url file:///etc/hostname` opens **nothing** (scheme rejected).
- `notify "build" "done"` pops a laptop toast.
- Copying text in a VPS app lands in the laptop clipboard (already-shipped path, re-verified).
- A printed http/https URL is CTRL-click-openable (already-shipped path, re-verified).
- On the **laptop** itself, `xdg-open ./file` and `xdg-open https://…` behave natively (shim
  transparent).
- Detached tmux / a non-wezterm SSH client: the above open-URL/notify calls no-op without error.

## Open items to verify at implementation

1. **tmux OSC 8 hyperlink passthrough** on the installed tmux version — clickable links rely on
   tmux forwarding OSC 8; confirm on the pinned version (fall back: links still copy/clipboard).
2. **Exact tmux passthrough wrapping** for OSC 777 vs OSC 1337 — the inner-ESC doubling and `ST`
   terminator differ subtly between sequences; verify each against a live wezterm+tmux before
   finalizing the shim `printf` templates (tmux FAQ "passthrough escape sequence").
3. **`SetUserVar` name charset** — confirm `open_url` (underscore) is accepted verbatim; adjust if
   wezterm restricts the name grammar.
4. **`wezterm.open_with` default-browser selection on Fedora** — confirm it honors the desktop
   default (Chrome, per the browser-mcp work) rather than a hardcoded handler.

## Future (v2, explicitly out of scope now)

- **SSH backhaul** for firing while detached/headless (the only gap of the in-band path): OpenSSH on
  a `tailscale0`-bound port, age-bundle bridge key, forced-command dispatcher, session-env discovery,
  scoped `accept` ACL.
- **Native wezterm-mux panes** (persistent native panes) via `wezterm-mux-server` on the VPS.
- **On-demand clipboard push** (VPS→laptop write beyond OSC 52 selection).
- **Confirmation/allowlist toggle** for open-URL, for a stricter posture.
- **Agent session-events notifier** — extend the OSC 777 notify into an emitter on the four
  agent events (approval / input / completion / failure), attention-first, deep-linking back to the
  session, and routed to a phone via ntfy / Web Push. Adopted from T3 Code's mobile agent-awareness
  model; see `2026-07-18-t3code-adoption-notes.md` and task #10.
