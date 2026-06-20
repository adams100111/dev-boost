# Contract: `profiles.toml` — add `cli` + `shell`

Add two entries to the existing `[profiles]` table (do NOT touch `base` or remove anything):
```toml
cli   = ["eza","bat","btop","zoxide","atuin","direnv","delta","lazygit","lazydocker",
         "dust","duf","sd","yq","gh","tealdeer","tpm","fastfetch","claude-code"]
shell = ["starship","bash-config","ghostty","nerd-fonts","dotfiles"]
```
- `profile_expand cli` → exactly those 18 modules; `profile_expand shell` → those 5.
- `devboost list --profile cli` and `--profile shell` depsort without cycle (after all
  these modules exist) and place `mise`(base) before `claude-code`, the inited tools
  before `dotfiles`, `dotfiles` before `bash-config`.

## Tests (extend `tests/profiles.bats`)
- `profile_expand cli`/`shell` membership/count (needs only the TOML).
- Full `devboost list --profile cli,shell` depsort-without-cycle is DEFERRED to the polish
  task (after all modules exist), same pattern as Spec 2's T019.
