# dev-boost

From a fresh laptop to a fully-configured developer workstation in **minutes**, with effectively
zero config — delivered by an unattended **Ventoy USB** (primary: `curl … | bash`; bonus: zero-touch
Kickstart). "Production ready" means the box can **build, out of the box**: Laravel (ddev),
.NET + Aspire, Python (uv), Next.js/React (web), React Native + Expo (Android) — plus editors
(VS Code + fresh), GUI apps (Obsidian w/ GitHub sync, Bruno, Bitwarden, …), terminal/shell/desktop
(wezterm + starship + tmux + GNOME), all restored from chezmoi-managed dotfiles. A bad update is a
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

**Or build a bootable USB online** (install the builder without configuring this machine, then build):
```bash
curl -fsSL https://raw.githubusercontent.com/adams100111/dev-boost/main/scripts/get.sh | bash -s -- usb
sudo devboost installer            # wizard: pick the USB, confirm the wipe
```
`-- usb` also downloads the Ventoy injection archive, so `installer` works with no clone/build; it
auto-fetches Ventoy + the Fedora ISOs at build time. See [docs/ventoy.md](docs/ventoy.md).

Releases are published automatically on each `v*` tag; `/latest/` always tracks the newest.

## Quick start — from the repo

Secrets (a GitHub PAT) are pre-provisioned once on the USB (`age`-encrypted); the GPU vendor is
**auto-detected** (no flag). The only possibly-interactive moment is a one-time Secure-Boot MOK
enrollment on NVIDIA when Secure Boot is on.

## Profiles

<!-- BEGIN generated profiles table (scripts/gen_profiles_table.py) -->
| Profile | Modules |
|---|---|
| `apps` | `obsidian`, `bruno`, `bitwarden`, `flameshot`, `localsend`, `vlc`, `gearlever`, `obsidian-sync` |
| `base` | `secrets`, `ssh-setup`, `rpmfusion`, `dnf-tune`, `fedora-third-party`, `flatpak`, `coreutils`, `git`, `curl`, `wget`, `unzip`, `jq`, `htop`, `ripgrep`, `fd`, `fzf`, `tmux`, `build-tools`, `mise`, `chezmoi`, `chezmoi-repo`, `docker`, `docker-build-gc` |
| `brain-host` | `mosh`, `caddy`, `crossarch-build` |
| `brain-tools` | `herdr`, `herdr-plugins` |
| `cli` | `eza`, `bat`, `btop`, `zoxide`, `atuin`, `direnv`, `delta`, `lazygit`, `lazydocker`, `dust`, `duf`, `sd`, `yq`, `gh`, `tealdeer`, `tpm`, `tmux-persist`, `fastfetch`, `claude-code` |
| `data` | `data-services` |
| `dev-hygiene` | `aspire-gc` |
| `devops` | `devops-tools`, `devops-lsp` |
| `devtools` | `web-runtimes`, `uv`, `python-lsp`, `web-lsp`, `dotnet-sdk`, `aspire`, `dotnet-lsp`, `ddev`, `playwright` |
| `dotnet` | `dotnet-sdk`, `aspire`, `dotnet-lsp` |
| `editors` | `vscode`, `fresh`, `fresh-lsp` |
| `full` | `base`, `cli`, `shell`, `gnome`, `multimedia`, `editors`, `python`, `web`, `laravel`, `dotnet`, `data`, `devops`, `react-native`, `apps`, `system`, `dev-hygiene`, `remote` |
| `gnome` | `gnome-settings`, `gnome-extensions`, `gnome-manager-apps` |
| `gnome-aesthetics` | `gnome-aesthetics-bundle` |
| `gnome-theme` | `gnome-theme-bundle` |
| `hardware-nvidia` | `nvidia-akmod`, `cuda`, `libva-nvidia-driver`, `secureboot-mok`, `nvidia-resign-service`, `nvidia-container-toolkit`, `nvidia-driver-ubuntu` |
| `laravel` | `ddev`, `ddev-remote`, `laravel-lsp` |
| `multimedia` | `ffmpeg-full`, `codecs`, `va-hwaccel`, `openh264`, `ffmpeg-ubuntu`, `codecs-ubuntu` |
| `optional-agents` | `herdr`, `herdr-plugins` |
| `optional-editors` | `neovim`, `jetbrains-toolbox` |
| `python` | `uv`, `python-lsp` |
| `react-native` | `web-runtimes`, `android-sdk`, `expo` |
| `remote` | `tailscale`, `mosh` |
| `security-cli` | `pass`, `pass-store` |
| `server` | `tailscale`, `server-firewall`, `zram`, `restic-b2`, `tmux-persist`, `docker`, `docker-build-gc` |
| `shell` | `starship`, `bash-config`, `wezterm`, `nerd-fonts`, `dotfiles`, `claude-statusline`, `claude-notify`, `wl-clipboard` |
| `system` | `snapper`, `snapper-dnf-hook`, `grub-btrfs`, `btrfs-assistant`, `btrfsmaintenance`, `fwupd`, `power-profiles-daemon`, `thermald`, `smartmontools`, `dnf-automatic-security`, `restic-backup`, `earlyoom`, `swapfile`, `gpu-detect` |
| `term` | `terminal` |
| `terminal` | `coreutils`, `git`, `curl`, `wget`, `unzip`, `jq`, `mise`, `chezmoi`, `ripgrep`, `fd`, `fzf`, `bat`, `eza`, `btop`, `zoxide`, `atuin`, `direnv`, `delta`, `lazygit`, `dust`, `duf`, `sd`, `yq`, `gh`, `tealdeer`, `fastfetch`, `tmux`, `fresh`, `starship`, `bash-config`, `dotfiles`, `wezterm`, `nerd-fonts`, `claude-statusline` |
| `web` | `web-runtimes`, `web-lsp` |

