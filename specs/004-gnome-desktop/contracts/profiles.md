# Contract: `profiles.toml` — add `gnome` + opt-in `gnome-aesthetics` + `gnome-theme`

Add to the existing `[profiles]` table (do NOT touch base/cli/shell):
```toml
gnome            = ["gnome-settings","gnome-extensions","gnome-manager-apps"]
gnome-aesthetics = ["gnome-aesthetics"]   # opt-in, NOT in full
gnome-theme      = ["gnome-theme"]        # opt-in, NOT in full
```
- `profile_expand gnome` → those 3 modules; `gnome-aesthetics`/`gnome-theme` → 1 each.
- `devboost list --profile gnome` depsorts without cycle (gnome-settings before
  gnome-extensions/manager). Full-resolution test DEFERRED to polish (after modules exist),
  same pattern as Specs 2/3.

## Tests (extend `tests/profiles.bats`)
- `profile_expand gnome`/`gnome-aesthetics`/`gnome-theme` membership/count (TOML-only).
- Full `list --profile gnome` depsort-without-cycle DEFERRED to the polish task.
