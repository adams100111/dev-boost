# dev-boost — remote fleet dev workflow (tailnet · mosh · brain-in-a-sandbox)

**Status:** Design approved (grilled) — ready for implementation planning
**Date:** 2026-07-22
**Author:** dits.sa.co@gmail.com

---

## 1. Goal

Make dev-boost provision a **fleet** — laptops + always-on Linux servers — that behaves like
one machine for agentic development: sit at any laptop (or your phone), attach a persistent
multi-agent session running on a server, and drive develop / build / orchestrate from one set
of verbs. Connectivity is private (Tailscale), interactive sessions survive roaming and sleep
(Mosh + herdr), and the dev/agent/build workload is **sandboxed** (a capped, sudo-less user)
so it can share a box with **production apps** without threatening them.

Reference fleet this design is validated against:

| Box | Arch | Nature | Role |
|-----|------|--------|------|
| `mate-dev`, `hp-dev` | — | Fedora laptops | dev seats (interchangeable thin clients) |
| `mod-sol` | x86_64 | **production server** (real apps) | also the x86 build/brain host |
| `my-dev` | arm64 | **production server** (real apps) | also an optional brain |

**Premises that shaped the design (from the design review):**
1. **There is no expendable box.** Both servers run live apps 24/7, so any brain/build
   capability on a server is an **opt-in, isolated overlay**, never a default. Passwordless
   sudo never goes near a server.
2. **The brain is a role, not a machine.** Selected by env (`DEVBOOST_BRAIN` /
   `DEVBOOST_BUILDER`). A future dedicated mini-server must be a **zero-architecture-change**
   move — install the same profiles, re-point one env var. The prod-sharing constraint is
   temporary and must not distort the architecture.
3. **Reuse existing engine infrastructure.** The `accounts` subsystem already provides
   capped, privilege-tiered, self-bootstrapping users — so the sandbox is a *managed account*,
   not a bespoke module.

### Non-goals
- No new laptop/server rewrite. `full` (Fedora workstation) and `server` (prod host) stay;
  this adds a connectivity spine, an opt-in brain overlay, and a DX layer.
- No orchestration daemon or control plane. The "fleet" is thin shell verbs over Tailscale +
  Mosh + herdr + podman.
