# dev-boost — Developer Recovery & Bootstrap Platform (2026)

**Status:** Design approved — ready for implementation planning
**Date:** 2026-06-19
**Author:** adams100111@gmail.com (with Claude Code)

---

## 1. Goal

From a **fresh machine**, with **zero interaction**, reach a fully-configured
developer workstation **in minutes** — able to build **Laravel, .NET, Python, and
React Native** apps, with **Obsidian** installed, synced to a GitHub repo, and its
notes directory wired into the OS, plus per-stack tooling and best-practice
configs.

Two entry points:

1. **Primary — one command** from a freshly-installed Fedora:
   `curl -fsSL <url>/install.sh | bash` (or `git clone … && ./install.sh`).
2. **Bonus — zero-touch** via a Kickstart `ks.cfg` on the Ventoy USB that
   installs the OS and runs the bootstrap on first boot.

### Priorities (in order)
Reproducibility · Unattended · Fast · Maintainability (Day-2) · Extensibility ·
Long-term sustainability.

### Non-goals
- Not a generic config-management framework (no Ansible/Salt). A small,
  legible bash engine + declarative data is deliberate.
- macOS/Arch are *schema-supported* but **Fedora is the only reference
  implementation** in this build; Ubuntu/Windows get a thinner path.

---

## 2. Architecture

The system is an **engine + data** design. A small Bash engine reads
self-contained **module manifests** and a **profiles** file. Every installable
thing in the platform is a module. The engine never changes when you add tools,
stacks, or operating systems.

```text
dev-boost/                         # single version-controlled monorepo
├── install.sh                     # thin entrypoint (curl|bash friendly) → bin/devboost
├── bin/
│   └── devboost                   # the engine CLI (bash)
├── lib/                           # engine internals
│   ├── log.sh                     # logging, color, summary report
│   ├── toml.sh                    # TOML → shell (via python3 tomllib)
│   ├── os.sh                      # OS/distro/arch detection
│   ├── depsort.sh                 # topological sort of `requires`
│   └── github.sh                  # PAT + SSH-key-upload helpers
├── modules/                       # THE extension point — one file/folder per tool
│   ├── git.toml                   # simple → declarative
│   ├── ddev/                      # complex → escape hatch
│   │   ├── module.toml
│   │   └── install.sh
│   └── …
├── profiles.toml                  # named bundles → module sets
├── devboost.lock                  # resolved exact versions (reproducibility)
├── config/
│   ├── mise.toml                  # pinned runtime versions
│   └── vscode-extensions.txt
├── dotfiles/                      # chezmoi source tree (imported from setup-scripts)
├── notes-vault/                   # Obsidian vault skeleton
├── templates/                     # project starters per stack
├── workstation-config/            # generated inventory/exports (state tracking)
├── ventoy/                        # USB layout + ks.cfg + Bootstrap/ + Docs/
├── windows/                       # install.ps1 (PowerShell engine, same manifests)
└── docs/                          # architecture, runbook, adding-a-module, maintenance
```

**Engine language:** pure Bash — the only interpreter guaranteed on a fresh
Fedora. TOML is parsed by Python 3 `tomllib` (ships with Fedora 40+/Ubuntu
24.04+); the first bootstrap step guarantees `python3` + `jq` + `age` exist.
Windows gets a parallel PowerShell engine reading the same `.toml` manifests.

---

## 3. Module system (the extension point)

### 3.1 Schema

A simple module is one TOML file. A complex module is a folder with
`module.toml` + an `install.sh` escape hatch (which receives the engine's env and
helpers).

```toml
# modules/bun.toml
name        = "bun"
category    = "javascript"
description = "Bun runtime"
requires    = ["mise"]                  # installed before this; drives topo-sort
profiles    = ["web", "react-native"]   # optional self-tagging

[install]
default = "mise use -g bun@latest"      # used for any OS lacking a specific key
fedora  = "…"                           # optional per-OS override
ubuntu  = "…"
macos   = "…"
windows = "winget install Oven-sh.Bun"

verify  = "bun --version"               # success ⇒ already installed ⇒ skip

[update]
default = "mise upgrade bun"            # optional; how this module updates itself
```

**Rules every module obeys:** declares `verify`, at least one `[install]` key,
and (if it has dependencies) `requires`. Adding a tool = one file. Adding an OS =
one key. Adding a stack = a new profile referencing modules.

### 3.2 Escape hatch (`install.sh`)

For tools with real logic (DDEV, Android SDK, .NET, NVIDIA). The engine sources
`lib/log.sh`, exports detected OS/arch, secrets env, and helper functions
(`have`, `as_root`, `dnf_install`, `flatpak_install`), then runs `install.sh`.
`module.toml` still provides `name/requires/verify/profiles`.

### 3.3 Cross-OS resolution

The engine picks the install command by precedence:
`<exact-distro>` → `<os-family>` → `default`. If none match, the module is
reported **unsupported on this OS** (surfaced by `doctor`), not silently skipped.

---

## 4. Engine CLI (`bin/devboost`)

