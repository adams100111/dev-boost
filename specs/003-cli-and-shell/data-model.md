# Phase 1 Data Model: cli-and-shell

No database. "Data" = module manifests, the two profile entries, the chezmoi source tree,
and the user config each module installs/applies. Mutated paths overridable in tests.

## Module entities
- **Simple cli tool module** (`modules/<tool>.toml`): `name`, `category="cli"`, `verify`
  (`command -v <bin>`), `[install].<os>`, `requires=[]`. No install.sh.
- **Escape-hatch module** (`modules/<name>/{module.toml,install.sh}`): `gh`, `claude-code`
  (`requires=["mise"]`), `starship`, `ghostty`, `nerd-fonts`, `dotfiles`, `tpm`.

## profiles.toml (EDIT — add two entries)
```toml
cli   = ["eza","bat","btop","zoxide","atuin","direnv","delta","lazygit","lazydocker",
         "dust","duf","sd","yq","gh","tealdeer","tpm","fastfetch","claude-code"]
shell = ["starship","bash-config","ghostty","nerd-fonts","dotfiles"]
```
Ordering by `requires` (claude-code→mise; bash-config→dotfiles; dotfiles→starship/atuin/
zoxide/fzf/direnv where configs reference them — at minimum requires the tools it inits).

## chezmoi source tree (`dotfiles/`, organized as chezmoi source)
| Managed dest | Source (chezmoi name) | Content origin |
|---|---|---|
| `~/.bashrc` | `dot_bashrc` | curated rc + init lines (starship, atuin, zoxide, fzf, direnv) |
| `~/.config/starship.toml` | `dot_config/starship.toml` | opinionated starship config (design §6.2) |
| `~/.config/ghostty/config` | `dot_config/ghostty/config` | ghostty theme/font/keybinds (§6.2) |
| `~/.tmux.conf` | `dot_tmux.conf` | tmux 3.6+ config imported from ../setup-scripts (§6.1) |
| `~/.config/atuin/config.toml` | `dot_config/atuin/config.toml` | atuin config |
| `~/.claude/…` | `private_dot_claude/…` | claude-code config (chezmoi-managed) |

## State / verify per module
| Artifact | Owner | Verify |
|---|---|---|
| each cli tool | per-tool module | `command -v <bin>` |
| claude-code (npm global) | claude-code | `command -v claude` (after mise/node) |
| starship binary | starship | `command -v starship` |
| ghostty + config | ghostty | `command -v ghostty` |
| dev fonts | nerd-fonts | `fc-list | grep -qi 'JetBrainsMono Nerd Font'` |
| applied dotfiles | dotfiles | representative managed file present + dev-boost sentinel (e.g. `~/.config/starship.toml` exists) |
| bash rc wired | bash-config | rc applied (init lines present, single copy) |

## Validation rules (from FRs)
| Rule | Source |
|---|---|
| one module per tool, verify by binary | FR-001 |
| claude-code after runtime manager | FR-002, FR-012 |
| prompt init wired in shell startup, not duplicated | FR-003, FR-007, FR-009 |
| fonts skipped when already installed | FR-006 |
| config applied from dev-boost chezmoi source, idempotent | FR-009 |
| unmatched OS reported unsupported | FR-011 |
| configs contain no secrets; nothing secret in git | FR-014 |

## Ordering (depsort via requires)
```
mise (base) → claude-code
starship, atuin, zoxide, fzf(base? fzf is base), direnv → dotfiles (rc inits them) → bash-config
```
