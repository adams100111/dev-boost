# dev-boost

From a fresh laptop to a fully-configured developer workstation in **minutes**, with effectively
zero config — delivered by an unattended **Ventoy USB** (primary: `curl … | bash`; bonus: zero-touch
Kickstart). "Production ready" means the box can **build, out of the box**: Laravel (ddev),
.NET + Aspire, Python (uv), Next.js/React (web), React Native + Expo (Android) — plus editors
(VS Code + fresh), GUI apps (Obsidian w/ GitHub sync, Bruno, Bitwarden, …), terminal/shell/desktop
(ghostty + starship + tmux + GNOME), all restored from chezmoi-managed dotfiles. A bad update is a
**reboot**, not a rebuild (Btrfs snapshots).

dev-boost is a small, legible **Bash engine + declarative data** (modules + `profiles.toml`):
adding a tool is one file; adding an OS is one key.

## Quick start

```sh
# From the repo (manual path — most reliable):
./install.sh                       # installs the 'full' workstation (default)
./install.sh --profile cli,shell   # or pick profiles
curl -fsSL https://…/install.sh | bash   # bootstrap path

# Inspect first (no changes):
./bin/devboost list --profile base
./bin/devboost doctor
```

Secrets (a GitHub PAT) are pre-provisioned once on the USB (`age`-encrypted); the GPU vendor is
**auto-detected** (no flag). The only possibly-interactive moment is a one-time Secure-Boot MOK
enrollment on NVIDIA when Secure Boot is on.

## Profiles

<!-- BEGIN generated profiles table (scripts/gen-profiles-table.sh) -->
| Profile | Installs (resolved modules) |
|---------|------------------------------|
| `apps` | bitwarden, bruno, flameshot, localsend, obsidian, obsidian-sync, vlc |
| `base` | build-tools, chezmoi, chezmoi-repo, coreutils, curl, dnf-tune, docker, fd, fedora-third-party, flatpak, fzf, git, htop, jq, mise, ripgrep, rpmfusion, secrets, ssh-setup, tmux, unzip, wget |
| `cli` | atuin, bat, btop, claude-code, delta, direnv, duf, dust, eza, fastfetch, gh, lazydocker, lazygit, sd, tealdeer, tpm, yq, zoxide |
| `data` | data-services |
| `dev-hygiene` | aspire-gc |
| `devops` | devops-lsp, devops-tools |
| `devtools` | aspire, ddev, dotnet-lsp, dotnet-sdk, python-lsp, uv, web-lsp, web-runtimes |
| `dotnet` | aspire, dotnet-lsp, dotnet-sdk |
| `editors` | fresh, fresh-lsp, vscode |
| `gnome` | gnome-extensions, gnome-manager-apps, gnome-settings |
| `gnome-aesthetics` | gnome-aesthetics-bundle |
| `gnome-theme` | gnome-theme-bundle |
| `hardware-nvidia` | cuda, libva-nvidia-driver, nvidia-akmod, nvidia-container-toolkit, nvidia-resign-service, secureboot-mok |
| `laravel` | ddev, laravel-lsp |
| `multimedia` | codecs, ffmpeg-full, openh264, va-hwaccel |
| `optional-editors` | jetbrains-toolbox, neovim |
| `python` | python-lsp, uv |
| `react-native` | android-sdk, expo, web-runtimes |
| `security-cli` | pass, pass-store |
| `shell` | bash-config, dotfiles, ghostty, nerd-fonts, starship |
| `system` | btrfs-assistant, btrfsmaintenance, dnf-automatic-security, earlyoom, fwupd, gpu-detect, grub-btrfs, power-profiles-daemon, restic-backup, smartmontools, snapper, snapper-dnf-hook, thermald |
| `terminal` | atuin, bash-config, bat, btop, chezmoi, coreutils, curl, delta, direnv, dotfiles, duf, dust, eza, fastfetch, fd, fresh, fzf, gh, ghostty, git, jq, lazygit, mise, nerd-fonts, ripgrep, sd, starship, tealdeer, tmux, unzip, wget, yq, zoxide |
| `web` | web-lsp, web-runtimes |
<!-- END generated profiles table -->