| Verb | Behavior |
|------|----------|
| `install [--profile X[,Y]] [--force] [--strict] [--secrets PATH]` | Expand profiles → topo-sort by `requires` → per module: `verify` (skip if green unless `--force`) → run best-match `install` → re-verify → record. Non-strict continues past failures; `--strict` aborts. Ends with a timed summary. |
| `verify [--profile X]` | Audit a machine: run every `verify`, report green/red. No changes. |
| `list [--profile X]` | List modules / profiles and their resolution for this OS. |
| `doctor` | Preflight: disk, network, OS detection, **OS support matrix** (which modules lack a key for this OS), secrets file presence. |
| `export` | Snapshot actual installed state (dnf, flatpak, `mise ls`, VS Code extensions) → `workstation-config/exports/`. |
| `diff` | Compare declared (repo) vs actual (machine); surface drift. |
| `update [--profile X]` | Run `[update]` steps / check upstream, **propose** new pinned versions into `config/mise.toml` + `devboost.lock`, refresh dnf/flatpak/extensions. Prints a diff; **never auto-commits**. |
| `add <name> [--folder]` | Scaffold a new module from a template (the friction-free path for new toolkits). |
| `self-update` | `git pull` the dev-boost repo, then re-validate. |

**Properties:** idempotent (verify-guarded), resumable (re-run does only what's
missing), legible (a failure names the module + the exact command that failed).

---

## 5. Profiles & module library (full set)

`full` is the default. Stacks compose by listing modules or other profiles.

```toml
# profiles.toml
[profiles]
base         = ["coreutils","git","curl","wget","unzip","jq","htop","ripgrep","fd","fzf","tmux",
                "build-tools","flatpak","mise","chezmoi","docker","secrets","ssh-setup"]
cli          = ["eza","bat","zoxide","atuin","direnv","delta","lazygit","lazydocker","btop",
                "dust","duf","sd","yq","gh","tealdeer","tpm"]
shell        = ["oh-my-posh","bash-config","ghostty","nerd-fonts"]
editors      = ["vscode"]                       # neovim / jetbrains-toolbox are opt-in (below)
laravel      = ["docker","ddev","composer","php","laravel-installer"]
dotnet       = ["dotnet-sdk","aspire"]
python       = ["uv","python"]
web          = ["node","pnpm","bun"]
react-native = ["node","jdk","android-sdk","android-cmdline","expo","watchman"]
devops       = ["terraform","kubectl","helm","k9s"]
data         = ["postgres-container","redis-container","dbeaver"]
apps         = ["obsidian","obsidian-sync","bruno","bitwarden","flameshot","localsend"]
full         = ["base","cli","shell","editors","laravel","dotnet","python","web",
                "react-native","devops","data","apps"]

# opt-in, NOT in full:
optional-editors = ["neovim","jetbrains-toolbox"]
hardware-nvidia  = ["rpmfusion","nvidia-akmod","cuda","secureboot-mok","nvidia-resign-service"]
```

Run examples:
`devboost install` (= full) · `devboost install --profile base,python,web` ·
`devboost install --profile full,hardware-nvidia,optional-editors`.

**Databases are containers**, not host installs (per spec): `data` modules ship a
`compose.yaml` in `templates/` and wrappers, not local PostgreSQL/Redis.

---

## 6. 2026 stack catalog & imported config

### 6.1 Imported verbatim from `../setup-scripts` (existing curation)
- **tmux** 3.6+ config (mouse, 50k scrollback, true-color/undercurl, 1-based
  index, vim pane nav, cwd-preserving splits, vi copy-mode, `wl-copy`).
- **oh-my-posh** — catppuccin theme + transient prompt + the split **Claude Code
  statusline** (left/right groups, `$COLUMNS` justify, `claude-statusline.sh`).
- **JetBrainsMono / Meslo Nerd Font Mono** (+ the Ptyxis `Mono` font gotcha
  documented).
- **NVIDIA + CUDA + Secure-Boot MOK signing + kernel-update resign service** →
  ported into the opt-in `hardware-nvidia` profile (machine-specific, off by
  default).

### 6.2 New 2026 additions
- **Terminal:** Ghostty as primary (shipped config: JetBrainsMono Nerd Font Mono,
  catppuccin-mocha, keybinds), **Ptyxis kept** as the GNOME fallback.
- **Shell:** stay on **bash** (oh-my-posh already wired); add **atuin** (history),
  **zoxide** (cd), **fzf**, **direnv** + curated aliases/functions in
  `dotfiles/bash/`.
- **Modern CLI:** eza, bat, delta, lazygit, lazydocker, btop, dust, duf, sd, yq,
  gh, tealdeer.
- **GUI apps (flatpak):** Obsidian, Bruno, DBeaver, VS Code, Bitwarden,
  Flameshot, LocalSend.
- **Editors:** VS Code primary (+ extension list); **Neovim/LazyVim** and
  **JetBrains Toolbox** (PhpStorm for Laravel, Rider for .NET) shipped as
  `optional-editors`.

