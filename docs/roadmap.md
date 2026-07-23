# dev-boost — Spec Roadmap to Production USB

> **Update (2026-06-26):** the platform has been **fully rewritten from Bash to typed Python**
> (spec `014-python-engine-core`, design `2026-06-26-python-engine-migration-design.md`). The
> rows below describe the original Bash deliverables — now the *behavioral spec* that was ported
> to typed modules + pytest and deleted. The engine, all ~100 modules, and all commands are typed
> Python shipped as a frozen binary; only `get.sh` + the Kickstart `%post` remain bash.


**Goal:** a Ventoy USB that installs Fedora unattended and lands a fully-configured
developer workstation on a laptop in minutes — `curl … | bash` (primary) or
zero-touch Kickstart (bonus). Source of truth: `docs/superpowers/specs/2026-06-19-devboost-platform-design.md`
(§11 phasing) + `.specify/memory/constitution.md`.

**Method:** each row below is one Spec Kit cycle — `/speckit-specify → /speckit-plan
→ /speckit-tasks → /speckit-implement` — producing working, test-green software on
its own (constitution §Development Workflow). We proceed top-to-bottom.

## Status legend
✅ done · 🚧 in progress · ⬜ not started

| # | Spec (kebab name) | Delivers | Depends on | Phase | Status |
|---|---|---|---|---|---|
| 0 | `engine-core` | `lib/*`, `bin/devboost` (install/verify/list/doctor), TOML→JSON, OS detect, Kahn dep-sort, verify-guarded install loop, curl\|bash entrypoint, summary. 36 bats tests. | — | 1 | ✅ |
| 1 | `secrets-and-auth` | `secrets` + `ssh-setup` modules: locate+`age`-decrypt `secrets.age` (JSON/jq), seed git identity + `credential.helper store`, generate `id_ed25519`, **upload pubkey via GitHub API** (non-blocking, `devboost:<hostname>`). `lib/secrets.sh` + `lib/github.sh`. `doctor`/entrypoint age+secrets preflight. **118 bats tests; final review APPROVE.** | engine | 2 | ✅ |
| 2 | `base-profile` | `base` modules: `rpmfusion` (free+nonfree+appstream), `dnf-tune`, `fedora-third-party`, `flatpak` (full Flathub), `build-tools`, `mise` (+**nvm/sdkman→mise migration**), `chezmoi` (dotfiles adopt, clones `$DEVBOOST_DOTFILES_REPO` via cred store), `docker`, 11 CLI tool modules; first real `profiles.toml`; `lib/pkg.sh`; doctor mise-drift warning. **304 bats tests; final review APPROVE.** | engine, secrets | 3 | ✅ |
| 3 | `cli-and-shell` | `cli` profile (18 tools: eza/bat/btop/delta/lazygit/lazydocker/gh/claude-code/tpm/…) + `shell` profile (starship default prompt, ghostty via COPR, nerd-fonts extracted from archives, dotfiles, bash-config) + **dotfiles applied via chezmoi** from dev-boost's `dotfiles/` source (tmux imported from setup-scripts, starship.toml, ghostty config, all shell-init lines single-sourced in `dot_bashrc`). **Zero engine touch; 484 bats tests; final review APPROVE** (caught+fixed nerd-fonts no-extract bug). | base (mise, chezmoi) | 3 | ✅ |
| 4 | `gnome-desktop` | `gnome` profile: `gnome-settings` (dconf load: dark/scaling/accent/buttons/tap-to-click), `gnome-extensions` (6 functional extensions installed **session-free** via `gext` + enabled by writing `enabled-extensions`, UUID/author verified), `gnome-manager-apps` (Extensions app + Extension Manager + gnome-tweaks). Plus opt-in `gnome-aesthetics`/`gnome-theme` bundles (reproducible — no manual gnome-look.org). `lib/gnome.sh`. **Zero engine touch; 666 bats tests; final review APPROVE.** | base | 3 | ✅ |
| 5 | `multimedia-codecs` | `multimedia` profile: full ffmpeg swap, `@multimedia` codecs, **`va-hwaccel`** (GPU-aware: Intel/AMD/NVIDIA VA-API + `vainfo` verify, hybrid installs both, partial-hybrid warns on unknown vendor), OpenH264/Cisco for Firefox. **Zero engine touch; 713 bats tests; final review APPROVE** (caught+fixed partial-hybrid GPU-detection gap). | base (rpmfusion) | 3 | ✅ |
| 6 | `editors` | `editors` profile: VS Code (MS-repo `code` + curated baseline extensions) and **`fresh`** terminal editor (rpm→script→cargo install) with profile-scoped LSP + formatter provisioning — each server a mise-managed pinned tool, idempotently jq-merged into `~/.config/fresh/config.json`; always-on base set (markdown/toml/bash/yaml), per-stack rows via `lib/fresh.sh` deferred to dev-stacks. **Zero engine touch; 749 bats tests; final review APPROVE.** | base, shell | 3/4 | ✅ |
| 7 | `dev-stacks` | `laravel` (ddev-only + intelephense; Pint per-project), `dotnet` (**.NET 10 LTS** SDK + standalone **Aspire CLI**, Persistent infra; csharp-ls/csharpier), `python` (**uv** + basedpyright/ruff), `web` (node 22/pnpm/bun + ts/eslint/tailwind/prettier), `react-native` (JDK 17/Android SDK API 35/Expo; **watchman dropped**, npx-only), `devops` (**OpenTofu**/kubectl/helm 4/k9s + tofu-ls), `data` (postgres 18/**valkey**/dbgate **containers**) + per-stack `templates/`. **Zero engine touch; +130 stack/depsort/wire tests → 887 bats green; context7-verified 2026-06 pins.** | base, editors | 4 | ✅ |
| 8 | `apps-and-obsidian` | `apps` profile — 6 Flathub GUI apps (obsidian, bruno, bitwarden, flameshot, localsend, vlc; **dbgate is the `data`-stack container, not a flatpak**; DBeaver optional) + **`obsidian-sync`**: repo-scoped **write deploy key** + isolated SSH alias, clone → `~/Vault`, auto-open registration (flatpak + native), Obsidian Git plugin pre-seed (pull-on-open + commit-and-sync), daily persistent `systemd --user` push backstop, `$VAULT_DIR`. **Zero engine touch** (reuses lib/github.sh + lib/secrets.sh; new feature-local lib/vault.sh); registry/context7-verified IDs/keys 2026-06; +48 tests → 935 bats green. | base (flatpak), secrets (GitHub API) | 5 | ✅ |
| 9 | `lifecycle-and-dev-hygiene` | `add`/`export`/`diff`/`update`/`self-update` CLI verbs (lib/lifecycle.sh) + committed deterministic `devboost.lock` (sorted TSV) + config/mise.toml seed + **`dev status/gc/down`** (lib/devhygiene.sh; precise orphan GC = label `persistent=false` AND creator-PID dead, never touches persistent/live) + `aspire-gc` hourly user timer module. **Engine-feature (TDD); existing install/verify/list/doctor unchanged; +26 tests → 961 bats green.** | engine, modules exist | 6 | ✅ |
| 10 | `system-resilience` | `system` profile: snapper + grub-btrfs + `python3-dnf-plugin-snapper`, btrfsmaintenance, fwupd, tuned-ppd/thermald (detect), earlyoom (dev-protecting), smartmontools, dnf-automatic-security, restic-backup. Plus **`gpu-detect`** (lspci → **auto-select** intel/amd/nvidia driver path, no flag) carrying the ported `../setup-scripts/fedora/nvidia/` fixes: MOK state machine, **CRC64→CRC32 module fix**, `nvidia-resign.service`, `libva-nvidia-driver`, nvidia-container-toolkit, `doctor --gpu`. + `optional-editors`. **12 system + 6 nvidia + gpu-detect + 2 optional-editors modules; lib/gpu.sh + doctor --gpu (plain doctor unchanged); design §10 oracle, all stubbed; +119 tests → 1080 bats green.** | base | 7 | ✅ |
| 11 | `ventoy-kickstart-usb` | **The shippable USB.** `ventoy/make-usb.sh`, `ventoy.json` (menu/auto_install/injection), `ks.cfg` (§10c **BTRFS subvolume layout** + `compress=zstd:1` + `/var/lib/gdm`), `devboost-firstboot.service` (self-disabling first-boot oneshot). Two boot paths. make-usb.sh refuses non-removable/system/partition/loop targets. *(Windows `install.ps1` is a thinner follow-on.)* **Artifacts only (zero engine touch); design §9/§10c oracle; hermetic tests; +11 → 1091 bats green.** | all installable modules | 8 | ✅ |
| 12 | `docs-and-readme` | Front-door `README.md` (generated profiles table via `scripts/gen-profiles-table.sh` + commands), `docs/`: architecture, recovery-runbook, adding-a-module, maintenance, obsidian-sync, ventoy. **Drift-gated (README lists every profile+verb); docs-only (zero engine touch); +5 → 1096 bats green.** | all | 9 | ✅ |
| 13 | `pass-opt-in` *(opt-in, off critical path)* | `security-cli` opt-in profile: `pass` CLI password-store (GPG+git), complementing the default Bitwarden GUI. Designs GPG-key provisioning for **unattended** decrypt (passphrase-less / gnome-keyring) + password-store git repo — analogous to how `secrets` provisions `age`. NOT in `full`. *(User-requested 2026-06-20.)* **Delivered: pass + pass-store (GPG key + `pass init` + optional store-repo clone, unattended; opt-in, NOT in full); zero engine touch; +8 → 1104 bats green.** | secrets, base | — | ✅ |

