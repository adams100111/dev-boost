# dev-boost

From a fresh laptop to a fully-configured developer workstation in **minutes**, with effectively
zero config — delivered by an unattended **Ventoy USB** (primary: `curl … | bash`; bonus: zero-touch
Kickstart). "Production ready" means the box can **build, out of the box**: Laravel (ddev),
.NET + Aspire, Python (uv), Next.js/React (web), React Native + Expo (Android) — plus editors
(VS Code + fresh), GUI apps (Obsidian w/ GitHub sync, Bruno, Bitwarden, …), terminal/shell/desktop
(ghostty + starship + tmux + GNOME), all restored from chezmoi-managed dotfiles. A bad update is a
**reboot**, not a rebuild (Btrfs snapshots).

dev-boost is a small, legible **strictly-typed Python engine** (Typer + Pydantic) plus declarative
data (typed modules + `profiles.toml`): adding a tool is one typed file; adding an OS is a localized
per-OS entry. It ships as a **frozen single-file binary** (no Python runtime on the target); the only
bash is the `curl|bash` bootstrap and the Kickstart `%post`.

## Quick start

```sh
# Installed binary (what get.sh / the USB place on PATH):
devboost install                 # installs the 'full' workstation (default)
devboost install cli shell       # or pick profiles
devboost list base               # inspect the resolved order (no changes)
devboost doctor                  # environment preflight
devboost install full --dry-run  # preview everything, mutate nothing

# From a clone (developing the engine):
cd engine && uv sync && uv run devboost list full

# Install from the clone so `devboost` runs from anywhere (editable, no rebuild):
scripts/install-dev.sh           # = uv tool install --editable ./engine
devboost installer --dry-run     # now works from any directory
```

Editable keeps the engine pointed at your checkout, so the repo-root data
(`profiles.toml`, `catalog.toml`, `ventoy/`) resolves correctly and code edits are
live. Uninstall with `uv tool uninstall devboost`. (A plain wheel install won't
work — that data lives outside the packaged module; the **frozen binary** is the
shippable artifact for fresh machines.)

## Install (any OS)

```bash
curl -fsSL https://raw.githubusercontent.com/adams100111/dev-boost/main/scripts/get.sh | bash -s -- terminal
```

Detects your architecture, downloads the matching frozen `devboost` binary from the latest GitHub Release,
verifies SHA256, **installs it onto PATH** (links `devboost` into `~/.local/bin`), and runs
`devboost install terminal` — no Python, no clone. Afterward `devboost …` works from anywhere. Add
`devtools` for language runtimes/frameworks, or `--dry-run` to preview:

```bash
curl -fsSL https://raw.githubusercontent.com/adams100111/dev-boost/main/scripts/get.sh | bash -s -- terminal devtools
```

Releases are published automatically on each `v*` tag; `/latest/` always tracks the newest.
(Requires this repo to be public.)

## Quick start — from the repo

Secrets (a GitHub PAT) are pre-provisioned once on the USB (`age`-encrypted); the GPU vendor is
**auto-detected** (no flag). The only possibly-interactive moment is a one-time Secure-Boot MOK
enrollment on NVIDIA when Secure Boot is on.

## Profiles

<!-- BEGIN generated profiles table (scripts/gen_profiles_table.py) -->
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
| `devboost installer [--device …] [--iso …] [--dry-run] [--refresh-iso] [--yes]` | Build **or non-destructively update** a bootable Ventoy USB: interactive wizard (or flags) — lists removable disks, probes the target (blank / foreign-Ventoy / existing dev-boost → offers update), stages **both the Live (manual) and netinst (zero-touch) ISOs**, downloads + verifies + caches each with a live progress bar, stages the binary/ks.cfg, and prints a final summary. `--dry-run` previews the whole plan and touches nothing. |

## Recovery walkthrough

0. Build the stick once: `sudo devboost installer` (interactive; add `--dry-run` to preview) — see [docs/ventoy.md](docs/ventoy.md).
1. Boot the **Ventoy USB** → pick Fedora (manual installer ~10 min, or the zero-touch auto-install entry).
2. Manual: reboot → `/opt/dev-boost/devboost install full` (the firstboot oneshot). Zero-touch: Kickstart installs
   Fedora with the snapshot-ready BTRFS layout, then a first-boot service runs `devboost install full`.
