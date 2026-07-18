# Design: an opt-in `remote` profile — Tailscale + GNOME Remote Desktop

**Created**: 2026-07-18
**Status**: Draft — awaiting review
**Scope**: A new opt-in profile plus two new Fedora modules in the spec-014 engine
(`engine/src/devboost/modules/`) and one `profiles.toml` line. No installer / media
changes. Design only — no module code is written here.

## Problem

A dev-boost workstation is a personal box you own, but today it can only be driven from
its own keyboard. The `server` profile already gives a headless VPS a mesh identity
(`tailscale` module — Tailscale SSH over the tailnet), but nothing lets you reach a
**GUI desktop** on a dev-boost *workstation* from another machine, and nothing wires the
workstation into the tailnet at all (the `tailscale` module lives only in `server`).

We want: from anywhere on your tailnet, open a terminal on the workstation (already solved
by Tailscale SSH) **and** open its GNOME desktop, with zero exposure to the LAN or the
public internet, and with the same unattended/degrade-gracefully posture as the rest of
the platform.

## Goal

One opt-in profile — `devboost install remote` — that makes a Fedora workstation reachable
over the tailnet two ways:

- **Terminal**: Tailscale SSH (reuse the existing `tailscale` module verbatim).
- **GUI**: RDP served by GNOME Remote Desktop's **system "Remote Login" daemon**, bound so
  it is reachable over the tailnet interface and **dropped everywhere else** by firewalld.

It must install unattended when the secrets bundle carries RDP credentials, and degrade to
a single printed one-time manual step when it does not — never blocking the install
(mirroring the `tailscale` module's `_secret()` pattern). `remote` is opt-in and is **not**
part of `full`, exactly like `gnome-aesthetics`, `gnome-theme`, `hardware-nvidia`,
`optional-editors`, and `security-cli`.

## Verified mechanics (sources)

Everything below was confirmed **this session** against live tooling/docs, per Constitution
Principle III (pins/behaviour verified from live data, never memory). Items I could **not**
fully verify are collected in "Open items to verify at implementation".

- **Fedora 44 package.** `dnf -C info gnome-remote-desktop` on this box → `gnome-remote-desktop
  50.2-1.fc44` (repo `updates`; `50.0` also present in `fedora`). The one package ships
  **both** daemons — `dnf -C repoquery -l` lists `/usr/lib/systemd/system/gnome-remote-desktop.service`
  and `-configuration.service` **and** the per-user `…/user/gnome-remote-desktop{,-headless,-handover}.service`.
  **No extra package** is needed for Remote Login. (`grdctl` ships in the same package:
  `/usr/bin/grdctl`.)
- **`grdctl` supports a system daemon.** `grdctl --help` on this box lists the global option
  `--system  — Configure system daemon for remote login` (and `--headless — … user session`),
  plus the `rdp` subcommands `enable`, `set-credentials [<username> [<password>]]`,
  `set-tls-cert <path>`, `set-tls-key <path>`, `set-auth-methods`, and `status [--show-credentials]`.
- **Remote Login command sequence.** GNOME's `gnome-remote-desktop` README (raw
  `…/-/raw/master/README.md`) gives the exact system-daemon recipe:
  ```sh
  grdctl --system rdp set-tls-key  ~gnome-remote-desktop/.local/share/gnome-remote-desktop/tls.key
  grdctl --system rdp set-tls-cert ~gnome-remote-desktop/.local/share/gnome-remote-desktop/tls.crt
  grdctl --system rdp set-credentials
  grdctl --system rdp enable
  systemctl enable --now gnome-remote-desktop.service
  ```
  and states `--system` "integrat[es] with GNOME Display Manager (GDM)" so a remote user
  "first authenticat[es] via a system wide password, which gives access to the graphical
  login screen" — i.e. a **fresh** GDM session, not a mirror of a local one.
