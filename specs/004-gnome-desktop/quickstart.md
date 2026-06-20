# Quickstart / Validation: gnome-desktop

Proves the `gnome` profile end-to-end **hermetically** (no real desktop/installs/session)
via the bats stub harness. See `contracts/` for exact interfaces.

## Prerequisites
- Repo checked out; `bats`, `jq`, `python3`. Specs 1–3 merged (base/flatpak/chezmoi on `main`).
- Desktop/package tooling (`gext`, `gnome-extensions`, `dconf`, `gsettings`, `gnome-shell`,
  `flatpak`, `dnf`, `git`, `fc-list`) is **stubbed** by `tests/fixtures/base/`. No GUI, no root.

## Run the tests (primary validation)
```bash
bats tests/gnome.bats tests/gnome-settings.bats tests/gnome-extensions.bats \
     tests/gnome-manager.bats tests/gnome-theme.bats tests/profiles.bats
# or the whole suite:
bats tests/
```
Expected: all green — settings applied + idempotent; each functional extension installed by
pinned UUID + author-verified + enabled once (no dup); a mismatched-author fixture → named
failure; non-GNOME host → unsupported failure; manager apps installed; opt-in
aesthetics/theme provisioned reproducibly. No real desktop/session.

## Resolution smoke (list only)
```bash
DEVBOOST_MODULES_DIR="$PWD/modules" DEVBOOST_PROFILES="$PWD/profiles.toml" \
  ./bin/devboost list --profile gnome
```
Expected: `gnome-settings` before `gnome-extensions`/`gnome-manager-apps`, no cycle.

## Manual smoke (optional, real Fedora-Workstation/GNOME VM)
```bash
DEVBOOST_MODULES_DIR="$PWD/modules" DEVBOOST_PROFILES="$PWD/profiles.toml" \
  ./bin/devboost install --profile gnome
```
Expected after a first GNOME login: dark mode + accent + scaling + window buttons applied;
the 6 functional extensions active; Extensions app + Extension Manager + gnome-tweaks
present; re-run reports every module skipped; `git ls-files` shows no secrets.

Opt-in bundles (add either or both):
```bash
# Aesthetics extensions (blur-my-shell, just-perfection, vertical-workspaces, astra-monitor, CoverflowAltTab):
DEVBOOST_MODULES_DIR="$PWD/modules" DEVBOOST_PROFILES="$PWD/profiles.toml" \
  ./bin/devboost install --profile gnome,gnome-aesthetics

# Themed look (WhiteSur-Dark gtk + Papirus icons + Bibata cursor + Inter font):
DEVBOOST_MODULES_DIR="$PWD/modules" DEVBOOST_PROFILES="$PWD/profiles.toml" \
  ./bin/devboost install --profile gnome,gnome-theme
```
Opt-in profiles (`gnome-aesthetics` → `gnome-aesthetics-bundle`; `gnome-theme` → `gnome-theme-bundle`) are independent and may be combined.

## Tear down
Throwaway VM only; no host changes via the test stubs.
