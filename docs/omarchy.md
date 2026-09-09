# Omarchy support

> **TL;DR** — On Omarchy, `devboost install` defaults to the **`omarchy`** profile and
> installs only the layer Omarchy does not already own: the configured dev stacks, the
> editor + LSP provisioning, secrets/SSH bootstrap, and the CLI tools Omarchy leaves out.
> `omarchy update` stays the one and only system updater.

Omarchy is [DHH's Arch + Hyprland distribution](https://omarchy.org/). Supporting it is
not the same job as supporting Arch, because Omarchy is an opinionated *platform*: it
ships the desktop, system-resilience, multimedia and NVIDIA layers dev-boost installs on
Fedora, and it packages several tools dev-boost otherwise pins itself. Treating it as
"Arch with a nice theme" would mean fighting it on every update.

## How detection works

Omarchy declares `ID=omarchy` and `ID_LIKE=arch` in `/etc/os-release`. `osinfo.detect()`
parses **both**, and `family_of()` falls back through `ID_LIKE` when the id itself is
unknown — so Omarchy resolves to the `arch` family and every `OsMap`/`per_os` strategy
selects its `arch=` entry.

This matters more than it looks. Before it, Omarchy resolved to a family named
`"omarchy"`, and `OsMap.get()` silently returned `default` (usually `None`) for every
lookup — so implementing `Pacman` on its own would have been dead code. The same fallback
gives any future Arch/Debian/Fedora derivative the right family for free.

## Packages: pacman, the AUR, and Omarchy's own helpers

`pkg.manager_for()` returns `Pacman` for the `arch` family.

- **Official repos** — `pacman -S --needed --noconfirm`. When `omarchy-pkg-add` is on
  PATH, dev-boost delegates to it instead: it is idempotent, verifies the package actually
  registered, and manages its own privilege elevation, so we never wrap it in `sudo`.
- **AUR** — `pkg.install_aur()`, preferring `omarchy-pkg-aur-add`, then `yay`, then
  `paru`. Never run as root (helpers refuse). It is deliberately a *separate* function
  from `install()`: the AUR is not a repo you add but a build service you invoke, and it
  carries a different trust model, so a module opts in by name.
- **Never `pacman -Sy`.** Syncing the package database without upgrading is a *partial
  upgrade* — the standard way to break a rolling-release box. `refresh_index()` is a
  deliberate no-op on Arch; syncing belongs to `omarchy update`, which snapshots first.
- **`add_repo()` raises.** Arch has no per-package repo mechanism, so a module carrying a
  `DnfRepo`/`AptRepo` source that does not apply here fails loudly instead of silently
  doing nothing.

## What dev-boost does *not* install on Omarchy

Two different mechanisms, for two different reasons:

| Mechanism | Meaning | Reported as |
|---|---|---|
| `families = (...)` | The module cannot run here at all — it needs dnf, apt or GRUB. | dropped from the plan |
| `provided_by = ("omarchy",)` | The platform already covers this concern. | `provided-by-omarchy` |

`provided_by` exists so that a module which does nothing still *says why*: the
constitution requires unsupported modules be reported, never silently skipped.

**Dropped (wrong OS):** `rpmfusion`, `dnf-tune`, `fedora-third-party`, `snapper-dnf-hook`,
`dnf-automatic-security`, `snapper`, `btrfsmaintenance`, `btrfs-assistant`, `swapfile`,
the whole `gnome` group, the Fedora/Ubuntu NVIDIA stack, and `flatpak`.

Two of those deserve a note:

- **`grub-btrfs`** — Omarchy boots **limine**, not GRUB, and already ships
  `limine-snapper-sync`. A GRUB snapshot menu is not merely Fedora-only here, it is wrong
  for the bootloader in use.
- **`flatpak`** — not installed on Omarchy at all. Every GUI app dev-boost ships exists as
  a native package, so `FlatpakApp` subclasses declare an `arch_pkg` (official or Omarchy
  repo) or an `aur_pkg` and install that instead. Pulling in a ~1 GB Flatpak runtime to
  duplicate `obsidian`, `bitwarden`, `vlc` and `localsend` would be pure overhead.

**Provided by Omarchy:** `herdr` (Omarchy packages a *newer* release than dev-boost pins —
installing ours would be a downgrade that then fights `omarchy refresh herdr`), `wezterm`
and `nerd-fonts` (Omarchy's terminal is **foot**, themed by `omarchy theme set` and routed
through `xdg-terminal-exec`), `flameshot` (Hyprland capture goes through
`omarchy capture ...`), `va-hwaccel`, `thermald` and `power-profiles-daemon`.

The `omarchy` profile is `full` minus `gnome` and `multimedia` — Arch ships codecs
unencumbered, so the RPM Fusion / restricted-extras swaps that profile exists to perform
have nothing to do here.

## Dotfiles: a tenant in `~/.config`, not the landlord

**Yes, you still get the dotfiles** — they are just delivered differently.

Omarchy owns `~/.bashrc` (it bootstraps `OMARCHY_PATH` and sources the Omarchy rc) and
ships its own `btop`, `lazygit`, `starship`, `herdr`, `tmux` and `git` configs. During
`omarchy update`, migrations call `omarchy-refresh-config`, which does
`cp -f <default> <user file>` (keeping a `.bak`). A chezmoi-managed file at one of those
paths loses that race on every update and then reports drift forever.

So dev-boost:

1. Splits its shell config into **`~/.config/devboost/shell.bash`** — the whole portable
   body (PATH additions, prompt, history, tool initialisers, and the `dev` / `expose` /
   `tsdev-sync` / `pw-*` helpers). On Fedora and Ubuntu, `~/.bashrc` simply sources it.
2. Ships a templated **`.chezmoiignore`** that, on Omarchy only, skips the eight paths the
   platform owns.
3. Has the **`bash-config`** module append one guarded `source` line to Omarchy's own
   `~/.bashrc`, in the user-editable section Omarchy explicitly invites you to use. It is
   idempotent and never rewrites the file.

Everything without an Omarchy counterpart — `atuin`, `ripgrep`, `bat`, `fresh`, `caddy`,
`fleet`, `systemd` user units, `~/.claude`, `~/.local/bin` — applies unchanged.

## Credentials without a USB

`secrets` normally reads an `age`-encrypted bundle provisioned on the USB — right for the
zero-touch path, pointless friction on a box you installed yourself. It now falls back to
an authenticated GitHub CLI (offered by name, never silently adopted) or an interactive
prompt, so no bundle is required. Unattended runs still never block.

This is **not Omarchy-specific** — see **[credentials.md](credentials.md)** for the full
resolution order, the interactive menu, and what `verify()` accepts.

The only Omarchy-flavoured detail: if you do want the reproducible bundle,

```bash
omarchy pkg add age jq
./scripts/make-secrets.sh --out ~/.config/devboost/bootstrap
export DEVBOOST_BOOTSTRAP_DIR=~/.config/devboost/bootstrap
```

Keep it under `$HOME`, not `/opt`: the Kickstart path uses `/opt/dev-boost` because
firstboot runs as root, but you run `devboost` as yourself and a root-owned `0600` private
key would be unreadable.

## Updating: delegate, don't duplicate

Building a second update path next to `omarchy update` would be the worst outcome of this
port: two tools racing over pacman, with dev-boost skipping the pre-update snapshot.

| Layer | Owner |
|---|---|
| System + AUR packages, mise runtimes | `omarchy update` |
| dev-boost's own pinned tooling | `devboost install --update` |

The **`omarchy-update-hook`** module registers a `post-update` hook at
`~/.config/omarchy/hooks/post-update.d/devboost-update`, which `omarchy update` runs after
packages and migrations. One `omarchy update` then brings the OS *and* the dev stack
current, with a rollback snapshot already taken. The hook exits `0` even on failure: by
then the system update has succeeded, and the dev-layer refresh is separable and safely
re-runnable.

On vanilla Arch there is no `omarchy` CLI and the module is a clean no-op.

## Known gaps

- **No CI runner.** A vanilla Arch container exercises the pacman path; the
  Omarchy-specific delegation (`omarchy-pkg-add`, hooks, refresh semantics) needs a real
  VM or an Omarchy box. Everything here is unit-tested against a fake executor.
- **AUR is unreviewed third-party build scripts.** `ddev-bin`, `visual-studio-code-bin`,
  `bruno-bin` and `gearlever` are all AUR. Aspire deliberately stays on
  `dotnet tool install -g` rather than the four-day-old `aspire-cli` AUR package.
- **`brain-host` on Arch is implemented but unexercised.** `browser-view` and `caddy`
  gained Arch branches (noVNC/websockify come from the AUR); no one has run
  `devboost brain` on an Arch box yet.
- **`devboost usb` does not build Omarchy media.** Omarchy has its own installer ISO and
  first-run provisioning; duplicating it in `catalog.toml` would add risk, not capability.
- **Rolling release.** Arch moves faster than pinned package names. The verify-first
  install loop absorbs most of it, but expect more churn than Fedora produced.
