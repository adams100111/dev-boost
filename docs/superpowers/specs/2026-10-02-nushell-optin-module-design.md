# Nushell — opt-in module design

**Status:** Design proposed — ready for implementation planning (one task-sized plan).
**Date:** 2026-10-02
**Facts verified:** 2026-10-02 (packaging APIs, GitHub API, upstream docs — see §3).
**Constitution:** v3.1.0. Merge gates: `uv run ruff check`, `uv run mypy`, `uv run pytest`.

## 0. Why this document lives here

Two shapes exist in this repo for "here is what we are building":

- `specs/0NN-<name>/spec.md` — a **Spec Kit cycle** for a *subsystem* (specs 001–014:
  `base-profile`, `cli-and-shell`, `python-engine-core`, …). Each one owns a profile group
  or an engine capability and comes with `plan.md`/`tasks.md`.
- `docs/superpowers/specs/YYYY-MM-DD-<name>-design.md` — a **single-module design**, paired
  with a `docs/superpowers/plans/` file. This is the shape every recent "add one opt-in
  module" has used: `2026-07-22-herdr-optional-app-design.md`,
  `2026-09-07-{claude-config,codex,pi-harness}-module-design.md`,
  `2026-09-09-orca-module-design.md`.

Nushell is one opt-in tool plus its dotfiles — strictly the second shape. It is **not** a
new Spec Kit cycle: it adds no engine capability, no profile group, and no OS. So this file
sits in `docs/superpowers/specs/` and follows the orca/herdr layout (Facts → Decisions →
Design → Non-goals → Risks → Testing → Milestones).

## 1. Problem statement

`CLAUDE.md` says the mission is a fully-configured workstation from zero config, and that
"production ready" means the box *builds* Laravel/.NET/Python/Next.js/React Native out of
the box with a fully-configured terminal/shell. The operator's day job on top of that box is
**agentic development** — Claude Code, Codex, the `pi` harness, `herdr` panes, the
`devbrain` remote fleet. Those agents spend their lives shelling out and then *parsing text*:
`ps` output, `df` output, `git` porcelain, `docker ps` columns. Every one of those parses is
a regex an agent can get wrong.

Nushell turns that text into typed tables with `| to json`, `| where`, `| get`, and
`detect columns`, which is a genuinely better contract for a program that reads command
output. The ask is therefore: **ship nu as an opt-in tool, configured well enough to be
pleasant, without putting one byte of risk on the unattended POSIX path that the whole
platform stands on.**

The honest headline of this design, stated up front because it reshapes everything below:

> **An agent never runs interactive nu.** An agent runs `nu -c "…"`, and `nu -c` sources
> *none* of the user config (verified, §3.4). So the interactive nu configuration is worth
> **zero** to the agentic use case. It exists purely for the operator's own panes, and must
> be justified — and sized — on that basis alone.

## 2. Scope

In: one `nushell` module (install, per-OS), a chezmoi-managed nu config, a catalog pin, tests,
a docs paragraph. Out: everything in §8.

---

## 3. Facts

Every row verified **2026-10-02** by the command or URL named. Anything not verified is
marked **UNVERIFIED** and must be resolved at implementation, not guessed.

### 3.1 Project maturity — `nushell/nushell`

Source: `api.github.com/repos/nushell/nushell`, `/releases`, `/contributors` (Link header).

| Fact | Value |
|---|---|
| Created | 2019-05-10 |
| License | MIT |
| Stars | 40,610 |
| Contributors | ~420 (Link header `rel="last"` at `per_page=1`) |
| Latest release | **0.116.0**, published 2026-09-26 |
| Previous 9 | 0.115.1 (08-23), 0.115.0 (08-15), 0.114.1 (07-11), 0.114.0 (07-05), 0.113.1 (05-30), 0.113.0 (05-24), 0.112.2 (04-15), 0.112.1 (04-11), 0.111.0 (03-01) |
| Cadence | a minor roughly every 4–7 weeks; patch releases follow within days |
| **Pre-1.0** | **yes — there is no 1.0.** Minor bumps are the breaking-change channel |

Read that cadence against our merge gates. `mypy --strict` + ruff + pytest prove *our* typed
Python; they prove nothing about a `.nu` config file, which is parsed only by nu itself, only
on the operator's machine, only at interactive startup. **A nu config regression is invisible
to CI by construction.** That is the central risk (R1, R2) and it is why §5 keeps the config
small and keeps every integration behind a `which` guard.

### 3.2 Packaging reality per OS

The repo's ladder is distro-package-first, pinned-upstream-fallback (`docs/adding-a-module.md`
step 1→3; `cli_tools.py` does this for `sd`, `dust`, `yq`, `fastfetch`, `gh`).

| OS | In the distro's own repos? | Version | Verified by |
|---|---|---|---|
| **macOS (Homebrew core)** | **yes**, formula `nushell` | **0.116.0** (365-day installs: 50,671) | `formulae.brew.sh/api/formula/nushell.json` |
| **Arch** | **yes**, repo `extra`, package `nushell` | **0.116.0-1**, updated 2026-09-26 | `archlinux.org/packages/search/json/?name=nushell` |
| **Fedora 43 / 44 / rawhide** | **yes**, package `nushell` | **0.99.1-8.fc44** (also `-8.fc43`, `-8.fc46`) | `mdapi.fedoraproject.org/f44/pkg/nushell` |
| **Debian (all suites)** | **no** | — (only `librust-clap-complete-nushell-dev`, a Rust *crate*, not the shell) | `packages.debian.org/search?keywords=nushell&searchon=names&suite=all` |
| **Ubuntu (all suites)** | **no** | — (same `librust-clap-complete-nushell-dev` only) | `packages.ubuntu.com/search?keywords=nushell&searchon=names&suite=all` |

**Fedora's package is 17 minor releases behind and that is disqualifying, not cosmetic.**
0.99.1 is below the floor of two integrations we want (direnv needs ≥ 0.104, zoxide needs
≥ 0.106 — §3.5). A box that installs `dnf install nushell` gets a shell our own config cannot
configure.

COPR search (`copr.fedorainfracloud.org/api_3/project/search?query=nushell`) returns 14+
projects; the three with a successfully-built `nushell` package:

| COPR | Version | Last successful build |
|---|---|---|
| `rustyclanker/nushell` | 0.114.1-1 | 2026-07-28 |
| `virulent/nushell` | 0.114.1-1 | 2026-07-17 |
| `bernardogn/nushell-bundled` | 0.114.1-1 | 2026-07-13 |
| `@rust/uutils-and-nushell` | **no built `nushell` package** — it is a Rust-SIG *dependency staging* repo (`rust-uucore`, `rust-phf`, …) | — |

All three are personal COPRs, none is atim-grade, all are two minors stale. **No COPR is
adopted** (D3) — the same judgement `Superfile` already records in `cli_tools.py` ("Fedora
has only personal COPRs, none of them atim-grade").

Upstream release assets (`/releases/latest`, 16 assets, plus a `SHA256SUMS` manifest):

| Asset | sha256 (from the GitHub asset `digest` field) |
|---|---|
| `nu-0.116.0-x86_64-unknown-linux-gnu.tar.gz` | `9f73a6913f9515a621bd916dc91d7f3e0494e488161c2d686f6b98ffa0555945` |
| `nu-0.116.0-aarch64-unknown-linux-gnu.tar.gz` | `bd854a1c7286cabb7830e744810c27152e3d332192e75cea9e3c92dced4e3dce` |
| `nu-0.116.0-x86_64-unknown-linux-musl.tar.gz` | `7b91aeef575080f4b90405ba4512f4ccd0c21a6fbcd99f18bde3272c75213f00` |
| `nu-0.116.0-aarch64-unknown-linux-musl.tar.gz` | `bc3503d0588caa7c2835d61337825152141c748c126817739cb86519c593416e` |
| `nu-0.116.0-aarch64-apple-darwin.tar.gz` | `8d3169054b0e8f04b60b38ac1673acf61cbf66c6d8073ebc732d5bc108b3add6` |

- **UNVERIFIED:** the tarball's *inner* layout (whether `nu` sits at the archive root or under
  `nu-<ver>-<target>/`). Resolve at implementation with `tar -tf` on the pinned asset before
  writing the `install -m 755` path. Do not copy `dust`'s assumption blindly.