## Critical path to first end-to-end USB install
`1 secrets-and-auth → 2 base-profile → 3 cli-and-shell` (minimal usable workstation)
`→ 11 ventoy-kickstart-usb` (packages + boots it). Specs 4–10 thicken the install
toward the full `production` set; spec 12 finalizes docs (drafted alongside each).

## Definition of done (platform — from design §1/§10)
- One command / zero-touch Kickstart → ready workstation in minutes, no prompts.
- **Builds out of the box:** Laravel (ddev), .NET + Aspire (`dotnet new`+`aspire`),
  Python (`uv run`), Next.js/React (`pnpm dev`), React Native + Expo **Android** build.
- Editors (VS Code + `fresh`), GUI apps, and terminal/shell/desktop configs all present
  and chezmoi-restored.
- Obsidian opens `~/Vault`, round-trips to GitHub automatically.
- **GPU auto-detected** — correct driver/VA-API installed with no flag (Intel/AMD clean;
  NVIDIA clean except one-time MOK screen when Secure Boot on).
- `devboost verify --profile full` fully green; re-running install is a no-op.
- "Fedora snapshots" entry in GRUB; bad update recoverable by reboot.
- Adding a tool = one file; adding an OS = one key.

## Verification status (proven vs. seam vs. unverified)

Honest coverage as of the 0.1.62 line — what is *proven working* versus *implemented but
unexercised*. This distinction was expensive to learn: the whole USB→install chain was a
stack of individually-buggy layers, each of which hid the next, so "the code is written" did
not mean "it works". Keep this current.

