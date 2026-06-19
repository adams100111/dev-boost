# Fedora-44 Guides — Analysis & Adoption Report

**Date:** 2026-06-19
**Sources:** `guides/fedora-44-1.md` … `fedora-44-4.md` (four Fedora 44 setup guides)
**Method:** one subagent deep-read each guide; findings consolidated here and folded into the design spec.

---

## What each guide is

| Guide | Topic | Usefulness to dev-boost |
|-------|-------|--------------------------|
| **fedora-44-1** | Clean install with **BTRFS snapshots + rollback** (manual subvolume layout, Snapper + grub-btrfs + BTRFS Assistant, DNF5 unification) | **High** — system/recovery foundation |
| **fedora-44-2** | "10 things after installing Fedora 44" (repos, GPU, terminal, GUI apps, GNOME tweaks, backups, AI tools, power) | Medium — apps + GNOME + gotchas |
| **fedora-44-3** | Install Fedora 44 from Windows + essential post-install (RPM Fusion, codecs, VLC/Steam, GNOME extensions) | Medium — codecs + GNOME |
| **fedora-44-4** | Top 10 **GNOME Shell extensions** + Extension Manager / Tweaks | Medium — GNOME desktop layer |

---

## Every app/tool found (exact, with verdict)

| App / tool | Guide | What it is | Verdict in dev-boost |
|---|---|---|---|
| Snapper | 1 | BTRFS snapshot manager | ✅ already in `system` |
| grub-btrfs | 1 | Boot-into-snapshot GRUB menu | ✅ already in `system` |
| **BTRFS Assistant** | 1 | GUI for snapper | ✅ **added** to `system` |
| DNF5 + `python3-dnf-plugin-snapper` | 1 | Auto-snapshot on every package op | ✅ **added** as `snapper-dnf-hook` (first-party) |
| **RPM Fusion** (free+nonfree) | 1,2,3 | Codecs/drivers repos | ✅ **promoted** to shared `base` dep (was Nvidia-only) |
| **ffmpeg / multimedia codecs** | 2,3 | `dnf swap ffmpeg-free ffmpeg` + codec group | ✅ **added** as new `multimedia` profile |
| **DNF config tuning** | 2,3 | `max_parallel_downloads`, `fastestmirror`, `defaultyes` | ✅ **added** as `base/dnf-tune` |
| **GNOME Tweaks** | 2,3,4 | GNOME UI config | ✅ **added** to new `gnome` profile |
| **Extension Manager** (`com.mattjakeman.ExtensionManager`) | 2,3,4 | Manage GNOME extensions | ✅ **added** to `gnome` |
| GNOME extensions: AppIndicator, Clipboard Indicator, Caffeine, GSConnect | 4 | Tray icons, clipboard history, inhibit-sleep, Android | ✅ **added** to `gnome` (functional set) |
| GNOME extensions: Dash-to-Dock, Blur-my-Shell, Just-Perfection, V-Shell, Vitals | 2,4 | Dock, blur, UI tweaks, monitor | ✅ **added** to `gnome` (opt-in aesthetics sub-bundle) |
| **Fresh** ([getfresh.dev](https://getfresh.dev)) | 2 | Modern **Rust terminal editor/IDE** — LSP, multi-cursor, magit git, Vim mode, SSH remote, plugins | ✅ **added** to `editors` as default terminal editor (initially ambiguous "Fresh (text editor)", then identified) |
| **VLC** | 2,3 | Media player | ✅ **added** to `apps` (Flatpak) |
| OBS Studio | 2 | Screen recording/streaming | ⏳ noted, not added (offer on request) |
| GParted | 2 | Disk partitioning GUI | ⏳ noted, not added (rescue ISOs cover this) |
| OpenCode | 2 | CLI AI coding agent | ➕ opt-in `ai` profile (secondary) |
| LM Studio | 2 | Local/offline LLM runner | ➕ opt-in `ai` profile (secondary) |
| Nvidia driver + CUDA | 2,3 | GPU | ✅ already in `hardware-nvidia` |
| AMD GPU driver (Mesa freeworld) | 2 | GPU | ✅ **added** as opt-in `hardware-amd` |
| fwupd | 3 | Firmware updates | ✅ already in `system` |
| Fira Code Nerd Font | 2 | Terminal font | ✅ covered by `shell/nerd-fonts` (we use JetBrainsMono) |
| Steam | 3 | Gaming | ❌ out of scope (dev platform) |
| Balena Etcher / Rufus / Fedora Media Writer | 3 | ISO writers | ❌ superseded by Ventoy + Kickstart |
| Starship | 2 | Shell prompt | ❌ rejected — keep oh-my-posh |
| auto-cpufreq | 2 | CPU scaling | ❌ rejected — conflicts with TLP **and** tuned-ppd |
| Timeshift / Pika Backup | 2 | Snapshots / file backup | ❌ rejected — keep snapper + restic |
| KDE Connect | 2 | Phone integration | ↔ overlaps localsend; GSConnect added in `gnome` instead |

---

## Configuration / settings adopted

- **BTRFS subvolume layout** (guide 1) → encoded into **Kickstart**: `root → /`, `home → /home` (snapper-managed); **`var/lib/gdm` writable subvol (mandatory** — read-only snapshot boot fails at login without it); non-snapshotted `opt`, `var/cache`, `var/log`, `var/spool`, `var/tmp`, `var/lib/containers`, `var/lib/flatpak`, `var/lib/libvirt`. `/boot` **inside root** (atomic kernel snapshots); **no swap partition** (zram only); **`compress=zstd:1`** on all btrfs fstab entries.
- **DNF5 ↔ Snapper transaction hooks** (guide 1) → first-party `snapper-dnf-hook` module (not the guide's opaque curl-piped installer).
- **DNF performance** (guides 2,3) → `base/dnf-tune` writes `/etc/dnf/dnf.conf` early so the bootstrap itself is faster.
- **GNOME desktop** (guides 2,3,4) → declarative via `gsettings`/`dconf load` (chezmoi-managed), **not** the GUI browser connector: `color-scheme=prefer-dark`, fractional scaling, window button layout, center-new-windows, tap-to-click, accent color. Extensions via `gnome-extensions-cli`/`gext` with **pinned UUIDs + verified authorship**.

## Gotchas captured in the spec (§10c)

RPM Fusion + `dnf-tune` run **before** the first big upgrade · reboot after GPU-driver install · `/var/lib/gdm` subvol mandatory for snapshot boot · **Flatpak apps bypass snapper** (non-snapshotted subvol → excluded from rollback) · pin GNOME extension UUIDs (dconf fragile across GNOME versions).

---

## Net change to dev-boost profiles

- **`base`** += `rpmfusion`, `dnf-tune`
- **`cli`** += `claude-code` (your primary AI agent)
- **`editors`** += `fresh`
- **`gnome`** (new, in `full`)
- **`multimedia`** (new, in `full`)
- **`system`** += `btrfs-assistant`
- **`apps`** += `vlc`
- **opt-in:** `ai` (opencode, lm-studio), `hardware-amd`
- **Kickstart** += full BTRFS subvolume layout

**Biggest gaps the guides exposed:** (1) the BTRFS *subvolume layout* that snapper/grub-btrfs depend on (we had the tools, not the layout); (2) a GNOME *desktop* layer (none existed before).