| Module | Category | Description |
|---|---|---|
| `agent-sudo` | server | Passwordless sudo for your user — so agents/automation never hang on a prompt. |
| `android-sdk` | react-native | Android SDK (cmdline-tools + platform/build-tools) + JDK via mise. |
| `aspire` | dotnet | Aspire CLI (dotnet global tool). |
| `aspire-gc` | dev-hygiene | Hourly GC of orphaned Aspire/dev containers (systemd --user timer). |
| `atuin` | cli |  |
| `bash-config` | shell | Verify the dotfiles-applied bash init (starship + devboost markers). |
| `bat` | cli |  |
| `bitwarden` | apps | Bitwarden desktop. |
| `bruno` | apps | Bruno API client. |
| `btop` | cli |  |
| `btrfs-assistant` | system | GUI for snapshots/subvolumes. |
| `btrfsmaintenance` | system | Scheduled BTRFS balance/scrub/trim. |
| `build-tools` | base | Compiler toolchain + common build dependencies. |
| `caddy` | brain-host | Caddy — locally-trusted reverse proxy (tls internal) for brain dev UIs. |
| `chezmoi` | base | Install the chezmoi dotfiles manager. |
| `chezmoi-repo` | base | Clone + apply the managed dotfiles repo via the credential store. |
| `claude-code` | cli | Claude Code CLI (npm; node via mise). |
| `claude-notify` | shell | Ping ntfy (phone) on Claude task-done / needs-input via Stop/Notification hooks. |
| `claude-statusline` | shell | Point Claude Code's statusLine at the managed ~/.claude/statusline.sh. |
| `codecs` | multimedia | Install the @multimedia codec group (Fedora-only via RPM Fusion). |
| `codecs-ubuntu` | multimedia | ubuntu-restricted-extras + libavcodec-extra (Ubuntu-only). |
| `coreutils` | base |  |
| `crossarch-build` | brain-host | Rootless podman + qemu binfmt for capped multi-arch (amd64+arm64) builds. |
| `cuda` | hardware-nvidia | CUDA toolkit (Fedora-only via RPM Fusion). |
| `curl` | base |  |
| `data-services` | data | Containerized data services (postgres/valkey/dbgate) compose template. |
| `ddev` | dev-stacks | Container-based Laravel/PHP dev orchestrator (no host php/composer). |
| `ddev-remote` | dev-stacks | On a server, bind ddev's router to all interfaces (tailnet-reachable projects). |
| `delta` | cli |  |
| `devops-lsp` | editors | tofu-ls for Terraform/OpenTofu (fresh). |
| `devops-tools` | devops | OpenTofu/kubectl/helm/k9s via mise. |
| `direnv` | cli |  |
| `dnf-automatic-security` | system | Automatic security-only dnf updates. |
| `dnf-tune` | base | Tune dnf.conf (parallel downloads, fastest mirror). |
| `docker` | base | Container engine (daemon enabled; invoking user added to docker group). |
| `docker-build-gc` | base | Cap Docker's build cache (daemon.json builder.gc) so it can't fill the disk. |
| `dotfiles` | shell | Apply the in-repo chezmoi dotfiles source. |
| `dotnet-lsp` | dotnet | csharp-ls + csharpier (dotnet global tools). |
| `dotnet-sdk` | dotnet | .NET 10 LTS SDK. |
| `duf` | cli |  |
| `dust` | cli |  |
| `earlyoom` | system | Userspace OOM killer (dev-protecting). |
| `expo` | react-native | React Native / Expo project template (npx-only; no global expo-cli). |
| `eza` | cli |  |
| `fastfetch` | cli |  |
| `fd` | base |  |
| `fedora-third-party` | base | Enable Fedora third-party repositories. |
| `ffmpeg-full` | multimedia | Swap ffmpeg-free for the full ffmpeg from RPM Fusion (Fedora-only). |
| `ffmpeg-ubuntu` | multimedia | ffmpeg from Ubuntu universe (Ubuntu/Debian-only). |
| `flameshot` | apps | Flameshot screenshots. |
| `flatpak` | base | Configure the (unfiltered) Flathub remote. |
| `fresh` | editors | The fresh terminal editor. |
| `fresh-lsp` | editors | Provision fresh's base LSP servers (mise-pinned) + config. |
| `fwupd` | system | Firmware updates. |
| `fzf` | base |  |
| `gearlever` | apps | Gear Lever — integrate & update AppImages (LM Studio, WezTerm, …). |
| `gh` | cli |  |
| `ghostty` | shell | GPU-accelerated terminal (optional; WezTerm is the default). |
| `git` | base |  |
| `gnome-aesthetics-bundle` | gnome | Opt-in aesthetic extras (fonts + theming helpers). |
| `gnome-extensions` | gnome | Install + enable the functional GNOME extension set (session-free via gext). |
| `gnome-manager-apps` | gnome | GNOME Tweaks + Extensions app + Extension Manager (flatpak). |
| `gnome-settings` | gnome | Apply the reference GNOME look-and-feel via a dconf dump. |
| `gnome-theme-bundle` | gnome | Opt-in reproducible GTK theme + icons (adw-gtk3 + papirus). |
| `gpu-detect` | system | Auto-detect the GPU vendor and record it for driver selection. |
| `grub-btrfs` | system | Boot into BTRFS snapshots from GRUB. |
| `herdr` | optional-agents | herdr — agent-aware terminal multiplexer (pinned binary). |
| `herdr-plugins` | optional-agents | Curated, pinned herdr plugin set. |
| `htop` | base |  |
| `jetbrains-toolbox` | optional-editors | JetBrains Toolbox app. |
| `jq` | base |  |
| `laravel-lsp` | editors | intelephense for Laravel/PHP (fresh). |
| `lazydocker` | cli |  |
| `lazygit` | cli |  |
| `libva-nvidia-driver` | hardware-nvidia | VA-API bridge for NVIDIA (Fedora-only via RPM Fusion). |
| `localsend` | apps | LocalSend file sharing. |
| `mise` | base | Install mise runtime version manager; migrate nvm/sdkman init blocks. |
| `mosh` | remote | Mosh — roaming-resilient terminal transport (client + mosh-server). |
| `neovim` | optional-editors | Neovim editor. |
| `nerd-fonts` | shell | JetBrainsMono Nerd Font. |
| `nvidia-akmod` | hardware-nvidia | akmod-nvidia driver (RPM Fusion, Fedora-only). |
| `nvidia-container-toolkit` | hardware-nvidia | GPU access for containers (Fedora-only via akmod deps). |
| `nvidia-driver-ubuntu` | hardware-nvidia | NVIDIA driver via ubuntu-drivers autoinstall (Ubuntu-only). |
| `nvidia-resign-service` | hardware-nvidia | Re-sign NVIDIA modules after a kernel/akmod rebuild (Fedora-only). |
| `obsidian` | apps | Obsidian notes. |
| `obsidian-sync` | apps | Provision the Obsidian vault: deploy key, clone, daily push backstop. |
| `openh264` | multimedia | Cisco OpenH264 for browser H.264 support (Fedora-only). |
| `pass` | security-cli | pass password-store CLI. |
| `pass-store` | security-cli | Initialize the GPG-backed password store (optionally cloned). |
| `playwright` | web | Playwright browsers + MCP — headless-shell on servers, full Chromium on GUI. |
| `power-profiles-daemon` | system | Power profile switching (D-Bus). |
| `python-lsp` | editors | basedpyright + ruff for Python (fresh). |
| `restic-b2` | server | Offsite encrypted backups — restic → Backblaze B2, nightly systemd timer. |
| `restic-backup` | system | Restic backup user service + timer. |
| `ripgrep` | cli | Fast recursive search (rg). |
| `rpmfusion` | base | Enable RPM Fusion free + nonfree + AppStream metadata. |
| `sd` | cli |  |
| `secrets` | base | Decrypt provisioned secrets; configure git identity + HTTPS credentials. |
| `secureboot-mok` | hardware-nvidia | Enroll a MOK so the signed NVIDIA modules load under Secure Boot (Fedora-only). |
| `server-firewall` | server | ufw baseline: deny incoming, allow SSH + tailscale0; disable exposed rpcbind. |
| `smartmontools` | system | Disk SMART monitoring. |
| `snapper` | system | BTRFS snapshots for / (retention-capped). |
| `snapper-dnf-hook` | system | dnf plugin: snapshot before/after transactions. |
| `ssh-setup` | base | Generate ed25519 key and register it with GitHub (non-blocking). |
| `starship` | shell | Cross-shell prompt. |
| `swapfile` | system | Disk swapfile sized to RAM for OOM headroom (page-out overflow above zram). |
| `tailscale` | server | Tailscale mesh VPN + Tailscale SSH (unattended via a secrets auth-key). |
| `tealdeer` | cli |  |
| `thermald` | system | Thermal management. |
| `tmux` | base |  |
| `tmux-persist` | cli | tmux-resurrect + tmux-continuum — restore tmux sessions across a reboot. |
| `tpm` | cli | tmux plugin manager. |
| `unzip` | base |  |
| `uv` | python | uv — fast Python package/project manager. |
| `va-hwaccel` | multimedia | GPU-aware VA-API hardware acceleration (Intel/AMD/NVIDIA); cross-distro. |
| `vlc` | apps | VLC media player. |
| `vscode` | editors | Visual Studio Code (Microsoft repo). |
| `web-lsp` | editors | ts/eslint/tailwind/prettier servers (fresh). |
| `web-runtimes` | web | node/pnpm/bun via mise. |
| `wezterm` | shell | GPU-accelerated terminal + multiplexer (nightly); default terminal. |
| `wget` | base |  |
| `wl-clipboard` | shell | Wayland clipboard CLI (wl-copy/wl-paste) — powers the image-paste bridge. |
| `yq` | cli |  |
| `zoxide` | cli |  |
| `zram` | server | Compressed-RAM swap (zstd, ~half RAM) — OOM insurance for long builds/agents. |
<!-- END generated profiles table -->

