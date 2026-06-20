# Quickstart / Validation: base-profile

Proves the profile end-to-end **hermetically** (no real installs, no network) using the
bats stub harness. See `contracts/` for exact module interfaces.

## Prerequisites
- Repo checked out; `bats`, `jq`, `python3` available.
- External commands (`dnf`, `rpm`, `flatpak`, `fedora-third-party`, `systemctl`,
  `usermod`, `getent`, `mise`, `chezmoi`, `git`, `sudo`) are **stubbed** by
  `tests/fixtures/base/` at test time. No root, no network.

## Run the tests (primary validation)
```bash
bats tests/profiles.bats tests/repos.bats tests/tools.bats tests/build-tools.bats \
     tests/mise.bats tests/chezmoi.bats tests/docker.bats tests/doctor-mise.bats
# or the whole suite (incl. Spec 1 + engine):
bats tests/
```
Expected: all green — each module installs + verifies, re-run is a no-op, the migration
present/absent branches behave, unsupported-OS is reported (not skipped), and the doctor
drift warning fires only when both managers are active. No test performs real I/O.

## Resolution smoke (no installs — list only)
```bash
# the real profiles.toml + modules resolve `base` and depsort without cycles
DEVBOOST_MODULES_DIR="$PWD/modules" DEVBOOST_PROFILES="$PWD/profiles.toml" \
  ./bin/devboost list --profile base
```
Expected: a topologically-ordered module list with `rpmfusion`/`secrets` before their
dependents, no cycle error.

## Manual smoke (optional, throwaway VM/container with root — real installs)
```bash
DEVBOOST_MODULES_DIR="$PWD/modules" DEVBOOST_PROFILES="$PWD/profiles.toml" \
  ./bin/devboost install --profile base
```
Expected outcomes (on Fedora):
- RPM Fusion free+nonfree (+appstream) installed; `/etc/dnf/dnf.conf` has the two tuning keys.
- `flatpak remotes` shows full `flathub`; third-party repos enabled.
- All CLI tools + the build toolchain verify present.
- `mise` installed; any prior nvm/sdkman versions preserved + their bashrc init commented.
- `chezmoi` initialized; if `DEVBOOST_DOTFILES_REPO` is set the dotfiles repo is cloned via
  `chezmoi init --apply <repo>` using credentials from `~/.git-credentials` (seeded by the
  `secrets` module); clone failure is non-blocking (warns, does not abort).
- `docker` installed, service enabled, user in `docker` group (re-login reported).
- Re-running `install --profile base` reports every module **skipped** (idempotent).
- `git ls-files` shows no secrets/keys.
```

## Tear down
Throwaway VM/container only; no host changes when run via the test stubs.