- **UNVERIFIED:** the glibc floor of the `-gnu` tarballs. `scripts/check-glibc-floor.sh`
  exists for exactly this; run it, and fall back to the `-musl` asset if the floor is above
  our oldest target (the `sd` module already takes a musl asset on aarch64 for a sibling
  reason).

Carapace (relevant to D10): brew core has `carapace` **1.8.0**
(`formulae.brew.sh/api/formula/carapace.json`); Arch official repos have **nothing**
(`archlinux.org/packages/search/json/?name=carapace` → empty); AUR has `carapace-bin` 1.8.0
(19 votes) and `carapace` 1.8.0 (3 votes) (`aur.archlinux.org/rpc/v5/info`); Fedora: no
package (`mdapi` 400 / not found). Carapace lists Nushell among its supported shells
(`carapace-sh/carapace-bin` README).

### 3.3 Nushell's config model

Source: `https://www.nushell.sh/book/configuration.html` (fetched 2026-10-02; the same page
is what ctx7 `/websites/nushell_sh_book` serves).

- Files, in load order: `env.nu` → `config.nu` → `$nu.vendor-autoload-dirs/*.nu` →
  `$nu.user-autoload-dirs/*.nu` → `login.nu` (login shells only). All optional.
- **Default config dir differs per OS** — this is the single most load-bearing config fact
  for us:
  - Linux: `~/.config/nushell`
  - **macOS: `~/Library/Application Support/nushell`** (not `~/.config`)
  - Windows: `%AppData%\Roaming\nushell`
- `$env.XDG_CONFIG_HOME`, when set to an absolute path, relocates the config dir to
  `<that>/nushell` — including on macOS. The docs warn to point it at the directory *above*
  `nushell`, never at a nu-only directory.
- `--config-home <path>` is a launch flag that beats `XDG_CONFIG_HOME`; unlike the env var it
  names the nushell directory **itself** (no `nushell` subdirectory appended).
- `$nu.data-dir` = `$XDG_DATA_HOME/nushell` when set. **`($nu.data-dir)/vendor/autoload` is
  appended to `$nu.vendor-autoload-dirs`** and is "intended for vendors' and package
  managers' startup files". The directory is **not created by default** — the writer must
  `mkdir` it.
- **Config-format churn is real and recent.** The docs state that `default_config.nu` "is
  essentially empty, since the defaults for all `$env.config` settings are now built into
  Nushell", and that first launch creates "an empty (other than comments) `env.nu` and
  `config.nu`". That is the end-state of a multi-release reshape: a `let-env config = { … }`
  record (the 0.68-era carapace snippet still in the blog), then the grouped record of 0.72,
  then today's `$env.config.<field>` mutation with built-in defaults. **Any `config.nu` we
  ship is written against today's shape and may need editing on a future minor.** Historical
  snippets found in blog posts (`let-env config = …`) must not be copied.

### 3.4 Launch-mode matrix — the fact the whole design turns on

From the same page's "Scenarios" section, verbatim behaviour per invocation:

| Invocation | `env.nu` | `config.nu` | `login.nu` | vendor-autoload | user-autoload |
|---|---|---|---|---|---|
| `nu` (REPL) | ✅ | ✅ | ❌ | ✅ | ✅ |
| **`nu -c "ls"`** | **❌** | **❌** | **❌** | **❌** | **❌** |
| `nu -l -c "ls"` | ✅ | ✅ | ✅ | ❌ | ❌ |
| `nu test.nu` (script) | ❌ | ❌ | ❌ | ❌ | ❌ |
| `nu -n --no-std-lib -c "ls"` | ❌ (also no stdlib, no plugins) | ❌ | ❌ | ❌ | ❌ |

Consequences, which §4 and §5 lean on hard:

1. `nu -c` is **hermetic**: the agent gets the same nu on every machine regardless of what
   the operator did to their config. That is exactly the property dev-boost wants and the
   one `bash -lc` does *not* have.
2. `nu -c` is **fast** — no config parse, no autoload.
3. It also means the interactive config buys the agent nothing. Do not size it as if it did.

### 3.5 Integration matrix

