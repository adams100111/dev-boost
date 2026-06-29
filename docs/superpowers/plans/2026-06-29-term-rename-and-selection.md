# `term` Rename + Selection UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the `terminal` CLI command to `term` and add a reusable, category-grouped interactive app picker (`--all`/`--no-all`) plus a repeatable `--app NAME` selector with typo suggestions, shared across `term`, `devtools`, and `install`.

**Architecture:** Insert one pure selection helper between profile-expansion and toposort in `cli/app.py`. Expansion produces the candidate module set; `select_modules` narrows it (all / interactive checklist / explicit `--app`); `toposort` then re-adds the `requires`-closure automatically, so a narrowed selection still yields a valid plan. The interactive checklist is isolated behind an injectable seam so tests run without a TTY.

**Tech Stack:** Python 3.12, Typer (CLI), questionary 2.0 (`checkbox` + `Separator`), `difflib` (stdlib, typo suggestions), pytest.

## Global Constraints

- `mypy --strict` + ruff + pytest are merge gates (constitution v3.0.0). All new code is fully typed; no `Any` leakage.
- No `subprocess` in modules/CLI — system effects go through the `Executor` seam. (This plan adds no system effects.)
- `from __future__ import annotations` at the top of every new module (repo convention).
- The `terminal` *profile* name in `profiles.toml` is unchanged — only the *command* is renamed. `install terminal` must keep working.
- Selection is a pure function plus one injectable I/O seam; the interactive prompt is never called in tests.

---

### Task 1: `resolve_apps` — validate `--app` names with typo suggestions

**Files:**
- Create: `engine/src/devboost/cli/selection.py`
- Test: `engine/tests/cli/test_selection.py`

**Interfaces:**
- Consumes: `devboost.core.log` (`log.error`), `typer.Exit`.
- Produces: `resolve_apps(expanded: list[str], apps: list[str]) -> list[str]` — returns the requested apps (deduped, order-preserving) if all are in `expanded`; otherwise prints `unknown app 'x' — did you mean: …?` and raises `typer.Exit(code=2)`.

- [ ] **Step 1: Write the failing test**

```python
# engine/tests/cli/test_selection.py
from __future__ import annotations

import pytest
import typer

from devboost.cli.selection import resolve_apps


def test_resolve_apps_returns_requested_when_all_known() -> None:
    assert resolve_apps(["git", "fzf", "bat"], ["fzf", "git"]) == ["fzf", "git"]


def test_resolve_apps_dedupes_preserving_order() -> None:
    assert resolve_apps(["git", "fzf"], ["git", "git", "fzf"]) == ["git", "fzf"]


def test_resolve_apps_unknown_raises_exit_with_suggestion(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(typer.Exit) as exc:
        resolve_apps(["git", "fzf", "bat"], ["gti"])
    assert exc.value.exit_code == 2
    err = capsys.readouterr().err
    assert "unknown app 'gti'" in err
    assert "git" in err  # suggestion
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/cli/test_selection.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'devboost.cli.selection'`

- [ ] **Step 3: Write minimal implementation**

```python
# engine/src/devboost/cli/selection.py
"""Module-selection helpers for profile-installing commands (--all / --no-all / --app)."""

from __future__ import annotations

import difflib

import typer

from devboost.core import log


def resolve_apps(expanded: list[str], apps: list[str]) -> list[str]:
    """Return the requested *apps* (deduped, order-preserving) if all are in *expanded*.

    On any unknown name, print a 'did you mean' hint and exit non-zero.
    """
    chosen: list[str] = []
    for a in apps:
        if a in expanded:
            chosen.append(a)
            continue
        suggestions = difflib.get_close_matches(a, expanded, n=3, cutoff=0.6)
        hint = f" — did you mean: {', '.join(suggestions)}?" if suggestions else ""
        log.error(f"unknown app {a!r}{hint}")
        raise typer.Exit(code=2)
    seen: set[str] = set()
    return [x for x in chosen if not (x in seen or seen.add(x))]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd engine && uv run pytest tests/cli/test_selection.py -v`
