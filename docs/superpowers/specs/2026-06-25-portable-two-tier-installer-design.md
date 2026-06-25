# Portable Two-Tier Developer-Environment Installer — Design

**Status:** Draft spec (not yet approved for implementation) — "spec it for later"
**Date:** 2026-06-25
**Author:** brainstorming session
**Supersedes/affects:** the bash engine described in
`docs/superpowers/specs/2026-06-19-devboost-platform-design.md`; requires a
constitution amendment (see §11).

---

## 1. Summary

A single, portable way to install **and fully configure** a developer's environment,
auto-detecting the OS (Fedora / Ubuntu / Debian families, down to a bare VPS), split
into **two independently-installable tiers**:

- **`terminal`** — the OS-usage layer (modern CLI tools + shell/prompt + dotfiles).
  Needed on *any* box: laptop, desktop, **headless server / VPS**.
- **`devtools`** — the development stack (language runtimes + frameworks: ddev,
  Aspire/.NET, Node, Python/uv, LSPs). Only on machines that build software.

The same tool is used three ways from one source of truth:
1. **Standalone**, curled onto any running OS (`curl … | get.sh -- terminal`).
2. By the **zero-config Ventoy firstboot** flow (`… install terminal devtools`).
3. Interactively on an existing dev-boost workstation.

**Major decision (this session):** the engine is **rewritten in strict-typed Python**
(replacing the current bash engine), shipped to cold boxes as a **frozen single-file
per-arch binary** so no Python runtime is required on the target.

---

## 2. Decisions locked in this session

| # | Question | Decision |
|---|----------|----------|
| 1 | Scope boundary | Two tiers: **terminal** (CLI/shell/usage) and **devtools** (runtimes/frameworks), independently installable. |
| 2 | Relation to existing engine | **One engine, two new profiles**, reused by the zero-config flow (no duplication / one source of truth). |
| 3 | Headless servers | **Auto-detect** no-display boxes and **skip GUI-only** modules (ghostty, nerd-fonts); same command everywhere. |
| 4 | Install source per tool | **Distro package first, pinned upstream fallback** (mise backend → official script → GitHub release). Versions pinned in the lockfile. |
| 5 | Engine language | **Full typed-Python rewrite** (strict typing via mypy/pyright; tests via pytest). Overrides the prior "reuse the bash engine" answer w.r.t. *language*; the *architecture* (profiles + declarative modules + verify-guarded idempotent installs) is preserved. |
| 6 | Python delivery on cold boxes | **Frozen single-file binary** (PyInstaller/Nuitka/shiv), per-arch, in-repo; a tiny bash `get.sh` downloads the right binary and runs it. **No `python3` needed on the target** — true zero-footprint cold start, matching how chezmoi/mise/starship ship. |
| 7 | CLI framework | **Typer** (type-hint-native, Click under the hood; FastAPI author). Subcommands via `add_typer`; typed params via `Annotated[...]`; hermetic tests via `typer.testing.CliRunner`. Freezes cleanly with PyInstaller/Nuitka. *(verified via context7 `/fastapi/typer`, v0.21.1)* |

> Note on #2 vs #5: "one engine, reused" is preserved — there is still exactly one
> engine and the zero-config flow calls it. What changed is the engine's *language*
> (bash → typed Python) and its *delivery* (sourced bash → frozen binary).

---

## 3. Goals / Non-goals

**Goals**
- One command installs + configures the complete terminal experience on Fedora,
  Ubuntu/Debian, and minimal VPSes — idempotently, unattended.
- Strict typing + a real test suite (pytest, mypy/pyright) for the engine logic
  (manifest schema, profile graph, dependency sort, plan builder).
- Cold-start with **zero runtime dependency** on the target (frozen binary).
- Complete, version-pinned tooling everywhere (no "apt has a 3-year-old eza").
- The zero-config Ventoy flow reuses the identical engine + profiles.

**Non-goals**
- Not a generic config-management fleet tool (no Ansible/Salt model — push-to-many).
- Not changing the GUI app catalog (Obsidian/Bruno/dbgate/Bitwarden) — out of scope.
- Not re-solving secrets/age provisioning — reuse the existing flow unchanged.

---

## 4. The two tiers (catalog)

Curated, portable lists — **not** today's `base` (which drags in Fedora-only
`rpmfusion`, `secrets`, `docker`).

### `terminal` (any OS, headless-aware)
- **Minimal deps:** `coreutils git curl wget unzip jq mise chezmoi`
  (`mise` doubles as a universal install backend — see §6).
- **CLI tools:** `ripgrep fd fzf bat eza btop zoxide atuin direnv delta lazygit
  dust duf sd yq gh tealdeer fastfetch tmux fresh`
- **Shell / prompt:** `starship` + `dotfiles` (chezmoi-applied: `.bashrc`,
  `starship.toml`, atuin, tmux.conf) + a `bash-config` verify gate.
- **GUI-only (auto-skipped headless):** `ghostty` `nerd-fonts`.

### `devtools` (dev machines, layers on `terminal`)
- `web-runtimes` (Node via mise), `uv` + `python-lsp`, `web-lsp`,
  `dotnet-sdk` + `aspire` + `dotnet-lsp`, `ddev` (Laravel/.NET/Aspire/Node/Python).

