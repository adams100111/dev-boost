# dev-boost — zsh optional interactive shell

**Status:** Design — ready for implementation planning
**Date:** 2026-07-29
**Author:** dits.sa.co@gmail.com

---

## 1. Goal

Add **zsh** — configured as a productive interactive login shell — to dev-boost as an
**opt-in, off-the-production-path** profile, together with a **curated, pinned** set of
four zsh plugins and a **chezmoi-managed** config ported from
[`radleylewis/zsh`](https://github.com/radleylewis/zsh) (a tasteful, framework-free zsh
setup: XDG-clean, vi-mode, autosuggestions, syntax highlighting, history-substring
search, fzf/zoxide/eza/bat integration).

The config's *taste and tool list* are adopted; its *install mechanism* is not. Upstream
clones plugins over the network on first interactive launch at an unpinned branch HEAD —
which violates dev-boost's reproducibility and unattended-install principles. Instead the
plugins are **vendored at pinned git refs during provisioning**, and the shell rc files
are shipped through dev-boost's **chezmoi source tree**, exactly as Spec 003 ships the
bash/starship/wezterm/tmux config.

zsh runs *as an alternative to* bash for the **interactive** shell only. Bash remains the
default login shell for anyone who doesn't opt in, and remains the scripting shell
everywhere (`get.sh`, Kickstart `%post`, module `Executor` shell-outs are untouched).

### Non-goals

- **Not on the default/production set.** zsh ships only under an opt-in profile; a
  freshly-built box is still bash-by-default unless the profile is selected.
- **Not a scripting-shell change.** No provisioning script, `get.sh`, `%post`, or engine
  `Executor` call is rewritten in zsh. This is purely the human's interactive shell.
- **Not oh-my-zsh / zinit / a plugin framework.** We keep upstream's ~40-line, no-framework
  approach — but replace its first-launch network clone with a pinned provisioning step.
- **No new prompt.** starship (shipped by Spec 003) is reused and normalizes the prompt
  across bash and zsh; we do not ship a second prompt or duplicate `starship.toml`.
- **No new CLI tools.** `ripgrep`, `fd`, `bat`, `fzf`, `zoxide`, `eza`, `neovim`,
  `starship` are already installed by the Spec 003 `cli` profile; this profile *requires*
  them, it does not reinstall them.

---

## 2. Placement & profile

- New opt-in profile **`optional-zsh`** (category `optional-shell`), following the
  `optional-editors` / `optional-agents` / `security-cli` pattern in
  `engine/src/devboost/modules/optional.py`. It is **not** included in any
  default/production profile.
- New typed module file: `engine/src/devboost/modules/zsh.py` (one file, `@register`
  classes, `mypy --strict` clean), holding `Zsh`, `ZshPlugins`, `ZshConfig`, and the
  opt-in `ZshDefaultShell` module (§6).
- Profile name `optional-zsh` deliberately differs from every module name (the
  **profile/module name-collision rule** — `Zsh`, not `optional-zsh`, is the module).
- Module dependency spine:
  `Zsh` → `ZshPlugins` (`requires=(Zsh,)`) → `ZshConfig` (`requires=(Zsh, ZshPlugins)`)
  → `ZshDefaultShell` (`requires=(ZshConfig,)`). `ZshConfig` additionally declares a soft
  dependency on the Spec 003 `cli`/`shell` deliverables (starship + the CLI toolset) so
  the config it applies has its referenced binaries present.

---

## 3. Package install — `Zsh` module

zsh **is** a first-class Fedora package (`dnf install zsh`), so — unlike herdr — there is
no release-binary download or SHA256 pin to manage; the distro package + repo GPG chain is
the trust boundary.

### Behavior
- `install()`: install the `zsh` package via the existing `lib/pkg` helper (Fedora: `dnf`).
- `verify()`: `ctx.ex.which("zsh")`.
- **OS-dispatch seam:** Fedora is the reference implementation; `Apt`/`debian`
  (`apt-get install zsh`) and Homebrew (`brew install zsh`) branches are stubbed
  (`raise UnsupportedOS` / `# seam — not implemented`) for later OSes, consistent with the
  engine's per-OS strategy (Spec 014). macOS already ships zsh as default; the Homebrew
  branch would install the newer keg only.

---

