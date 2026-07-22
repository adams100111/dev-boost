# systemd user units

## browser-mcp.service — per-session browsers for remote Claude Code

Runs one always-on **Playwright MCP** server on this laptop, bound to the
**Tailscale** interface. Remote Claude Code sessions (running on another box)
connect over the tailnet and each gets **its own isolated, visible browser**
here — so `mcp__playwright__browser_*` tools drive a real Chromium on your
screen, as if Claude were local. One server multiplexes N sessions (Playwright
MCP gives each connection its own browser context; `--isolated` keeps them from
sharing a profile). Launcher: [`~/.local/bin/browser-mcp`](../../../dot_local/bin/executable_browser-mcp).

### On a dev-boost machine this is automatic

The `dotfiles` module applies this tree via chezmoi, which drops the unit **and**
the `default.target.wants/` symlink — so the service is enabled and starts on your
next graphical login. Two one-time prerequisites the dotfiles can't do for you:

```sh
# 1. A browser. The launcher prefers your installed Google Chrome (channel
#    `chrome`) and needs no download; if Chrome is absent it falls back to
#    Playwright's Chromium, which you install once:
#        npx -y playwright@latest install --with-deps chromium
#    Force a choice any time with BROWSER_CHANNEL=chrome|chromium|msedge.

# 2. (optional) keep it running while logged out — needs a privileged action:
loginctl enable-linger "$USER"
```

Start it now without waiting for a re-login:

```sh
systemctl --user daemon-reload
systemctl --user enable --now browser-mcp.service   # --now also starts it
```

Watch it: `systemctl --user status browser-mcp.service` · `journalctl --user -u browser-mcp -f`

### The other end — one line on the box that runs Claude

Add a **user-scope** MCP server pointing at this laptop's Tailscale IP
(`tailscale ip -4`), so every Claude Code project/session reuses it:

```sh
claude mcp add --scope user --transport http \
  playwright-laptop  http://<this-laptop-tailscale-ip>:8931/mcp
```

Notes:
- The launcher binds only to the Tailscale IP and pins `--allowed-hosts` to that
  exact `ip:port` — reachable from your tailnet, not from untrusted wifi. Never
  `tailscale funnel` it; the MCP server is unauthenticated.
- `--isolated` browsers are **ephemeral** (no saved logins between runs) — that's
  what gives clean per-session isolation. For a session that must persist a login,
  give that one its own `--user-data-dir` instead.
