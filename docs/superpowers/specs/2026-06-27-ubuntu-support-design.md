# Ubuntu support — Design (Phase 1)

**Date:** 2026-06-27 · **Status:** Phase 1 approved for implementation.

dev-boost was built with OS-dispatch seams (`OsMap`, `Module.per_os`, the `PackageManager` Protocol;
`osinfo` already maps `ubuntu/debian/mint/pop → debian`). Only the **Fedora** branch is implemented —
`pkg.py` literally says *"Dnf is implemented; Apt/Pacman are seams for later specs."* This spec fills the
Debian/Ubuntu seam.

## Target ISOs (catalog data — real, verified)
- **amd64** — Ubuntu Budgie 26.04 desktop:
  `https://cdimage.ubuntu.com/ubuntu-budgie/releases/26.04/release/ubuntu-budgie-26.04-desktop-amd64.iso`
  sha256 `cbdebfa6517d6f64ecc07f6b91a672cf623e1f378b1b92c6e2d27bd7c8b6ca42`
- **arm64** — vanilla Ubuntu 26.04 desktop (resolute):
  `https://cdimage.ubuntu.com/ubuntu/releases/resolute/release/ubuntu-26.04-desktop-arm64.iso`
  sha256 `c2afd538d66fdd77377d03f1ed2ac76a34f1c116baecc9a8170d68f833121f57`

These are **Live desktop** images (no separate netinst). In the catalog they get `isos` only (no
`autoinstall`) — so the builder stages the Live ISO and ventoy.json emits no `auto_install` block (the
dual-ISO design already makes `autoinstall` optional). → the USB **boots Ubuntu for a manual install**.

## Phase 1 scope (this spec)
1. **Catalog:** add an `ubuntu-26.04` `Os` entry (both arches, Live-only) to `catalog.toml`.
2. **`Apt` `PackageManager`** in `exec/primitives/pkg.py`: `apt-get install -y` (with `DEBIAN_FRONTEND=
   noninteractive`), `dpkg -s` for `installed`, repo add via `add-apt-repository`/sources.list.d.
   Wire `manager_for()` to return `Apt()` for `family == "debian"`. Generalise `Source` so a per-OS repo
   can be an `AptRepo` on Ubuntu (model already names `AptRepo` as a type).
3. **flatpak on Ubuntu:** ensure the `flatpak` primitive/module installs flatpak + adds Flathub on Ubuntu
   (Ubuntu defaults to snap; flatpak itself is cross-distro once installed).
4. **Portable-profile module overrides** (`base`/`cli`/`shell`/`terminal`): add `OsMap[str]` package-name
   overrides where apt names differ (e.g. `fd-find`/`fd`, `bat`→`batcat`, `build-essential`); convert the
   handful of COPR sources to PPA/alternatives; mark genuinely Fedora-only modules (e.g. `rpmfusion`,
   `dnf-tune`, `fedora-third-party`) so they report *unsupported* on Ubuntu rather than fail.

**Result:** `devboost install terminal` (and `cli`/`shell`) works on an Ubuntu box; the USB boots Ubuntu.

## Phase 2 (separate spec — NOT now)
- **Zero-touch on Ubuntu** via subiquity `autoinstall.yaml` / cloud-init `user-data` (≠ Kickstart) +
  Ventoy auto-install binding + an OS-dispatched firstboot delivery.
- **Full module parity**: dev-stacks, `system` (snapper/grub-btrfs are btrfs/Fedora-specific → Ubuntu
  equivalents or Fedora-only), desktop config (amd64 is **Budgie**, not GNOME).

## Non-negotiables
- No module ever names `apt`/`dnf` directly — everything dispatches through `manager_for(ctx.os)` /
  `Module.per_os`. `mypy --strict` + ruff + pytest stay green. Modules unsupported on the detected OS are
  **reported**, never silently skipped.