- No managed-service dependency to function (no ngrok/Cloudflare account required).
- Not a mobile client — the phone side (Tailscale app + Blink/Termux, or herdr's own client)
  is the operator's choice, out of provisioning scope.

---

## 2. Layered model (why each tool, what it is NOT)

Three connectivity layers, each solving a different failure mode. Placing them correctly is
the whole design:

| Layer | Job | Tool | Not this |
|-------|-----|------|----------|
| **Reachability + auth** | private road to the box, keyless, ACL'd | **Tailscale (SSH)** — already shipped | but it's still a TCP session that dies on sleep/roam |
| **Resilient transport** | session survives sleep, Wi-Fi→cellular, IP change; lag-free typing | **Mosh** (UDP roaming) | not the work-preservation layer |
| **Persistent session** | panes + running agents survive independent of any client | **herdr / tmux** — already shipped | — |

**Honest calibration:** once you always work inside herdr on the server, Mosh is not
load-bearing *for your data* (reconnect over Tailscale SSH + `herdr attach` and nothing was
lost). Mosh's real value is **UX under motion** — no manual reconnect after sleep/roam, and
instant typing on cellular/phone. It's a featherweight distro package that directly serves the
mobile/roaming reality, so it earns a spot in the spine; but herdr is the safety layer.

### HTTPS in front of dev servers — "domain per device"
Covered in three tiers, no new architecture required:
1. **Per-device domain — free, automatic:** Tailscale **MagicDNS** gives every box a stable
   *short* name (`mod-sol`, `my-dev`) usable directly (`ssh mod-sol`, `mosh my-dev`,
   `https://mod-sol.<tailnet>.ts.net`). Works on every device with the Tailscale app
   (iOS/macOS/Windows/Android/Linux). `tailscale serve` adds HTTPS on that name (real cert,
   no open ports). **This is the default story** — short names *are* your hostnames; memorable.
2. **Per-service subdomains on a device:** **Caddy** (`*.localhost` + `tls internal`), fronted
   by `tailscale serve` to reach from a laptop. The multi-site case Caddy earns its keep for.
3. **Custom/vanity public domain per device:** **documented opt-in recipe** only
   (Caddy DNS-01 ACME or `tailscale funnel`). Needed solely for a device you can't put on the
   tailnet, or an external webhook — not for reaching your own devices.

### Evaluated alternatives (verdicts)
- **Mosh vs Eternal Terminal** → Mosh default (UDP roaming; scrollback covered by herdr).
  `et` **deferred** to a documented recipe.
- **portless vs localias vs Caddy** → localias dropped (Caddy-with-sugar); **Caddy** is the
  foundation and covers static named-HTTPS via a dotfiles `Caddyfile`; **portless deferred**
  (real agentic value but Node-24 dep + pre-1.0 churn).
- **Public exposure: funnel vs cloudflared** → `tailscale funnel` is the free default (a
  `fleet` verb, no install). **cloudflared deferred** to a recipe. The `edge` profile is
  dropped entirely.
- **Sandbox: managed account vs bespoke module vs container** → **managed account** (§4). The
  container-isolation tier is a **documented future seam**, not built now.

---

## 3. Profile structure

Leaf profiles hold modules; `full` aggregates leaf profiles. Changes:

| Profile | Kind | Contents | Applied to |
|---------|------|----------|------------|
| **`remote`** *(new leaf)* | connectivity spine | `tailscale`, `mosh` | included by `full` (laptops) |
| **`full`** *(changed)* | laptop aggregate | add `remote` | `mate-dev`, `hp-dev` |
| **`server`** *(changed)* | prod host baseline | `tailscale`, `server-firewall`, `zram`, `restic-b2`, `tmux-persist`, `docker`, `docker-build-gc` — **`agent-sudo` removed** | `mod-sol`, `my-dev` |
| **`brain-host`** *(new leaf, opt-in)* | sudo host tools for the brain | `mosh`, `caddy`, `crossarch-build` | the server chosen to host the brain |
| **`brain-tools`** *(new leaf, opt-in)* | demoted user-level brain tools | `herdr`, `herdr-plugins` | `devbrain`'s `bootstrap_profiles` |

**Behavior change:** `agent-sudo` leaves the default `server` profile (passwordless sudo on a
prod host is the footgun this design isolates against). The `AgentSudo` module is unchanged
and becomes `profiles = ()` — installed only on purpose (`devboost install agent-sudo`), for
expendable boxes. Changelog-noted.

Profile names (`remote`, `brain-host`, `brain-tools`) are checked to differ from every module
name. `validate_profiles` stays green.

The fleet install shapes:
```
laptop  $  curl … | bash -s -- full        # joins tailnet + Mosh
server  $  curl … | bash -s -- server       # prod baseline, hardened, NO agent-sudo
brain   $  devboost brain                    # opt-in overlay on a chosen server (§5)
```

---

## 4. The sandbox = a `devbrain` managed account (no new module)

The `accounts` subsystem (`devboost accounts` + `users.toml` + `reconcile.apply_user` +
`bootstrap_user` via `DemotingExecutor`) already provides everything the sandbox needs, tested:
non-sudo privilege tier, cgroup slice caps (`ram`/`cpu`/`tasks`), disk quota, linger, and
**demoted bootstrap of profiles into the user's home**. So the sandbox is a managed account:

```toml
[users.devbrain]
privilege = "none"          # cannot sudo — removes admin group, no sudoers. The safety core.
ram   = "8G"                # cgroup slice cap on user-<uid>.slice — can't starve prod
cpu   = "200%"
tasks = 4096
disk  = "50G"
linger = true               # herdr / mosh-server persist without an active login
ssh_authorized_keys = [ "<mate-dev key>", "<hp-dev key>" ]   # so `mosh devbrain@brain` works
bootstrap_profiles = ["brain-tools"]                          # herdr etc., installed AS devbrain
```

**Why this and not a bespoke `agent-sandbox` module:** reuses tested infrastructure (privilege
tiers, cgroup caps, quota, demoted bootstrap) instead of reimplementing user creation +
slices; it *is* the engine's committed model.

**Isolation the account already gives:** can't sudo; capped CPU/mem/disk/tasks (can't starve
prod); and — because prod runs as its *own* user with normal perms — `devbrain` can't read
prod's files anyway. That covers "don't crash prod." A stronger **container tier** (rootless-
podman namespace isolation) is a **documented future overlay**, addable without changing this
model; deliberately not built now (high complexity — PID/mount namespaces for interactive
herdr, podman-in-podman for builds — for a modest marginal gain over correctly-permissioned
users).