Expected: PASS (3 tests). Confirm `log.error` writes to stderr — if it writes to stdout, change the assertion to read `capsys.readouterr().out` and note it in the test.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/cli/selection.py engine/tests/cli/test_selection.py
git commit -m "feat(cli): resolve_apps validates --app names with typo suggestions"
```

---

### Task 2: `select_modules` + injectable checklist seam

**Files:**
- Modify: `engine/src/devboost/cli/selection.py`
- Test: `engine/tests/cli/test_selection.py`

**Interfaces:**
- Consumes: `resolve_apps` (Task 1); `devboost.model.Module`; `collections.abc.Mapping`.
- Produces:
  - `Checklist = Callable[[list[str], Mapping[str, type[Module]]], list[str]]` (type alias).
  - `group_choices(expanded, modules) -> list[tuple[str | None, str | None]]` — pure grouping helper returning `(category_header, None)` separator rows and `(None, module_name)` item rows, categories sorted, empty category → `"Other"`. (Separated out so it's testable without questionary.)
  - `select_modules(expanded, modules, *, all_: bool, apps: list[str], checklist: Checklist | None = None) -> list[str]` — `apps` wins; else `all_` returns `expanded` unchanged; else calls `checklist` (default `prompt_checklist`).
  - `prompt_checklist(expanded, modules) -> list[str]` — the real questionary seam (not unit-tested).

- [ ] **Step 1: Write the failing test**

```python
# append to engine/tests/cli/test_selection.py
from collections.abc import Mapping

from devboost.cli.selection import group_choices, select_modules
from devboost.model import Module


class _Cli(Module):
    name = "git"
    category = "Terminal tools"


class _Gui(Module):
    name = "obsidian"
    category = "GUI apps"


class _Bare(Module):
    name = "mystery"
    category = ""


_MODS: Mapping[str, type[Module]] = {"git": _Cli, "obsidian": _Gui, "mystery": _Bare}


def test_group_choices_groups_by_category_sorted_with_other_bucket() -> None:
    rows = group_choices(["git", "obsidian", "mystery"], _MODS)
    assert rows == [
        ("GUI apps", None),
        (None, "obsidian"),
        ("Other", None),
        (None, "mystery"),
        ("Terminal tools", None),
        (None, "git"),
    ]


def test_select_modules_all_returns_expanded() -> None:
    assert select_modules(["git", "obsidian"], _MODS, all_=True, apps=[]) == ["git", "obsidian"]


def test_select_modules_apps_takes_precedence_over_all() -> None:
    assert select_modules(["git", "obsidian"], _MODS, all_=True, apps=["obsidian"]) == ["obsidian"]


