# Phase 1 Data Model: base-profile

No database. "Data" is module manifests, the profiles file, and the system/user state
each module reconciles. All mutated paths are overridable in tests via env/scratch roots.

## Module manifest entities

- **Simple tool module** (`modules/<tool>.toml`): `name`, optional `category`, `verify`
  (`command -v <tool>` or `rpm -q <pkg>`), `[install].<os>` (e.g. `fedora = "sudo dnf
  install -y <pkg>"`), optional `requires`. No `install.sh`.
- **Logic module** (`modules/<name>/{module.toml,install.sh}`): same keys; `[install]`
  invokes `bash "$DEVBOOST_ROOT/modules/<name>/install.sh"`.

## profiles.toml (NEW)

```toml
[profiles]
base = ["secrets","ssh-setup","rpmfusion","dnf-tune","fedora-third-party","flatpak",
        "coreutils","git","curl","wget","unzip","jq","htop","ripgrep","fd","fzf","tmux",
        "build-tools","mise","chezmoi","docker"]
```
Real ordering comes from each module's `requires`, not list order (engine depsorts).

## System / user state reconciled

| Artifact | Owner module | Idempotent verify |
|---|---|---|
| `rpmfusion-free-release` + `rpmfusion-nonfree-release` (+ `*-appstream-data`) | rpmfusion | `rpm -q` both release pkgs |
| `/etc/dnf/dnf.conf` keys `max_parallel_downloads=10`, `fastestmirror=true` | dnf-tune | both keys present with values |
| third-party repos enabled | fedora-third-party | `fedora-third-party query` == enabled |
| flatpak installed + `flathub` remote (unfiltered) | flatpak | `flatpak remotes` contains flathub; not filtered |
| each CLI tool installed | per-tool module | `command -v <tool>` |
| build toolchain bundle | build-tools | key members present (e.g. `command -v gcc make cmake`) |
| `mise` installed | mise | `command -v mise` |
| migrated runtime versions (USER global) | mise | `~/.config/mise/config.toml` lists migrated versions (repo `config/mise.toml` NOT written at install — F2/§III) |
| legacy init blocks commented in `~/.bashrc` | mise | block lines start with `#`, migration note present |
| `chezmoi` installed + initialized | chezmoi | `command -v chezmoi` AND `~/.local/share/chezmoi` exists |
| docker installed + service enabled + user in group | docker | `command -v docker` AND service enabled AND `getent group docker` ∋ user |

## Migration record (mise)

- Reads: `~/.nvm` (node versions), `~/.sdkman` (java current).
- Writes: `mise use -g <runtime>@<version>` (preserving exact versions → user global
  `~/.config/mise/config.toml`); `~/.bashrc` legacy blocks commented (delimited, not
  deleted) + dated migration note. (Repo `config/mise.toml` is NOT written here — F2/§III.)
- Leaves `~/.nvm` / `~/.sdkman` directories in place (rollback).

## Validation rules (from FRs)

| Rule | Source |
|------|--------|
| rpmfusion enabled before any nonfree install | FR-001 |
| dnf.conf reconciled, not duplicated | FR-002 |
| flathub full remote; vendor filter removed | FR-004 |
| one module per tool | FR-005 |
| migration preserves versions; comments not deletes init blocks | FR-007, SC-004 |
| doctor warns on mise+legacy both active | FR-008 |
| chezmoi clone non-blocking by default | FR-009 |
| docker group via getent; re-login reported | FR-010 |
| unmatched OS = unsupported failure, not skipped | FR-012 |
| no secret in git; state files not world-readable | FR-015 |

## Ordering (depsort via `requires`)

```
rpmfusion ─┐ (before nonfree consumers)
dnf-tune   ┤
flatpak    ┤
fedora-third-party
secrets (Spec 1) ──> chezmoi   (chezmoi requires secrets for the private clone)
mise, docker, tools: no inter-base requires (leaf), ordered after repos where they dnf-install
```