**Brain is a portable role:** on a future *dedicated* mini-server you install the same
`brain-host` profile and either keep `devbrain` or run the brain as your own user — the profile
doesn't know whether it's wrapped. Zero architecture change.

---

## 5. New modules (Fedora reference impl; per-OS seams)

One typed file each, `@register`, `mypy --strict` clean, hermetic `Executor` tests. Secret-
reading uses the existing `_secret(ctx, field)` graceful pattern. OS-specific installs gate on
`ctx.os.family`/`distro` and `raise UnsupportedOS` (or stub) for unimplemented OSes.

### 5.1 `mosh` — resilient transport → `remote`, `brain-host`
- `install()`: `pkg.install(ctx, "mosh")` — the single package ships **both** client and
  `mosh-server`; per-OS is the existing `pkg` seam (dnf/apt).
- `verify()`: `ctx.ex.which("mosh")`.
- No config. UDP 60000–61000 rides `tailscale0`, already allowed by `server-firewall` —
  **zero new firewall rules** (documented).
- `profiles = ("remote", "brain-host")`.

### 5.2 `caddy` — locally-trusted reverse proxy (`tls internal`) → `brain-host`
- `install()`: per-OS — Fedora via the Caddy COPR / official RPM repo (`pkg.add_repo` with a
  `DnfRepo`); Debian via Caddy's apt repo (`AptRepo`). Fedora is the reference impl.
- Ships a **starter `Caddyfile` as a chezmoi source** under `dotfiles/` (version-controlled,
  restored like the wezterm/starship configs), e.g. `app.localhost { tls internal;
  reverse_proxy localhost:3000 }`. Default install places binary + starter config; the systemd
  service is started only once the operator populates the Caddyfile.
- `verify()`: `ctx.ex.which("caddy")`.
- Rationale it stays default (not opt-in): featherweight (single Go binary, ~15–40 MB idle),
  and always-present multi-site local HTTPS is a genuine convenience. `profiles = ("brain-host",)`.

### 5.3 `crossarch-build` — capped rootless multi-arch builds → `brain-host`
Single module provisioning "capped rootless multi-arch builds":
- Installs **`podman`** (daemonless, first-class rootless) — coexists with the existing
  docker-ce (only the `podman-docker` *CLI shim* conflicts, and `docker.py` already removes
  it). Ensures `devbrain`'s subuid/subgid ranges (auto-allocated by `useradd`).
- Registers **`qemu-user-static` / binfmt** system-wide (host, one-time sudo) so rootless
  `podman build --platform linux/amd64,linux/arm64 --manifest … && podman manifest push`
  works, run **as capped `devbrain`** (no docker group → no root → sandbox intact).
- **Why podman not `docker buildx`:** buildx runs on the host docker daemon whose `docker`
  group is root-equivalent — giving `devbrain` that would break the non-sudo isolation, and
  host builds are uncapped (starve prod). Rootless podman under `devbrain`'s slice is the only
  path that is *both* capped *and* unprivileged. On a future dedicated box, plain `docker
  buildx` (already installed via `base`) is the free, simpler path — no sandbox needed.
- `verify()`: `podman` present; `binfmt` shows the arm64 handler.
- `profiles = ("brain-host",)`.

### 5.4 `herdr` / `herdr-plugins` — reused (already shipped) → `brain-tools`
Add `"brain-tools"` to their `profiles`. Both install user-level (herdr → `~/.local/bin` via
`install -Dm755`; plugins via `herdr plugin install`) — so they run correctly in `devbrain`'s
**demoted** bootstrap (no sudo). herdr config ships as a chezmoi dotfile applied in the
bootstrap.

---

## 6. The `devboost brain` wrapper (thin CLI)

A thin new subcommand orchestrating two *existing* operations with `devbrain` defaults:
1. `install brain-host` (sudo host tools: mosh, caddy, crossarch-build) — via the existing
   `_run(["brain-host"])`.
