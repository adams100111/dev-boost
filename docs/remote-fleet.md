# Remote fleet — operator guide

Turn a laptop (or two) plus always-on Linux servers into one machine for agentic
development: connect over a private mesh, keep a session alive through sleep and
roaming, and run the actual work — builds, agents, editors — in a capped, sudo-less
sandbox that can safely share a box with production. This is the operator's guide to
provisioning and running that fleet with dev-boost.

If you only want the four-line summary and the `fleet` verb table, see the "Remote
fleet" section in [`README.md`](../README.md). This document is the full narrative.

---

## 1. Concept & topology

Three layers, stacked, each solving a different failure mode. Getting them in the
right place is the whole design:

| Layer | Job | Tool | It is *not* |
|-------|-----|------|--------------|
| **Reachability + auth** | a private, keyless, ACL'd road to the box | **Tailscale** (mesh VPN + Tailscale SSH) | a session that survives sleep/roam on its own — it's still a TCP connection underneath |
| **Resilient transport** | the session survives sleep, Wi-Fi→cellular, IP changes; no lag typing on a bad link | **Mosh** (UDP roaming) | the safety net for your *data* — it carries keystrokes, not state |
| **Persistent session** | panes and running agents survive independent of any one client | **herdr** (agent-aware terminal multiplexer) | — |

**Honest calibration:** once you always work inside herdr on the server, Mosh is not
load-bearing for your data — reconnect over plain Tailscale SSH and `herdr attach` and
nothing was lost. Mosh's real value is **UX under motion**: no manual reconnect after
your laptop sleeps or you hop from Wi-Fi to cellular, and responsive typing even on a
phone connection. It's a lightweight distro package, so it earns a permanent spot in
the spine — but herdr, not Mosh, is what actually preserves your work.