Stacks (`python`/`web`/`laravel`/`dotnet`/`data`/`devops`/`react-native`) are opt-in per project;
`hardware-nvidia` is auto-selected by `gpu-detect` on NVIDIA hardware; `optional-editors` is opt-in.

## Commands

| Command | Description |
|---------|-------------|
| `devboost install [--profile a,b] [--force] [--strict]` | Resolve profiles → topo-sort → verify-guarded install (default: full). |
| `devboost verify [--profile a,b]` | Audit: run every `verify`, report green/red. No changes. |
| `devboost list [--profile a,b]` | Show the resolved module order for this OS. |
| `devboost doctor [--gpu]` | Preflight (disk/net/OS/secrets); `--gpu` runs the GPU driver diagnostic. |
| `devboost add <name> [--folder]` | Scaffold a new module from the template. |
| `devboost export` | Snapshot actual installed state into `workstation-config/exports/`. |
| `devboost diff [--profile a,b]` | Declared (repo) vs actual (machine) drift; exit ≠ 0 on drift. |
| `devboost update [--profile a,b]` | Propose pinned bumps + regenerate `devboost.lock`; never auto-commits. |
| `devboost self-update` | `git pull` dev-boost, then re-validate. |
| `devboost dev <status\|gc\|down>` | Dev-environment resource hygiene (orphan Aspire AppHost GC). |

## Recovery walkthrough

1. Boot the **Ventoy USB** → pick Fedora (manual installer ~10 min, or the zero-touch auto-install entry).
2. Manual: reboot → `cd …/VTOY/Bootstrap/dev-boost && ./install.sh`. Zero-touch: Kickstart installs
   Fedora with the snapshot-ready BTRFS layout, then a first-boot service runs `install.sh --profile full`.
3. **Bad update?** Reboot → GRUB "Fedora snapshots" → boot the pre-update snapshot.

See [docs/recovery-runbook.md](docs/recovery-runbook.md) and [docs/ventoy.md](docs/ventoy.md).

## Adding a tool

```sh
devboost add ripgrep            # scaffolds modules/ripgrep/module.toml
```
```toml
name     = "ripgrep"
category = "cli"
requires = []
profiles = ["cli"]
verify   = "rg --version"        # success ⇒ already installed ⇒ skipped
[install]
fedora = "dnf install -y ripgrep"   # per-OS keys; non-Fedora without a key ⇒ unsupported
```
Add it to a profile in `profiles.toml`, commit. See [docs/adding-a-module.md](docs/adding-a-module.md).

## Requirements & supported OS

- **Reference OS:** Fedora Workstation 44 (modules ship `[install].fedora` keys).
- **Engine:** bash 5, python3 ≥ 3.11, jq, `age` (for secrets). Other OSes: add `[install].<os>` keys
  (Cross-OS-via-Data) — non-Fedora modules without a key are reported unsupported, never silently skipped.
- **Tests:** `bats tests/`.

## Docs

[architecture](docs/architecture.md) · [recovery-runbook](docs/recovery-runbook.md) ·
[adding-a-module](docs/adding-a-module.md) · [maintenance](docs/maintenance.md) ·
[obsidian-sync](docs/obsidian-sync.md) · [ventoy](docs/ventoy.md) · [vm-testing](docs/vm-testing.md) · [roadmap](docs/roadmap.md)

## Validate before shipping (in a throwaway Fedora VM)

```sh
scripts/vm-test.sh engine --iso Fedora-Live.iso        # engine-only: install Fedora, run ./install.sh
scripts/vm-test.sh usb --kickstart Fedora-netinst.iso  # full USB (device-less zero-touch via ventoy/ks.cfg)
scripts/vm-test.sh usb --device /dev/sdX               # full USB (boot the real Ventoy stick, passthrough)
scripts/make-secrets.sh --out /tmp/sec                 # build the age-encrypted secrets bundle (PAT never logged)
```
Full runbook (prereqs, snapshots, what to verify): [docs/vm-testing.md](docs/vm-testing.md).
