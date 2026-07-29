# Targeted tool update (`devboost install --update`) — design

**Date:** 2026-07-29
**Status:** approved, pre-implementation

## Problem

dev-boost has no *safe, targeted* way to upgrade already-installed CLI tools.

The install model is verify-guarded and idempotent (`core/runner.py:50-65`): if `verify()`
passes, `install()` is skipped. So re-running `devboost install` on a provisioned box is a
no-op — it never upgrades tools that are already present. This is by design for cheap
convergence, but it means the modern-CLI toolset (lazydocker, lazygit, eza, atuin, dust, sd,
yq, fastfetch, gh, …) is frozen at whatever version first landed.

`devboost install --force` *does* upgrade everything (dnf/apt `install` upgrades in place;
the binary-drop tools re-fetch the latest release; the lazydocker/lazygit scripts self-update).
But `--force` re-runs **every** module, including the heavy, side-effecting ones:

- `Docker` restarts the daemon,
- `Dotfiles` runs `chezmoi apply --force`, overwriting local dotfile edits,
- GNOME/driver modules rewrite dconf and reinstall drivers.

So the only existing "update" is a blunt instrument that is disruptive for a routine
"bump my CLI tools" action. The gap is a *lightweight, non-destructive* tool refresh.

This is especially visible for **lazydocker** and **lazygit**, which install via their upstream
scripts / GitHub-release binaries to `~/.local/bin` (no `dnf`/COPR — see the 2026-07-29 installer
unification). They are outside the `dnf-automatic` security-update timer entirely, so *nothing*
updates them automatically.

## Goal

Add `devboost install --update`: force-refresh **only** the tools that are safe to re-run,
leaving heavy provisioning modules untouched.

## Design

### 1. A `self_updating` marker on modules

Add a class attribute to the module model:

- `Module.self_updating: ClassVar[bool] = False` (root default — the conservative choice).
- `PackageModule.self_updating = True` (override).

Rationale: a `PackageModule` is, by definition, a **single package or single binary** installed
and verified by presence on `PATH`. Re-running its `install()` is inherently safe — it
upgrades-in-place (`dnf install` / `apt-get install`) or re-fetches the latest binary/script,
and no-ops when already current. Every *dangerous* module (Docker, Dotfiles, GNOME, drivers) is
a plain `Module` subclass with a custom side-effecting `install()`, so it stays `False`
automatically. New CLI tools added as `PackageModule` subclasses opt in for free.

Individual modules may override `self_updating = False` if a specific package install turns out
to have side effects that should not be re-run on a routine update.

### 2. The `--update` install path

Add an `--update` flag to the `install` command (and it flows through the shared `_run` helper,
so the tier commands `term`/`devtools`/`server` inherit it).

Semantics:

- Resolve the normal ordered module set for the selected profiles (unchanged).
- For each module in dependency order:
  - if `module.self_updating` is `True` → **force-install** it (bypass the verify-skip, exactly
    like `--force` but scoped to this module),
  - else → **no-op** (do not install, do not force). A missing heavy module is *not* installed
    by `--update`; that is what a normal `install` is for.

`--update` and `--force` remain distinct and composable in meaning:

| Invocation | Effect |
|---|---|
| `devboost install` | verify-guarded: install only what's missing |
| `devboost install --force` | re-run **every** module unconditionally |
| `devboost install --update` | force-refresh **only** `self_updating` modules; skip the rest |

If both `--force` and `--update` are passed, `--force` wins (force everything) — `--update` is a
*narrowing* of force, so the broader flag dominates. This is a documented edge, not a hard error.

`--update` flows through the existing `_run` helper, so it **retains the up-front
`refresh_index`** (`apt-get update` on Debian; no-op on Fedora). This matters: an apt-backed
`self_updating` tool would otherwise re-install against stale metadata and never see a newer
version. `--offline` remains honored (it skips the network refresh, and the binary-drop tools
that need network simply fail-soft as they do today).

### 3. Documentation

**`docs/maintenance.md` — new "Updating" section** making the three update channels explicit:

- `devboost self-update` — replaces the **engine binary** (checksummed GitHub-release swap).
- `devboost install --update` — upgrades the **CLI tools** in place (the `self_updating` set).
- the `dnf-automatic` timer — **OS security** patches only (provisioned by `dnf-automatic-security`).

The same section documents that **lazydocker and lazygit install via their upstream scripts to
`~/.local/bin`** (no `dnf`/COPR), which is exactly why they rely on `install --update` to upgrade
rather than riding OS package updates — the install method and the update path are documented as
one coherent story. Any stale reference implying lazydocker comes from the `atim/lazydocker` COPR
is corrected to match the merged installer-unification change.

## Testing

- **Model:** `PackageModule().self_updating is True`; a plain `Module` subclass defaults `False`.
- **Runner:** with `--update` semantics,
  - a `self_updating` module is (force-)installed **even when `verify()` already passes**,
  - a non-`self_updating` module is **skipped even when it is missing** (`verify()` false).
- **CLI:** `install --update` wires through `_run` to the filtered path (smoke test on the Typer
  command, asserting the update flag reaches the runner).

## Out of scope

- A themed `~/.config/lazydocker/config.yml` dotfile (separate, un-greenlit work).
- Version-aware `verify()` (network calls in verify would break `--offline` and slow every run;
  explicitly rejected).
- Any change to the misnamed `devboost update` command (lockfile regeneration) — untouched.

## Merge gates

`uv run pytest` + `mypy --strict` + ruff green in `engine/`.
