# Contract: `apps` GUI modules (Flathub)

Six modules, `category="apps"`, `requires=["flatpak"]`, `profiles=["apps"]`, only `[install].fedora`.
Each installs one Flathub app; the app ID is the in-repo source of truth (research.md, verified 2026-06-21).

## Per-app module.toml (pattern — Obsidian shown)
```toml
name        = "obsidian"
category    = "apps"
description = "Obsidian notes app (Flathub)"
requires    = ["flatpak"]
profiles    = ["apps"]
verify      = "flatpak info md.obsidian.Obsidian"

[install]
fedora = "flatpak install -y flathub md.obsidian.Obsidian"
```
- install command must be `flatpak install -y flathub <id>` (non-interactive; precedent
  `modules/gnome-manager-apps/install.sh`). No `default`/other-OS keys (Principle VI).
- The six IDs: md.obsidian.Obsidian, com.usebruno.Bruno, com.bitwarden.desktop,
  org.flameshot.Flameshot, org.localsend.localsend_app, org.videolan.VLC.
- NO dbgate module (container from data stack); DBeaver not installed (optional alt, documented).

## Tests (`tests/apps.bats`, stubbed)
- each module: `flatpak install -y flathub <id>` attempted (assert STUB_FLATPAK_LOG) with the right ID;
  verify GREEN when the flatpak stub reports the app present; idempotent skip when already installed
  (engine verify-guard); unsupported-OS (non-fedora) → engine failure. No real flatpak/network.
- assert NO dbgate flatpak install attempted.
