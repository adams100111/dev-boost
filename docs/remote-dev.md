# Remote dev — build on a server, keep the keyboard and browser on your laptop

When your laptop runs out of RAM on type-checks, .NET/Laravel builds, language
servers, and Docker, the fix is not a bigger laptop — it's to **do the heavy work
on a server and use it from the laptop**. Your laptop becomes a thin window: you
type in your terminal, edit in `fresh`, run Claude Code — but the CPU and RAM belong
to the server. This guide sets that up end to end using dev-boost's own pieces.

## The model

```
┌──────────┐        Tailscale (private mesh)        ┌─────────────────────┐
│  laptop  │  ───────────────────────────────────▶ │  VPS  (your dev box)│
│  screen  │   ssh / dev / expose / pw-server       │  builds · LSP · Docker
│  browser │                                        │  Claude · fresh · ddev
└──────────┘                                        └─────────────────────┘
                                                     ┌─────────────────────┐
                                              ─────▶ │ dedicated (PRODUCTION)
                                                     │ shipped apps only
                                                     └─────────────────────┘
```

- **Your laptop** — the screen, keyboard, and browser. Runs almost nothing.
- **Your VPS** — the **dev box**. Roomy, solo, safe to hammer with builds. This is
  where Claude Code, `fresh`, type-checks, Docker, and dev servers run.
- **A dedicated server running production** — a **hands-off box**. Never run dev
  builds next to shipped apps; one bad build can OOM a live app. Keep it on the
  network only so you can reach it for deploys and ops.

### VPS vs dedicated: use both, never "switch"

Once every machine joins your **tailnet** (see below), they are *all reachable by
name at the same time*. You never switch — you pick which name to connect to:

| Box | Good for | Role |
|-----|----------|------|
| **VPS** (e.g. 24 GB, solo) | builds, LSP, Docker, Playwright, dev servers | **primary dev box** |
| **Dedicated** (runs prod) | deploys, migrations, log-checking | **production — hands off** |
| **Laptop** | screen, keyboard, browser | thin client |

Rule of thumb: **`dev my-vps` to build, `ssh my-prod` only to ship.**

## Why Tailscale (not plain SSH or mosh)

