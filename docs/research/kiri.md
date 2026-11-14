# Kiri — evaluation as a Docker runtime and public-link provider

Researched 2026-11-14 against [libracoder/kiri](https://github.com/libracoder/kiri) at
`baa2d41` (v0.2.0, released 2026-11-10), [runkiri.com](https://runkiri.com) and the
project's issue tracker.

**Verdict:** don't adopt Kiri for its public link — `fleet expose` already covers
the VPS → Mac case and does it better. Revisit Kiri as an opt-in, macOS-only
`docker_runtime = "kiri"` once the blockers below are closed.

## What Kiri is

- A Docker Desktop / OrbStack replacement written in Rust, licensed Apache-2.0 (free for
  work use, like Colima).
- On macOS: one small Linux VM with Kiri's own ~10 MB kernel and a ~900 KB Rust agent as
  PID 1. The agent starts containers with `clone3`; there is no dockerd, runc or containerd.
  On Linux the same agent runs on the host kernel and replaces dockerd.
- Speaks the Docker Engine API, so `docker`, Compose and buildx work against a `kiri`
  docker context. Builds go through BuildKit in a Kiri container (buildx's
  docker-container driver).
- Extras: `*.kiri.local` names with HTTPS from a name-constrained CA, `kiri k8s start`
  (single-node k3s), `kiri machine create` (Linux machines with `/Users` mounted), USB
  pass-through (beta), `kiri import` from OrbStack / Docker Desktop, and a native window
  plus menu bar item.
- Claimed speed: ~2.5 ms to start and remove a container through the API, against
  ~213 ms for Docker Desktop and ~380 ms for OrbStack (Kiri's own benchmark,
  `bench/results.json`).
- Maturity: repo created 2026-11-02, labelled beta, about 10 contributors, ~3.2k stars.
- Install: `.dmg` (signed and notarized), `.msi`, `.deb` / `.rpm`. **No Homebrew cask.**
  Kiri updates itself.

## Kiri Share (the public link)

From `crates/kiri/src/share.rs` and `crates/kiri-share-proto`:

| Aspect | Finding |
|---|---|
| Infrastructure | Kiri's hosted service: `edge.runkiri.com:443`, links on `*.runkiri.cloud`. The server isn't in the repo, so it can't be self-hosted. |
| Sign-in | GitHub device flow; the token is stored in `~/.kiri/share.json`. A random device ID is sent "so a ban can follow the machine". |
| Limits | The service sends a speed limit (bytes/s), a monthly data allowance, a reserved-name quota and a quota of live links at once. No pricing is published; "free in beta". |
| Visitors | Browsers see a Kiri warning page on the first visit. |
| Access control | None in the client. Anyone with the URL reaches the service; there's no password or allow-list. |
| Names | `kiri share reserve NAME` asks for `NAME.runkiri.cloud`; a person at Kiri reviews it, usually within a day. Until then shares get a random address. |
| Builds | Only official builds carry the signing key; self-built clients show as "unverified". |
| Strengths | Real HTTPS (phones, webhooks and OAuth callbacks accept it), reconnects on its own, logs each request live, shares from every machine in one list, can share any `host:port`, not just containers. |

CLI: `kiri share PORT | HOST:PORT | CONTAINER [NAME]`, plus `reserve`, `names`,
`release`, `login`, `logout`, `status`, and `--json` for scripts.

### Compared with what dev-boost already has

`docs/remote-fleet.md` §6:

- `fleet expose <port>` runs `tailscale serve`: a real-cert HTTPS URL that only tailnet
  devices can reach. No third party, no data cap, no warning page, and the dev server
  isn't on the public internet.
- `fleet expose <port> --pub` runs Tailscale Funnel when a public link is needed.

For your own devices Kiri Share is worse: the link is public, a third party controls it,
and it has limits and a warning page. Its only real advantage is one-click sharing from
its window to people outside the tailnet.

## Fit as a dev-boost Docker runtime

**What fits**

- On macOS it would plug into the existing `DockerRuntime` interface
  (`engine/src/devboost/modules/_docker_runtime.py`) as a fourth choice next to Colima,
  OrbStack and Docker Desktop (`docs/docker-runtimes.md`).
- The licence is as clean as Colima's, unlike OrbStack and Docker Desktop.
- `kiri setup` sets up the docker context and `/var/run/docker.sock`, and writes
  `~/.testcontainers.properties` when the socket isn't available.

**Blockers**

1. **No daemon config file.** `docker-build-gc` caps the BuildKit cache through
   `merge_daemon_config`; Kiri has no dockerd and builds in a separate BuildKit
   container, so the cap needs another mechanism.
2. **Distribution.** No Homebrew cask, and self-updates clash with the versions pinned
   in `devboost.lock`.
3. **ddev (Laravel).** [#99](https://github.com/libracoder/kiri/issues/99) (gzipped tar on
   `PUT /containers/{id}/archive` stopped ddev's router) is fixed, but ddev isn't in
   Kiri's own tests.
4. **Testcontainers (.NET Aspire and tests).**
   [#121](https://github.com/libracoder/kiri/issues/121), still open: the image's default
   command is dropped when a container is started through the API.
5. **Stability.** [#50](https://github.com/libracoder/kiri/issues/50), still open: the VM
   crashes many times a day under Postgres and Playwright load (guest kernel bug in
   `skb_segment`); fixes are in progress.
6. **Linux.** Kiri would replace docker-ce outright on Fedora, losing the NVIDIA runtime
   setup (`nvidia-ctk`) and the known-good engine. Not recommended there.

## When to revisit

Reconsider when all of these hold:

- Kiri reaches roughly 0.3–1.0;
- #121 and #50 are closed;
- a ddev Laravel project and an Aspire app run cleanly on it.

Then spec an opt-in `docker_runtime = "kiri"` for macOS (Colima stays the default) that
replaces the build-cache cap and turns off Kiri's self-updates.