Stacks (`python`/`web`/`laravel`/`dotnet`/`data`/`devops`/`react-native`) are opt-in per project;
`hardware-nvidia` is auto-selected by `gpu-detect` on NVIDIA hardware; `optional-editors` is opt-in.

**`optional-agents`** — herdr (agent-aware terminal multiplexer) + a curated, pinned plugin set.
Opt-in; not part of `full`. Runs alongside tmux.

`devboost brain` provisions a sandboxed **devbrain** brain on a chosen server (installs the
`brain-host` tools + a capped, sudo-less account that runs herdr and cross-arch builds).

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

0. Build the stick once (online, no clone): `curl … get.sh | bash -s -- usb` then
   `sudo devboost installer` (interactive; add `--dry-run` to preview) — see [docs/ventoy.md](docs/ventoy.md).
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
| starship | Catppuccin prompt: minimal git, polyglot versions, RAM/disk gauges (auto-hidden inside tmux — the tmux bar owns them there), last-command exit code on failure, red `⚠` badge when resources are critical (`dot_config/starship.toml`) |
| wezterm | default terminal: OS light/dark-reactive Catppuccin, **top** tab bar (tmux owns the bottom), tmux-style keys, SSH domains, clickable links (`Ctrl+Shift+Click` / `LEADER u` — work through tmux), smart paste (clipboard image → uploaded to the VPS → path Claude reads as `[Image]`), **opt-in** RAM/disk gauges (`prefs.show_resource_gauges`) + critical-resource background alert (`dot_config/wezterm/`) |
| claude-statusline | Claude Code status line: dir · git · RAM/disk (left), model · context% · cost (right); whole row goes red when resources are critical (`private_dot_claude/statusline.sh`) |
| ghostty | optional terminal theme + font (`dot_config/ghostty/config`) |
| tmux | mouse, true-color, vi copy, **bottom** status bar with RAM/disk gauges + critical badge (visible even while a full-screen app fills the pane), session-persistence via resurrect+continuum (survives a reboot) (`dot_tmux.conf`, `dot_config/tmux/resources.sh`) |
| atuin | fuzzy history, directory up-key, enter-accept, secret-scrub, e2e-encrypted **sync** across machines (top-level keys — a prior `[settings]` nesting was silently ignored by atuin; recording wired via bash-preexec in the managed `.bashrc`) |
| claude-notify | phone push (ntfy) on Claude Code task-done / needs-input via Stop/Notification hooks; no-op until `DEVBOOST_NTFY_URL` is set (`private_dot_claude/hooks/notify.sh`) |
| bat | `--style=full`, Catppuccin theme |
| ripgrep | glob-ignores (node_modules/dist/build/lockfiles); via `RIPGREP_CONFIG_PATH` |
| lazygit | delta paging, Nerd Fonts v3 |
| git/delta | delta as pager (XDG `~/.config/git/config`; identity stays in `~/.gitconfig`) |

