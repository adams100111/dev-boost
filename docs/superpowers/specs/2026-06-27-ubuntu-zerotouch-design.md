# Ubuntu zero-touch (subiquity autoinstall) — Design (Phase 2a)

**Date:** 2026-06-27 · **Status:** approved for implementation. Builds on Ubuntu Phase 1/2b.

## The mechanism (verified via canonical/autoinstall-desktop docs)
Ubuntu does NOT use Kickstart. Unattended install = **subiquity autoinstall**: a `#cloud-config`
`user-data` with an `autoinstall:` block (`version: 1`, `identity`, `storage`, `packages`,
`late-commands`), delivered to the installer via cloud-init **NoCloud** (a `CIDATA` seed with
`user-data` + `meta-data`, or Ventoy's auto-install injection). `late-commands` run in the installer
with the target mounted at `/target` (use `curtin in-target -- <cmd>` for chrooted ops) — this is the
Ubuntu analogue of Fedora's Kickstart `%post`.

Key difference vs Fedora: **no separate netinst.** Ubuntu autoinstall runs off the **same desktop Live
ISO** (`isos`), seeded with the user-data — there is no second media to stage.

## Architecture — OS-dispatch the autoinstall
A new family-dispatched `autoinstall` seam in the builder. For each OS, the builder asks:
*does this OS support zero-touch, and with what config + which boot image?*

| Family | Config file | Boot image (ventoy `auto_install`) | Firstboot delivery |
|---|---|---|---|
| `fedora` | `ks.cfg` (existing `render_kscfg`) | the **netinst** `autoinstall` ISO | Kickstart `%post` (existing) |
| `debian` | `user-data` + `meta-data` (new `render_user_data`) | the **Live** desktop ISO itself | autoinstall `late-commands` (new) |

Concretely:
1. **`media/autoinstall.py` (new)** — `autoinstall_for_os(ctx, cfg) -> AutoinstallPlan | None` returning,
   per family: the config filename(s) + rendered content + the Ventoy image to bind. `None` when the OS
   has no zero-touch support pinned.
2. **`render_user_data(profiles, *, arch)`** — emits the `#cloud-config` autoinstall:
   - `version: 1`; `identity` = a provisional `devboost` user (real identity/secrets are applied by the
     firstboot run from the age bundle — autoinstall just needs *a* user); `storage: {layout: {name: direct}}`
     (Phase 2a keeps it simple — **not** the Fedora BTRFS-subvolume layout; that's a later refinement);
     `packages: [ubuntu-desktop-minimal]` (the desktop ISO already carries the set).
   - `late-commands`: copy the injected `devboost` binary + `secrets.age`/`age-key.txt` from the USB
     (`/cdrom`/the VTOY mount) into `/target/opt/dev-boost/`; write
     `/target/etc/systemd/system/devboost-firstboot.service` (oneshot: `ExecStart=/opt/dev-boost/devboost
     install full`, `ExecStartPost` disables on success — same contract as Fedora, with
     `DEVBOOST_BOOTSTRAP_DIR=/opt/dev-boost` etc.) and `curtin in-target -- systemctl enable
     devboost-firstboot.service`; `curtin in-target -- apt-get install -y cloud-init`.
   - emit an empty `meta-data` alongside (NoCloud requires both).
3. **`stages` / `render_ventoy_json`** — the `auto_install` block dispatches by family: Fedora →
   `{image: /ISO/<netinst>, template: /Bootstrap/ks.cfg}`; Ubuntu →
   `{image: /ISO/<live>, template: /Bootstrap/user-data}` (+ stage `meta-data`). `injection` (binary)
   still covers the booted image so the binary reaches the installer env on either path.
4. **catalog** — Ubuntu stays **Live-only** (`isos`, no separate `autoinstall` media). The builder enables
   Ubuntu zero-touch by **family**, not by a pinned netinst. Add a small `Os`-level flag if needed
   (`zero_touch: bool`, default true for fedora/debian) — or infer from family.

## What Phase 2a does NOT do (honest scope)
- **No BTRFS-subvolume layout for Ubuntu** (uses `storage: direct`) — the snapshot-ready layout is Fedora-
  specific for now; an Ubuntu equivalent (or zsys/timeshift) is a later refinement.
- **Ventoy's exact Ubuntu auto-install injection** (cmdline/`ds=nocloud`) — implemented per Ventoy's
  documented Ubuntu support, but **like the Fedora zero-touch, NOT verified on a real Ubuntu VM install.**
  Expect real-VM iteration. The dev-boost side (config generation, staging, firstboot) is what we build +
  unit-test; the actual Anaconda/subiquity behavior is first-real-run.

## Tests (hermetic)
- `render_user_data`: contains `version: 1`, the `late-commands` that copy the binary/secrets + enable
  the firstboot service, and a valid `#cloud-config` header; `render_kscfg` unchanged for Fedora.
- `autoinstall_for_os`: fedora → ks.cfg + netinst image; debian → user-data + live image; an OS with no
  support → None.
- `render_ventoy_json` (or its caller): Ubuntu `auto_install` binds the **Live** ISO + `user-data`;
  Fedora binds the **netinst** + `ks.cfg`.
- `mypy --strict` + ruff + pytest green.