- **firewalld trusted zone.** firewalld.org (predefined-zones) defines `trusted` as *"All
  network connections are accepted."* `man firewall-cmd` on this box confirms the syntax
  `[--permanent] [--zone=zone] --add-interface=interface` and `--query-interface=interface`
  and `--reload`. `firewall-cmd` is present at `/usr/bin/firewall-cmd`; firewalld is the
  Fedora default host firewall (contrast Ubuntu's `ufw`, which the `server` profile uses).

## Non-goals (each stated so it is not smuggled in)

- **Not implementing the modules.** This is the design; the two modules, their tests, and
  the `profiles.toml`/`tailscale.profiles` edits land in a separate plan → impl cycle.
- **Not RustDesk / VNC / Sunshine / xrdp.** RDP via `gnome-remote-desktop` is chosen (see
  "Why RDP + Tailscale"); alternatives were considered and rejected there.
- **Not public-internet exposure.** RDP (3389) is never added to the `public` zone; it is
  reachable **only** over `tailscale0`.
- **Not Ubuntu / aarch64.** Both new modules are Fedora-only (`families = ("fedora",)`) and
  raise `UnsupportedOS` elsewhere — the reference-first seam approach (Constitution VI). The
  reused `tailscale` module is already cross-family; only the Fedora bits are new.
- **Not changing the `server` profile's firewall.** `server-firewall` stays `ufw` on
  Debian; the tailnet-trusting step here is a distinct Fedora/firewalld module.

## Decisions

### Why RDP + Tailscale (over VNC / RustDesk / Sunshine / xrdp)

RDP through `gnome-remote-desktop` is the GNOME-native, packaged-in-Fedora path — one dnf
package, a first-party CLI (`grdctl`), first-party systemd units, and a GNOME-blessed GDM
integration. It needs no third-party relay, no account, and no COPR. Tailscale supplies the
transport and identity (already in the platform and already provisioned by the `age`
bundle), so the RDP listener never has to face the LAN or internet. VNC is unencrypted by
default and lower-fidelity; RustDesk/Sunshine add a third-party relay/account and are
game-streaming/support-desk shaped, not "reach my workstation"; xrdp is a separate stack
that fights GNOME/Wayland. Reachability is solved by the tailnet, not by exposing a port —
so the fancy NAT-traversal features of the alternatives buy us nothing.

### GNOME RDP mode: **system "Remote Login" (`grdctl --system`)**, not Desktop Sharing

`gnome-remote-desktop` offers two shapes:

- **Desktop Sharing** (per-user daemon; `grdctl` with no flag, or `--headless`): shares/
  mirrors the user's **already-active** session, or spawns a headless one *for a logged-in
  user*. Credentials are a dedicated RDP username/password stored per-user.
- **Remote Login** (system daemon; `grdctl --system` + `gnome-remote-desktop.service`):
  the machine-level daemon integrates with GDM and starts a **fresh** graphical session via
  PAM when a remote client connects — no one needs to be sitting at the physical console.

**Recommendation: Remote Login.** A dev-boost workstation reached remotely will usually have
**nobody logged in at the console** (it may have just booted, or sit locked). Desktop Sharing
has nothing to share in that state; Remote Login presents GDM and creates a session on
demand. It is also the mode the GNOME README documents for unattended/headless use, and its
units (`gnome-remote-desktop.service`) are exactly what we enable at install. The cost is
that it needs a TLS cert provisioned up front (Settings would auto-generate one; the CLI
does not) — handled below.

Alternative rejected: Desktop Sharing / `--headless` per-user daemon — simpler credential
story, but requires an active/logged-in user session to exist, which defeats "reach the box
when nobody's home".

### RDP credentials: from secrets, degrade to a printed one-time step

The system daemon has its own credential store (`grdctl --system rdp set-credentials
[<username> [<password>]]` — verified in `--help`). The module reads them **optionally** from
the `age` bundle via the same `_secret()` shape the `tailscale`/`restic-b2` modules use:

- `DEVBOOST_RDP_USER` — optional; **defaults to the invoking login user** (`_current_user()`,
  as `server.py` already computes) when only a password is supplied.
- `DEVBOOST_RDP_PASSWORD` — the RDP password.

Behaviour:

- **Both present (or password + default user)** → `grdctl --system rdp set-credentials <user>
  <pass>` runs; RDP is fully unattended.
- **Absent** → install still completes: it enables the daemon and prints one clear next step
  (`sudo grdctl --system rdp set-credentials <user> <pass>`), never blocking. This is the
  identical degrade path to `tailscale` ("run `sudo tailscale up --ssh` once").

Rationale: Constitution IV (unattended by default, credentials pre-provisioned, never
prompted mid-run) with the platform's established "missing secret → warn, don't fail" rule.
We do **not** touch the user's *system* password (no `chpasswd`): the RDP credential is the
daemon's own, so provisioning it can't lock anyone out of their Linux account.

> The RDP credential authenticates the RDP connection to the system daemon, which then hands
> off to GDM. The **exact** end-to-end auth chain (whether GDM re-prompts for the PAM
> password after the RDP credential, on 50.2 specifically) is an "open item to verify" — but
> it does not change the provisioning design: we set the daemon credential from secrets and
> print the manual fallback either way.

### TLS certificate: generate a self-signed cert at install; point `grdctl` at it

The RDP backend requires a TLS cert+key; the `grdctl` CLI (unlike the Settings toggle) does
**not** auto-generate one. The module generates a self-signed cert **only if absent**
(idempotent) into the system daemon's data dir and registers it:

```sh
openssl req -x509 -newkey rsa:4096 -nodes -days 3650 \
    -subj "/CN=$(hostname)" \
    -keyout <datadir>/tls.key -out <datadir>/tls.crt
grdctl --system rdp set-tls-key  <datadir>/tls.key
grdctl --system rdp set-tls-cert <datadir>/tls.crt
```

where `<datadir>` is the gnome-remote-desktop **system user's** data dir
(`~gnome-remote-desktop/.local/share/gnome-remote-desktop/`, per the README). The cert/key
must be owned by / readable by that system user (exact uid + mode is an open item). A
self-signed cert is correct here: the client already trusts the endpoint by virtue of
reaching it over the authenticated tailnet, so a CA-issued cert adds nothing. RDP clients
show a first-connect fingerprint prompt (GNOME Connections included) — a one-time accept.

### Firewall: trust `tailscale0`, touch nothing on `public` — as its **own** module

The exposure control is: put `tailscale0` in firewalld's `trusted` zone so tailnet traffic
(RDP **and** SSH) is accepted, and leave the `public`/default zone untouched so 3389 is
dropped on every other NIC. The daemon may bind `0.0.0.0:3389`, but firewalld's default zone
drops inbound 3389, so it is reachable **only** over the tailnet.

```sh
firewall-cmd --permanent --zone=trusted --add-interface=tailscale0
firewall-cmd --reload
```

**This is a separate module, `tailscale-firewalld`, not folded into
`gnome-remote-desktop`.** Rationale (one module = one responsibility):

- Trusting `tailscale0` is a **Tailscale/host-network** concern, not an RDP one — it also
  governs Tailscale SSH and anything else on the tailnet. It is the firewalld analogue of
  what `server-firewall` does on Debian with `ufw allow in on tailscale0`.
- It must **not** live in the reused `tailscale` module: that module is cross-family and must
  stay free of firewalld (Fedora-only) logic — `server-firewall` deliberately keeps the ufw
  logic out of `tailscale` for the same reason.
- Keeping it out of `gnome-remote-desktop` lets the RDP module be purely about `grdctl`, and
  lets the firewall step be verified/re-run independently.

Alternative rejected: fold the zone step into `gnome-remote-desktop` — conflates two
responsibilities and would re-trust the interface every time RDP is reconfigured, and would
wrongly imply the trust is RDP-specific.

Guard: `tailscale-firewalld.install` no-ops cleanly if firewalld isn't running (`firewall-cmd
--state`), and is Fedora-only (`UnsupportedOS` elsewhere). We add the interface **explicitly**
rather than relying on Tailscale's installer to do it (see open items) — the explicit step is
idempotent and self-documenting.

### Module + profile shape

Reuse `tailscale`; add two Fedora modules; compose one profile.

**Reused — `tailscale`** (`engine/src/devboost/modules/server.py`, unchanged logic): its
`profiles` tuple gains `"remote"` → `profiles = ("server", "remote")`. A module may belong to
multiple profiles; `registry.validate_profiles` requires every declared profile to exist in
`profiles.toml`, so the `remote` key must be added in the same change.

**New — `gnome-remote-desktop`** (new file, e.g. `modules/remote_desktop.py`):

```
name        = "gnome-remote-desktop"
category    = "remote"
description = "GNOME Remote Desktop RDP (system Remote Login), reachable over the tailnet."
gui         = True
families    = ("fedora",)
profiles    = ("remote",)
# No hard `requires = (Secrets,)`: RDP creds are read OPTIONALLY and degrade (as tailscale).
```

**New — `tailscale-firewalld`** (same new file — both are "remote" category):

```
name        = "tailscale-firewalld"
category    = "remote"
description = "Trust the tailscale0 interface in firewalld (tailnet accepted; LAN/public dropped)."
families    = ("fedora",)
profiles    = ("remote",)
```

**`profiles.toml`** — a new opt-in line, alongside the other opt-in profiles, and **absent
from `full`**:

```toml
remote = ["tailscale","tailscale-firewalld","gnome-remote-desktop"]
```

`full` is unchanged (it already excludes the opt-in set). `remote` is a peer of
`gnome-aesthetics` / `gnome-theme` / `hardware-nvidia` / `optional-editors` / `security-cli`.

### `verify()` / `install()` sketches (describe, not implement)

**`gnome-remote-desktop`**

- `verify(ctx)` → Fedora **and** `systemd.is_enabled(ctx, "gnome-remote-desktop.service")`
  **and** RDP shown enabled in `grdctl --system status` (run `sudo`, since the system daemon's
  config is root-owned). Exact status-string match is an open item; the intent is "system RDP
  backend is enabled".
- `install(ctx)`:
  1. non-Fedora → `raise UnsupportedOS(...)`.
  2. `pkg.install(ctx, "gnome-remote-desktop")`.
  3. TLS: if the cert/key are absent, `openssl req -x509 …` into the system daemon's data dir;
     `grdctl --system rdp set-tls-key <key>` then `set-tls-cert <cert>` (both `sudo`).
  4. Credentials: `user = DEVBOOST_RDP_USER or _current_user()`,
     `pw = _secret(ctx, "DEVBOOST_RDP_PASSWORD")`. If `pw` →
     `grdctl --system rdp set-credentials <user> <pw>` (`sudo`); else `log.warn(...)` with the
     one-time manual command.
  5. `grdctl --system rdp enable` (`sudo`).
  6. `systemd.enable_system_unit(ctx, "gnome-remote-desktop.service", now=True)`.

**`tailscale-firewalld`**

- `verify(ctx)` → Fedora **and** `firewall-cmd --zone=trusted --query-interface=tailscale0`
  reports bound (exit 0 / "yes").
- `install(ctx)`:
  1. non-Fedora → `raise UnsupportedOS(...)`.
  2. if `firewall-cmd --state` is not running → `log.warn` and return (nothing to trust yet).
  3. `firewall-cmd --permanent --zone=trusted --add-interface=tailscale0` (`sudo`).
  4. `firewall-cmd --reload` (`sudo`).

All external commands run as argv lists through `ctx.ex.run` (Constitution: injected executor,
no shell strings) — the one exception is the existing `tailscale` module's documented
`curl|sh` escape hatch, which we do not touch.

## Data flow

```
devboost install remote
        │  profiles.expand(["remote"])  →  [tailscale, tailscale-firewalld, gnome-remote-desktop]
        │  graph.toposort(...)          →  deterministic order (no inter-deps declared here)
        ▼
tailscale.install
    curl|sh installer; `tailscale up --ssh --authkey=<secret>`  (or warn: run it once)
        ▼
tailscale-firewalld.install            (Fedora; firewalld running)
    firewall-cmd --permanent --zone=trusted --add-interface=tailscale0 ; --reload
        ▼
gnome-remote-desktop.install           (Fedora)
    dnf install gnome-remote-desktop
    openssl … tls.{crt,key}  →  grdctl --system rdp set-tls-key/set-tls-cert
    _secret(DEVBOOST_RDP_PASSWORD) present? → grdctl --system rdp set-credentials <user> <pw>
                                     absent? → log.warn(one-time manual step)
    grdctl --system rdp enable
    systemctl enable --now gnome-remote-desktop.service
        ▼
Client (any tailnet node): GNOME Connections / any RDP client → <workstation-magicdns-name>
    (e.g. `dev-laptop.tailnet-xxxx.ts.net`) or its 100.x tailscale IP, port 3389.
    Accept the self-signed cert fingerprint once; authenticate; GDM starts a fresh session.
    Reachable ONLY over tailscale0 — dropped on the LAN/public zone.
```

## Errors

| Condition | Behaviour |
|---|---|
| Non-Fedora target (either new module) | `raise UnsupportedOS(...)` naming the module + detected distro (mirrors `snapper`/`grub-btrfs`). |
| No `age` bundle / no `DEVBOOST_RDP_PASSWORD` | `_secret()` → `None`; install completes, prints one-time `grdctl --system rdp set-credentials` step. Never fails. |
| firewalld not running | `tailscale-firewalld` warns and returns (nothing to trust yet); re-run after firewalld is up (idempotent). |
| `dnf install` / `grdctl` non-zero | surfaces as the primitive's `InstallError` / a failed `ctx.ex.run` — names the module + exact command (Constitution II). |

## Testing

Hermetic, no network, no device — `FakeExecutor` asserting argv order (the `test_server.py`
pattern: seed `present=` / `scripts=`, read `ctx.ex.calls`).

**`gnome-remote-desktop`**
1. `install` on Fedora with a fake `_secret` returning `DEVBOOST_RDP_PASSWORD` issues, in
   order: `dnf install -y gnome-remote-desktop`; the `openssl` cert-gen (only when the cert is
   absent); `grdctl --system rdp set-tls-key …`; `set-tls-cert …`; `set-credentials <user>
   <pw>`; `rdp enable`; `systemctl enable --now gnome-remote-desktop.service`.
2. `install` with `_secret` → `None`: **no** `set-credentials` call, a warning is logged, and
   the daemon is still enabled (graceful degrade).
3. `install` re-run with the cert already present does **not** regenerate it (idempotent).
4. `verify` reads `grdctl --system status` + `systemctl is-enabled` (true/false cases).
5. `install` on a non-Fedora `Ctx` raises `UnsupportedOS`.

**`tailscale-firewalld`**
6. `install` on Fedora (firewalld "running") issues `firewall-cmd --permanent --zone=trusted
   --add-interface=tailscale0` then `firewall-cmd --reload`.
7. `install` when `firewall-cmd --state` is not "running" warns and issues **no**
   `--add-interface`.
8. `verify` reads `--query-interface=tailscale0`; non-Fedora raises `UnsupportedOS`.

**profiles / registry**
9. Load `profiles.toml`: `remote` exists and equals `["tailscale","tailscale-firewalld",
   "gnome-remote-desktop"]`.
10. `expand(["remote"], …)` yields exactly those three module names.
11. **Opt-in guard**: `expand(["full"], …)` contains **none** of `tailscale-firewalld` /
    `gnome-remote-desktop`, and `"remote"` is not a token inside `full` — the test that pins
    the mission rule "`full` excludes opt-in profiles" (peer of the nvidia-exclusion tests).
12. `registry.validate_profiles` passes with `tailscale.profiles == ("server","remote")` (the
    reused module's new profile resolves to a real key).

**Gates**: `mypy --strict`, `ruff`, and the full `pytest` suite stay green (Constitution V +
Workflow gates).

## Acceptance

- On a Fedora workstation, `devboost install remote` installs `tailscale`,
  `tailscale-firewalld`, and `gnome-remote-desktop`; with `DEVBOOST_RDP_PASSWORD` in the
  bundle it completes **unattended**.
- From another tailnet node, **GNOME Connections** (or any RDP client) connects to the
  workstation's MagicDNS name / 100.x IP on 3389, accepts the self-signed fingerprint once,
  authenticates, and lands in a fresh GNOME session.
- The RDP port is **not** reachable from the LAN or public internet (verified: 3389 refused on
  a non-tailnet address; accepted over `tailscale0`).
- Terminal access is unchanged Tailscale SSH.
- With **no** secrets bundle, install still completes and prints the one-time `grdctl --system
  rdp set-credentials` step; nothing blocks.
- `remote` never appears in a `full` install.
- `mypy --strict`, `ruff`, `pytest` green.

## Open items to verify at implementation (could not fully confirm live this session)

1. **Tailscale's own firewalld behaviour.** Tailscale's Linux daemon is reported to add
   `tailscale0` to the `trusted` zone automatically when firewalld is present, but the source
   page I tried 404'd this session — **unverified**. The design does the step **explicitly and
   idempotently** regardless, so correctness does not depend on the auto-behaviour; confirm at
   impl whether our `--add-interface` is a duplicate no-op or the only actor.
2. **Exact `--system` auth chain on 50.2.** Commands (`set-credentials`, `enable`, the system
   unit) are verified from `grdctl --help` and the GNOME README; a **live RDP handshake**
   (does GDM re-prompt for the PAM password after the RDP credential? does `set-credentials`
   gate the connection or only pre-fill?) was **not** exercised. Verify against a real client
   during impl; the credential-provisioning design is unaffected either way.
3. **TLS cert ownership/mode + system-user home path.** The `~gnome-remote-desktop/.local/
   share/gnome-remote-desktop/` path is from the README; the exact uid, home, and required
   file mode for the `gnome-remote-desktop` system user must be confirmed (`getent passwd
   gnome-remote-desktop`) so the cert is readable by the daemon.
4. **Daemon bind address.** Assumed `0.0.0.0:3389` (dropped on `public`, accepted on trusted
   `tailscale0`). Confirm the system daemon's listen address on 50.2; if it can be bound to a
   specific interface, that is a defence-in-depth follow-up but not required for the posture.
5. **`grdctl --system status` output string.** Confirm the exact text `verify()` should match
   for "RDP backend enabled" on 50.2 (the CLI help documents the command, not its output).