[Tailscale](https://tailscale.com) puts your machines on a private, encrypted
network only you can see. After it's installed on each box:

- Every machine gets a **stable name** — `ssh my-vps` works from anywhere, even
  when IPs change or a box sits behind a home router. No port-forwarding on the
  router, no addresses to memorise.
- You can then **close public SSH entirely** and reach the box only over the
  tailnet (dev-boost's `server-firewall` module is built for this).
- It adds one thing plain SSH can't: **`tailscale serve`** publishes a port to a
  real HTTPS URL your devices can open — which replaces fiddly `ssh -L` port
  forwarding for browser testing (see [Browser testing](#browser-testing)).

## One-time setup

### 1. On each server

On an Ubuntu/Debian VPS:

```bash
curl -fsSL https://raw.githubusercontent.com/adams100111/dev-boost/main/scripts/get.sh | bash -s -- term devtools
devboost install server     # tailscale + firewall + zram + agent-sudo + restic + tmux-persist
```

What the `server` tier gives you, and why each matters here:

- **`tailscale`** — joins the tailnet with Tailscale SSH. If you didn't bake a
  `TAILSCALE_AUTHKEY` into the secrets bundle, run `sudo tailscale up --ssh` once.
- **`zram`** — compressed-RAM swap: **OOM insurance** for long builds and agents.
- **`agent-sudo`** — passwordless sudo so **Claude Code never hangs on a sudo prompt**
  while working unattended.
- **`server-firewall`** — locks the box to SSH + the tailnet interface.
- **`restic-b2`** — nightly encrypted offsite backups of your work.
- **`term` + `devtools`** — your CLI/shell/dotfiles plus the language runtimes
  (ddev, .NET/Aspire, Node, uv, Playwright) so the box can actually build.

For Laravel/ddev reachable over the tailnet, also:

```bash
devboost install laravel    # includes ddev-remote → binds ddev's router to all interfaces
```

### 2. On your laptop

Join the same tailnet so the servers are reachable and the helper commands light up:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --ssh
```

Then let dev-boost mirror every tailnet machine into `~/.ssh/config` for you — one command,
zero hand-editing:

```bash
tsdev-sync           # writes a managed block of Host entries from `tailscale status`
```

Every machine on your tailnet becomes a clean `dev <name>` target **and** a WezTerm launcher
entry (`LEADER d`), using stable MagicDNS names. Re-run it after adding a machine. (Override the
login user with `DEVBOOST_SSH_USER`; the block is idempotent and lives between `# >>> devboost
tailnet >>>` markers, so your own `~/.ssh/config` entries are untouched.)

Prefer to do it by hand? A plain entry works too:

```sshconfig
Host my-vps            # dev box
    HostName my-vps    # Tailscale MagicDNS name
    User you
```

## Daily workflow

The `dev` helper (shipped in the managed `.bashrc`) is the one command you need:

```bash
dev my-vps innovation        # ssh in, land in ~/projects/innovation, ready to work
```

That single command:
1. `ssh`es into `my-vps`,
2. finds the `innovation` repo (searches `~/projects` then `~/repos`),
3. attaches or creates a **persistent tmux session** named after the repo, and
4. drops you at a prompt **inside the repo**.

Then work — all of it on the server's RAM:

```bash
claude               # Claude Code — its TS + Python LSPs run here, not on your laptop
fresh .              # your editor, on the server
npm run check:all    # type-checks on the server
ddev start && npm run build
```

Close the lid, reconnect later with the same `dev my-vps innovation`, and tmux drops
you back exactly where you were (thanks to `tmux-persist`). One session per repo.

See [the `dev` reference](#the-dev-helper) below for all the options.

## Browser testing

None of this needs `ssh -L` port forwarding — the tailnet handles reachability.

### Just view your app in the laptop browser

```bash
# on the VPS:
expose 5173          # → prints https://my-vps.<tailnet>.ts.net  (auto-HTTPS)
```

Open that URL on your laptop. `exposed` shows what's published; `unexpose` takes it
down. (`expose 18888` for the Aspire dashboard.)

### Playwright — two different tools, don't confuse them

The **test runner** runs your `playwright test` suite; the **MCP** is the browser
Claude Code drives (the `browser_*` tools). They connect differently.

#### Test runner — headed browser on the laptop, suite runs on the VPS

```bash
# laptop:
pw-server            # opens a real browser window on the laptop; prints a pw-connect line
# VPS:
pw-connect ws://my-laptop:5000/pw   # your `playwright test` run on the VPS, shown locally
```

#### MCP — three topologies, pick per task

Verified against `@playwright/mcp`: `--headless` defaults to **false** (headed),
`--cdp-endpoint` connects to an existing browser, and `--port/--host` runs the MCP as an
HTTP server a remote client attaches to (endpoint path `/mcp`).

**1. Headless on the server (default — zero laptop).** Claude runs the MCP on the VPS
with no display and hands back screenshots. Best for unattended / bulk runs.

**2. Headed on the laptop, driven from the server** — `pw-mcp` + `pw-laptop` (recommended for *watching*):

```bash
# laptop — headed browser opens here (a persistent profile: your logins survive across runs).
# It advertises this laptop's STABLE MagicDNS name, so the server config never changes:
pw-mcp                       # persistent-profile Chrome
pw-mcp --extension           # …or drive your REAL open Chrome via the bridge extension
```

Then on the **server**, register it once — one word if you've set `DEVBOOST_DEV_LAPTOP`:

```bash
pw-laptop                    # = claude mcp add --transport http --scope user \
                             #     playwright-laptop http://$DEVBOOST_DEV_LAPTOP:8931/mcp
```

Claude (on the VPS) drives the browser; the window opens on your laptop. Only a
browser's worth of RAM stays local — trivial next to the LSP/builds you offloaded.

**Make it automatic on every server:** put your laptop's MagicDNS name in the age secrets
bundle as `DEVBOOST_DEV_LAPTOP` (alongside the Tailscale key). Every box you provision then
knows it — `pw-laptop` is a bare one-word command there, and because the URL uses the *stable*
name, the registration never goes stale. `pw-laptop <name> <port>` overrides it ad-hoc.

**3. MCP on the server, browser on the laptop via CDP** (true "MCP on the server", fiddlier):

```bash
# laptop — a headed Chrome with remote debugging, reverse-tunneled so it looks local to the VPS:
chromium --remote-debugging-port=9222 &
ssh -R 9222:localhost:9222 my-vps
# VPS:
npx @playwright/mcp@latest --cdp-endpoint ws://localhost:9222
```

Chrome guards `--remote-debugging-port` to *localhost* and rejects cross-host Host
headers, so you must **tunnel** the port to appear local on the server (the `ssh -R`
above) rather than pointing at a raw tailnet IP. Prefer topology 2 for watching; this
exists for when the MCP itself must live on the server.

> Headed topologies (2 and 3) need a graphical session on the laptop and Playwright's
> browser installed (`npx playwright install chromium` if the MCP reports it missing).

## The `dev` helper

```
dev <host> [repo]
```

| Invocation | Result |
|------------|--------|
| `dev my-vps innovation` | ssh + attach/create the `innovation` session in the repo |
| `dev my-vps` | a plain `dev` session in `$HOME` |
| `dev my-vps /srv/app` | an absolute remote path, used as-is |

- **Repo lookup** searches `$DEV_REPO_ROOTS` (colon-separated, default
  `~/projects:~/repos`), first match wins. A repo you name but that isn't found is a
  **hard error** (exit 3) — it won't silently drop you somewhere else. Running `dev`
  with no repo is a valid "just give me a session" and lands in `$HOME`.
- **Configure the search roots per server** by exporting `DEV_REPO_ROOTS` in that
  box's `~/.bash_profile` or `~/.profile` (it describes *that* machine's layout).
  The resolver runs under a remote login shell so the export is honored. Example:
  `export DEV_REPO_ROOTS=/srv/www:$HOME/code`.
- **tmux** gives one persistent session per repo (`new-session -A -D`: attach if it
  exists, and detach any stale connection so the view always fits your current
  screen). On a box without tmux it falls back to a plain shell in the repo.
- You always land at a prompt and launch `claude`/`fresh` yourself.

> Requires a bash-compatible login shell on the remote (the dev-boost fleet uses
> bash). It's laptop-side and needs only `ssh`.

## Helper quick reference

| Where | Command | Does |
|-------|---------|------|
| laptop | `tsdev-sync` | mirror the tailnet into `~/.ssh/config` (→ `dev`/WezTerm targets) |
| laptop | `dev <host> [repo]` | ssh in + attach a per-repo tmux session in the repo |
| laptop | `pw-mcp [--extension] [port]` | run the Playwright MCP here (headed) for a server-side Claude |
| server | `pw-laptop [name] [port]` | register the laptop's headed MCP with Claude (uses `$DEVBOOST_DEV_LAPTOP`) |
| server | `expose <port>` | publish a VPS port at `https://<host>.<tailnet>.ts.net` |
| laptop | `img2ssh <host>` | paste a clipboard image into an SSH'd Claude Code |

## Related pieces

- `ddev-remote` — binds ddev's router to all interfaces so ddev projects are
  reachable over the tailnet.
- `tmux-persist` — restores your sessions after a reboot.