| Tool | nu support | Documented invocation | Minimum nu | Source |
|---|---|---|---|---|
| **starship** | yes | `starship init nu \| save -f ($nu.data-dir \| path join "vendor/autoload/starship.nu")` (upstream's own words; it also tells you to `mkdir` that dir) | **0.96+** (stated on the page) | `starship.rs/guide/` |
| **zoxide** | yes | `zoxide init nushell \| save -f ~/.zoxide.nu` then `source` it from `config.nu` | **0.106.0+** (stated in the README) | `zoxide` README (`main`) |
| **atuin** | yes | `atuin init nu` (`Shell::Nu`, `#[value(rename_all = "lower")]`; the template is `crates/atuin/src/shell/atuin.nu`) | not stated — **UNVERIFIED** | `atuinsh/atuin` `init.rs` + `src/shell/` listing |
| **direnv** | yes | a `$env.config.hooks.env_change.PWD` hook that does `direnv export json \| from json \| … \| load-env`, with `use std/config *` for the PATH re-conversion | **0.104+** (stated in the cookbook) | `nushell.sh/cookbook/direnv.html` |
| **mise** | yes | two steps: `env.nu` does `^mise activate nu \| save $mise_path --force`, `config.nu` does `use ($nu.default-config-dir \| path join mise.nu)`. mise's nu activation is a **module**, not a sourced script | not stated — **UNVERIFIED** | `jdx/mise` `docs/installing-mise.md` |
| **carapace** | yes | `external_completer` closure calling `carapace $spans.0 nushell $spans \| from json` — but the canonical snippet in the nu blog is **0.68-era (`let-env config`) and will not parse today** | n/a | `carapace-bin` README; `nushell.sh/blog/2022-09-06`, `cookbook/external_completers.html` |

mise's own shell-feature matrix (`jdx/mise` `docs/getting-started.md`) marks Nushell as
**Yes** for `mise activate`, `mise shell`, and the `chpwd` hook, and **No** for shell aliases
(`[shell_alias]`). Bash and zsh are Yes for all four.

Note the floor arithmetic: direnv needs ≥ 0.104, zoxide needs ≥ 0.106. **Fedora's 0.99.1
clears neither.** Pinning 0.116.0 clears all three known floors with margin.

---

## 4. The load-bearing design question: nu is not POSIX

This section is the spine. Everything in §5 is downstream of it.

### 4.1 What must never change, and why — with citations

| Invariant | Why | Evidence |
|---|---|---|
| **dev-boost never runs `chsh`, never writes `/etc/shells`, never sets `$SHELL`.** | It does not today — `chsh` and `/etc/shells` appear **nowhere** in `engine/src`, `dotfiles/`, or `scripts/`. This design keeps that true rather than introducing the capability and then guarding it. | repo-wide grep, 2026-10-02 |
| **The login shell stays bash on Linux and zsh on macOS.** | Those are the shells the whole dotfiles layer is written for: `dotfiles/dot_bashrc`, `dot_zshrc`, `dot_zprofile`, `dot_bash_profile`, and `dot_config/devboost/shell.bash` / `shell.zsh`. `shell.py:_TAKEN_OVER` / `_TAKEN_OVER_LINUX` name exactly those files as the ones chezmoi owns wholesale, with `back_up_taken_over` / `record_rc_digest` bookkeeping behind them. nu owns none of that machinery and must not try to. | `engine/src/devboost/modules/shell.py:41-48`, `:156-251` |
| **`~/.config/devboost/env.sh` stays POSIX sh.** | Its own header says "POSIX sh only: no bashisms". It is sourced by bash, by zsh, **and on macOS by `~/.bash_profile` so `bash -lc` launchers see the same PATH**. It is the one file that defines PATH/EDITOR for every non-interactive launcher on the box. nu cannot read it, and nu must never become a reason to rewrite it. | `dotfiles/dot_config/devboost/env.sh:1-6` |
| **The engine's `Executor` keeps executing argv, not shell strings.** | `RealExecutor` is documented as "Runs argv lists via subprocess — never a shell string" and builds `cmd = (["sudo", *argv]) if sudo else list(argv)`. Where a shell *is* needed, modules write `ctx.ex.run(["sh", "-c", script])` — **naming `sh` explicitly**, never `$SHELL`. | `engine/src/devboost/exec/executor.py:80`, `:103`; `cli_tools.py` passim (`_ATUIN_DEBIAN`, `_DUST_DEBIAN`, `_SUPERFILE_INSTALL`, …) |
| **Every script in `scripts/` keeps its shebang.** | `get.sh`, `release.sh`, `build-bundle.sh`, `preflight.sh`, `vm-test*.sh`, `install-dev.sh`, `make-secrets.sh`, `import-*.sh` are `#!/usr/bin/env bash`; `smoke-assert.sh` is `#!/bin/sh`. A shebang is immune to the login shell — which is precisely why these are safe and why nothing here needs changing. | `head -1 scripts/*.sh` |
| **`claude-code`, `codex-code`, `pi-harness` and the `Bash` tool keep a POSIX shell.** | Claude Code's shell tool is literally the *Bash* tool; the `devbrain` fleet and the `dev` helper already pin `bash -lc` on the far side of ssh. | `dotfiles/dot_config/devboost/aliases.sh` (`ssh -t "$host" "… bash -lc …"`) |

**The engine is already immune.** That is worth stating plainly because it is the opposite of
the intuition: because `RealExecutor` never consults `$SHELL` and every shell-string call
spells `sh`, an operator who changed their login shell to nu would **not** break
`devboost install`. The breakage lands elsewhere (§4.4).

### 4.2 Where nu genuinely earns its place for agentic work

Not aesthetics — parse elimination. Concrete, with the structured-output contract named. (The
commands below are the shapes an agent would run; each uses commands documented in the nu
command reference — `detect columns` is a real command, `nushell.sh/commands/docs/detect_columns.html`,
checked 2026-10-02 — but the exact column names each produces on a given host are
**UNVERIFIED** and belong in the implementation's smoke check, not in a promise here.)

```sh
# Processes over 1 GB RSS, as JSON an agent parses with json.loads — no ps-column regex.
nu -c 'ps | where mem > 1gb | select pid name mem | to json'

# Which mise-managed tools are active here — typed rows instead of two-space-column text.
nu -c 'mise ls --json | from json | to json'

# Any text tool that prints columns, turned into records without a regex per tool:
nu -c 'docker ps | detect columns | to json'

# Disk pressure as a number, not a string an agent has to strip a "%" off:
nu -c 'sys disks | where used > (0.9 * $it.total) | to json'

# Read-modify-write a JSON config without jq quoting hell inside a Bash tool call:
nu -c 'open package.json | get scripts | to json'
```

The properties that matter to a program, not a person:

1. **`| to json` is a total function from a pipeline to a parseable value.** The agent's
   contract becomes `json.loads(stdout)` instead of a per-tool regex that silently breaks when
   a column widens or a locale changes.
2. **Typed cells.** `mem > 1gb` and `used > …` are numeric comparisons, not string compares
   on `"1.2G"`. An agent writing a threshold check in bash has to shell out to `awk` and get
   the unit suffix right; in nu the filter is the comparison.
3. **`detect columns` generalises the hardest case** — a tool that prints a table and offers
   no `--json`. One command replaces a bespoke `awk`/`cut` per tool.
4. **Errors are values with spans.** A failed pipeline reports *where*, which is a better
   diagnostic to hand back to a model than `sh: 1: Syntax error: ...`.
5. **`nu -c` is hermetic (§3.4).** The agent's command behaves identically on a fresh USB
   install and on a three-year-old laptop whose operator has 400 lines in their `config.nu`.
   `bash -lc` cannot promise that.

That is a real, specific win, and it is available **without nu being anybody's shell.**

### 4.3 How nu coexists — the position, and the defence

**Position: nu is an explicitly-invoked, interactive-optional extra. It is a *command*, not a
*shell*, as far as dev-boost is concerned.**

Concretely:

- Agents reach it as `nu -c "…"` from inside their existing bash tool. No harness
  configuration changes. No `$SHELL`. Nothing to undo if nu is uninstalled.
- The operator reaches it by typing `nu` in a bash/zsh pane (including a herdr pane). It
  exits back to bash. `herdr`'s config gains **no** shell setting — `dotfiles/dot_config/herdr/config.toml`
  stays as it is.
- The chezmoi-managed `config.nu`/`env.nu` serve *only* that interactive REPL.

Why this and not the alternatives:

- *"Make nu the login shell for people who opt in."* Rejected: it converts a reversible
  `devboost install nushell` into a change that can lock the operator out of their own agent
  workflow (§4.4), and it would require dev-boost to grow `chsh` + `/etc/shells` handling it
  has never had. The blast radius is wildly out of proportion to the benefit, and the benefit
  (a nicer REPL) is available without it.
- *"Set nu as herdr's per-pane default shell."* Rejected: a herdr pane is where agents get
  launched. Making the agent's parent shell nu re-introduces every POSIX assumption problem
  one level down, for an ergonomic gain the operator can get by typing three characters.
- *"Don't configure it at all; just install the binary."* Tempting, and genuinely close. See
  §10 — a bare nu with no prompt, no direnv and no mise is strictly worse than bash for the
  operator and would simply go unused. A *small* config (five generated lines) is the
  difference between a tool and a curiosity. But it stays small.

### 4.4 Failure modes, and what dev-boost does about each

| # | Failure | What actually breaks | What dev-boost does |
|---|---|---|---|
| F1 | **Operator runs `chsh -s $(which nu)`** | `ssh host '<cmd>'` runs `<cmd>` through the *login shell* → every remote one-liner that is not wrapped in `bash -lc` breaks. Anything reading `$SHELL` to spawn a child spawns nu. | dev-boost never does it, never documents it as supported, and the shipped `config.nu` carries a header comment saying so (D13). The module does **not** add nu to `/etc/shells` — without that entry `chsh` refuses, so the dangerous path requires the operator to edit a root-owned file first. That is the "hard to take by accident" property. |
| F2 | **`dev <repo>` on a box with no tmux** | `dotfiles/dot_config/devboost/aliases.sh:50` ends with `cd "$dir" \|\| exit 1; exec "${SHELL:-bash}" -i`. Under F1 that becomes `exec nu -i` — **nu has no `-i` flag**, so the helper dies instead of dropping you in a shell. | A concrete, citable consequence of F1. Not worked around (working around F1 would legitimise it); named here and in the config header so the first person to hit it knows why. The `ssh` branch of the same helper already pins `bash -lc` and is unaffected. |
| F3 | **`direnv`'s bash hook vs nu's** | They are different mechanisms: `eval "$(direnv hook bash)"` in `shell.bash`, versus an `env_change.PWD` hook record in nu. Neither sees the other. A `.envrc` applied in a bash pane is not applied in a nu pane started elsewhere. | Ship nu's own hook (D8). Accept the divergence — it is inherent, not a bug. The bash hook is untouched. |
| F4 | **mise activation differs** | nu's activation is a generated **module** that must exist *before* `config.nu` parses (mise's docs are explicit). And `[shell_alias]` does not work under nu at all (mise's own matrix). | `env.nu` always writes `mise.nu` first (D7); `config.nu` `use`s it unconditionally. mise is in `base`, so it is present on every dev-boost box — no conditional-`use` parse-time problem. The shell-alias gap is documented, not papered over. |
| F5 | **macOS config dir is `~/Library/Application Support/nushell`** | chezmoi writes `~/.config/nushell/…`. nu finds it only because `env.sh` exports `XDG_CONFIG_HOME="${HOME}/.config"` on macOS — and only for a nu launched from a shell that sourced `env.sh`. A nu launched from a GUI/launcher reads an empty config and the operator sees "my config does nothing". | D6: on macOS the module creates `~/Library/Application Support/nushell` as a **symlink** to `~/.config/nushell` when that path is absent. Both routes then land on the same chezmoi-managed files. Idempotent; never clobbers a real directory. |
| F6 | **A pre-1.0 minor changes `$env.config` shape** | Our `config.nu` throws a parse error at every interactive nu start. Nothing else on the box notices (the agent path is `nu -c`, which never reads it). | Blast radius is one REPL. Mitigation in R1/R2: keep `config.nu` to the minimum, pin the version, and put the integration generation in `env.nu` behind `which` guards so a missing tool is never an error. |
| F7 | **Fedora's `nushell` 0.99.1 already on PATH** | `which nu` succeeds, the module skips as "installed", and the operator gets a nu too old for the direnv (≥0.104) and zoxide (≥0.106) integrations — a *silent* half-working state, the worst kind. | D4: `verify_linux` checks a **version floor**, not just `which` (the `Herdr` module already does exactly this — `herdr.py:39-51`). An under-floor nu is treated as drift and replaced. |
| F8 | **Operator's own `~/.config/nushell/config.nu` exists** | `chezmoi apply --force` would overwrite it silently. | D5: add both files to `shell.py:_TAKEN_OVER_CONFIGS`, so `back_up_taken_over` keeps `config.nu.pre-devboost` first — the exact treatment `~/.config/voxtype/config.toml` already gets. |

---

## 5. Decisions

| # | Decision | Rationale |
|---|---|---|
| **D1** | **One module, named `nushell`. No new profile. `profiles = ()`.** Opt in by name: `devboost install nushell`. | This is the most recent precedent in the tree: `Superfile` (`cli_tools.py`, end of file) ships `profiles = ()` with the docstring "Deliberately in no profile. `cli` is a toolchain tier, and a file manager is an application preference (the reasoning `base` already spells out for voxtype)". A *second shell* is the purest possible "preference". Creating no profile also makes the **profile/module name-collision rule structurally unviolatable** — there is no profile to collide with. If a profile is ever wanted later it must be `optional-shells` (following `optional-editors`/`optional-terminals`), **never** `nushell`. |
| **D2** | **Not in `base`, `cli`, `shell`, `full`, `macos`, `terminal`, `omarchy`, or `server`.** | `profiles.toml` states the doctrine twice. On `base`: "Everything in `base` is toolchain — compilers, VCS, containers, secrets." On `cli` (via Superfile): "`cli` is a toolchain tier." `shell` is the *configured login shell* group (`starship`, `bash-config`, `zsh-config`, `dotfiles`, `ghostty`, `nerd-fonts`) — putting an alternative shell there would be an actively misleading signal about its status. |
| **D3** | **Install source per OS: distro package where it is current, pinned upstream tarball where it is not.** macOS → Homebrew `nushell`; Arch/Omarchy → pacman `nushell` (`extra`, 0.116.0-1, routed through `omarchy-pkg-add` automatically by `pkg.Pacman`); **Fedora and Debian/Ubuntu → the pinned, SHA256-verified upstream tarball** into `~/.local/bin`. | Fedora *has* a package but it is 0.99.1 — below two integration floors (§3.2), so it fails the only test that matters. Debian/Ubuntu have none. No COPR is current or maintained to a standard this repo accepts (§3.2). This is precisely the shape of `Sd` (`fedora_pkg` declared but unused; Arch packages it properly; everyone else gets the release binary). |
| **D4** | **`verify_linux` enforces a version floor** (`_NU_MIN = (0, 106, 0)`), not just `which("nu")`. | F7. A distro nu already on PATH must not be mistaken for a working install. `Herdr.verify` is the in-tree model for this: `which` → run `--version` → parse → compare → "an older pin is upgraded; a newer one is kept as is". `0.106.0` is the highest *documented* floor among the shipped integrations (zoxide); direnv's 0.104 and starship's 0.96 are below it. |
| **D5** | **Pin `0.116.0` in `catalog.toml` under a `[nushell]` tooling table**, assets keyed `linux-x86_64` / `linux-aarch64` via `media.catalog.asset_key`, each with the sha256 from §3.2. No macOS asset (brew owns that). | Constitution III: "Runtime versions MUST be pinned … so two machines built weeks apart are identical." `[herdr]` is the exact existing shape, including `asset_key`'s "a Mac can never pick a Linux binary" guarantee, and `catalog.toml` is already load-validated for 64-hex sha256. A `curl … \| sh` or a `releases/latest` lookup would give neither reproducibility nor integrity on an unattended USB — the `herdr` design already litigated this. |
| **D6** | **Config ships through chezmoi as `dotfiles/dot_config/nushell/{env.nu,config.nu}`, unconditionally (even on boxes without nu).** On macOS the module additionally symlinks `~/Library/Application Support/nushell` → `~/.config/nushell` when that path does not exist. | Unconditional shipping is the existing pattern for opt-in tools: `dot_config/wezterm/` ships although `wezterm` is `optional-terminals`; `dot_config/voxtype/` ships although voxtype is in no profile. An inert `.nu` file on a box without nu costs nothing. The symlink closes F5 without a second copy of the config and without touching `env.sh`'s macOS `XDG_CONFIG_HOME` export. |
| **D7** | **Integrations are *generated* at nu startup into `($nu.data-dir)/vendor/autoload/`, from `env.nu`, each behind a `which` guard** — except mise, which is generated into `$nu.default-config-dir/mise.nu` and `use`d from `config.nu`. | This is upstream's own instruction, not an invention: starship's docs say verbatim to `mkdir ($nu.data-dir \| path join "vendor/autoload")` and save `starship init nu` there, and the nu book describes those dirs as "intended for vendors' and package managers' startup files". One uniform mechanism for four tools means one thing to maintain across nu minors, not four. mise is the documented exception because its activation is a *module*. The `which` guard means a box missing a tool gets a silent no-op, never a startup error. |
| **D8** | **Ship configured: starship, zoxide, atuin, direnv, mise. Exactly those five.** | They are the five tool initialisers in `dot_config/devboost/shell.bash` (fzf is the sixth and is bash-keybinding-specific — nu has its own line editor, reedline, so there is nothing to port). Parity with the bash pane is the whole operator-facing point; a nu pane without a prompt, without `.envrc`, and without mise's PATH is not a usable dev pane. All five have upstream-documented nu support (§3.5) and all five clear the pinned version's floors. |
| **D9** | **direnv's hook is the cookbook `env_change.PWD` form, with `use std/config *`** — not a `pre_prompt` hook. | The cookbook states the `env_change` form is the recommended, more efficient one, and that the `std/config` helper is needed to turn direnv's string `PATH` back into a nu list. An older nu blog post recommends `pre_prompt`; it is superseded. Requires nu ≥ 0.104 — covered by D4's 0.106 floor. |
| **D10** | **Carapace is deliberately NOT shipped.** | Three reasons, each sufficient. (a) **Packaging**: absent from Fedora and from Arch's official repos; brew-only + AUR (§3.2) — adopting it means a fourth bespoke install path for a completion engine. (b) **dev-boost has no carapace module at all today**; this spec is not the place to add one. (c) **The canonical nu snippet is stale** — the widely-copied `external_completer` example is 0.68-era `let-env config = { … }` and will not parse against today's `$env.config`, so we would be shipping a hand-ported guess (§3.3). nu's built-in completions are adequate for a secondary REPL. Seam left open: if carapace is ever added as its own module, the nu side is one more generated file in the same `vendor/autoload` dir. |
| **D11** | **The `dev` / `expose` / `pw-*` / `tsdev-sync` helpers in `aliases.sh` are NOT ported to nu.** | They are POSIX shell functions, ~200 lines, with their own tmux/ssh/tailscale logic. Porting doubles the maintenance surface of the box's most operationally load-bearing helpers so that they also work in a shell nobody logs into. They remain reachable from nu by their real form: `bash -lc 'dev myrepo'`. Zero agentic value (agents use `nu -c`, which reads no config at all). |
| **D12** | **No `login.nu`.** | `login.nu` only runs when nu *is* the login shell. Shipping one would be the platform quietly preparing for a configuration it says it does not support. |
| **D13** | **`config.nu`'s header states the contract in the file itself:** nu is interactive-only; it is not `$SHELL`; `nu -c` reads none of this file; do not `chsh` to it; `dev` will break if you do (F2). Plus the standard `devboost — managed by chezmoi` marker. | The marker is load-bearing machinery, not decoration: `shell.py:_MANAGED_MARKER` / `_managed_digest` use it to tell "ours, unmodified" from "the user edited it", which is what makes D14's backup correct rather than noisy. And the warning belongs where the operator will actually read it. |
| **D14** | **Add `.config/nushell/config.nu` and `.config/nushell/env.nu` to `shell.py:_TAKEN_OVER_CONFIGS`.** | F8. That dict is exactly "non-rc files the dotfiles take over wholesale, on every OS but Omarchy"; `Dotfiles._taken_over_for` merges it into both the macOS and the Linux sets, so `back_up_taken_over` writes `.pre-devboost` before the first forced apply and `record_taken_over` records the digest after. The same treatment `~/.config/voxtype/config.toml` gets. No `.chezmoiignore` entry is needed: Omarchy ships no nushell config, so there is nothing to lose a race with. |
| **D15** | **`self_updating = True`** (the `PackageModule` default) **and `category = "cli"`.** | A single-binary/single-package install is safe to re-run in place, which is the stated condition for the default. On Fedora/Debian `--update` re-runs the pinned fetch; bumping the pin in `catalog.toml` is then the deliberate, reviewed version bump Constitution III asks for. |
| **D16** | **`gui = False`, no `families` restriction, no `provided_by`.** | nu is a terminal program and is wanted on headless boxes too — `gui=True` would make `build_plan` drop it there (the mistake the orca design calls out by name). All four families (fedora/debian/arch/macos) have a real path, so `families` would only add a way to be wrong. No platform ships it pre-configured, so nothing is `provided_by`. |

---

## 6. Design

### 6.1 The module

One new file, `engine/src/devboost/modules/nushell.py` (nu is substantial enough to warrant
its own file rather than another entry at the end of `cli_tools.py`; `herdr.py` and `orca.py`
set that precedent).

```
class Nushell(PackageModule)
    name         = "nushell"
    category     = "cli"
    description  = "Nushell — structured-data shell (`nu`); opt-in, never the login shell."
    profiles     = ()                 # D1 — opt in by name
    cmd          = "nu"
    fedora_pkg   = "nushell"          # declared but UNUSED on Fedora (0.99.1 — D3);
                                      # it is what _resolve_pkg falls back to on Arch
    arch_pkg     = "nushell"          # extra, 0.116.0-1
    brew_pkg     = "nushell"          # homebrew-core, 0.116.0 (PackageModule default name
                                      # already matches, but spell it out)
    self_updating = True              # D15
```

`PackageModule` field semantics being relied on (`_pkgmodule.py`):

- macOS is handled **entirely by the base class** — `verify`/`install` route to
  `brew_strategy()` → `BrewFormula("nushell")` before any Linux code runs, and
  `requires = (Homebrew,)` comes for free. This is why the subclass overrides
  `install_linux`/`verify_linux` and **never** `install`/`verify` (the base class docstring
  states this rule).
- No `debian_pkg`, no `aur_pkg`, no `copr_repo` (D3). No `debian_cmd`/`arch_cmd`: the binary
  is `nu` everywhere.

Overrides:

```
verify_linux(ctx) -> bool          # D4
    which("nu") and parse `nu --version` >= _NU_MIN (0, 106, 0)
    a non-zero `nu --version`, or an unparseable one, is drift → False

install_linux(ctx) -> None         # D3
    arch   -> super().install_linux(ctx)      # pacman / omarchy-pkg-add, via _resolve_pkg
    others -> pinned tarball:
        pin   = catalog.nushell_pin()
        asset = pin.assets[asset_key(ctx.os)]     # linux-x86_64 | linux-aarch64
        missing key -> InstallError("nushell", f"no pinned binary for {key!r}", 1)
        ctx.ex.run(["sh", "-c", script])          # set -e; mktemp -d; trap rm -rf EXIT;
                                                  # curl -fL --proto '=https' --retry 2;
                                                  # sha256sum -c -;  tar -xf;
                                                  # install -m 755 … "$HOME/.local/bin/nu"
        not res.ok -> InstallError("nushell", "download or checksum verification failed", code)

install(…)  — NOT overridden.  macOS stays on Homebrew automatically (base-class rule).
```

The script is modelled line-for-line on `Herdr.install` (`herdr.py:53-80`): `set -e`, a
`trap` that cleans `$tmp` on **any** exit including a checksum failure, `curl -fL --proto
'=https'`, then `sha256sum -c -` *before* `install`. `~/.local/bin` is already on
`RealExecutor`'s PATH (`_prepend_mise_dirs`), so `which("nu")` succeeds immediately after.
The one deviation from `Herdr`: nu ships a **tarball**, so there is a `tar -xf` step and the
inner path must be read off the real archive first (§3.2, UNVERIFIED).

The macOS symlink (D6) is the only non-brew work on a Mac. It belongs in a small
`_link_macos_config_dir(ctx)` called from `install_linux`'s sibling path — i.e. the module
overrides `install` **only if** that proves necessary; the cleaner shape is a tiny
`per_os = OsMap(macos=…)` composite, or a `MacosConfigLink` `Installer` wrapped around
`BrewFormula("nushell")`. Resolve the shape at implementation; the behaviour is fixed:

```
if ~/Library/Application Support/nushell does not exist (and is not a symlink):
    mkdir -p ~/.config/nushell ; ln -s ~/.config/nushell "~/Library/Application Support/nushell"
otherwise: no-op  (never replace a real directory the operator owns)
```

### 6.2 OS-dispatch seams

| Family | Path | Seam used |
|---|---|---|
| macos | `BrewFormula("nushell")` | `PackageModule.brew_strategy()` — zero subclass code |
| arch / omarchy | `pkg.install(ctx, "nushell")` | `PackageModule._resolve_pkg` + `pkg.Pacman`, which routes to `omarchy-pkg-add` when present |
| fedora | pinned tarball | `install_linux` override + `catalog.nushell_pin()` |
| debian | pinned tarball | same branch — no Debian-specific code at all |

Adding a future OS = one more `asset_key` row in `catalog.toml`, or one `*_pkg` attribute.
No engine change (Constitution I, VI).

### 6.3 `catalog.toml`

```toml
# nushell — assets keyed "<os>-<arch>" (media.catalog.asset_key). macOS comes from
# Homebrew, so no macos-* asset is pinned here. sha256 values are the GitHub release
# asset digests (the release also publishes a SHA256SUMS manifest).
[nushell]
version = "0.116.0"

[nushell.assets.linux-x86_64]
url = ".../v0.116.0/nu-0.116.0-x86_64-unknown-linux-gnu.tar.gz"
sha256 = "9f73a6913f9515a621bd916dc91d7f3e0494e488161c2d686f6b98ffa0555945"

[nushell.assets.linux-aarch64]
url = ".../v0.116.0/nu-0.116.0-aarch64-unknown-linux-gnu.tar.gz"
sha256 = "bd854a1c7286cabb7830e744810c27152e3d332192e75cea9e3c92dced4e3dce"
```

`media/catalog.py` gains a `nushell_pin()` beside `herdr_pin()` and the `[nushell]` table
joins the "Tooling pins — excluded from OS catalog validation" block. The 64-hex sha256
validation is inherited.

### 6.4 The dotfiles

`dotfiles/dot_config/nushell/env.nu` — generation only, every line guarded:

```nu
# ~/.config/nushell/env.nu — dev-boost's nu environment.
# devboost — managed by chezmoi; edit dotfiles/dot_config/nushell/env.nu in the dev-boost
# repo. Do not edit this file manually.
#
# Integration modules are GENERATED here into the vendor autoload dir, which nu loads
# after config.nu (startup step 24). This is upstream's own pattern (starship docs).
# Every block is guarded: a box without the tool gets a no-op, never a startup error.

const DEVBOOST_AUTOLOAD = ($nu.data-dir | path join "vendor" "autoload")
mkdir $DEVBOOST_AUTOLOAD        # nu does NOT create data-dir subdirectories itself

if (which starship | is-not-empty) {
  ^starship init nu | save -f ($DEVBOOST_AUTOLOAD | path join "starship.nu")
}
if (which zoxide | is-not-empty) {
  ^zoxide init nushell | save -f ($DEVBOOST_AUTOLOAD | path join "zoxide.nu")
}
if (which atuin | is-not-empty) {
  ^atuin init nu | save -f ($DEVBOOST_AUTOLOAD | path join "atuin.nu")
}

# mise activation is a MODULE, not a sourced script, so it goes in the config dir and is
# `use`d from config.nu (mise docs, "Nushell"). mise is in `base`, i.e. on every dev-boost
# box, so config.nu can `use` it unconditionally — but write a stub when it is missing so a
# parse-time `use` can never fail.
let mise_path = ($nu.default-config-dir | path join "mise.nu")
if (which mise | is-not-empty) {
  ^mise activate nu | save -f $mise_path
} else if not ($mise_path | path exists) {
  "# devboost: mise not installed on this box — intentionally empty.\n" | save -f $mise_path
}
```

`dotfiles/dot_config/nushell/config.nu` — the small part:

```nu
# ~/.config/nushell/config.nu — dev-boost's nu configuration.
#
# READ THIS FIRST. Nushell here is an INTERACTIVE EXTRA, not a shell this machine runs on:
#   • bash (Linux) / zsh (macOS) remain the login shell. dev-boost never runs `chsh` and
#     never adds nu to /etc/shells.
#   • Agents (Claude Code, Codex, pi) invoke nu as `nu -c "…"`, which reads NONE of this
#     file — by design: that makes an agent's nu identical on every machine.
#   • Do NOT chsh to nu. Among other things `dev <repo>` ends in `exec "${SHELL:-bash}" -i`
#     and nu has no `-i` flag, so the helper would die instead of giving you a shell.
#   • Reach the POSIX helpers (dev / expose / pw-*) from nu as: bash -lc 'dev myrepo'
#
# devboost — managed by chezmoi; edit dotfiles/dot_config/nushell/config.nu in the
# dev-boost repo. Do not edit this file manually.

use std/config *
use ($nu.default-config-dir | path join "mise.nu")

# direnv — the cookbook's env_change.PWD hook (needs nu >= 0.104). `update cells` puts
# direnv's string PATH back into a nu list via the stdlib conversion.
$env.config.hooks.env_change.PWD = ($env.config.hooks.env_change.PWD? | default [])
$env.config.hooks.env_change.PWD ++= [{||
  if (which direnv | is-empty) { return }
  direnv export json | from json | default {} | update cells --columns [ PATH ] {
    do (env-conversions).path.from_string $in
  } | load-env
}]
```

Everything else — table style, banner, history — is left at nu's built-in defaults
(§3.3: the defaults now live in the binary, and `default_config.nu` is essentially empty).
Fewer settings written = fewer things a minor bump can invalidate.

`.chezmoiignore`: **no change**. The files apply on Linux and macOS alike (same seed, same
path — exactly how `~/.config/zed` is handled). Omarchy ships no nushell config, so there is
no `omarchy-refresh-config` race to dodge.

`shell.py`: one dict grows (D14):

```python
_TAKEN_OVER_CONFIGS = {
    ".config/voxtype/config.toml":  "dot_config/voxtype/config.toml.tmpl",
    ".config/nushell/config.nu":    "dot_config/nushell/config.nu",
    ".config/nushell/env.nu":       "dot_config/nushell/env.nu",
}
```

No other change to `shell.py`: `Dotfiles._taken_over_for` already merges `_TAKEN_OVER_CONFIGS`
into both the macOS and the Linux sets, and `back_up_taken_over` / `record_taken_over` then
handle these paths with no new code.

---

## 7. What verify checks (summary)

| OS | `verify` |
|---|---|
| macOS | `BrewFormula("nushell").verify(ctx)` — asks brew, not PATH (base-class rationale: macOS ships its own old tools that would satisfy a `which`) |
| Linux (all) | `which("nu")` **and** `nu --version` ≥ `0.106.0`; a failed or unparseable `--version` is drift |

The dotfiles are verified by the existing `Dotfiles` digest stamp — no nushell-specific
verify, and no second module. Adding one would mean a module whose verify re-implements
chezmoi's job.

---

## 8. Non-goals

Stated flatly, because each is a thing a reasonable person might otherwise assume:

1. **nu does not become the login shell.** Not by default, not behind a flag, not behind a
   profile. dev-boost adds no `chsh` capability and does not write `/etc/shells`.
2. **nu does not become `$SHELL`.** Nothing in `env.sh`, `shell.bash`, `shell.zsh`,
   `dot_zprofile` or `dot_bash_profile` changes.
3. **nu does not become the agent shell.** Claude Code's Bash tool, the Codex and `pi`
   harnesses, and `RealExecutor` keep running POSIX shells. Agents reach nu as `nu -c "…"`
   from inside those.
4. **nu is not a member of `base`, `cli`, `shell`, `full`, `macos`, `terminal`, `omarchy`,
   `server`, or any other profile.** It has no profile at all.
5. **No profile named `nushell` is created** — now or later (project memory rule: a profile
   name must never equal a module name).
6. **No carapace** (D10), no nu port of the `dev`/`expose`/`pw-*` helpers (D11), no
   `login.nu` (D12), no nu plugins, no `nu_plugin_*` registration.
7. **herdr is not reconfigured.** No per-pane nu default; `dot_config/herdr/config.toml` is
   untouched.
8. **No Windows.** Out of the platform's scope entirely.
9. **No nu scripts in `scripts/`.** Constitution: bash there is a non-logic bootstrap stub
   and everything else is typed Python. nu is a third thing; it does not get a foothold.

---

## 9. Risks

| # | Risk | Mitigation |
|---|---|---|
| **R1** | **Pre-1.0 breaking changes.** 0.116.0 with a minor every 4–7 weeks and no 1.0; minors are where breaking changes land. | The binary is **pinned** (D5), so a release cannot change a built machine. Bumps are deliberate and reviewed (Constitution III). The *integration* surface is where breakage would show, and it is four generated files + one hook — small enough to re-verify in minutes against the release notes at bump time. Make "read nushell's release notes" an explicit step of the pin bump. |
| **R2** | **Config-format churn specifically.** nu has reshaped its config at least three times (`let-env config` → grouped record → `$env.config` with built-in defaults, §3.3), and CI cannot catch a `.nu` parse error — our gates type-check Python, not nu. | Ship the *minimum* that makes a pane usable (D8) and nothing cosmetic; let built-in defaults be the defaults. Keep every integration behind a `which` guard so a missing tool degrades to a no-op. **Add a nu-syntax gate (M3):** a test that runs `nu --config <ours> --env-config <ours> -n -c 'exit 0'` when `nu` is on PATH and skips otherwise — cheap, and it turns a silent REPL break into a red test on any dev box with nu installed. Never copy a config snippet out of an old blog post (the carapace one is the live example of why). |
| **R3** | **POSIX assumptions elsewhere.** Tools, scripts and harnesses that assume `$SHELL` is POSIX. | Structurally avoided rather than mitigated: nu never becomes `$SHELL` (§8), the engine never reads `$SHELL` (`executor.py:80`), and every `scripts/*.sh` has a shebang. The residual exposure is only the operator's own F1. |
| **R4** | **Operator foot-gun: `chsh` to nu.** | Hard to reach by accident: the module does not add nu to `/etc/shells`, and without that entry `chsh` refuses the shell — the operator must first edit a root-owned file. The `config.nu` header names the consequence, including the concrete `dev` breakage (F2). dev-boost does not try to *prevent* a determined operator; it declines to pave the road. |
| **R5** | **Fedora's stale 0.99.1 silently satisfying `which nu`.** | D4's version floor. This is the subtlest failure in the whole design — a half-configured shell that reports healthy — and it is the reason `verify` is not just `which`. |
| **R6** | **Two divergent shell configs to maintain** (`shell.bash`/`shell.zsh` vs `env.nu`/`config.nu`): a tool added to one and forgotten in the other. | Accepted, and bounded by D8/D11: the nu side carries *only* the five initialisers, never the helpers or aliases. A test asserts the shipped `env.nu` references exactly the five (M2), so adding a sixth initialiser to bash without a decision about nu shows up as a conscious choice, not a silent drift. |
| **R7** | **macOS config-dir divergence** (`~/Library/Application Support/nushell`). | D6's symlink plus the existing `XDG_CONFIG_HOME` export in `env.sh`. Two independent routes to the same files; the symlink never replaces a real directory. |
| **R8** | **The pinned tarball's inner layout / glibc floor are unverified** (§3.2). | Blocking items for M1: `tar -tf` the pinned asset, and run `scripts/check-glibc-floor.sh`. Switch to the `-musl` asset if the floor is too high (`sd` already does this on aarch64). Do not ship on an assumption. |
| **R9** | **Yet another opt-in tool nobody uses**, carrying maintenance forever. | Honest and real. Bounded by the small blast radius (one module, two dotfiles, one catalog table) and by the fact that the *valuable* half — `nu -c` for agents — needs no config at all and keeps working even if the interactive half rots. If the interactive config ever becomes a burden, delete it and keep the binary; that is a clean, independent retreat. |

---

## 10. Honest assessment — what should and should not be built

**Build the install.** It is one `PackageModule` subclass with one override, following a path
this repo has walked a dozen times, and it unlocks a genuinely better output contract for
every agent on the box at the cost of `nu -c`. The agent-facing value is real, is independent
of configuration, and is immune to nu's config churn.

**Build the config — but keep it to the five lines sketched in §6.4, and do not grow it.**
The argument for *some* config is that a nu pane without a prompt, without `.envrc`, and
without mise's PATH is strictly worse than the bash pane next to it and would simply go
unused; five generated lines close that gap. The argument against *more* is §3.4: an agent
reads none of it, so every additional line is pure operator ergonomics bought with pre-1.0
maintenance risk that CI cannot see.

**Do not build**, and this is the part worth saying plainly:

- **A `nushell` profile.** There is nothing to group. One module, opt in by name
  (`devboost install nushell`) — Superfile's shape, and it makes the name-collision rule
  moot instead of merely satisfied.
- **Carapace, and any completion-engine work.** (D10.) Three independent reasons; the stale
  canonical snippet alone should stop it.
- **A nu port of the `dev`/`expose`/`pw-*` helpers.** (D11.) Doubling the maintenance of the
  box's most operationally load-bearing shell functions so they also work in a shell nobody
  logs into is a bad trade at any price. `bash -lc 'dev myrepo'` already works from nu.
- **Any form of "make nu your shell" support** — a flag, a profile, a documented `chsh`
  recipe, a herdr per-pane default. The ceiling on the upside is a nicer REPL; the floor on
  the downside is an operator who cannot run their own agent harness. dev-boost's entire
  value proposition is unattended reproducibility; shipping a supported path to a
  non-POSIX login shell contradicts it.

If only one of these ships, ship the install.

---

## 11. Testing

New file `engine/tests/modules/test_nushell.py`, modelled directly on
`engine/tests/modules/test_superfile.py` and `test_glow.py` (same `OsInfo` constants, same
`FakeExecutor` + `ex.calls[-1]` assertion style, same "is it opt-in" closing test).

```python
MAC     = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA  = OsInfo("fedora", "fedora", "x86_64")
UBUNTU  = OsInfo("ubuntu", "debian", "x86_64", version_id="24.04")
ARCH    = OsInfo("arch", "arch", "x86_64")
OMARCHY = OsInfo("omarchy", "arch", "aarch64", id_like=("arch",))
```

| # | Test | Asserts |
|---|---|---|
| T1 | `test_nushell_uses_the_packaged_build_where_one_is_current` | MAC → `["brew","install","--formula","-y","nushell"]`; ARCH → `["sudo","pacman","-S","--needed","--noconfirm","nushell"]` (the `test_superfile` / `test_glow` shape) |
| T2 | `test_nushell_on_omarchy_uses_the_omarchy_pkg_helper` | `FakeExecutor(present={"omarchy-pkg-add"})` → `["omarchy-pkg-add","nushell"]` |
| T3 | `test_fedora_and_debian_install_the_pinned_tarball_not_the_distro_package` | both → `ex.calls[-1][:2] == ["sh","-c"]`; the script contains the pinned version, the pinned **sha256**, `sha256sum -c -`, `curl -fL`, `--proto '=https'`, and `install -m 755`; and it contains **no** `dnf install nushell` / `apt-get install nushell`. Comment cites §3.2: Fedora's 0.99.1 is below the integration floor |
| T4 | `test_pinned_asset_is_selected_by_os_and_arch` | `OsInfo("fedora","fedora","aarch64")` → the `aarch64` URL + its sha256; a Mac can never select a Linux asset (`asset_key` contract) |
| T5 | `test_unknown_arch_raises_installerror` | `OsInfo("fedora","fedora","riscv64")` → `InstallError` naming `nushell` (no silent skip — Constitution II) |
| T6 | `test_verify_enforces_the_version_floor_not_just_which` | `present={"nu"}` + `scripts={"nu": Result(0, stdout="0.116.0")}` → True; `"0.99.1"` → **False** (the Fedora-package trap, F7); `Result(1)` → False; unparseable stdout → False |
| T7 | `test_verify_on_macos_asks_brew_not_path` | macOS verify goes through the brew strategy, not `which` |
| T8 | `test_nushell_is_opt_in_and_re_runnable` | `Nushell.profiles == ()`, `Nushell.self_updating is True`, `Nushell.gui is False`, `Nushell.families == ()` |

Catalog + profile + dotfiles guards:

| # | Test | Where | Asserts |
|---|---|---|---|
| T9 | `test_nushell_pin_is_wellformed` | `engine/tests/` beside the existing catalog tests | `nushell_pin()` loads; `version` is set; both `linux-*` assets have a 64-hex sha256 and a URL containing that version |
| T10 | `test_no_profile_is_named_after_a_module` | `engine/tests/cli/` | the **general** form of the project rule: `set(profiles) & set(modules) == set()` against the real `profiles.toml` + registry. Catches `nushell` and every future collision, not just this one |
| T11 | `test_nushell_is_in_no_profile` | `engine/tests/cli/` | `"nushell"` appears in no profile list in `profiles.toml` (the lock that keeps D1/D2 true, mirroring `test_orca_profile.py`'s expansion lock) |
| T12 | `test_nu_dotfiles_never_make_nu_the_login_shell` | `engine/tests/` | the shipped `dot_config/nushell/*.nu` contain no `chsh`, no `/etc/shells`, no `$env.SHELL` assignment; `config.nu` carries `_MANAGED_MARKER`; `env.nu` references exactly the five tools of D8 (R6's drift lock) |
| T13 | `test_nu_config_parses` (skip-unless-present) | `engine/tests/` | when `nu` is on PATH: `nu -n --config <repo config.nu> --env-config <repo env.nu> -c 'exit 0'` exits 0. Otherwise `pytest.skip`. The only gate that can catch R2 |

Merge gates, unchanged and all required green from `engine/`:
`uv run ruff check` · `uv run mypy` · `uv run pytest` · 100-col lines.
`engine/tests/core/test_macos_contract.py` ("fails if you add a module with no macOS answer")
is satisfied for free by `PackageModule`'s brew path.

---

## 12. Milestones

Small and ordered; each ends green on all three gates and is independently committable.

**M0 — resolve the two blocking unknowns (no code).**
`tar -tf` the pinned `linux-x86_64` asset to fix the inner path; run
`scripts/check-glibc-floor.sh` against it and switch to `-musl` if the floor is too high.
Record both answers in this file. *(R8; blocks M1.)*

**M1 — the pin.** `[nushell]` in `catalog.toml` + `nushell_pin()` in `media/catalog.py` + T9.
*(D5.)*

**M2 — the module.** `engine/src/devboost/modules/nushell.py`, T1–T8, T10, T11. Opt-in,
no profile, version floor, pinned tarball. **This is the milestone that delivers the agentic
value** — `nu -c` works the moment the binary lands, with no config at all.
*(D1–D4, D15, D16.)*

**M3 — the config.** `dotfiles/dot_config/nushell/{env.nu,config.nu}`, the
`_TAKEN_OVER_CONFIGS` entries in `shell.py`, the macOS symlink, T12, T13.
*(D6–D9, D13, D14.)*

**M4 — docs + README.** A short "Nushell (opt-in)" section in `docs/` stating: how to install
it, that it is never the login shell, that agents use `nu -c`, that `bash -lc '<helper>'`
reaches the POSIX helpers, and how to bump the pin (including "read nushell's release notes").
Regenerate the README module table:
`uv run --project engine python scripts/gen_profiles_table.py`, splice between the
`<!-- BEGIN/END generated profiles table -->` markers (README.md:95 / :321), and confirm a
`nushell` **module** row appears and **no** `nushell` profile row does.

M2 is shippable alone. M3 is shippable alone on top of it. If M3 ever becomes a maintenance
burden, it can be deleted without touching M1/M2 (§10).

---

## 13. Sources

**Upstream, fetched 2026-10-02:** `api.github.com/repos/nushell/nushell` (+ `/releases`,
`/releases/latest`, `/contributors`); `nushell.sh/book/configuration.html`;
`nushell.sh/cookbook/direnv.html`; `nushell.sh/cookbook/external_completers.html`;
`nushell.sh/book/3rdpartyprompts.html`; `nushell.sh/commands/docs/detect_columns.html`;
`nushell.sh/blog/2022-09-06-nushell-0_68.html` (cited only as the **stale** carapace snippet);
`starship.rs/guide/`; `github.com/ajeetdsouza/zoxide` README (`main`);
`github.com/atuinsh/atuin` `crates/atuin/src/command/client/init.rs` + `src/shell/`;
`github.com/jdx/mise` `docs/installing-mise.md`, `docs/getting-started.md`;
`github.com/carapace-sh/carapace-bin` README. Nushell docs were resolved through `ctx7`
(`/websites/nushell_sh_book`, `/websites/nushell_sh`) and cross-checked against the live
pages.

**Packaging APIs, queried 2026-10-02:** `formulae.brew.sh/api/formula/{nushell,carapace}.json`;
`archlinux.org/packages/search/json/?name={nushell,carapace}`;
`mdapi.fedoraproject.org/{f43,f44,rawhide}/pkg/nushell`;
`copr.fedorainfracloud.org/api_3/project/search` + `/api_3/package/list`;
`packages.debian.org/search` and `packages.ubuntu.com/search` (`searchon=names`, `suite=all`);
`aur.archlinux.org/rpc/v5/info`.

**In-repo:** `CLAUDE.md`; `.specify/memory/constitution.md` (v3.1.0); `docs/roadmap.md`;
`docs/adding-a-module.md`; `profiles.toml`; `catalog.toml`;
`engine/src/devboost/modules/{_pkgmodule,cli_tools,shell,mise,herdr,orca}.py`;
`engine/src/devboost/{model,exec/executor,media/catalog}.py`;
`engine/tests/modules/{test_superfile,test_glow}.py`; `dotfiles/.chezmoiignore`;
`dotfiles/dot_config/devboost/{shell.bash,env.sh,aliases.sh}`;
`dotfiles/dot_config/herdr/config.toml`; `scripts/gen_profiles_table.py`; `scripts/*.sh`.

**Precedent designs:** `docs/superpowers/specs/2026-07-22-herdr-optional-app-design.md`
(pinned+checksummed opt-in binary; "why pinned, not `latest` or `curl|sh`");
`docs/superpowers/specs/2026-09-09-orca-module-design.md` +
`docs/superpowers/plans/2026-09-09-orca-module.md` (the opt-in-module doc shape followed here).