### Portable tiers (typed engine)

- `devboost term` — CLI/shell tools + dotfiles. Runs on any OS incl. a headless
  Ubuntu/Fedora VPS (auto-skips GUI-only pieces). Verify-guarded: re-running installs
  only what's missing; `--dry-run` previews.
- `devboost devtools` — language runtimes + frameworks (ddev, Aspire/.NET, Node, uv).
- `devboost server` — headless-VPS hardening + ops (Ubuntu/Debian): passwordless sudo for
  your user (`agent-sudo` — so Claude Code / automation never hang on a password prompt;
  visudo-validated, one-time interactive setup), Tailscale + Tailscale SSH, a ufw baseline
  (deny-in, keep SSH, open `tailscale0`, disable exposed rpcbind), zram swap, restic→B2
  nightly offsite backups, and tmux session-persistence. dev-boost's
  `system` tier is Fedora-desktop-shaped (btrfs/snapper/dnf); `server` is the Ubuntu-server
  counterpart. Dropping public `:22` and provisioning B2/Tailscale secrets stay deliberate
  operator steps.

Both resolve the same typed-Python modules + `profiles.toml`, with a distro-package-first,
pinned-upstream-fallback install ladder. See the [Install (any OS)](#install-any-os)
section above for the one-liner.

**Remote dev over Tailscale (zero-config).** Develop on the VPS, use it from the laptop:
`tsdev-sync` (laptop) mirrors the whole tailnet into `~/.ssh/config`, so `dev <host> [repo]`
ssh's in and drops you into a persistent per-repo tmux session ready to work; `ddev-remote`
binds ddev's router to the tailnet on servers; managed shell helpers make the rest one word —
`expose <port>` publishes a VPS port at `https://<host>.<tailnet>.ts.net` (auto-TLS),
`pw-server` (laptop) + `pw-connect <ws>` (VPS) run the Playwright **test runner** on the VPS
while the headed browser opens on your laptop, and `pw-mcp` (laptop) + `pw-workstation` (VPS) run the
Playwright **MCP** headed on the laptop for Claude on the VPS to drive — `pw-workstation` auto-detects
the laptop you connected from, so it works on any server from any laptop with no config. Aspire:
`expose 18888` for the dashboard. See [docs/remote-dev.md](docs/remote-dev.md).

## Requirements & supported OS

- **Reference OS:** Fedora Workstation 44 (each module implements a Fedora install path).
- **Engine:** ships as a **frozen single-file binary** — no Python or other runtime deps on the
  target; the only bash is `get.sh` + the Kickstart `%post`. Developing it needs **python ≥ 3.12 +
  `uv`**; `age` is used for the secrets bundle. Other OSes: a module adds a per-OS `Installer`
  strategy (`per_os`) — modules without one for the detected OS are reported unsupported, never
  silently skipped.
- **Tests:** `cd engine && uv run pytest` (+ `mypy --strict` + ruff).

## Docs

[architecture](docs/architecture.md) · [recovery-runbook](docs/recovery-runbook.md) ·
[adding-a-module](docs/adding-a-module.md) · [maintenance](docs/maintenance.md) ·
[obsidian-sync](docs/obsidian-sync.md) · [remote-dev](docs/remote-dev.md) · [ventoy](docs/ventoy.md) · [vm-testing](docs/vm-testing.md) · [roadmap](docs/roadmap.md)

## Validate before shipping (in a throwaway Fedora VM)

```sh
scripts/vm-test.sh engine --iso Fedora-Live.iso        # engine-only: install Fedora, run devboost install full
scripts/vm-test.sh usb --kickstart Fedora-netinst.iso  # full USB (device-less zero-touch via ventoy/ks.cfg)
scripts/vm-test.sh usb --device /dev/sdX               # full USB (boot the real Ventoy stick, passthrough)
scripts/make-secrets.sh --out /tmp/sec                 # build the age-encrypted secrets bundle (PAT never logged)
```
Full runbook (prereqs, snapshots, what to verify): [docs/vm-testing.md](docs/vm-testing.md).

## License & disclaimer

Licensed under the [MIT License](LICENSE).

**Use entirely at your own risk.** dev-boost performs destructive and system-level operations — it
**wipes the target drive** when building install media, installs/removes packages, rewrites system and
desktop configuration, and provisions secrets (GitHub PAT, SSH keys). It is provided **"as is", without
warranty of any kind** (see LICENSE), and **you alone are responsible** for any data loss, downtime, or
damage resulting from its use. Read what it does, and **test in a VM** (`scripts/vm-test.sh`) before
running it against real hardware or a drive you care about.

It's a personal workstation setup — opinionated tool choices and a specific dotfiles/secrets flow —
shared for reference and reuse, not a supported product (issues/PRs aren't guaranteed a response).
