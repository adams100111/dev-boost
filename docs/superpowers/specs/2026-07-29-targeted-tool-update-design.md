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

Add an `--update` flag to the **`install` command only**. It is *not* added to the tier
commands `term`/`devtools`/`server` — those are independent Typer commands with their own
signatures, and `--update` is a cross-cutting mode, not a per-tier concept. This matches how
`--offline` is already `install`-only. The "update my terminal tier" case is
`devboost install --update terminal`.

**Implementation shape — filter the plan, reuse `force`, leave the runner untouched.** The
runner's force decision is global (`_run_one` checks `ctx.force`), so `--update` is implemented
entirely in the `_run` helper as *"a `--force` run over a filtered plan"*:

```python
# in _run(), after build_plan(order, modules, ctx.os):
if update:
    plan = [pm for pm in plan if modules[pm.name]().self_updating]
    if not plan:
        log.info("no self-updating tools in selection")
    force = True   # force-install the kept (self_updating) modules
```

`core/runner.py` is **not modified** — the kept modules force-install through the existing
verify-guarded loop; everything else simply isn't in the plan. Dependency-block logic still
works (deps not in the filtered plan just aren't checked).

Resulting behavior:

| Invocation | Effect |
|---|---|
| `devboost install` | verify-guarded: install only what's missing |
| `devboost install --force` | re-run **every** module unconditionally |
| `devboost install --update` | force-refresh **only** `self_updating` modules; skip the rest |

**`--force` and `--update` are mutually exclusive** — passing both raises
`typer.BadParameter("--force and --update are mutually exclusive")`. The two modes are
conceptually opposed ("everything" vs "only the refreshable tools"); erroring is the only
contract that never silently discards a flag the user typed. (Guard lives in the `install`
command, before `_run`.)

**Ordering / offline:** `--update` keeps the up-front `refresh_index` already in `_run`
(`apt-get update` on Debian; no-op on Fedora) — without it, an apt-backed `self_updating` tool
would re-install against stale metadata and never see a newer version. `--offline` composes:
the plan is filtered to `self_updating` **then** the offline filter drops network-only modules.
`--dry-run` previews the filtered set as "would install".

**`--app` composition:** `--app` intersects with the `--update` filter — `install --app
lazydocker --update` refreshes lazydocker; `install --app docker --update` yields an empty plan
(docker is not `self_updating`) → the "no self-updating tools in selection" no-op. To force a
single *non*-refreshable app, use `install --force --app docker` (`--force`/`--app` are not
mutually exclusive; only `--force`/`--update` are).

### 3. Documentation

**`docs/maintenance.md` — new "Updating" section** disambiguating the three "update" surfaces
up front (the collision is real: a user wanting to update tools will reasonably type `devboost
update` and get a silent lockfile rewrite):

| Command | Updates | Notes |
|---|---|---|
| `devboost update` | **nothing installed** — regenerates `devboost.lock` | misnomer; kept as-is |
| `devboost self-update` | the **engine binary** | checksummed GitHub-release swap |
| `devboost install --update` | the **CLI tools** in place | the `self_updating` set |
| `dnf-automatic` timer | **OS security** patches only | provisioned by `dnf-automatic-security` |

The section also documents that **lazydocker and lazygit install via their upstream scripts to
`~/.local/bin`** (no `dnf`/COPR), which is exactly why they rely on `install --update` to upgrade
rather than riding OS package updates — install method and update path as one coherent story. Any
stale reference implying lazydocker comes from the `atim/lazydocker` COPR is corrected.

Two more doc touch-points:
- The `update` command's docstring/`--help` gains a one-line pointer: *"to upgrade installed
  software, use `devboost install --update` (this only rewrites devboost.lock)."*
- The **quarterly checklist** gains a step: `devboost install --update` to pick up non-security
  CLI-tool version bumps (`dnf-automatic` covers security only).

## Testing

- **Model:** `PackageModule().self_updating is True`; a plain `Module` subclass defaults `False`;
  a representative base package (`Git`) is in the `self_updating` set (locks in the *broad*
  semantics — all `PackageModule`s, not a hand-picked "modern CLI" subset).
- **Runner path (via `_run`):** with `--update`,
  - a `self_updating` module is (force-)installed **even when `verify()` already passes**,
  - a non-`self_updating` module is **absent from the plan even when it is missing**,
  - an all-heavy selection filters to an empty plan → no-op, exit 0 (no error).
- **CLI:** `install --update` wires through to the filtered path; **`install --force --update`
  raises `BadParameter`** (mutual exclusion).

## Out of scope

- A themed `~/.config/lazydocker/config.yml` dotfile (separate, un-greenlit work).
- Version-aware `verify()` (network calls in verify would break `--offline` and slow every run;
  explicitly rejected).
- Any change to the *behavior* of the misnamed `devboost update` command (it still only
  regenerates `devboost.lock`); only its `--help` text gains a pointer to `install --update`.
  Renaming it (e.g. → `devboost lock`) or adding a top-level `devboost upgrade` verb was
  considered and deferred — both are breaking CLI changes beyond this gap-fix.

## Merge gates

`uv run pytest` + `mypy --strict` + ruff green in `engine/`.