def test_select_modules_no_all_uses_injected_checklist() -> None:
    captured: dict[str, object] = {}

    def fake_checklist(expanded: list[str], modules: Mapping[str, type[Module]]) -> list[str]:
        captured["expanded"] = list(expanded)
        return ["git"]

    out = select_modules(["git", "obsidian"], _MODS, all_=False, apps=[], checklist=fake_checklist)
    assert out == ["git"]
    assert captured["expanded"] == ["git", "obsidian"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/cli/test_selection.py -k "group_choices or select_modules" -v`
Expected: FAIL with `ImportError: cannot import name 'group_choices'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to engine/src/devboost/cli/selection.py
from collections.abc import Callable, Mapping

from devboost.model import Module

Checklist = Callable[[list[str], Mapping[str, type[Module]]], list[str]]


def group_choices(
    expanded: list[str], modules: Mapping[str, type[Module]]
) -> list[tuple[str | None, str | None]]:
    """Rows for a grouped checklist: (header, None) separators + (None, name) items.

    Categories are sorted; modules with an empty category fall under 'Other'.
    """
    by_cat: dict[str, list[str]] = {}
    for name in expanded:
        by_cat.setdefault(modules[name].category or "Other", []).append(name)
    rows: list[tuple[str | None, str | None]] = []
    for cat in sorted(by_cat):
        rows.append((cat, None))
        rows.extend((None, name) for name in by_cat[cat])
    return rows


def prompt_checklist(expanded: list[str], modules: Mapping[str, type[Module]]) -> list[str]:
    """Interactive grouped multi-select (all preselected). Not unit-tested (needs a TTY)."""
    import questionary

    choices: list[object] = []
    for header, name in group_choices(expanded, modules):
        if header is not None:
            choices.append(questionary.Separator(f"── {header} ──"))
        else:
            choices.append(questionary.Choice(title=name, value=name, checked=True))
    answer = questionary.checkbox("Select apps to install", choices=choices).ask()
    return list(answer) if answer else []


def select_modules(
    expanded: list[str],
    modules: Mapping[str, type[Module]],
    *,
    all_: bool,
    apps: list[str],
    checklist: Checklist | None = None,
) -> list[str]:
    """Narrow *expanded* to the install set. --app wins; else all_; else interactive."""
    if apps:
        return resolve_apps(expanded, apps)
    if all_:
        return expanded
    return (checklist or prompt_checklist)(expanded, modules)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd engine && uv run pytest tests/cli/test_selection.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/cli/selection.py engine/tests/cli/test_selection.py
git commit -m "feat(cli): select_modules with category-grouped checklist seam"
```

---

### Task 3: Wire selection into `_run`; rename `terminal` → `term`; add flags to `term`/`devtools`/`install`

**Files:**
- Modify: `engine/src/devboost/cli/app.py` (split `_order`, extend `_run`, rename command, add options)
- Test: `engine/tests/cli/test_app_selection.py`

**Interfaces:**
- Consumes: `select_modules` (Task 2); existing `expand`, `toposort`, `load`, `load_profiles`, `validate_profiles`, `build_plan`, `run_plan`.
- Produces:
  - `_resolve(tokens: list[str], root: Path) -> tuple[dict[str, type[Module]], list[str]]` — returns `(modules, expanded_names)` (expansion **without** toposort).
  - `_run(tokens, root, dry_run, force, offline=False, *, all_: bool = True, apps: list[str] | None = None) -> list[RunResult]` — now narrows via `select_modules` then toposorts.
  - New command `term`; `terminal` command removed.
  - Shared option aliases `AllOpt`, `AppOpt`.

- [ ] **Step 1: Write the failing test**

```python
# engine/tests/cli/test_app_selection.py
from __future__ import annotations

from typer.testing import CliRunner

from devboost.cli.app import app

runner = CliRunner()


def test_term_command_exists_and_terminal_removed() -> None:
    names = {c.name for c in app.registered_commands}
    assert "term" in names
    assert "terminal" not in names


def test_term_help_lists_all_and_app_flags() -> None:
    result = runner.invoke(app, ["term", "--help"])
    assert result.exit_code == 0
    assert "--all" in result.output
    assert "--no-all" in result.output
    assert "--app" in result.output


def test_term_unknown_app_exits_nonzero_with_suggestion() -> None:
    # --app against the terminal profile; 'gti' is unknown -> exit 2 + suggestion.
    result = runner.invoke(app, ["term", "--app", "gti", "--dry-run"])
    assert result.exit_code == 2
    assert "unknown app 'gti'" in (result.output + str(result.stderr_bytes or b""))
```

(If `CliRunner` is configured with `mix_stderr=True` in this repo, the message lands in `result.output`; the assertion accepts either stream.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/cli/test_app_selection.py -v`
Expected: FAIL — `term` not registered / `terminal` still present.

- [ ] **Step 3: Implement — split `_order`, extend `_run`**

In `engine/src/devboost/cli/app.py`, replace the `_order` function (lines ~35-40) with a `_resolve` + thin `_order`, and add the selection narrowing to `_run`:

```python
from devboost.cli.selection import select_modules  # add to imports

def _resolve(tokens: list[str], root: Path) -> tuple[dict[str, type[Module]], list[str]]:
    modules = load()
    profiles = load_profiles(root / "profiles.toml")
    validate_profiles(modules, set(profiles))
    expanded = expand(tokens or ["full"], profiles, modules)
    return modules, expanded


def _order(tokens: list[str], root: Path) -> tuple[list[str], dict[str, type[Module]]]:
    modules, expanded = _resolve(tokens, root)
    return toposort(expanded, modules), modules
```

Then change `_run`'s signature and body (lines ~58-73):

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
) -> list[RunResult]:
    modules, expanded = _resolve(tokens, root)
    selected = select_modules(expanded, modules, all_=all_, apps=apps or [])
    order = toposort(selected, modules)
    extra = [n for n in order if n not in selected]
    if extra:
        log.info(f"+{len(extra)} required dependencies added: {', '.join(extra)}")
    ctx = Ctx(os=osinfo.detect(), ex=RealExecutor(), force=force, dry_run=dry_run)
    plan = build_plan(order, modules, ctx.os)
    if offline:
        plan = _apply_offline_filter(plan, modules)
    elif not dry_run:
        pkg.refresh_index(ctx)
    results = run_plan(plan, modules, ctx)
    if any(r.status == "fail" for r in results):
        raise typer.Exit(code=1)
    return results
