# Phase 0 Research: cli-and-shell

Spec clarifications settled in specify. Remaining unknowns are plan-level; decisions below.

## D1. Tool granularity & install method
**Decision**: One module per cli tool. Pure-TOML (`verify=command -v <bin>`, per-OS dnf)
for everything packaged in Fedora/RPM Fusion: `eza, bat, btop, zoxide, atuin, direnv,
delta(git-delta), lazygit, lazydocker, dust, duf, sd, yq, tealdeer, fastfetch`. Escape
hatches only for: `gh` (add the GitHub CLI dnf repo first), `tpm` (tmux plugin manager —
git clone to `~/.tmux/plugins/tpm`, not a package), `claude-code` (npm global via mise
node), `starship`/`ghostty`/`nerd-fonts` (see below).
**Rationale**: matches the engine "one file per tool" principle and Spec-2 precedent;
keeps the diff/test surface minimal. Binary≠package names handled in `verify`
(eza→`eza`, git-delta→`delta`, tealdeer→`tldr`, dust→`dust` pkg `rust-dust`/`du-dust`).

## D2. claude-code (runtime-dependent)
**Decision**: `modules/claude-code` `requires=["mise"]`; install via `npm install -g
@anthropic-ai/claude-code` using mise-managed node (ensure a node version through mise
first). `verify=command -v claude`. The `~/.claude/` config is chezmoi-managed (D5).
**Rationale**: design §10c — claude-code is the primary AI agent in `cli`, installed as an
npm global via mise node. Dependency ordering via `requires` (engine handles it).

## D3. starship + shell init wiring
**Decision**: `starship` module installs the binary (dnf or the official installer). It
does NOT edit `~/.bashrc` directly — the chezmoi-managed bash rc (D5) contains
`eval "$(starship init bash)"` plus the `atuin`/`zoxide`/`fzf`/`direnv` init lines. So all
shell-startup wiring lives in ONE managed file, applied idempotently by the `dotfiles`
module. This satisfies FR-007 (no duplicate entries) structurally — a managed file is
replaced, never appended.
**Rationale**: avoids N modules each appending to `~/.bashrc` (a duplication/idempotency
hazard); the rc is the single source of the interactive-shell wiring.

## D4. ghostty + nerd-fonts
**Decision**: `ghostty` via COPR `dnf copr enable -y scottames/ghostty` then install;
config via chezmoi (D5); Ptyxis left installed as the GNOME fallback. `nerd-fonts`
downloads JetBrainsMono + Meslo Nerd Font Mono into `~/.local/share/fonts` and runs
`fc-cache`; `verify` via `fc-list | grep -qi 'JetBrainsMono Nerd Font'`. Both are
Fedora-reference; on unsupported OS the engine reports unsupported. Document the Ptyxis
`Mono` font gotcha in the config.
**Rationale**: design §6.2; COPR is the maintained ghostty path on Fedora; fc-list is the
durable font verify.

## D5. The chezmoi source tree + `dotfiles` apply module
**Decision**: dev-boost ships its curated configs in the repo `dotfiles/` directory,
organized as a **chezmoi source** (chezmoi naming, e.g. `dot_bashrc`,
`dot_config/starship.toml`, `dot_config/ghostty/config`, `dot_tmux.conf`,
`dot_config/atuin/config.toml`, `private_dot_claude/`). The existing `dotfiles/`
subdirs (bash/git/ssh/terminal/vscode/zsh) are reorganized/imported into this layout
(tmux + ghostty + bash rc imported from `../setup-scripts` §6.1). A `modules/dotfiles`
module runs `chezmoi apply --source "$DEVBOOST_ROOT/dotfiles" --destination "$HOME"`
(source-dir override so it applies dev-boost's tree, independent of any user
`DEVBOOST_DOTFILES_REPO`). `verify` = a representative managed file is present and matches
(e.g. `~/.config/starship.toml` exists and contains a dev-boost sentinel). `bash-config`
`requires=["dotfiles"]` (or folds into it) and verifies the rc is applied.
**Rationale**: design §2/§6.5 — configs live in `dotfiles/`, chezmoi-managed.
Source-override keeps this feature's configs authoritative and decoupled from the
optional personal-repo clone in base. `chezmoi apply` is inherently idempotent.
**Open for plan→tasks**: exact chezmoi source naming + which existing `dotfiles/` files
are kept vs imported from setup-scripts — resolved during implementation against the real
`../setup-scripts` content.

## D6. Testing (no real installs/network)
**Decision**: extend `tests/fixtures/base/stubs.bash` (backward-compatible) with stubs for
`cargo`, `npm`, `fc-list`/`fc-cache`, COPR (`dnf copr`), and a `chezmoi apply` stub that
records the source/dest + simulates writing managed files into the scratch HOME; plus
knobs for font-present/absent and apply-success. Tests assert: each tool's resolved
install command + binary verify; claude-code orders after mise; `dotfiles` apply writes
the managed files and re-apply is a no-op (no duplicate rc lines); unsupported-OS path.
**Rationale**: hermetic, fast, §V real-behavior; mirrors Spec 1/2.

## Outcome
No unresolved NEEDS CLARIFICATION. Ready for Phase 1.