Both are defined as **data** (profile entries), so adding/removing a tool is a
one-line manifest/profile change — no engine edit (preserves Engine + Data
separation, even with a Python engine).

---

## 5. Architecture (typed-Python engine)

A single legible engine. Modules + profiles remain **declarative TOML data**;
the engine parses and **validates** them into typed models, builds a plan, and
executes it idempotently.

```
get.sh (bash, ~30 lines)         # download arch-matched frozen binary, exec it
        │
        ▼
devboost (frozen single-file binary; typed-Python + Typer inside)
  ├─ cli (Typer)                 # subcommands, typed params, --dry-run/--force, CliRunner tests
  ├─ os.detect()                 # distro → family → arch ; is_headless()
  ├─ manifest.load()             # parse TOML → validated Module models (pydantic/dataclass)
  ├─ profile.expand()            # profile names → flat module set (+ transitive requires)
  ├─ graph.toposort()            # stdlib graphlib.TopologicalSorter ; cycle detection
  ├─ plan.build()                # resolve per-module install action + fallback ladder
  └─ run(plan)                   # verify-guard → install → re-verify → summary ; --dry-run
```

### CLI surface (Typer)
One root `typer.Typer()` app; the two tiers are first-class subcommands plus a
generic `install`:

```
devboost terminal [--dry-run] [--force]        # install the terminal tier
devboost devtools [--dry-run] [--force]         # install the devtools (dev-stack) tier
devboost install terminal devtools [...]        # one or more tiers/profiles
devboost verify | list | doctor                 # introspection
```

- Subcommands wired with `app.add_typer(terminal.app, name="terminal")` etc.
- Params typed via `Annotated[bool, typer.Option()]` (`--dry-run`, `--force`),
  `Annotated[list[str], typer.Argument()]` for profile names.
- Tested hermetically with `typer.testing.CliRunner` (asserts exit code + planned
  output without touching the system), alongside the engine pytest suite.

### Typed models (illustrative)
- `Module`: `name`, `category`, `requires: list[str]`, `verify: Command`,
  `install: dict[OsKey, Action]`, `gui: bool`, optional `fallback: FallbackLadder`.
- `Action`: either a shell `Command`, a `PkgInstall(fedora=…, debian=…)`, or a
  `PluginRef` (typed Python plugin for genuinely complex modules).
- `Profile`: `name`, `members: list[str]`.
- `Plan`: ordered `list[PlannedModule]` each carrying its resolved action.

### Idempotency (Principle II preserved)
Every module declares a `verify`. The engine runs it first; green ⇒ skip (unless
`--force`); after install it re-verifies and records `ok/fail/skip`. `--dry-run`
prints the plan without executing.

### OS detection & package abstraction
`os.detect()` maps distro → family (`fedora`/`debian`/`arch`/`macos`) → arch,
exactly as `lib/os.sh` does today. A typed `PackageManager` strategy wraps
`dnf`/`apt` (and brew) behind one interface.

### Headless detection (decision #3)
`is_headless()` = no `$DISPLAY` and no `$WAYLAND_DISPLAY` and no graphical session.
Modules flagged `gui = true` (ghostty, nerd-fonts) are **planned-as-skipped** when
headless — their verify short-circuits green and install logs a skip. So
`devboost install terminal` on a VPS installs all shell tools + dotfiles and
cleanly omits GUI packages. Same command on a laptop installs them.

---

## 6. Install-source strategy (decision #4)

Per tool, a **fallback ladder**, stopping at the first that satisfies `verify`:

1. **Native distro package** — `dnf install` / `apt install` (fast, integrated).
2. **mise backend** — `mise use -g aqua:<owner/repo>` | `cargo:<name>` |
   `github:<owner/repo>` (recent, pinned, identical across distros).
   *Verified via context7 (`/jdx/mise`): backend syntax `aqua:`/`cargo:`/`github:`/`npm:`/`pipx:`.*
3. **Official install script** — e.g. zoxide
   `curl -sSfL https://raw.githubusercontent.com/ajeetdsouza/zoxide/main/install.sh | sh`
   *(verified via context7 `/ajeetdsouza/zoxide`)*.
4. **GitHub release binary** — last-resort direct download.

Rationale: native where it works; on Ubuntu/Debian where `eza`/`zoxide`/`starship`/
`atuin`/`fresh`/`delta`/`lazygit` are missing or stale, the ladder still yields a
current, **lock-pinned** version. Resolved versions are written to the lockfile
(today `devboost.lock`) for reproducibility (Principle III).

Shell init lines (`eval "$(zoxide init bash)"`, starship, atuin, direnv, fzf
keybindings) stay **owned by the dotfiles/chezmoi layer**, not the install step —
preserving the single-copy idempotent `.bashrc` already in `dotfiles/dot_bashrc`.

---

## 7. Delivery & bootstrap (decision #6)

- **Build (CI):** freeze the typed-Python engine into a **single-file, dependency-free
  binary per arch** (`x86_64`, `aarch64`) via PyInstaller/Nuitka/shiv. Artifacts
  committed/released in-repo.