**Proven (exercised end-to-end this cycle):**
- `devboost installer` builds a correct Ventoy USB on Fedora/x86_64: Ventoy installs, the
  data partition mounts, both ISOs + payload + `ks.cfg` + `ventoy.json` are staged, marker
  written. Verified on real SanDisk hardware.
- `ks.cfg` parses under Anaconda's own F44 pykickstart handler (CI gate).
- `%pre` disk selection: skips zram/loop/dm and the boot media, refuses on zero or multiple
  candidates, honours `devboost.disk=` (executed tests against faked lsblk/sysfs/cmdline).

**Implemented but NOT yet verified on real hardware (the remaining risk):**
- **Zero-touch install to a booted, provisioned desktop.** Has never completed once —
  Anaconda only started getting *past* kickstart parsing at 0.1.62. The next failure, if any,
  is new (partitioning / `%post` / firstboot).
- **`devboost install full` to green + no-op re-run.** The 100+ modules and the five DoD
  build targets (Laravel/ddev, .NET+Aspire, Python/uv, Next.js, RN+Expo Android) have not
  been watched to completion on a fresh box this cycle.
- **GPU auto-detect → `hardware-nvidia` injection.** Mechanism verified in code
  (`gpu-detect` marker → `plan.build_plan`); never run on real NVIDIA hardware.
- **Secrets end-to-end** (build `--secrets` → `%post` stage → firstboot decrypt → Obsidian
  sync). Every leg was individually buggy at some point; the whole chain is unproven.

**Shipped, opt-in:**
- herdr optional agent-multiplexer — pinned binary + 3 vetted pinned plugins + chezmoi config,
  under the opt-in `optional-agents` profile (runs alongside tmux). Spec:
  `docs/superpowers/specs/2026-07-22-herdr-optional-app-design.md`.
- **Remote fleet — M1 (tailnet reach):** laptops (`full`) now join the tailnet and ship
  Mosh via the new `remote` spine profile. (M2 brain overlay + M3 DX/docs to follow.)
- **Remote fleet — M2 pt1 (brain tooling):** `caddy` + `crossarch-build` modules and the
  `brain-host`/`brain-tools` opt-in profiles; `agent-sudo` removed from the default `server`
  profile (now explicit opt-in). (M2 pt2: `devbrain` account + `devboost brain` wrapper.)
- **Remote fleet — M2 pt2 (sandboxed brain):** `devboost brain` provisions the capped,
  sudo-less `devbrain` account (privilege=none + cgroup caps, bootstraps `brain-tools`) and
  installs the `brain-host` tools in one command. (M3: `fleet` DX verbs + operator guide.)

**Seam only — deliberately not implemented, do not mistake for working:**
- **Ubuntu/Debian.** The catalog offers `ubuntu-26.04`, the wizard lets you pick it,
  `autoinstall.py` renders subiquity `user-data`, and modules carry `Apt`/`debian` branches —
  but the Ubuntu install path is a per-OS *seam* (Spec 014: Fedora reference, OS-dispatch
  seams for later OSes). Several module branches are literally `# seam — not implemented`.
- **aarch64.** The release builds and publishes a `devboost-aarch64` binary and the catalog
  pins aarch64 ISOs, but no aarch64 build or install has been exercised.
