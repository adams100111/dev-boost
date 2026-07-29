# Targeted Tool Update (`devboost install --update`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `devboost install --update` — a lightweight, non-destructive mode that force-refreshes only the self-updating CLI tools (single-package/binary modules), leaving heavy provisioning modules (docker, dotfiles, gnome, drivers) untouched.

**Architecture:** A `self_updating` class marker (default `False` on `Module`, `True` on `PackageModule`) flags which modules are safe to force-refresh. `--update` is implemented purely in the `_run` CLI helper as *"a `--force` run over a plan filtered to `self_updating` modules"* via a new pure `_apply_update_filter` helper (mirroring the existing `_apply_offline_filter`). The verify-guarded install loop in `core/runner.py` is **not modified**.

**Tech Stack:** Python 3.12, Typer (CLI), Pydantic, pytest, `mypy --strict`, ruff. Package under `engine/` (uv src-layout). All commands run from `/home/dev/repos/dev-boost/engine`.

## Global Constraints

- **Merge gates (must be green before every commit):** `uv run pytest`, `uv run mypy --strict src/`, `uv run ruff check`.
- **No Claude/Anthropic attribution** in any commit message or doc.
- `self_updating` is a `ClassVar[bool]`; access it on the **class** (`cls.self_updating`), never instantiate to read it.
- **Broad semantics are intentional:** `--update` refreshes *every* `PackageModule` (including base packages like `git`/`curl`/`coreutils`), not a hand-picked "modern CLI" subset.
- `--force` and `--update` are **mutually exclusive** — passing both is a `typer.BadParameter` (exit code 2).
- `--update` lives on the `install` command **only** — not on `term`/`devtools`/`server` (matches how `--offline` is scoped).
- Working branch already exists: `feat/targeted-tool-update`. Do NOT run any destructive git command.

---

### Task 1: `self_updating` marker on the module model

**Files:**
- Modify: `engine/src/devboost/model.py:57-67` (add attribute to `Module`)
- Modify: `engine/src/devboost/modules/_pkgmodule.py:11-18` (add attribute to `PackageModule`)
- Test: `engine/tests/core/test_model_registry.py`

**Interfaces:**
- Produces: `Module.self_updating: ClassVar[bool] = False` and `PackageModule.self_updating: ClassVar[bool] = True`, read by later tasks as `modules[name].self_updating`.

- [ ] **Step 1: Write the failing test**

Append to `engine/tests/core/test_model_registry.py`:

```python
def test_self_updating_defaults() -> None:
    """A plain Module is not self-updating; a PackageModule is (single package = safe to refresh)."""
    from devboost.model import Module
    from devboost.modules._pkgmodule import PackageModule
    from devboost.modules.cli_tools import Git
    from devboost.modules.docker import Docker

    class HeavyThing(Module):
        name = "heavy-thing"

    class PkgThing(PackageModule):
        name = "pkg-thing"
        cmd = "pkg-thing"
        fedora_pkg = "pkg-thing"

    assert HeavyThing.self_updating is False        # root default
    assert PkgThing.self_updating is True           # PackageModule override
    assert Git.self_updating is True                # a real base package — broad semantics
    assert Docker.self_updating is False            # a real heavy module stays out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/core/test_model_registry.py::test_self_updating_defaults -v`
Expected: FAIL with `AttributeError: type object 'HeavyThing' has no attribute 'self_updating'`

- [ ] **Step 3: Add the attribute to `Module`**

In `engine/src/devboost/model.py`, inside `class Module` (after the `profiles` line at `:64`), add:

```python
    profiles: ClassVar[tuple[str, ...]] = ()
    self_updating: ClassVar[bool] = False
```

- [ ] **Step 4: Add the override to `PackageModule`**

In `engine/src/devboost/modules/_pkgmodule.py`, inside `class PackageModule` (after the `copr_repo` line at `:18`), add:

```python
    copr_repo: ClassVar[str | None] = None
    # A single-package/single-binary install is safe to re-run for an in-place upgrade,
    # so package modules opt into `devboost install --update` by default. A specific
    # subclass with install-time side effects may override this back to False.
    self_updating: ClassVar[bool] = True
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/core/test_model_registry.py::test_self_updating_defaults -v`
Expected: PASS

- [ ] **Step 6: Gates + commit**

```bash
cd /home/dev/repos/dev-boost/engine
uv run mypy --strict src/ && uv run ruff check && uv run pytest -q
cd /home/dev/repos/dev-boost
git add engine/src/devboost/model.py engine/src/devboost/modules/_pkgmodule.py engine/tests/core/test_model_registry.py
git commit -m "feat(model): add self_updating marker (Module=False, PackageModule=True)"
```