## 4. Plugins — `ZshPlugins` module

`requires = (Zsh,)`. Ships the **curated, pinned** set — the exact four upstream uses —
each as an `(id, owner/repo, git-ref)` tuple, mirroring the `HerdrPlugins` module.

### Pin (in `catalog.toml`)
A new tooling table alongside `[ventoy]` / `[herdr]`:

```toml
[zsh_plugins]
# each pinned to a reviewed commit SHA (not a branch/tag that can move); bump deliberately.
autosuggestions          = { repo = "zsh-users/zsh-autosuggestions",              ref = "<sha>" }
history_substring_search = { repo = "zsh-users/zsh-history-substring-search",      ref = "<sha>" }
vi_mode                  = { repo = "jeffreytse/zsh-vi-mode",                      ref = "<sha>" }
fast_syntax_highlighting = { repo = "zdharma-continuum/fast-syntax-highlighting",  ref = "<sha>" }
```

`catalog.toml`'s load-time validation is extended to check the `[zsh_plugins]` entries
(each has a `repo` slug and a 40-hex `ref`).

### Behavior
- `install()`: for each plugin, clone into the chezmoi-applied plugins dir
  (`${ZDOTDIR:-$HOME/.config/zsh}/plugins/<name>`) and **check out the pinned SHA**
  (`git clone` → `git -C <dir> checkout <ref>`, or `git fetch --depth=1 origin <ref>`).
  If the dir already exists, fetch + checkout the pinned ref (idempotent; re-pin on bump).
- `verify()`: each plugin dir exists **and** `git -C <dir> rev-parse HEAD` == the pinned
  ref (so a drifted checkout is a failure, not a silent pass).
- Runs **during provisioning**, not at first shell launch — the first interactive zsh
  needs no network and is fully deterministic.

### Why pinned SHAs (not upstream's first-launch `git clone --depth=1`)
1. **Reproducibility** — identical fresh machines must converge to the same state; a
   default-branch HEAD clone diverges over time with no last-good rollback. This is the same
   argument that pins every ISO, ventoy, and the herdr binary.
2. **Unattended / offline** — first interactive shell must not depend on network reachability
   or an upstream being up; provisioning is the one controlled network phase.
3. **Supply chain** — `fast-syntax-highlighting` lives under `zdharma-continuum` (the
   community fork after the original `zdharma` maintainer deleted their repos). A pinned,
   reviewed SHA means an upstream force-push or account compromise can't silently land new
   code on a fresh box; the checksum-equivalent here is the commit SHA.

The upstream `zplugin-update` convenience is replaced by **re-pinning in `catalog.toml`**
(a reviewed bump), consistent with how every other dev-boost dependency is updated.

---

## 5. Config — `ZshConfig` module (chezmoi)

`requires = (Zsh, ZshPlugins)`. The rc files are **ported into dev-boost's own chezmoi
source tree** (`dotfiles/`, the source of truth per Spec 003 §2/§6.5) and applied with
`chezmoi apply` — never cloned from the upstream repo.

### Shipped files (ported from `radleylewis/zsh`, lightly adapted)
- `.zshenv` — XDG dirs, `EDITOR`/`VISUAL=nvim`, `GPG_TTY`, `PATH` prepend of `~/.local/bin`,
  `ZDOTDIR=$XDG_CONFIG_HOME/zsh`. **Reconciled with the existing bash env** so exported
  vars stay consistent across shells (no divergent `PATH`/`EDITOR`).
- `.zshrc` — history opts (XDG history file, `SHARE_HISTORY`, dup-ignore), `AUTOCD`,
  completion (`compinit` cached, menu-select, case-insensitive), and the module sources.
- `aliases.zsh`, `bindings.zsh` (vi-mode word-jump), `fzf.zsh` (Ctrl-R/T/F).
- `plugins.zsh` — **rewritten**: no `_zplugin_load` network clone; it simply sources the
  four pinned plugin dirs that `ZshPlugins` already placed. `zplugin-update` is dropped
  (updates happen via re-pin).
- `prompt.zsh` — initializes **starship** (already installed by Spec 003) pointing at the
  **existing shipped `starship.toml`**; no second prompt config is added.