### 6.3 Best-practice configs (data, in `dotfiles/` + `config/`)
Pinned runtime versions; opinionated `.gitconfig` (delta, aliases, sane
defaults); global `.gitignore`; `.editorconfig`; VS Code `settings.json` +
extensions; hardened `~/.ssh/config`; `direnv`/`mise` integration; per-stack
project starters in `templates/` (laravel, dotnet, python, nextjs,
react-native).

---

## 7. Unattended auth & Obsidian sync

The "no pause" requirement means credentials are **pre-provisioned**, never
prompted. The original spec's "show key, wait for GitHub" step is removed.

Boot sequence (all non-interactive):

1. `doctor` preflight (net/disk/os/secrets present).
2. **`secrets` module:** locate `secrets.age` (Ventoy USB, or `--secrets PATH`),
   decrypt with an `age` keyfile on the USB (zero-touch) or one passphrase →
   export `GITHUB_PAT`, `GIT_USER`, `GIT_EMAIL`. The secret is **never in git**.
3. Configure git identity + `credential.helper store` seeded with the PAT →
   private HTTPS clones work immediately.
4. Generate `id_ed25519`; **upload the public key to GitHub via API** (the PAT) —
   non-blocking, no pause; the machine ends with a real registered SSH key.
5. Clone `dotfiles` → `chezmoi apply`; clone `notes-vault` → `~/Vault`; clone
   `templates`.
6. **Obsidian:** register `~/Vault` in `~/.config/obsidian/obsidian.json` (opens
   automatically); pre-seed `.obsidian` with the **Obsidian Git** plugin
   (auto-pull on open, auto-commit/push on a timer) + a systemd user timer as a
   belt-and-suspenders push; export `$VAULT_DIR` in bash rc + register an XDG
   user dir so the OS knows where notes live.
7. Run the selected profiles. Final timed summary.

---

## 8. Day-2 lifecycle management

**Principle:** the git repo is the single source of truth; machines are
disposable projections of it. Every change flows repo → machine via the same
engine.

- **Reproducibility:** versions pinned in `config/mise.toml` + `devboost.lock`.
  Two machines built weeks apart are byte-for-byte identical.
- **Update everything:** `devboost update` → proposes pinned bumps + refreshes
  dnf/flatpak/extensions → `git diff` → you commit. Other machines:
  `devboost self-update && devboost install`.
- **Add a tool/stack:** `devboost add foo` → fill one file → add to a profile →
  commit.
- **Add an OS:** add `[install].<os>` keys to the affected modules; `doctor`
  reports coverage gaps.
- **Drift:** `devboost export` + `devboost diff` track declared vs actual into
  `workstation-config/`.
- **Cadence:** quarterly ISO refresh, version review, vault push — documented in
  `docs/maintenance.md`.

---

## 9. Ventoy USB & Windows

- **Ventoy layout** (`ventoy/`): `ISO/` (Fedora, Ubuntu, Windows 11, SystemRescue,
  Rescuezilla, GParted), `Bootstrap/` (offline copy of dev-boost + `secrets.age` +
  `ks.cfg`), `Installers/` (offline VS Code/Git/etc.), `Backups/`, `Docs/`.
- **Kickstart** `ks.cfg`: automated Fedora partition/install + a `%post` /
  first-boot unit that runs `install.sh` → the zero-touch path.
- **Windows** (`windows/install.ps1`): winget-based PowerShell engine reading the
  same module manifests; secondary support (thinner than Fedora).

---

## 10. Success criteria

- One command (or zero-touch Kickstart) → ready workstation in **minutes, no
  prompts**.
- `ddev start`, `dotnet new` + `aspire`, `uv run`, `pnpm dev`, and an Expo/RN
  **Android** build all work immediately.
- Obsidian opens `~/Vault` and round-trips to GitHub automatically.
- `devboost verify --profile full` is fully green; **re-running install is a
  no-op** (idempotent).
- Terminal/prompt/tmux match the imported `setup-scripts` experience.
- Adding a new tool is a single new file; adding an OS is a single new key.

---

## 11. Implementation phasing (for the plan)

1. **Engine core** — `lib/*`, `bin/devboost`, TOML parse, OS detect, dep-sort,
   verify-guarded install, summary. Tests with 2–3 trivial modules.
2. **Auth + secrets** — `secrets`/`ssh-setup` modules, `age` decrypt, PAT
   credential store, SSH key API upload.
3. **base + cli + shell** modules + dotfiles import (tmux, oh-my-posh, ghostty,
   bash, fonts) via chezmoi.
4. **Stacks** — laravel, dotnet, python, web, react-native, devops, data modules
   + `templates/`.
5. **apps + Obsidian sync** — obsidian, obsidian-sync, bruno, dbeaver, etc.
6. **Lifecycle** — `update`/`export`/`diff`/`add`/`self-update`, `devboost.lock`.
7. **hardware-nvidia** (port from setup-scripts) + **optional-editors**.
8. **Ventoy/Kickstart** + **Windows** PowerShell engine.
9. **Docs** — architecture, recovery runbook, adding-a-module, maintenance.
