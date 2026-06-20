# Contract: US3 managers (`mise`, `chezmoi`, `docker`)

Logic modules sourcing `lib/log.sh`+`lib/pkg.sh` (chezmoi also `lib/secrets.sh`).

## mise
- `requires=[]`. `verify`: `command -v mise`.
- `install.sh`:
  1. install mise (fedora: dnf/COPR or official installer per design; pin method in impl).
  2. **Migration (conditional, idempotent)**: if `~/.nvm` present → resolve node version(s),
     `mise use -g node@<v>`; if `~/.sdkman` present → resolve java current, `mise use -g
     java@<v>` — `mise use -g` writes the USER global config (`~/.config/mise/config.toml`),
     which preserves the versions. Then `comment_block ~/.bashrc` for the nvm and sdkman
     init blocks (never delete) + dated migration note. Absent ⇒ no-op. Does NOT write the
     repo's committed `config/mise.toml` (that pin is the later `update` spec's job; §III).
  3. Versions are PRESERVED (no upgrade/downgrade) — SC-004.
- Re-run: already-pinned + already-commented ⇒ no changes.

## chezmoi
- `requires=["secrets"]`. `verify`: `command -v chezmoi` AND `~/.local/share/chezmoi` exists.
- `install.sh`: install chezmoi; `chezmoi init` to adopt config; clone the dotfiles repo over
  HTTPS using the credential store seeded by `secrets` (Spec 1). Clone failure → `log_warn`
  + return 0 (non-blocking default; engine verify-after-install handles strict abort, same
  pattern as Spec 1 ssh-setup). Never echo credentials.

## docker
- `requires=[]`. `verify`: `command -v docker` AND docker service enabled AND
  `getent group docker` contains `$USER`.
- `install.sh`: add docker-ce repo (fedora: `dnf config-manager` / repo file), install
  docker-ce + compose plugin, `sudo systemctl enable --now docker`, `sudo usermod -aG
  docker $USER`. `log_warn`/`log_info` that a **re-login is required** for the group to take
  effect (do NOT assume active this session). Idempotent (repo add-if-absent; group add
  only if not member).

## Tests (`tests/mise.bats`, `tests/chezmoi.bats`, `tests/docker.bats`) — stubs for mise/chezmoi/git/dnf/systemctl/usermod/getent/sudo + fake `~/.nvm`/`~/.sdkman`
- mise: install attempted; migration present-branch (fake ~/.nvm with a version → `mise use
  -g node@<v>` attempted, bashrc block commented, config pinned, version unchanged) and
  absent-branch (no ~/.nvm/.sdkman → no migration calls); empty-legacy edge (dir present, no
  versions → no `mise use`, block still commented); idempotent re-run.
- chezmoi: install + init; clone uses credential path; clone-failure → warn + return 0, no
  state; verify maps to binary + chezmoi dir; no credential echoed.
- docker: repo added once; service enabled; group added only when absent; verify via getent;
  re-login warning emitted; idempotent re-run.