3. **Bad update?** Reboot → GRUB "Fedora snapshots" → boot the pre-update snapshot.

See [docs/recovery-runbook.md](docs/recovery-runbook.md) and [docs/ventoy.md](docs/ventoy.md).

## Adding a tool

```sh
devboost add ripgrep            # scaffolds engine/src/devboost/modules/ripgrep.py
```
```python
@register
class Ripgrep(Module):
    name = "ripgrep"
    category = "cli"
    requires = ()                          # references to other Module classes
    profiles = ("cli",)
    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("rg")          # True ⇒ already installed ⇒ skipped
    def install(self, ctx: Ctx) -> None:
        pkg.install(ctx, "ripgrep")        # OS-dispatched; never names dnf/apt
```
Add it to a profile in `profiles.toml`, commit. See [docs/adding-a-module.md](docs/adding-a-module.md).

## Bundled tool configs

dev-boost ships curated, chezmoi-managed configs (Catppuccin Mocha) applied by the
`dotfiles` module — single-copy and idempotent (no secrets):

| Tool | Config |
|------|--------|
| starship | minimal prompt (`dot_config/starship.toml`) |
| ghostty | terminal theme + font (`dot_config/ghostty/config`) |
| tmux | mouse, true-color, vi copy (`dot_tmux.conf`) |
| atuin | fuzzy history, directory up-key, enter-accept, secret-scrub |
| bat | `--style=full`, Catppuccin theme |
| ripgrep | glob-ignores (node_modules/dist/build/lockfiles); via `RIPGREP_CONFIG_PATH` |
| lazygit | delta paging, Nerd Fonts v3 |
| git/delta | delta as pager (XDG `~/.config/git/config`; identity stays in `~/.gitconfig`) |

### Portable tiers (typed engine)

- `devboost terminal` — CLI/shell tools + dotfiles. Runs on any OS incl. a headless
  Ubuntu/Fedora VPS (auto-skips GUI-only pieces). Verify-guarded: re-running installs
  only what's missing; `--dry-run` previews.
- `devboost devtools` — language runtimes + frameworks (ddev, Aspire/.NET, Node, uv).

Both resolve the same declarative TOML modules/profiles as the bash engine, with a
distro-package-first, pinned-upstream-fallback install ladder. See the [Install (any OS)](#install-any-os)
section above for the one-liner.

## Requirements & supported OS

- **Reference OS:** Fedora Workstation 44 (modules ship `[install].fedora` keys).
- **Engine:** bash 5, python3 ≥ 3.11, jq, `age` (for secrets). Other OSes: add `[install].<os>` keys
  (Cross-OS-via-Data) — non-Fedora modules without a key are reported unsupported, never silently skipped.
- **Tests:** `cd engine && uv run pytest` (+ `mypy --strict` + ruff).

## Docs

[architecture](docs/architecture.md) · [recovery-runbook](docs/recovery-runbook.md) ·
[adding-a-module](docs/adding-a-module.md) · [maintenance](docs/maintenance.md) ·
[obsidian-sync](docs/obsidian-sync.md) · [ventoy](docs/ventoy.md) · [vm-testing](docs/vm-testing.md) · [roadmap](docs/roadmap.md)

## Validate before shipping (in a throwaway Fedora VM)

```sh
scripts/vm-test.sh engine --iso Fedora-Live.iso        # engine-only: install Fedora, run devboost install full
scripts/vm-test.sh usb --kickstart Fedora-netinst.iso  # full USB (device-less zero-touch via ventoy/ks.cfg)
scripts/vm-test.sh usb --device /dev/sdX               # full USB (boot the real Ventoy stick, passthrough)
scripts/make-secrets.sh --out /tmp/sec                 # build the age-encrypted secrets bundle (PAT never logged)
```
Full runbook (prereqs, snapshots, what to verify): [docs/vm-testing.md](docs/vm-testing.md).