### Behavior
- `install()`/`apply`: `chezmoi apply` the zsh-scoped files; ensure `/etc/zsh/zshenv`
  points `ZDOTDIR` at `$XDG_CONFIG_HOME/zsh` (idempotent managed block, not a clobber).
- `verify()`: `~/.config/zsh/.zshrc` present and the managed `/etc/zsh/zshenv` block in
  place; `zsh -ic 'exit'` returns 0 (config loads without error, plugins source cleanly).
- **Idempotent** — re-apply changes nothing and does not duplicate startup entries
  (same guarantee as Spec 003 FR-009).

---

## 6. Default-shell switch — `ZshDefaultShell` module

A configured zsh that isn't your login shell is pointless; but flipping the login shell in
an unattended build is the one genuinely user-visible, mildly-risky action here — so it is
its **own module**, gated so selecting `optional-zsh` is what opts you in.

### Behavior
- `install()`: if the target user's shell is not already zsh, `chsh -s "$(command -v zsh)"`
  for the provisioning target user. Guard: only run when `zsh` is in `/etc/shells` (add it
  if the package didn't); **check current shell first** so re-runs are a no-op.
- `verify()`: `getent passwd <user>` login shell == the zsh path.
- **Bash is never removed or altered** — it remains a working login shell and the scripting
  shell. A user can revert with a single `chsh -s /bin/bash`.
- **OS seam:** Fedora reference; macOS/Ubuntu branches stubbed. On the frozen-binary /
  root-readonly path, the chsh targets the real provisioning user, not `settings.root`.

---

## 7. Interaction with existing shell setup (Spec 003)

- **No duplication.** starship, wezterm, tmux, fonts, and the CLI toolset are Spec 003's;
  `optional-zsh` *reuses* them. The only net-new artifacts are the `zsh` package, four
  pinned plugin dirs, the zsh-scoped rc files, and the `/etc/zsh/zshenv` `ZDOTDIR` block.
- **fzf/zoxide/eza/bat integration** already exists for bash (Spec 003 US3); the zsh
  `fzf.zsh`/`plugins.zsh` wire the same tools into the zsh startup — same binaries, zsh
  init lines.
- **tmux** `default-shell` is left as-is; users who want tmux to spawn zsh set it in their
  personal `DEVBOOST_DOTFILES_REPO` layer (out of scope), or it follows the login shell.

---

## 8. Testing (bats-stub harness + engine tests)

- `Zsh.verify` → `zsh` present; idempotent re-install is a no-op; unknown OS reported
  unsupported (never silently skipped).
- `ZshPlugins` → each plugin dir at exactly the pinned SHA; a drifted/absent checkout
  fails; re-run with same pins is a no-op; a bumped pin re-checks-out.
- `ZshConfig` → `zsh -ic 'exit'` exits 0 with all four plugins sourced; managed
  `/etc/zsh/zshenv` block present and not duplicated on re-apply.
- `ZshDefaultShell` → login shell flips only when selected; re-run no-op; bash still a
  valid login shell afterward.
- `catalog.toml` load-time validation rejects a malformed `[zsh_plugins]` entry (missing
  repo / non-40-hex ref).
- `mypy --strict` + ruff + pytest are the merge gates (constitution v3.0.0).

---

## 9. Out of scope

- Making zsh the **default** production shell (a separate decision if this proves out).
- oh-my-zsh / zinit / any plugin framework or the upstream plugin marketplace.
- Rewriting any provisioning/scripting in zsh.
- Ubuntu/macOS implementation beyond the stubbed OS-dispatch seams.
- A personal-dotfiles bridge for zsh (the user's `DEVBOOST_DOTFILES_REPO` layer is theirs).

---

## 10. Spec-cycle & roadmap

- This design is the front-door; it graduates to a `specs/0NN-optional-zsh/` speckit cycle
  (spec.md/plan.md/tasks.md) if approved, or lands directly as a small module PR given how
  closely it mirrors the already-shipped `herdr` opt-in profile.
- Roadmap "Shipped, opt-in" gets an entry once landed:
  *"zsh optional interactive shell — pinned 4-plugin set + chezmoi config (ported from
  radleylewis/zsh), under the opt-in `optional-zsh` profile; bash stays default + the
  scripting shell. Spec: `docs/superpowers/specs/2026-07-29-zsh-optional-shell-design.md`."*
