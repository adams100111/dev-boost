# Contract: `profiles.toml` (NEW — first real profiles file)

The engine reads `$DEVBOOST_PROFILES` (default `$DEVBOOST_ROOT/profiles.toml`) via
`lib/profile.sh::profile_expand`. This feature creates it with the `base` set.

```toml
[profiles]
base = ["secrets","ssh-setup","rpmfusion","dnf-tune","fedora-third-party","flatpak",
        "coreutils","git","curl","wget","unzip","jq","htop","ripgrep","fd","fzf","tmux",
        "build-tools","mise","chezmoi","docker"]
```

- Only `base` is defined now; later specs add `cli`, `shell`, etc. (do NOT add empty
  placeholders).
- `profile_expand base` MUST flatten to exactly these modules (order irrelevant; depsort
  orders by `requires`).
- `secrets`/`ssh-setup` already exist (Spec 1) and are referenced, not re-created.

## Tests (`tests/profiles.bats`)
- `profile_expand base` yields the full module set (count + membership).
- `devboost list --profile base` (with real `profiles.toml` + `modules/`) depsorts without
  cycle and places `rpmfusion`/`secrets` before their dependents.