2. `accounts create devbrain --privilege none --ram … --cpu … --disk … --tasks … --linger
   --with-profile brain-tools` (+ seed `ssh_authorized_keys` from the operator's laptop keys)
   — via the existing accounts path, which itself runs the demoted `brain-tools` bootstrap.

Design points:
- **Default caps:** sane fixed defaults (`ram=8G`, `cpu=200%`, `disk=50G`, `tasks=4096`),
  overridable via pass-through flags; prints a **"review devbrain caps for this box"** note
  (right caps depend on prod headroom). No auto-computed fractions (fragile).
- **Idempotent:** re-running converges (apply/adopt path), never errors if `devbrain` exists.
- **`authorized_keys`:** seeded so `fleet dev` can `mosh devbrain@$DEVBOOST_BRAIN`.

---

## 7. The `fleet` DX layer (chezmoi dotfiles — no new binary)

A `fleet` **dispatcher** shipped as a chezmoi-managed shell file (sourced by `bash-config`, in
the `shell` profile — it's typed from the *laptop*). Bare one-word aliases (`dev`, `ship`, …)
ship **commented-out** in the same file for opt-in. Hosts come from a sourced
`~/.config/fleet/config` (`DEVBOOST_BRAIN` / `DEVBOOST_BUILDER` / `DEVBOOST_EDGE`), with
commented defaults; each verb errors cleanly if its var is unset.

| Verb | Does |
|------|------|
| `fleet dev` | `mosh devbrain@$DEVBOOST_BRAIN` + attach `herdr` (the develop/orchestrate seat) |
| `fleet ship <img>` | on `$DEVBOOST_BUILDER` as devbrain: `podman build --platform linux/amd64,linux/arm64 --manifest <img> && podman manifest push` |
| `fleet expose <port>` | `tailscale serve` (tailnet); `--pub` → `tailscale funnel` |
| `fleet edge` | `ssh $DEVBOOST_EDGE` (pull latest image / check prod) |
| `fleet status` | herdr agent snapshot — working / blocked / done |

Intended DX: **develop** from a laptop via VS Code Remote-SSH into the sandbox; **orchestrate**
from the other laptop via `fleet dev` (same herdr session — observe/control makes both laptops
multiplayer); **build** via `fleet ship` (capped rootless podman on the x86 server); **edge**
to the public-facing server. One source of truth (the sandbox), identical shell everywhere
(chezmoi), MagicDNS short names for reachability.

---

## 8. Per-OS strategy & pinning

- **Fedora is the reference implementation** for every new module. Debian/Ubuntu seams present
  where servers run there (`mosh`, `caddy`, `crossarch-build`/podman), gating on
  `ctx.os.family` with `raise UnsupportedOS` for unimplemented paths.
- **Repo-managed tools** (`mosh`, `caddy`, `podman`, `qemu-user-static`) install via the
  package manager like `docker`/`ufw` — not SHA-pinned, consistent with precedent.

---

## 9. Testing (merge gates: `mypy --strict`, ruff, pytest)

Hermetic, injected-`Executor`, no network:
- **Per module** — install command sequence (`pkg.install` / per-OS branch / `add_repo`),
  `verify()` true/false, secret-absent graceful degradation.
- **`crossarch-build`** — podman install (+ coexistence with docker), binfmt registration, and
  the multi-arch `--platform … --manifest` invocation shape.
- **`devbrain` account** — a config test that the recipe yields `privilege="none"` + caps; an
  `accounts` reconcile test that a `privilege=none` user gets **no** sudoers drop-in.
- **`devboost brain` wrapper** — orchestrates `brain-host` install then `accounts create
  devbrain` with the right presets; idempotent on re-run.
- **Profiles** — `validate_profiles` green with `remote`/`brain-host`/`brain-tools`;
  `expand("full")` now includes `tailscale`+`mosh`; `expand("server")` **no longer** includes
  `agent-sudo`.
- **`fleet` verbs** — shell-level: each verb errors cleanly when its host var is unset, and
  emits the expected wrapped command when set.
- **Regression** — existing `server`/`system`/`base` profile + `AgentSudo` tests updated for
  the `agent-sudo` removal and the `remote` leaf.

---

## 10. Documentation (a first-class, comprehensive deliverable)

Docs are treated as a real deliverable, not an afterthought — updated per milestone (each
milestone ships its own doc slice) with a dedicated operator guide as the capstone.

### 10.1 Standalone operator guide — `docs/remote-fleet.md` *(new, the capstone)*
The full narrative an operator needs to run a fleet, structured as:
- **Concept & topology** — the layered model (Tailscale → Mosh → herdr), the four-box
  reference fleet, and the "brain is a role, not a machine" premise.
- **Per-role setup** — the exact `curl … | bash -s -- <profile>` per box (laptop `full`,
  server `server`), then `devboost brain` on the chosen brain host; what each installs; the
  secrets each needs (`TAILSCALE_AUTHKEY`, B2, optional Telegram).
- **The `devbrain` sandbox** — what it is (capped, sudo-less managed account), how to review/
  tune its caps for a prod box, and how to reach it (`fleet dev` / `mosh devbrain@brain`).
- **Daily DX flow** — VS Code Remote-SSH to develop, `fleet dev` to orchestrate, herdr
  multiplayer (observe/control), `fleet ship` for capped cross-arch builds, MagicDNS names.
- **Domains** — MagicDNS short names (default), Caddy sub-routing, `tailscale serve`.
- **The mini-server migration** — how a future dedicated box is a zero-change move (install
  `brain-host`, re-point `DEVBOOST_BRAIN`, optionally drop the sandbox / use docker buildx).
- **Deferred / opt-in recipes** — copy-pasteable: Eternal Terminal, portless, cloudflared,
  vanity/public domains (Caddy DNS-01 ACME / `tailscale funnel`), and the future
  container-isolation tier — each clearly marked "not installed by default."
- **Troubleshooting** — mosh UDP over `tailscale0`, MagicDNS resolution, Tailscale SSH ACLs,
  rootless-podman subuid/subgid, cap tuning.

### 10.2 `README.md`
- Regenerate the profiles table (`scripts/gen_profiles_table.py`) for the new
  `remote`/`brain-host`/`brain-tools` rows.
- Add a concise **"Remote fleet"** section (the four-box story + the `fleet` verbs) that links
  out to `docs/remote-fleet.md` for the full guide.
- Note the `agent-sudo`-removed-from-`server` **behavior change** in the changelog/notes.

### 10.3 `docs/roadmap.md`
- Move the remote-fleet workflow to "Shipped," with the deferred items listed as follow-ups.

### 10.4 In-code docs
- Each new module (`mosh`, `caddy`, `crossarch-build`) carries a module docstring in the house
  style (what/why/per-OS notes), matching `server.py`/`docker.py`.
- The `devbrain` `users.toml` example is documented inline where the accounts recipe lives.

### 10.5 `CLAUDE.md` (project mission)
- A one-line pointer under the mission/active-plan section noting the remote-fleet capability
  and its guide, so the fleet story is discoverable from the repo's entry doc.

### 10.6 This design doc
- Committed under `docs/superpowers/specs/`.

---

## 11. Milestones (for the plan phase)

- **M1 — tailnet reach:** `remote` leaf + `mosh` module + `full` includes `remote`. Laptops
  join the tailnet and get Mosh. *Independently shippable, smallest, highest value.*
- **M2 — brain overlay:** `caddy` + `crossarch-build` modules, `brain-host`/`brain-tools`
  profiles, `devbrain` account recipe, `devboost brain` wrapper; `agent-sudo` removed from
  `server`; `herdr`/`herdr-plugins` gain `brain-tools`.
- **M3 — DX + comprehensive docs:** `fleet` dispatcher + `~/.config/fleet/config`, Caddy
  starter `Caddyfile`, and the full documentation set (§10): the standalone
  `docs/remote-fleet.md` operator guide, README "Remote fleet" section + profiles-table regen,
  roadmap move, in-code module docstrings, `CLAUDE.md` pointer, and the deferred-recipe docs.

Each of M1/M2 also updates its own doc slice (README rows + roadmap) as it lands, so docs never
lag the code; M3 adds the capstone operator guide and ties the story together.

---

## 12. Decisions resolved during design + grill

- Delivery → **curl direct**, no USB.
- Sandbox → **`devbrain` managed account** (accounts subsystem), not a bespoke module;
  container tier = **future seam**.
- Brain tooling **splits host (sudo: mosh/caddy/crossarch-build) vs user (demoted:
  herdr/herdr-plugins)** because a `privilege=none` bootstrap can't sudo.
- Brain is a **portable role** (env-selected); prod-sharing is temporary → **no architecture
  distortion**; mini-server = zero-change move.
- Builds → **rootless podman as capped `devbrain`** now; **docker buildx free** on a future
  dedicated box.
- **`caddy` stays default** (featherweight); **`agent-sudo` out of `server`** → opt-in.
- Laptops join via **`remote`** (Tailscale SSH reused + Mosh client).
- Domains → **MagicDNS short names + Caddy sub-routing** default; vanity/public = recipe.
- `fleet` → **dispatcher** (bare aliases opt-in); `devbrain` reachable via `authorized_keys`.
- **Deferred (recipes, not built):** cloudflared, eternal-terminal, portless, container tier,
  vanity domains, `edge` profile.
</content>