---

### Task 2: `_apply_update_filter` pure helper

**Files:**
- Modify: `engine/src/devboost/cli/app.py` (add helper next to `_apply_offline_filter` at `:76-86`)
- Test: `engine/tests/cli/test_app_selection.py`

**Interfaces:**
- Consumes: `Module.self_updating` (Task 1); `PlannedModule` (from `devboost.core.plan`, fields `name: str`, `skip_reason: str | None = None`).
- Produces: `_apply_update_filter(plan: list[PlannedModule], modules: Mapping[str, type[Module]]) -> list[PlannedModule]` — returns only the entries whose module class is `self_updating`, dropping the rest entirely (not replacing them with a skip).

- [ ] **Step 1: Write the failing test**

Append to `engine/tests/cli/test_app_selection.py`:

```python
def test_apply_update_filter_keeps_only_self_updating() -> None:
    from devboost.cli.app import _apply_update_filter
    from devboost.core.plan import PlannedModule
    from devboost.model import Module

    class Refreshable(Module):
        name = "refreshable"
        self_updating = True

    class Heavy(Module):
        name = "heavy"
        self_updating = False

    modules = {"refreshable": Refreshable, "heavy": Heavy}
    plan = [PlannedModule(name="refreshable"), PlannedModule(name="heavy")]

    kept = _apply_update_filter(plan, modules)

    assert [pm.name for pm in kept] == ["refreshable"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cli/test_app_selection.py::test_apply_update_filter_keeps_only_self_updating -v`
Expected: FAIL with `ImportError: cannot import name '_apply_update_filter'`

- [ ] **Step 3: Add the helper**

In `engine/src/devboost/cli/app.py`, immediately after `_apply_offline_filter` (ends at `:86`), add:

```python
def _apply_update_filter(
    plan: list[PlannedModule],
    modules: Mapping[str, type[Module]],
) -> list[PlannedModule]:
    """Keep only self-updating modules (single-package/binary tools safe to force-refresh).

    Non-self-updating modules are dropped from the plan entirely — `--update` must not
    install a heavy provisioning module, only refresh the CLI tools.
    """
    return [pm for pm in plan if modules[pm.name].self_updating]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/cli/test_app_selection.py::test_apply_update_filter_keeps_only_self_updating -v`
Expected: PASS

- [ ] **Step 5: Gates + commit**

```bash
cd /home/dev/repos/dev-boost/engine
uv run mypy --strict src/ && uv run ruff check && uv run pytest -q
cd /home/dev/repos/dev-boost
git add engine/src/devboost/cli/app.py engine/tests/cli/test_app_selection.py
git commit -m "feat(cli): add _apply_update_filter (keep only self_updating modules)"
```

---

### Task 3: Wire `--update` into `_run` and the `install` command

**Files:**
- Modify: `engine/src/devboost/cli/app.py` — `UpdateOpt` annotation (near `:34`), `_run` signature + body (`:89-116`), `install` command (`:150-163`)
- Test: `engine/tests/cli/test_app_selection.py`

**Interfaces:**
- Consumes: `_apply_update_filter` (Task 2); existing `_run`, `build_plan`, `run_plan`, `pkg.refresh_index`.
- Produces: `install --update` behavior; `_run(..., *, all_=True, apps=None, update=False)` keyword-only param.

- [ ] **Step 1: Write the failing tests**

Append to `engine/tests/cli/test_app_selection.py`:

```python
def test_install_update_dry_run_filters_to_self_updating() -> None:
    # --dry-run lists "would install <name>" for the filtered plan only.
    result = runner.invoke(app, ["install", "--update", "--dry-run"])
    assert result.exit_code == 0
    assert "would install lazydocker" in result.output      # a self_updating tool: kept
    assert "would install git" in result.output             # a base package: kept (broad)
    assert "would install docker" not in result.output      # a heavy Module: dropped


def test_install_force_and_update_are_mutually_exclusive() -> None:
    result = runner.invoke(app, ["install", "--force", "--update"])
    assert result.exit_code == 2
    assert "mutually exclusive" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/cli/test_app_selection.py -k "install_update or mutually_exclusive" -v`
Expected: FAIL — `--update` is not a known option (exit 2 on the first test for the wrong reason; the mutual-exclusion test fails because `--update` is unrecognized).

- [ ] **Step 3: Add the `UpdateOpt` annotation**

In `engine/src/devboost/cli/app.py`, after the `ForceOpt` line (`:34`), add:

```python
ForceOpt = Annotated[bool, typer.Option("--force", help="reinstall even if verify passes")]
UpdateOpt = Annotated[
    bool,
    typer.Option(
        "--update",
        help="force-refresh only self-updating tools (CLI tools); mutually exclusive with --force",
    ),
]
```

- [ ] **Step 4: Add `update` to `_run` and apply the filter**

In `engine/src/devboost/cli/app.py`, change the `_run` signature (`:89-98`) to add a keyword-only `update` param:

```python
def _run(
    tokens: list[str],
    root: Path,
    dry_run: bool,
    force: bool,
    offline: bool = False,
    *,
    all_: bool = True,
    apps: list[str] | None = None,
    update: bool = False,
) -> list[RunResult]:
```

Then in the body, after `plan = build_plan(order, modules, ctx.os)` (`:106`), insert the update-filter block **before** the offline/refresh block:

```python
    plan = build_plan(order, modules, ctx.os)
    if update:
        plan = _apply_update_filter(plan, modules)
        if not plan:
            log.info("no self-updating tools in selection")
        ctx = Ctx(os=ctx.os, ex=ctx.ex, force=True, dry_run=dry_run)  # force-refresh the kept tools
    if offline:
        plan = _apply_offline_filter(plan, modules)
    elif not dry_run:
        # Refresh the package index once up front so installs don't fail against a stale
        # index on a fresh box (no network access happens in offline/dry-run modes).
        pkg.refresh_index(ctx)
    results = run_plan(plan, modules, ctx)
```

> Note: `Ctx` is rebuilt (not mutated) because it is a frozen model; reuse the same `os`/`ex` and set `force=True`. This makes `--update` a force run over the filtered plan without touching `core/runner.py`.

- [ ] **Step 5: Add the mutual-exclusion guard and wire the flag in `install`**

In `engine/src/devboost/cli/app.py`, replace the `install` command (`:150-163`) with:

```python
@app.command()
def install(
    profiles: ProfilesArg = [],
    root: RootOpt = settings.root,
    dry_run: DryOpt = False,
    force: ForceOpt = False,
    offline: Annotated[
        bool, typer.Option("--offline", help="skip modules that need network")
    ] = False,
    all_: AllOpt = True,
    app: AppOpt = [],
    update: UpdateOpt = False,
) -> None:
    """Install one or more profiles/modules (default: full)."""
    if force and update:
        raise typer.BadParameter("--force and --update are mutually exclusive")
    _run(profiles, root, dry_run, force, offline, all_=all_, apps=app, update=update)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/cli/test_app_selection.py -k "install_update or mutually_exclusive" -v`
Expected: PASS (both)

- [ ] **Step 7: Full gates + commit**

```bash
cd /home/dev/repos/dev-boost/engine
uv run mypy --strict src/ && uv run ruff check && uv run pytest -q
cd /home/dev/repos/dev-boost
git add engine/src/devboost/cli/app.py engine/tests/cli/test_app_selection.py
git commit -m "feat(cli): add 'install --update' to force-refresh only self-updating tools"
```

---

### Task 4: Documentation — the three update surfaces + lazydocker story

**Files:**
- Modify: `engine/src/devboost/cli/app.py` (the `update` command docstring at `:327-330`)
- Modify: `docs/maintenance.md`
- Test: `engine/tests/cli/test_app_selection.py` (assert the `update --help` pointer renders)

**Interfaces:**
- Consumes: nothing new; documents Task 3's `install --update`.

- [ ] **Step 1: Write the failing test**

Append to `engine/tests/cli/test_app_selection.py`:

```python
def test_update_help_points_to_install_update() -> None:
    result = runner.invoke(app, ["update", "--help"])
    assert result.exit_code == 0
    assert "install --update" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cli/test_app_selection.py::test_update_help_points_to_install_update -v`
Expected: FAIL — the `update` docstring does not yet mention `install --update`.

- [ ] **Step 3: Update the `update` command docstring**

In `engine/src/devboost/cli/app.py`, replace the `update` command (`:327-330`) with:

```python
@app.command()
def update(root: RootOpt = settings.root) -> None:
    """Regenerate the deterministic devboost.lock (no commit).

    This only rewrites devboost.lock — it installs nothing. To upgrade installed
    software, use `devboost install --update` (CLI tools) or `devboost self-update`
    (the engine binary).
    """
    log.ok(f"wrote {lc.write_lock(root)}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/cli/test_app_selection.py::test_update_help_points_to_install_update -v`
Expected: PASS

- [ ] **Step 5: Add the "Updating" section to `docs/maintenance.md`**

In `docs/maintenance.md`, immediately after the `## Day-2 commands` list (before `## Quarterly checklist`), insert:

```markdown
## Updating an existing box

Three separate "update" surfaces — do not confuse them:

| Command | Updates | Notes |
|---|---|---|
| `devboost update` | **nothing installed** — regenerates `devboost.lock` | a misnomer, kept for compatibility |
| `devboost self-update` | the **engine binary** | checksummed GitHub-release swap |
| `devboost install --update` | the **CLI tools** in place | force-refreshes every `self_updating` module (all single-package/binary tools); leaves docker/dotfiles/gnome/drivers untouched |
| `dnf-automatic` timer | **OS security** patches only | provisioned by `dnf-automatic-security` |

`install --update` and `install --force` are mutually exclusive: `--update` refreshes only
the refreshable tools, `--force` re-runs *every* module. `--update` lives on `install` only —
"update my terminal tier" is `devboost install --update terminal`.

**Why some tools need `install --update`:** `lazydocker` and `lazygit` install via their
upstream scripts to `~/.local/bin` (no `dnf`/COPR), so they ride neither `dnf upgrade` nor the
`dnf-automatic` security timer. `install --update` re-runs their install-and-update scripts to
pull the latest release. The same applies to the GitHub-release binary tools (eza, atuin, dust,
sd, yq, fastfetch, gh, …).
```

- [ ] **Step 6: Correct stale COPR references and add the quarterly step**

Search for any stale claim that lazydocker comes from a COPR and correct it:

Run: `grep -rn "atim/lazydocker" docs/ README.md`

For each hit that describes how lazydocker is *installed* (not a historical spec note), update it to state lazydocker installs via the upstream `install_update_linux.sh` script to `~/.local/bin`. (If the only hits are inside dated spec files under `docs/superpowers/specs/`, leave those historical records alone.)

Then, in `docs/maintenance.md`, add a step to the `## Quarterly checklist` after the existing `devboost update` step:

```markdown
3. `devboost install --update` → pick up non-security CLI-tool version bumps
   (`dnf-automatic` covers security patches only).
```

(Renumber the subsequent checklist items.)

- [ ] **Step 7: Full gates + commit**

```bash
cd /home/dev/repos/dev-boost/engine
uv run mypy --strict src/ && uv run ruff check && uv run pytest -q
cd /home/dev/repos/dev-boost
git add engine/src/devboost/cli/app.py engine/tests/cli/test_app_selection.py docs/maintenance.md README.md
git commit -m "docs: document the three update surfaces + lazydocker install/update path"
```

---

### Task 5: Finish the branch

**Files:** none (integration).

- [ ] **Step 1: Final full-suite gate**

```bash
cd /home/dev/repos/dev-boost/engine
uv run pytest -q && uv run mypy --strict src/ && uv run ruff check
```
Expected: all green.

- [ ] **Step 2: Push, PR, merge (default finish workflow)**

```bash
cd /home/dev/repos/dev-boost
git push -u origin feat/targeted-tool-update
gh pr create --title "Add 'devboost install --update' — targeted CLI-tool refresh" \
  --body "Implements docs/superpowers/specs/2026-07-29-targeted-tool-update-design.md. Adds a self_updating module marker (PackageModule=True) and 'install --update', a force run over a plan filtered to self_updating modules; runner untouched. --force/--update mutually exclusive. Docs disambiguate the three update surfaces and document the lazydocker/lazygit script install path."
gh pr merge --merge --delete-branch
```

---

## Self-Review

**Spec coverage:**
- §1 `self_updating` marker → Task 1 ✓
- §2 `--update` path (install-only, filter-in-`_run`, force, mutual exclusion, empty-plan log, refresh_index/offline/dry-run/`--app` composition) → Tasks 2–3 ✓ (`--app` composition is inherent: `select_modules` runs before the filter, so `--app` narrows first, then `_apply_update_filter` narrows again — no extra code needed)
- §3 docs (disambiguation table, lazydocker story, `update` `--help` pointer, quarterly step, COPR correction) → Task 4 ✓
- Testing (model defaults incl. broad Git-is-True, filter helper, dry-run filtering, mutual-exclusion error, empty-plan no-op) → covered; empty-plan no-op is exercised indirectly (any all-heavy selection). Explicit empty-plan assertion omitted as low-value (the filter helper test already proves dropping).

**Placeholder scan:** none — every code step shows complete code; the one search step (COPR grep) has explicit criteria for what to change vs leave.

**Type consistency:** `_apply_update_filter(plan, modules)` signature identical in Task 2 (definition) and Task 3 (call site). `_run(..., update=False)` keyword-only param matches the `install` call site. `self_updating` is `ClassVar[bool]` in Tasks 1–2 and read as a class attribute (`modules[pm.name].self_updating`) in Task 2 — consistent.