```

- [ ] **Step 4: Implement — option aliases, rename command, add flags**

Add the option aliases near the other `*Opt` definitions (after line 32):

```python
AllOpt = Annotated[bool, typer.Option("--all/--no-all", "-a",
                                      help="install all apps in the tier (default); "
                                           "--no-all opens an interactive picker")]
AppOpt = Annotated[list[str], typer.Option("--app",
                                           help="install only this app (repeatable)")]
```

Replace the `terminal` command (lines 172-177) with `term`, and add the flags:

```python
@app.command()
def term(
    root: RootOpt = settings.root,
    dry_run: DryOpt = False,
    force: ForceOpt = False,
    all_: AllOpt = True,
    app: AppOpt = [],
) -> None:
    """Install the terminal tier (--no-all to pick interactively, --app NAME for one)."""
    _run(["terminal"], root, dry_run, force, all_=all_, apps=app)
```

Add the same `all_`/`app` flags to `devtools` (lines 180-185) and `install` (lines 107-118), threading them into `_run`:

```python
# devtools:
def devtools(root: RootOpt = settings.root, dry_run: DryOpt = False, force: ForceOpt = False,
             all_: AllOpt = True, app: AppOpt = []) -> None:
    """Install the devtools tier."""
    _run(["devtools"], root, dry_run, force, all_=all_, apps=app)

# install (add the two flags, keep offline):
def install(profiles: ProfilesArg = [], root: RootOpt = settings.root, dry_run: DryOpt = False,
            force: ForceOpt = False, offline: Annotated[bool, typer.Option("--offline", ...)] = False,
            all_: AllOpt = True, app: AppOpt = []) -> None:
    """Install one or more profiles/modules (default: full)."""
    _run(profiles, root, dry_run, force, offline, all_=all_, apps=app)
```

- [ ] **Step 5: Run tests + type/lint gates**

Run: `cd engine && uv run pytest tests/cli/test_app_selection.py -v && uv run mypy --strict src/devboost/cli/selection.py src/devboost/cli/app.py && uv run ruff check src/devboost/cli`
Expected: PASS; mypy clean; ruff clean.

- [ ] **Step 6: Run the full suite to catch references to the old command**

Run: `cd engine && uv run pytest -q`
Expected: PASS. If a test references the old `terminal` command (search `grep -rn "\"terminal\"\|'terminal'" tests`), update it to `term`. Note: tests referencing the `terminal` *profile* token (e.g. `_run(["terminal"])` paths, `media/wizard` `_PROFILES`) are correct and must NOT change.

- [ ] **Step 7: Commit**

```bash
git add engine/src/devboost/cli/app.py engine/tests/cli/test_app_selection.py
git commit -m "feat(cli): rename terminal->term; add --all/--no-all/--app selection to term/devtools/install"
```

---

### Task 4: Update docs for the rename

**Files:**
- Modify: `docs/architecture.md:9` (command list)

**Interfaces:** none (docs only).

- [ ] **Step 1: Update the command list**

In `docs/architecture.md` line 9, change `terminal/devtools/dev` to `term/devtools/dev` in the Typer command enumeration. Verify no other doc names the *command* `terminal` (the guides reference the shell concept, not the command):

Run: `grep -rn "devboost terminal\|\`terminal\`" docs/ | grep -iv profile`
Expected: only the `2026-06-25-portable-two-tier-installer-design.md` historical design (leave as historical) and the line you just edited.

- [ ] **Step 2: Commit**

```bash
git add docs/architecture.md
git commit -m "docs: reflect terminal->term command rename"
```

---

## Self-Review

- **Spec coverage:** rename (Task 3/4) ✓; `-a/--all` default + `--no-all` (Task 3) ✓; category-grouped checklist via `Separator` + "Other" bucket (Task 2) ✓; preselected (Task 2 `checked=True`) ✓; repeatable `--app` + typo suggestion (Tasks 1, 3) ✓; dependency closure via toposort (Task 3 — `extra` log line) ✓; generalized across `term`/`devtools`/`install` (Task 3) ✓; no live search (omitted by design) ✓.
- **Placeholders:** none — every step has real code/commands.
- **Type consistency:** `select_modules`/`resolve_apps`/`group_choices`/`prompt_checklist`/`Checklist` names are consistent across Tasks 1-3; `_resolve`/`_run` signatures match their call sites.
