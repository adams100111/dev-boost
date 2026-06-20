# Contract: `dotfiles` apply module + chezmoi source layout

## chezmoi source (repo `dotfiles/`, chezmoi naming)
Organize dev-boost's curated configs as a chezmoi source tree:
```
dotfiles/
├── dot_bashrc                       # curated rc + ALL shell-init lines (starship, atuin, zoxide, fzf, direnv) + dev-boost sentinel comment
├── dot_tmux.conf                    # tmux 3.6+ config imported verbatim from ../setup-scripts (§6.1)
├── dot_config/starship.toml         # opinionated starship config (§6.2)
├── dot_config/ghostty/config        # ghostty theme/font/keybinds (§6.2) + Ptyxis Mono gotcha note
├── dot_config/atuin/config.toml     # atuin config
└── private_dot_claude/…             # claude-code config (chezmoi-managed)
```
No secrets in any file (FR-014). Init lines live ONLY here (single source → no duplication).

## `modules/dotfiles`
- `requires`: the tools whose init the rc references that are in this feature
  (`starship`, `atuin`, `zoxide`, `direnv`; `fzf` is base) — so config applies after they exist.
- `verify`: a representative managed file is present and carries the dev-boost sentinel,
  e.g. `[ -f ~/.config/starship.toml ] && grep -q 'devboost' ~/.bashrc`.
- `install.sh`: `chezmoi apply --source "$DEVBOOST_ROOT/dotfiles" --destination "$HOME"`
  (source-override so dev-boost's tree is authoritative, independent of base's optional
  `DEVBOOST_DOTFILES_REPO`). Idempotent: chezmoi replaces managed files (no append → no
  duplicate rc lines, FR-007/FR-009). Never writes secrets.

## Tests (`tests/dotfiles.bats`) — stubbed `chezmoi apply` writing into scratch HOME
- apply writes the managed files (`~/.bashrc`, `~/.config/starship.toml`, `~/.tmux.conf`, …) with the init lines + sentinel.
- re-apply is a no-op: the rc has EXACTLY ONE copy of each init line (assert count==1).
- verify green only after apply; red before.
- the `chezmoi apply` stub asserts `--source` points at the dev-boost tree.