- **Cold-start entry:** `get.sh` (bash, minimal — the *only* shell that must run on a
  bare box): detect arch + family, ensure `git`/`curl`, download the matching binary
  to `~/.local/share/devboost/bin/devboost`, then `exec devboost install "$@"`
  (default profile `terminal`).
  ```
  curl -fsSL https://…/get.sh | bash -s -- terminal           # any OS, incl. VPS
  curl -fsSL https://…/get.sh | bash -s -- terminal devtools  # full dev machine
  ```
- **No `python3` on the target.** The interpreter is inside the frozen binary. This
  is what keeps the "works on any OS / minimal VPS" promise intact despite choosing
  Python (Ubuntu-minimal often ships no python3; PEP 668 blocks system pip).
- **Zero-config reuse:** the Ventoy firstboot service runs the same binary:
  `devboost install terminal devtools`. One engine, one catalog, no drift.

---

## 8. Module authoring surface

Adding a tool stays **one declarative TOML file** (low contributor friction — the
common case must be cheapest, per Principle I). The engine validates it against the
typed schema and fails loudly on malformed manifests (a real win of typing over the
hand-rolled bash TOML parser). Example:

```toml
name     = "eza"
category = "cli"
requires = []
verify   = "command -v eza"
gui      = false

[install]
fedora = "sudo dnf install -y eza"
debian = "sudo apt-get install -y eza"   # added for Ubuntu parity

[fallback]            # used when distro pkg absent / too old
mise   = "aqua:eza-community/eza"
```

Genuinely complex modules may reference a **typed Python plugin** (`PluginRef`)
implementing an `install()/verify()` interface, instead of a shell snippet.

---

## 9. Testing strategy

- **Engine logic (pytest + mypy/pyright):** manifest schema validation, profile
  expansion, toposort (cycles/diamonds/missing deps), headless skip, fallback-ladder
  selection (mock `dnf`/`apt` absent ⇒ asserts mise path), plan/dry-run output.
  Hermetic: fake package managers on `PATH` / monkeypatched subprocess.
- **Install steps:** assert the *generated command/plan* per OS without touching the
  system; integration truth comes from the existing **VM harness**
  (`scripts/vm-test.sh`), which is language-agnostic and kept.
- **Migration of the 1,118 BATS tests:** engine-level BATS tests assert bash
  function behavior and will be **re-expressed in pytest**; module/command-level
  assertions are largely portable. Plan a parity checklist so coverage doesn't
  regress across the rewrite.

---

## 10. Migration plan (bash → typed-Python)

Phased, so `main` stays green:
1. **Stand up the typed engine** behind the same CLI surface (`install/verify/list/
   doctor/add/export/diff/update`), reading the *existing* TOML manifests.
2. **Port modules' OS keys** for Ubuntu parity + add `[fallback]` ladders for the
   terminal tier (eza, zoxide, starship, atuin, fresh, delta, lazygit, ghostty…).
3. **Add `terminal` + `devtools` profiles**; wire `is_headless` gating on `gui`
   modules.
4. **Frozen-binary build in CI** + `get.sh`.
5. **Migrate tests** to pytest with a parity checklist; keep the VM harness.
6. **Flip** the Ventoy firstboot + `curl|bash` entry to the binary; retire the bash
   engine once parity is proven.

This is large — strongly consider splitting into **two specs**: (A) "typed-Python
engine re-platform + delivery" and (B) "two-tier portable profiles + Ubuntu parity".
B is shippable on the bash engine too if A slips.

---

## 11. Governance impact (must-read)

This **contradicts the current constitution**
(`.specify/memory/constitution.md`, Technology & Security Constraints): *"The engine
is **pure Bash**; … **No other interpreters or config-management frameworks**."*
Adopting a typed-Python engine is a **MAJOR constitution amendment** and must be
ratified (with a SYNC IMPACT report + version bump) **before** implementation. The
amendment should also re-state Principle I (Engine + Data Separation) in
language-neutral terms and record the frozen-binary delivery as the mechanism that
upholds Principle IV (Unattended) and the cold-start promise.

---

## 12. Risks & open questions

- **Frozen-binary size/build matrix:** per-arch builds, glibc vs musl on minimal
  images, reproducibility of the binary, and where artifacts are hosted (repo LFS vs
  GitHub Releases). Needs a build spike.
- **Plugin boundary:** which modules justify a typed Python plugin vs a shell
  snippet? Default to declarative TOML; reserve plugins for the few complex ones.
- **Test parity:** concrete mapping from the 1,118 BATS assertions to pytest so the
  rewrite doesn't silently lose coverage.
- **Constitution amendment** ratified first (blocking).
- **Scope split** A/B (see §10) — decide before writing the implementation plan.

---

## 13. Next steps (when picking this up)

1. Ratify the constitution amendment (run `speckit-constitution`).
2. Decide the A/B spec split.
3. Build spike: frozen single-file binary on Fedora + Ubuntu-minimal, confirm
   zero-dependency cold start on a bare VPS.
4. Then invoke the writing-plans skill to produce the implementation plan(s).