**The brain is a role, not a machine.** "Brain" means the box (and the sandboxed
account on it) that runs your persistent herdr session and cross-arch builds. It is
selected by which server you ran `devboost brain` on and which host your `fleet`
config points at — not baked into the architecture. There is no dedicated,
expendable box yet: both production servers run real apps 24/7, so the brain
currently has to share a box with production. That constraint is temporary (see
[§7, the mini-server migration](#7-the-mini-server-migration)) and the design
deliberately avoids distorting itself around it — the sandbox (below) is what makes
sharing safe in the meantime.

### Reference fleet

The shape this guide assumes (adjust names to your own tailnet):

| Box | Install | Role |
|-----|---------|------|
| Laptop(s) — Fedora, e.g. `mate-dev`, `hp-dev` | `full` | dev seats — thin, interchangeable clients |
| Production server #1 — Ubuntu, e.g. `mod-sol` | `server` (+ `devboost brain`) | real apps **and** the x86 build/brain host |
| Production server #2 — Ubuntu, e.g. `my-dev` | `server` | real apps (an optional second/arm64 brain) |

Only **one** server needs to run `devboost brain` to have a working fleet. A second
brain-capable server is useful for an arm64 native builder, but not required — the
first is enough to develop, build, and ship.

---

## 2. Per-role setup

### Laptop (Fedora) — dev seat

```bash
curl -fsSL https://raw.githubusercontent.com/adams100111/dev-boost/main/scripts/get.sh | bash -s -- full
```

`full` is the whole workstation aggregate (editors, language runtimes, GUI apps,
shell/terminal — see the profiles table in `README.md`). What matters for the fleet:
it now includes the `remote` leaf profile (`tailscale`, `mosh`), so every laptop
**joins the tailnet and gets Mosh automatically** — no separate step. It also
installs `dotfiles` (chezmoi), which is what puts the `fleet` command on your PATH
(`~/.local/bin/fleet`, from `dotfiles/dot_local/bin/executable_fleet`) and seeds
`~/.config/fleet/config`.

### Server (Ubuntu/Debian) — production host

```bash
curl -fsSL https://raw.githubusercontent.com/adams100111/dev-boost/main/scripts/get.sh | bash -s -- server
```

`server` installs: `tailscale` (joins the tailnet), `server-firewall` (ufw: deny
incoming, allow SSH + `tailscale0`), `zram` (compressed swap — OOM insurance),
`restic-b2` (nightly encrypted offsite backups), `tmux-persist`, `docker` +
`docker-build-gc`. Notably, **`agent-sudo` (passwordless sudo) is not in `server`** —
that footgun is opt-in only (`devboost install agent-sudo`), on purpose: a prod host
never gets passwordless sudo by default.

`server` alone does **not** install chezmoi/dotfiles (those live in the `base`/`shell`
profiles, which are laptop-only). That's fine for the base server role; see the note
in [§6, Domains](#6-domains) about the one extra step it implies for the Caddy
starter config.

### Brain host — one chosen server

Once a server is up (via `server` above), pick the one that will host the brain and
run:

```bash
devboost brain
```

This does two things, in order:
1. **Installs `brain-host`** (sudo, host-level tools): `mosh`, `caddy`,
   `crossarch-build` (rootless podman + qemu binfmt for multi-arch builds).
2. **Creates the `devbrain` managed account** — capped, sudo-less (see
   [§3](#3-the-devbrain-sandbox)) — seeded with your SSH public key(s) so you can
   `mosh devbrain@<brain-host>` afterwards, and bootstraps the `brain-tools` profile
   (`herdr`, `herdr-plugins`) *inside that account's home*.

Flags (from `devboost brain --help`): `--ram` (default `8G`), `--cpu` (default
`200%`), `--disk` (default `50G`), `--tasks` (default `4096`), `--ssh-key`
(repeatable — falls back to your own `~/.ssh/*.pub` if omitted), `--dry-run`,
`--force`, `--apply/--no-apply`. It's idempotent: re-running converges rather than
erroring if `devbrain` already exists. After it runs, it prints a reminder:

```
review devbrain caps for this box (ram/cpu/disk/tasks) — production headroom matters: devboost accounts edit devbrain
```

Take that reminder seriously — the defaults are conservative but arbitrary; see
[§3](#3-the-devbrain-sandbox) for tuning.

### Secrets each role needs

Secrets are read from an age-encrypted bundle (the same one the rest of dev-boost
uses); every secret is optional — a missing one degrades to a printed warning and a
next-step, it never blocks the rest of the install.

| Secret | Used by | Effect if missing |
|--------|---------|--------------------|
| `TAILSCALE_AUTHKEY` | `tailscale` (both `full` and `server`) | node isn't brought up automatically; run `sudo tailscale up --ssh` once by hand |
| `B2_ACCOUNT_ID`, `B2_ACCOUNT_KEY`, `RESTIC_REPOSITORY`, `RESTIC_PASSWORD` | `restic-b2` (`server`) | `restic` is installed but the nightly backup timer is never wired up |
| `DEVBOOST_HERDR_TELEGRAM_TOKEN`, `DEVBOOST_HERDR_TELEGRAM_CHAT_ID` (plain env vars, not the secrets bundle) | `herdr-plugins` (`brain-tools`, installed by `devboost brain`) | herdr's Telegram notify plugin installs but is left unconfigured (non-blocking) |

---

## 3. The `devbrain` sandbox

`devbrain` is a **managed account** created by `devboost brain` — not a container,
not a bespoke sandboxing module, just a normal Linux user provisioned through
dev-boost's existing `accounts` subsystem (`users.toml` + cgroup slice caps). Its
recipe:

- `privilege = "none"` — **the safety core.** No sudo group membership, no sudoers
  entry. Nothing installed by this path ever grants `devbrain` sudo, on this box or
  any other.
- Cgroup caps on `user-<uid>.slice`: RAM, CPU, and task-count ceilings (defaults
  `8G` / `200%` / `4096` tasks), plus a disk quota (default `50G`) — so a runaway
  build or agent loop can't starve the production apps sharing the box.
- `linger = true` — herdr and `mosh-server` keep running under `devbrain` even with
  no active login, so a session survives you closing your laptop.
- `ssh_authorized_keys` — seeded from `devboost brain --ssh-key` or your own
  `~/.ssh/*.pub`. This is how `mosh devbrain@<brain-host>` and
  `ssh devbrain@<brain-host>` authenticate — key-only, no password login.
- `bootstrap_profiles = ["brain-tools"]` — `herdr` and `herdr-plugins` install
  *inside `devbrain`'s home*, as `devbrain`, via a demoted (non-sudo) bootstrap —
  because a `privilege=none` account can't sudo, brain tooling has to split into
  host-level sudo tools (`brain-host`: mosh, caddy, crossarch-build) versus
  user-level demoted tools (`brain-tools`: herdr).

**Isolation this actually buys you:** `devbrain` can't sudo; it's capped so it can't
starve the host's CPU/RAM/disk/process table; and because production runs as its own
user with normal Unix permissions, `devbrain` can't read production's files either.
That's enough to stop "a runaway agent crashes prod" — it is **not** namespace-level
isolation (no separate PID/mount namespace, no container). Treat it as
**acceptable, not zero-risk**: a correctly-permissioned, capped user, sharing a
kernel with production. A stronger container-isolation tier is a documented future
option (§8), deliberately not built yet — the marginal safety gain over a capped,
unprivileged user didn't justify the complexity for now.

**Reviewing and tuning caps:**

```bash
devboost accounts edit devbrain
```

Opens an interactive form prefilled with `devbrain`'s current settings, then
re-applies it on save. Also useful: `devboost accounts list` (table of every managed
account and its caps) and `devboost accounts disable devbrain` / `enable devbrain`
if you need to lock it out reversibly (e.g. before a maintenance window on a
production box).

**Reaching it:**

```bash
fleet dev                         # mosh devbrain@$DEVBOOST_BRAIN, then attach herdr
mosh devbrain@<brain-host>        # the same thing, spelled out
ssh devbrain@<brain-host>         # plain SSH also works — same authorized_keys
```

There is no password login and no sudo — if you ever find yourself wanting
`sudo` inside `devbrain`, that's a sign the work belongs on the host account (via
`fleet edge` / a direct SSH to your own login) instead, not a reason to loosen the
sandbox.

---

## 4. Daily DX flow

The intended day-to-day shape, once a brain host exists:

1. **Develop** from a laptop with VS Code's Remote-SSH extension, pointed at
   `devbrain@<brain-host>` (add a `Host` entry to `~/.ssh/config` for that user/host
   pair — `devbrain` is a separate login from your own tailnet user, so it isn't
   covered by a generic tailnet-mirroring helper). Editing, language servers, and
   type-checking all run on the brain host's CPU/RAM, capped, not on your laptop.
2. **Orchestrate** via `fleet dev` — this attaches the same herdr session `devbrain`
   is running. Because herdr sessions are observe/control, not exclusive, a second
   laptop running `fleet dev` lands in the **same session** — both laptops become
   multiplayer on one set of running agents, rather than each spinning up its own.
3. **Build** with `fleet ship <img> [dir]` — capped, rootless multi-arch container
   builds run on `$DEVBOOST_BUILDER` as `devbrain` (see [§5](#5-cross-arch-builds)).
4. **Reach production** with `fleet edge` — a plain `ssh $DEVBOOST_EDGE` into the
   public-facing/production box, for checking on or deploying the shipped app. This
   is a different login than `devbrain` — it's your own account on the prod box, used
   deliberately and briefly, not where agents live.
5. **Check on agents** with `fleet status` — a herdr agent snapshot (working /
   blocked / done) on the brain, without attaching the full session.

All five verbs read their host targets from `~/.config/fleet/config`
(`DEVBOOST_BRAIN`, `DEVBOOST_BUILDER`, `DEVBOOST_EDGE`), sourced by the `fleet`
script itself. The shipped file ships with all three commented out:

```bash
# export DEVBOOST_BRAIN=my-dev        # the box hosting the sandboxed devbrain brain
# export DEVBOOST_BUILDER=mod-sol     # the box that runs multi-arch `fleet ship` builds
# export DEVBOOST_EDGE=my-dev         # the public-facing / production box for `fleet edge`
```

Uncomment and fill in your own MagicDNS names (§6). Each verb fails cleanly with a
named-variable error (not a silent hang or a cryptic SSH failure) if its target isn't
set — e.g. `fleet dev` with `DEVBOOST_BRAIN` unset prints `fleet: DEVBOOST_BRAIN is
not set — add it to ~/.config/fleet/config` and exits non-zero.

---

## 5. Cross-arch builds

`fleet ship <img> [dir]` runs, on `$DEVBOOST_BUILDER` as the capped `devbrain` user:

```bash
podman build --platform linux/amd64,linux/arm64 --manifest <img> . && podman manifest push <img>
```

`crossarch-build` (part of `brain-host`) provisions this: it installs **podman**
(daemonless, rootless-first) and registers `qemu-user-static` binfmt handlers so a
single rootless build can target both architectures via emulation. `devbrain`'s
subuid/subgid ranges (needed for rootless user namespaces) are auto-allocated by
`useradd` when the account is created — nothing extra to configure.

**Why podman as capped `devbrain`, not `docker buildx` on the host:** `docker buildx`
runs against the host's `docker` daemon, whose `docker` group is root-equivalent —
handing `devbrain` that access would defeat the entire non-sudo sandbox, and a
host-level build is uncapped (it can starve production). Rootless podman under
`devbrain`'s cgroup slice is the only path that is **both** capped **and**
unprivileged. (`docker` is still installed on servers via the `server` profile — it's
just not what `fleet ship` uses, and not something `devbrain` has access to.)

An arm64 production server (e.g. `my-dev`) typically only needs to **pull** the
resulting multi-arch manifest and run it — it doesn't need `crossarch-build` unless
you also want it to build.

---

## 6. Domains

Three tiers, no extra infrastructure required for the first two:

### MagicDNS short names — the default

Once a box has joined the tailnet (`tailscale`, part of both `full` and `server`),
Tailscale's MagicDNS gives it a stable short hostname — e.g. `mod-sol`, `my-dev` —
usable directly: `ssh mod-sol`, `mosh devbrain@my-dev`,
`https://mod-sol.<your-tailnet>.ts.net`. This works from any device running the
Tailscale app (iOS/macOS/Windows/Android/Linux) with no extra setup. **These short
names are your `fleet` config values** (`DEVBOOST_BRAIN`, `DEVBOOST_BUILDER`,
`DEVBOOST_EDGE`) — memorable, no certificates to manage.

For HTTPS on a device (a real cert, no open ports), use:

```bash
fleet expose <port>          # tailscale serve --https=443 localhost:<port> — tailnet-only
fleet expose <port> --pub    # tailscale funnel <port> — publicly reachable (see §8)
```

### Caddy sub-routing — multiple services on one device

When one device needs several named services (not just one port), the brain host's
`caddy` (part of `brain-host`) fronts them by name using `*.localhost` (RFC 6761 —
resolves to `127.0.0.1`) and `tls internal` (a locally-trusted cert, no ACME needed).
The starter ships as a chezmoi-managed dotfile in the repo,
`dotfiles/dot_config/caddy/Caddyfile`:

```caddyfile
app.localhost {
	tls internal
	reverse_proxy localhost:3000
}

aspire.localhost {
	tls internal
	reverse_proxy localhost:18888
}
```

Front it with `fleet expose 443` (or a `tailscale serve`/`funnel` on the relevant
port) to reach `https://app.localhost`-style names from a laptop over the tailnet.

**One gap worth knowing about:** `devboost brain` (via `brain-host`) installs the
`caddy` binary, but does not itself place this starter file — it's chezmoi source,
and chezmoi/dotfiles application lives in the `base`/`shell` profiles, which are
laptop-only (`full`), not part of `server` or `brain-host`. On a server that only
ran `server` + `devboost brain`, get the starter Caddyfile onto the box explicitly —
either `devboost install base shell` on that server (pulls in `chezmoi` +
`chezmoi-repo` + `dotfiles`, applying the whole managed dotfiles set, Caddyfile
included), or copy `dotfiles/dot_config/caddy/Caddyfile` over by hand and point your
`caddy` invocation at it. Then start/reload caddy yourself once the file is in place.

### Vanity/public domains — deferred, opt-in only

Not installed by default; see [§8](#8-deferred--opt-in-recipes).

---

## 7. The mini-server migration

Everything above treats the brain as a **role** layered onto a production server out
of necessity — both current servers run live apps, so there's no expendable box yet.
The moment a dedicated mini-server exists, moving the brain there is deliberately a
**zero-architecture-change** move:

1. `curl … | bash -s -- server` on the new box (or `full`, if it's Fedora and doubles
   as another dev seat).
2. `devboost brain` on the new box — same command, same `brain-host`/`devbrain`
   recipe.
3. Re-point `~/.config/fleet/config` on your laptops: update `DEVBOOST_BRAIN` (and
   `DEVBOOST_BUILDER`, if the new box is also your builder) to the new box's MagicDNS
   name. `DEVBOOST_EDGE` stays pointed at whichever box is actually production.
4. Optionally **drop the sandbox** on the new box — since it's dedicated (no
   production sharing it), you could run herdr/builds as your own user with plain
   `docker buildx` instead of capped rootless podman under `devbrain`. Nothing forces
   this; keeping `devbrain` costs nothing and the same recipe still works identically
   on a dedicated box.
5. Optionally decommission the brain overlay on the old production server
   (`devboost accounts disable devbrain` there, or leave it as a cold standby).

No new profiles, no new modules, no rewritten `fleet` verbs — just re-pointing three
environment variables and choosing whether to keep the sandbox now that sharing a
box with production is no longer a constraint.

---

## 8. Deferred / opt-in recipes

Everything in this section is **not installed by default** by any dev-boost profile.
These are documented, copy-pasteable options for when the shipped defaults (Mosh,
Caddy `tls internal`, `tailscale serve`/`funnel`, the `devbrain` managed-account
sandbox) don't cover what you need.

### Eternal Terminal (`et`)

Evaluated against Mosh and not chosen as the default (Mosh already covers UDP
roaming; herdr already covers scrollback/session persistence, which is `et`'s other
main selling point). If you specifically want `et`'s resume-into-tmux-pane behavior:

```bash
# Debian/Ubuntu
sudo apt-get install -y et

# Fedora
sudo dnf install -y et
```

### portless

A Node-based local-domain/tunnel tool with real agentic-workflow value, deferred
because of its Node ≥ 24 dependency and pre-1.0 churn — not something dev-boost pins
and verifies today. If you want it anyway:

```bash
npm install -g portless
```

Consult portless's own docs for usage; dev-boost does not wire it into any profile
or `fleet` verb.

### cloudflared (public tunnels)

`tailscale funnel` (via `fleet expose <port> --pub`) is the shipped, no-install
default for public exposure. `cloudflared` is a documented alternative if you're
already on Cloudflare or need a public hostname that isn't your tailnet's:

```bash
# Debian/Ubuntu
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo gpg --dearmor -o /usr/share/keyrings/cloudflare-main.gpg
echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt-get update && sudo apt-get install -y cloudflared

cloudflared tunnel login
cloudflared tunnel create brain
cloudflared tunnel route dns brain your-subdomain.example.com
cloudflared tunnel run brain
```

### Vanity / public domains (Caddy DNS-01 ACME)

The shipped Caddy config uses `tls internal` (locally-trusted, tailnet-only certs).
For a real public certificate on your own domain, add a DNS-01 site block instead
(needs your DNS provider's Caddy plugin — not bundled by dev-boost's `caddy`
install, which uses the stock Fedora COPR / Debian apt packages):

```caddyfile
app.example.com {
	reverse_proxy localhost:3000
	# tls { dns <your-provider> <api-token> }   # requires a DNS-plugin Caddy build
}
```

Or use `tailscale funnel` (already shipped, no extra build needed) if a `*.ts.net`
public hostname is enough — see [§6](#6-domains).

### Container-isolation tier

The `devbrain` sandbox today is a capped, unprivileged Linux **user** — real
isolation (can't sudo, can't starve the host, can't read production's files) but not
namespace-level isolation. A stronger tier — rootless-podman namespace isolation for
`devbrain` itself (PID/mount namespaces for interactive herdr sessions,
podman-in-podman for builds) — is a documented future option, not built now: the
complexity (nested rootless podman, namespace-aware herdr sessions) was judged not
worth it yet for the marginal safety gain over a correctly capped, sudo-less user.
If your threat model needs it before dev-boost ships it, look at rootless Podman's
own `--userns` / `--pid=private` machinery as a starting point, layered manually on
top of the existing `devbrain` account.

---

## 9. Troubleshooting

**Mosh doesn't connect, or hangs after connecting.** Mosh's UDP range (60000–61000)
rides the `tailscale0` interface, which `server-firewall` already allows — there are
no extra firewall rules to add on a dev-boost-provisioned server. If it still hangs,
confirm both ends actually see each other over Tailscale first (`tailscale ping
<host>`) before suspecting Mosh itself — most "Mosh is broken" reports are actually
a Tailscale reachability problem underneath.

**`ssh mod-sol` / `mosh devbrain@my-dev` says "unknown host."** MagicDNS resolution
needs the Tailscale app/daemon running on the *client* device too, not just the
server — check `tailscale status` locally, and confirm MagicDNS is enabled for your
tailnet (it's on by default, but can be turned off in the admin console). Falling
back to the full `<name>.<tailnet>.ts.net` form or the tailnet IP rules out a local
resolution issue.

**`ssh`/`mosh` connects but is refused or drops immediately.** Check Tailscale SSH
ACLs in your tailnet's admin console/policy file — Tailscale SSH is ACL-gated
per-user/per-tag, separate from the `ssh_authorized_keys` on the `devbrain` account
itself. A key being correctly seeded on `devbrain` doesn't help if the tailnet ACL
doesn't permit the connection in the first place.

**`fleet ship` fails with a rootless/permission error from podman.** Rootless
multi-arch builds depend on `devbrain` having subuid/subgid ranges allocated
(`/etc/subuid`, `/etc/subgid` — auto-assigned by `useradd` when `devboost brain`
created the account). If they're missing or were stripped by some other tooling,
`podman build` under `devbrain` will fail with namespace/permission errors even
though `podman` itself is installed and on PATH. Also confirm the qemu binfmt
handler registered: `test -e /proc/sys/fs/binfmt_misc/qemu-aarch64` (this is exactly
what `crossarch-build`'s own `verify()` checks) — a partial or failed qemu
registration lets `podman` install cleanly while emulated-arch builds still fail.

**The brain host feels starved, or production got slow after `devboost brain`.**
The `devbrain` caps (`ram`/`cpu`/`disk`/`tasks`) are conservative fixed defaults
(`8G`/`200%`/`50G`/`4096`), not computed from the box's actual headroom — tune them
for the specific host with `devboost accounts edit devbrain`. If you're not sure how
much headroom production needs, err tight and loosen later; a starved `devbrain`
session is an inconvenience, a starved production app is an incident.
