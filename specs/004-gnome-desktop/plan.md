# Implementation Plan: gnome-desktop

**Branch**: `004-gnome-desktop` | **Date**: 2026-06-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/004-gnome-desktop/spec.md`

## Summary

Deliver the `gnome` profile as **data + escape-hatch modules over the existing engine**,
plus one additive sourced helper `lib/gnome.sh` and a chezmoi-managed dconf dump. The
`gnome-settings` module applies the reference look-and-feel via `dconf load` from a managed
dump (idempotent). The `gnome-extensions` module installs the curated functional set
**session-free**: download each pinned UUID for the detected GNOME Shell version via
`gext` (gnome-extensions-cli), verify authorship, then enable by writing the
`org.gnome.shell enabled-extensions` key (dedup) — never relying on a live shell.
`gnome-manager-apps` installs the official Extensions app, Extension Manager (flatpak),
and gnome-tweaks. Opt-in `gnome-aesthetics` (extension sub-bundle) and `gnome-theme`
(User Themes + pinned vinceliuice theme + Papirus + Bibata + Inter, reproducible) are
separate profiles, not in `full`. Non-GNOME/no-desktop → modules fail "unsupported" via a
`gnome_require` guard. Zero engine/`bin/devboost` change. Built test-first with bats,
mocking `gext`/`gnome-extensions`/`dconf`/`gsettings`/`flatpak`/`dnf`/`fc-list` — no real
installs or graphical session.

## Technical Context

**Language/Version**: Bash (engine + modules); python3/jq (existing).
**Primary Dependencies**: `gext`/`gnome-extensions-cli` (extension fetch), `dconf`/`gsettings` (settings + enable list), `flatpak` (manager apps), `dnf` (gnome-tweaks, Papirus, Inter, gext via pipx/pip or COPR), `gnome-shell --version` (version detect), `fc-cache` (theme fonts). No new engine runtime dependency.
**Storage**: user config — a chezmoi-managed dconf dump applied via `dconf load`; per-user extensions under `~/.local/share/gnome-shell/extensions/`; theme/icon/cursor/font dirs. No database.
**Testing**: `bats`; extend `tests/fixtures/base/stubs.bash` with `gext`/`gnome-extensions`/`dconf`/`gsettings` stubs + a GNOME-present/absent knob + a shell-version knob. No real desktop/installs (§V).
**Target Platform**: Fedora Workstation + GNOME (reference). Non-GNOME/other OS → reported unsupported via module guard.
**Project Type**: Single-project Bash bootstrap engine.
**Performance Goals**: Not latency-sensitive; correctness + idempotency.
**Constraints**: Unattended (no session needed); idempotent/verify-guarded; engine untouched; no secret in git; pinned UUIDs + verified authorship.
**Scale/Scope**: `lib/gnome.sh` + ~5 modules (gnome-settings, gnome-extensions, gnome-manager-apps, gnome-aesthetics opt-in, gnome-theme opt-in) + a dconf dump + 3 profile entries (`gnome`, `gnome-aesthetics`, `gnome-theme`) + ~5 bats files.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Engine + Data Separation** — PASS (no engine touch). New capability is modules (data + escape-hatch) + the additive `lib/gnome.sh` + a chezmoi dconf dump (data) + 3 `profiles.toml` entries. `run_install`/`depsort`/`module.sh`/`profile.sh`/`bin/devboost` unchanged.
- **II. Idempotent & Verify-Guarded** — PASS. `dconf load` is idempotent; `gext` install skips present extensions; the enable list is dedup-managed; each module verifies end-state (extension dir present + in enable list; setting key value; app installed).
- **III. Reproducible — Repo is Source of Truth** — PASS. dconf dump + pinned extension UUIDs + pinned theme tag live in the repo; no secret committed; managed config has no secrets.
- **IV. Unattended by Default** — PASS. Extensions installed + enabled WITHOUT a live session (download via gext + write enable key); all installs non-interactive.
- **V. Test-First (NON-NEGOTIABLE)** — PASS. Settings apply, extension install/enable/authorship-verify/no-dup, unsupported-env, and opt-in bundles are failing-bats-first; all desktop tooling stubbed.
- **VI. Cross-OS via Data** — PASS. Per-OS `[install]` keys where packaged; the GNOME-vs-not distinction (not an OS key) is a module `gnome_require` guard that fails "unsupported", honoring FR-010's no-silent-skip.

**Result: PASS** — proceed to Phase 0.

## Project Structure

### Documentation (this feature)
```text
specs/004-gnome-desktop/
├── plan.md, research.md, data-model.md, quickstart.md
├── contracts/
│   ├── lib-gnome.md          # gnome_require, shell_version, ext_install/verify/enable, dconf_load
│   ├── gnome-settings.md     # dconf dump + apply module (US1)
│   ├── gnome-extensions.md   # functional set install+enable, session-free (US2)
│   ├── manager-and-optin.md  # manager apps + gnome-aesthetics + gnome-theme (US3)
│   └── profiles.md           # gnome / gnome-aesthetics / gnome-theme entries
└── tasks.md
```

### Source Code (repository root)
```text
lib/
└── gnome.sh                  # NEW — gnome_require (unsupported guard), gnome_shell_version, ext_install (gext by uuid+version), ext_verify_author, ext_enable (enabled-extensions dconf, dedup), dconf_load_managed
modules/                      # NEW gnome modules
├── gnome-settings/{module.toml,install.sh,gnome.dconf}  # dconf load the repo data dump (F1: plain repo file, not chezmoi dot_; F2: no enabled-extensions key)
├── gnome-extensions/{module.toml,install.sh}   # functional set (pinned UUIDs) install+enable; SOLE owner of enabled-extensions
├── gnome-manager-apps/{module.toml,install.sh} # org.gnome.Extensions + Extension Manager (flatpak) + gnome-tweaks
├── gnome-aesthetics/{module.toml,install.sh}   # OPT-IN aesthetics extension sub-bundle
└── gnome-theme/{module.toml,install.sh}        # OPT-IN User Themes + vinceliuice + papirus + bibata + inter
profiles.toml                 # EDIT — add `gnome`, `gnome-aesthetics`, `gnome-theme`
tests/
├── gnome-settings.bats, gnome-extensions.bats, gnome-manager.bats, gnome-theme.bats, gnome.bats(lib)  # NEW
└── fixtures/base/stubs.bash  # EXTEND (backward-compatible): gext/gnome-extensions/dconf/gsettings stubs + GNOME-present + shell-version knobs
```

**Structure Decision**: Single-project Bash engine; additive. No engine/`bin/devboost`
change. The shared extension/dconf logic lives in `lib/gnome.sh` (sourced), keeping the
modules thin (like Spec-2's `lib/pkg.sh`).

## Complexity Tracking

> No constitution violations — no engine touch. `lib/gnome.sh` is an additive sourced
> helper (the §3.2 helper pattern, same precedent as `lib/pkg.sh`). Table empty.
