# Contract: `profiles.toml` — add `gnome` + opt-in `gnome-aesthetics` + `gnome-theme`

Add to the existing `[profiles]` table (do NOT touch base/cli/shell):
```toml
gnome            = ["gnome-settings","gnome-extensions","gnome-manager-apps"]
gnome-aesthetics = ["gnome-aesthetics-bundle"]   # opt-in, NOT in full
gnome-theme      = ["gnome-theme-bundle"]        # opt-in, NOT in full
```
- `profile_expand gnome` → those 3 modules; `gnome-aesthetics`/`gnome-theme` → 1 each (`gnome-aesthetics-bundle`/`gnome-theme-bundle`).
- `devboost list --profile gnome` depsorts without cycle (gnome-settings before
  gnome-extensions/manager). Full-resolution test DEFERRED to polish (after modules exist),
  same pattern as Specs 2/3.

## Tests (extend `tests/profiles.bats`)
- `profile_expand gnome` membership/count (3 modules).
- `profile_expand gnome-aesthetics` → `gnome-aesthetics-bundle` (non-empty, 1 module).
- `profile_expand gnome-theme` → `gnome-theme-bundle` (non-empty, 1 module).
- Full `list --profile gnome` depsort-without-cycle DEFERRED to the polish task.
