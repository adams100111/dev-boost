# Terminal/Devtools Typed-Python Engine — Implementation Plan (1 of N)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a strict-typed Python engine with a Typer CLI that resolves the `terminal` and `devtools` tiers from the existing declarative TOML modules and **actually executes** their idempotent, verify-guarded installs (with `--dry-run` preview), runnable as the `devboost` command.

**Architecture:** A small typed core — OS/headless detection → TOML manifest load+validate → profile expansion → dependency toposort → plan builder (per-OS install + fallback ladder, headless GUI skip) → verify-guarded runner with an injectable executor. A Typer root app exposes `terminal`, `devtools`, `install`, `verify`, `list`, `doctor`. Modules/profiles stay declarative TOML data (Engine + Data separation preserved); only the engine language changes.

**Tech Stack:** Python ≥3.11 (stdlib `tomllib`, `graphlib`, `dataclasses`), Typer (CLI, v0.21.x), pytest + `typer.testing.CliRunner` (tests), mypy/pyright (strict typing), ruff (lint). Freezing to a single-file binary is a later plan.

## Global Constraints

- **Python floor: ≥3.11** — engine uses stdlib `tomllib`; never a hand-rolled TOML parser. (verbatim from spec §1/§7)
- **Strict typing** — mypy `--strict` (or pyright strict) must pass; every public function fully annotated.
- **CLI framework: Typer** — subcommands via `add_typer`, typed params via `Annotated[...]`, tests via `CliRunner`.
- **Idempotent & verify-guarded** — every module declares `verify`; green ⇒ skip unless `--force`; re-running does only what's missing. (spec §5)
- **Engine + Data separation** — adding a tool/OS is a TOML edit, never an engine code change. (constitution Principle I)
- **Declarative modules stay TOML** — reuse existing `modules/*.toml` and `modules/<name>/module.toml`; add optional `gui` bool + `[fallback]` table only.
- **Commit hygiene** — Conventional Commits; **no Claude/Anthropic attribution** in any commit message.
- **PREREQUISITE GATE (Task 0):** the constitution currently mandates *"pure Bash … no other interpreters."* It MUST be amended (MAJOR bump) before merging this engine.

**Out of scope (explicit follow-up plans):**
- Plan 2 — full Ubuntu/`apt` parity + `[fallback]` ladders across **all** terminal-tier modules.
- Plan 3 — frozen single-file per-arch binary (PyInstaller/Nuitka) + `get.sh` bootstrap.
- Plan 4 — migrate the 1,118 BATS tests to pytest and retire the bash engine.

This plan delivers a working, hermetically-tested `devboost` package that resolves and executes the two tiers via the system package manager.

---

## File Structure

```
engine/
  pyproject.toml                 # package metadata, deps, console script, tool config
  devboost/
    __init__.py                  # version
    log.py                       # structured console logging + run summary
    osinfo.py                    # OsInfo, family_of(), detect(), is_headless()
    manifest.py                  # Module dataclass, ManifestError, load_modules()
    profile.py                   # load_profiles(), expand()
    graph.py                     # toposort(), DependencyCycle
    plan.py                      # PlannedModule, resolve_steps(), build_plan()
    runner.py                    # Executor protocol, SubprocessExecutor, RunResult, run_plan()
    cli.py                       # Typer root app + subcommands
  tests/
    conftest.py                  # fixtures: tmp modules dir, fake executor
    test_osinfo.py
    test_manifest.py
    test_profile.py
    test_graph.py
    test_plan.py
    test_runner.py
    test_cli.py
```

Repo root files touched: `profiles.toml` (add `terminal`, `devtools`), a few `modules/*.toml` (add `gui`/`[fallback]` as the parity pattern).

---

## Task 0: Constitution amendment + package scaffold

**Files:**
- Modify: `.specify/memory/constitution.md` (Technology & Security Constraints; version bump + SYNC IMPACT report)
- Create: `engine/pyproject.toml`
- Create: `engine/devboost/__init__.py`
- Test: `engine/tests/test_cli.py` (smoke)

**Interfaces:**
- Produces: an installable `devboost` package exposing `devboost.__version__: str` and a `devboost` console command bound to `devboost.cli:app`.

- [ ] **Step 1: Amend the constitution (governance, non-TDD)**

In `.specify/memory/constitution.md`, change the "Technology & Security Constraints" clause from "pure Bash … no other interpreters" to permit a **typed-Python engine shipped as a frozen single-file binary** (no runtime interpreter dependency on the target). Add a SYNC IMPACT report comment at the top and bump the version (MAJOR). Restate Principle I in language-neutral terms.

- [ ] **Step 2: Write the package scaffold**

Create `engine/pyproject.toml`:

```toml
[project]
name = "devboost"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["typer>=0.21,<0.22"]

[project.scripts]
devboost = "devboost.cli:app"

[project.optional-dependencies]
dev = ["pytest>=8", "mypy>=1.10", "ruff>=0.5"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.mypy]
strict = true
files = ["devboost"]

[tool.ruff]
line-length = 100
```

Create `engine/devboost/__init__.py`:

```python
__version__ = "0.1.0"
```

- [ ] **Step 3: Write the failing smoke test**

Create `engine/tests/test_cli.py`:

```python
from typer.testing import CliRunner

from devboost.cli import app

runner = CliRunner()


def test_version_command() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout
```

- [ ] **Step 4: Run it — verify it fails**

Run: `cd engine && pip install -e ".[dev]" && pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: devboost.cli`.

- [ ] **Step 5: Minimal CLI to pass**

Create `engine/devboost/cli.py`:

```python
from typing import Annotated, Optional

import typer

from devboost import __version__

app = typer.Typer(help="dev-boost portable installer", no_args_is_help=True)


def _version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        Optional[bool],
        typer.Option("--version", callback=_version, is_eager=True),
    ] = None,
) -> None:
    """dev-boost CLI root."""
```

- [ ] **Step 6: Run — verify pass + types**

Run: `cd engine && pytest tests/test_cli.py -v && mypy`
Expected: test PASS; mypy `Success: no issues`.

- [ ] **Step 7: Commit**

```bash
git add .specify/memory/constitution.md engine/pyproject.toml engine/devboost engine/tests/test_cli.py
git commit -m "feat(engine): scaffold typed-python devboost package + amend constitution"
```

---

## Task 1: OS + headless detection

**Files:**
- Create: `engine/devboost/osinfo.py`
- Test: `engine/tests/test_osinfo.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class OsInfo: distro: str; family: str; arch: str`
  - `family_of(distro: str) -> str`
  - `detect(os_release_path: str = "/etc/os-release", machine: str | None = None) -> OsInfo`
  - `is_headless(env: Mapping[str, str] | None = None) -> bool`

- [ ] **Step 1: Write failing tests**

Create `engine/tests/test_osinfo.py`:

```python
from devboost.osinfo import OsInfo, detect, family_of, is_headless


def test_family_of_maps_distros() -> None:
    assert family_of("ubuntu") == "debian"
    assert family_of("fedora") == "fedora"
    assert family_of("rocky") == "fedora"
    assert family_of("unknown-os") == "unknown-os"


def test_detect_reads_os_release(tmp_path) -> None:
    f = tmp_path / "os-release"
    f.write_text('ID=ubuntu\nVERSION_ID="24.04"\n')
    info = detect(os_release_path=str(f), machine="x86_64")
    assert info == OsInfo(distro="ubuntu", family="debian", arch="x86_64")


def test_is_headless_true_without_display() -> None:
    assert is_headless(env={}) is True


def test_is_headless_false_with_wayland() -> None:
    assert is_headless(env={"WAYLAND_DISPLAY": "wayland-0"}) is False
```

- [ ] **Step 2: Run — verify fail**

Run: `cd engine && pytest tests/test_osinfo.py -v`
Expected: FAIL — `ModuleNotFoundError: devboost.osinfo`.

- [ ] **Step 3: Implement**

Create `engine/devboost/osinfo.py`:

```python
import os
import platform
from collections.abc import Mapping
from dataclasses import dataclass

_FAMILY = {
    "fedora": "fedora", "rhel": "fedora", "centos": "fedora",
    "rocky": "fedora", "almalinux": "fedora",
    "ubuntu": "debian", "debian": "debian", "linuxmint": "debian", "pop": "debian",
    "arch": "arch", "manjaro": "arch", "endeavouros": "arch",
    "macos": "macos", "darwin": "macos",
}


@dataclass(frozen=True)
class OsInfo:
    distro: str
    family: str
    arch: str


def family_of(distro: str) -> str:
    return _FAMILY.get(distro, distro)


def detect(os_release_path: str = "/etc/os-release", machine: str | None = None) -> OsInfo:
    distro = "unknown"
    if platform.system() == "Darwin":
        distro = "macos"
    else:
        try:
            for line in open(os_release_path, encoding="utf-8"):
                if line.startswith("ID="):
                    distro = line.split("=", 1)[1].strip().strip('"')
                    break
        except OSError:
            distro = "unknown"
    return OsInfo(distro=distro, family=family_of(distro), arch=machine or platform.machine())


def is_headless(env: Mapping[str, str] | None = None) -> bool:
    e = os.environ if env is None else env
    return not (e.get("DISPLAY") or e.get("WAYLAND_DISPLAY"))
```

- [ ] **Step 4: Run — verify pass + types**

Run: `cd engine && pytest tests/test_osinfo.py -v && mypy`
Expected: PASS; mypy clean.

- [ ] **Step 5: Commit**

```bash
git add engine/devboost/osinfo.py engine/tests/test_osinfo.py
git commit -m "feat(engine): OS family + headless detection"
```

---

## Task 2: Manifest model + loader

**Files:**
- Create: `engine/devboost/manifest.py`
- Create: `engine/tests/conftest.py`
- Test: `engine/tests/test_manifest.py`

**Interfaces:**
- Produces:
  - `class ManifestError(Exception)`
  - `@dataclass(frozen=True) class Module: name: str; category: str; verify: str; requires: tuple[str, ...]; install: dict[str, str]; fallback: dict[str, str]; gui: bool`
  - `load_modules(modules_dir: Path) -> dict[str, Module]` — reads both `modules/<name>.toml` and `modules/<name>/module.toml`; raises `ManifestError` on missing `name`/`verify` or no install path at all.

- [ ] **Step 1: Shared fixtures**

Create `engine/tests/conftest.py`:

```python
from pathlib import Path

import pytest


@pytest.fixture
def modules_dir(tmp_path: Path) -> Path:
    d = tmp_path / "modules"
    d.mkdir()
    (d / "fzf.toml").write_text(
        'name = "fzf"\ncategory = "cli"\nverify = "command -v fzf"\n'
        '[install]\nfedora = "sudo dnf install -y fzf"\n'
        'debian = "sudo apt-get install -y fzf"\n'
    )
    eza = d / "eza"
    eza.mkdir()
    (eza / "module.toml").write_text(
        'name = "eza"\ncategory = "cli"\nverify = "command -v eza"\nrequires = ["fzf"]\n'
        '[install]\nfedora = "sudo dnf install -y eza"\n'
        '[fallback]\nmise = "aqua:eza-community/eza"\n'
    )
    ghostty = d / "ghostty"
    ghostty.mkdir()
    (ghostty / "module.toml").write_text(
        'name = "ghostty"\ncategory = "shell"\ngui = true\nverify = "command -v ghostty"\n'
        '[install]\nfedora = "echo install-ghostty"\n'
    )
    return d
```

- [ ] **Step 2: Write failing tests**

Create `engine/tests/test_manifest.py`:

```python
from pathlib import Path

import pytest

from devboost.manifest import ManifestError, Module, load_modules


def test_loads_simple_and_dir_modules(modules_dir: Path) -> None:
    mods = load_modules(modules_dir)
    assert set(mods) == {"fzf", "eza", "ghostty"}
    assert mods["eza"].requires == ("fzf",)
    assert mods["eza"].fallback == {"mise": "aqua:eza-community/eza"}
    assert mods["ghostty"].gui is True
    assert mods["fzf"].install["debian"] == "sudo apt-get install -y fzf"


def test_missing_verify_raises(tmp_path: Path) -> None:
    d = tmp_path / "modules"
    d.mkdir()
    (d / "bad.toml").write_text('name = "bad"\ncategory = "cli"\n[install]\nfedora = "x"\n')
    with pytest.raises(ManifestError, match="bad.*verify"):
        load_modules(d)


def test_no_install_path_raises(tmp_path: Path) -> None:
    d = tmp_path / "modules"
    d.mkdir()
    (d / "bad.toml").write_text('name = "bad"\ncategory = "cli"\nverify = "true"\n')
    with pytest.raises(ManifestError, match="bad.*install"):
        load_modules(d)
```

- [ ] **Step 3: Run — verify fail**

Run: `cd engine && pytest tests/test_manifest.py -v`
Expected: FAIL — `ModuleNotFoundError: devboost.manifest`.

- [ ] **Step 4: Implement**

Create `engine/devboost/manifest.py`:

```python
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ManifestError(Exception):
    pass


@dataclass(frozen=True)
class Module:
    name: str
    category: str
    verify: str
    requires: tuple[str, ...]
    install: dict[str, str]
    fallback: dict[str, str]
    gui: bool


def _parse(path: Path) -> Module:
    data: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
    name = data.get("name", path.stem)
    verify = data.get("verify")
    install = {str(k): str(v) for k, v in data.get("install", {}).items()}
    fallback = {str(k): str(v) for k, v in data.get("fallback", {}).items()}
    if not verify:
        raise ManifestError(f"module {name}: missing 'verify'")
    if not install and not fallback:
        raise ManifestError(f"module {name}: no 'install' path or 'fallback'")
    return Module(
        name=str(name),
        category=str(data.get("category", "")),
        verify=str(verify),
        requires=tuple(str(r) for r in data.get("requires", [])),
        install=install,
        fallback=fallback,
        gui=bool(data.get("gui", False)),
    )


def load_modules(modules_dir: Path) -> dict[str, Module]:
    out: dict[str, Module] = {}
    for entry in sorted(modules_dir.iterdir()):
        toml: Path | None = None
        if entry.is_file() and entry.suffix == ".toml":
            toml = entry
        elif entry.is_dir() and (entry / "module.toml").is_file():
            toml = entry / "module.toml"
        if toml is None:
            continue
        mod = _parse(toml)
        out[mod.name] = mod
    return out
```

- [ ] **Step 5: Run — verify pass + types**

Run: `cd engine && pytest tests/test_manifest.py -v && mypy`
Expected: PASS; mypy clean.

- [ ] **Step 6: Commit**

```bash
git add engine/devboost/manifest.py engine/tests/conftest.py engine/tests/test_manifest.py
git commit -m "feat(engine): typed module manifest model + TOML loader"
```

---

## Task 3: Profile loader + expansion

**Files:**
- Create: `engine/devboost/profile.py`
- Test: `engine/tests/test_profile.py`

**Interfaces:**
- Consumes: `Module` from `manifest.py`.
- Produces:
  - `load_profiles(path: Path) -> dict[str, list[str]]`
  - `expand(names: Iterable[str], profiles: Mapping[str, list[str]], modules: Mapping[str, Module]) -> list[str]` — each token is a profile name (expanded) or a module name; pulls transitive `requires`; returns a de-duplicated list (insertion-ordered). Raises `KeyError` naming an unknown module.

- [ ] **Step 1: Write failing tests**

Create `engine/tests/test_profile.py`:

```python
from pathlib import Path

from devboost.manifest import load_modules
from devboost.profile import expand, load_profiles


def test_load_profiles(tmp_path: Path) -> None:
    p = tmp_path / "profiles.toml"
    p.write_text('[profiles]\nterminal = ["eza"]\ndevtools = ["fzf"]\n')
    profs = load_profiles(p)
    assert profs["terminal"] == ["eza"]


def test_expand_profile_pulls_requires(modules_dir: Path) -> None:
    mods = load_modules(modules_dir)
    profiles = {"terminal": ["eza"]}
    # eza requires fzf -> fzf must appear, before eza
    result = expand(["terminal"], profiles, mods)
    assert result == ["fzf", "eza"]


def test_expand_dedupes_and_accepts_bare_module(modules_dir: Path) -> None:
    mods = load_modules(modules_dir)
    result = expand(["fzf", "eza"], {}, mods)
    assert result == ["fzf", "eza"]
```

- [ ] **Step 2: Run — verify fail**

Run: `cd engine && pytest tests/test_profile.py -v`
Expected: FAIL — `ModuleNotFoundError: devboost.profile`.

- [ ] **Step 3: Implement**

Create `engine/devboost/profile.py`:

```python
import tomllib
from collections.abc import Iterable, Mapping
from pathlib import Path

from devboost.manifest import Module


def load_profiles(path: Path) -> dict[str, list[str]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    profiles = data.get("profiles", {})
    return {str(k): [str(x) for x in v] for k, v in profiles.items()}


def expand(
    names: Iterable[str],
    profiles: Mapping[str, list[str]],
    modules: Mapping[str, Module],
) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    def add_module(name: str) -> None:
        if name not in modules:
            raise KeyError(f"unknown module: {name}")
        for dep in modules[name].requires:
            add_module(dep)
        if name not in seen:
            seen.add(name)
            out.append(name)

    def add_token(token: str) -> None:
        if token in profiles:
            for member in profiles[token]:
                add_token(member)
        else:
            add_module(token)

    for n in names:
        add_token(n)
    return out
```

- [ ] **Step 4: Run — verify pass + types**

Run: `cd engine && pytest tests/test_profile.py -v && mypy`
Expected: PASS; mypy clean.

- [ ] **Step 5: Commit**

```bash
git add engine/devboost/profile.py engine/tests/test_profile.py
git commit -m "feat(engine): profile loader + recursive expansion with transitive requires"
```

---

## Task 4: Dependency toposort

**Files:**
- Create: `engine/devboost/graph.py`
- Test: `engine/tests/test_graph.py`

**Interfaces:**
- Consumes: `Module`.
- Produces:
  - `class DependencyCycle(Exception)`
  - `toposort(names: list[str], modules: Mapping[str, Module]) -> list[str]` — stable topological order over `requires` restricted to `names`; raises `DependencyCycle` on a cycle.

- [ ] **Step 1: Write failing tests**

Create `engine/tests/test_graph.py`:

```python
import pytest

from devboost.graph import DependencyCycle, toposort
from devboost.manifest import Module


def _m(name: str, requires: tuple[str, ...] = ()) -> Module:
    return Module(name, "cli", "true", requires, {"fedora": "x"}, {}, False)


def test_toposort_orders_deps_first() -> None:
    mods = {"a": _m("a", ("b",)), "b": _m("b")}
    assert toposort(["a", "b"], mods) == ["b", "a"]


def test_toposort_detects_cycle() -> None:
    mods = {"a": _m("a", ("b",)), "b": _m("b", ("a",))}
    with pytest.raises(DependencyCycle):
        toposort(["a", "b"], mods)
```

- [ ] **Step 2: Run — verify fail**

Run: `cd engine && pytest tests/test_graph.py -v`
Expected: FAIL — `ModuleNotFoundError: devboost.graph`.

- [ ] **Step 3: Implement**

Create `engine/devboost/graph.py`:

```python
from collections.abc import Mapping
from graphlib import CycleError, TopologicalSorter

from devboost.manifest import Module


class DependencyCycle(Exception):
    pass


def toposort(names: list[str], modules: Mapping[str, Module]) -> list[str]:
    selected = set(names)
    ts: TopologicalSorter[str] = TopologicalSorter()
    for name in names:
        deps = [d for d in modules[name].requires if d in selected]
        ts.add(name, *deps)
    try:
        return list(ts.static_order())
    except CycleError as exc:
        raise DependencyCycle(str(exc)) from exc
```

- [ ] **Step 4: Run — verify pass + types**

Run: `cd engine && pytest tests/test_graph.py -v && mypy`
Expected: PASS; mypy clean.

- [ ] **Step 5: Commit**

```bash
git add engine/devboost/graph.py engine/tests/test_graph.py
git commit -m "feat(engine): dependency toposort with cycle detection"
```

---

## Task 5: Plan builder (per-OS install, fallback ladder, headless skip)

**Files:**
- Create: `engine/devboost/plan.py`
- Test: `engine/tests/test_plan.py`

**Interfaces:**
- Consumes: `Module`, `OsInfo`.
- Produces:
  - `@dataclass(frozen=True) class PlannedModule: name: str; verify: str; steps: tuple[str, ...]; skip_reason: str | None`
  - `resolve_steps(mod: Module, os_info: OsInfo) -> tuple[str, ...]` — ordered ladder: `install[distro]` → `install[family]` → `install["default"]` (first match only), then fallback `mise use -g <spec>`, then fallback `curl -fsSL <url> | sh`.
  - `build_plan(order: list[str], modules: Mapping[str, Module], os_info: OsInfo, headless: bool) -> list[PlannedModule]` — sets `skip_reason="headless-gui"` for GUI modules when headless, `"unsupported-os"` when the ladder is empty.

- [ ] **Step 1: Write failing tests**

Create `engine/tests/test_plan.py`:

```python
from devboost.manifest import Module
from devboost.osinfo import OsInfo
from devboost.plan import build_plan, resolve_steps


def _m(name: str, install: dict[str, str], fallback: dict[str, str] = {}, gui: bool = False) -> Module:
    return Module(name, "cli", f"command -v {name}", (), install, fallback, gui)


FEDORA = OsInfo("fedora", "fedora", "x86_64")
UBUNTU = OsInfo("ubuntu", "debian", "x86_64")


def test_resolve_prefers_distro_then_fallback() -> None:
    mod = _m("eza", {"fedora": "dnf eza"}, {"mise": "aqua:eza-community/eza"})
    # On ubuntu there's no apt key -> falls to mise ladder step
    assert resolve_steps(mod, UBUNTU) == ("mise use -g aqua:eza-community/eza",)
    # On fedora the distro install wins, mise still appended as fallback
    assert resolve_steps(mod, FEDORA) == ("dnf eza", "mise use -g aqua:eza-community/eza")


def test_build_plan_skips_gui_when_headless() -> None:
    mods = {"ghostty": _m("ghostty", {"fedora": "echo g"}, gui=True)}
    plan = build_plan(["ghostty"], mods, FEDORA, headless=True)
    assert plan[0].skip_reason == "headless-gui"


def test_build_plan_marks_unsupported() -> None:
    mods = {"x": _m("x", {"fedora": "echo x"})}
    plan = build_plan(["x"], mods, UBUNTU, headless=False)
    assert plan[0].skip_reason == "unsupported-os"
```

- [ ] **Step 2: Run — verify fail**

Run: `cd engine && pytest tests/test_plan.py -v`
Expected: FAIL — `ModuleNotFoundError: devboost.plan`.

- [ ] **Step 3: Implement**

Create `engine/devboost/plan.py`:

```python
from collections.abc import Mapping
from dataclasses import dataclass

from devboost.manifest import Module
from devboost.osinfo import OsInfo


@dataclass(frozen=True)
class PlannedModule:
    name: str
    verify: str
    steps: tuple[str, ...]
    skip_reason: str | None


def resolve_steps(mod: Module, os_info: OsInfo) -> tuple[str, ...]:
    steps: list[str] = []
    for key in (os_info.distro, os_info.family, "default"):
        if key in mod.install:
            steps.append(mod.install[key])
            break
    if "mise" in mod.fallback:
        steps.append(f"mise use -g {mod.fallback['mise']}")
    if "script" in mod.fallback:
        steps.append(f"curl -fsSL {mod.fallback['script']} | sh")
    return tuple(steps)


def build_plan(
    order: list[str],
    modules: Mapping[str, Module],
    os_info: OsInfo,
    headless: bool,
) -> list[PlannedModule]:
    plan: list[PlannedModule] = []
    for name in order:
        mod = modules[name]
        steps = resolve_steps(mod, os_info)
        skip: str | None = None
        if mod.gui and headless:
            skip = "headless-gui"
        elif not steps:
            skip = "unsupported-os"
        plan.append(PlannedModule(mod.name, mod.verify, steps, skip))
    return plan
```

- [ ] **Step 4: Run — verify pass + types**

Run: `cd engine && pytest tests/test_plan.py -v && mypy`
Expected: PASS; mypy clean.

- [ ] **Step 5: Commit**

```bash
git add engine/devboost/plan.py engine/tests/test_plan.py
git commit -m "feat(engine): plan builder with fallback ladder + headless GUI skip"
```

---

## Task 6: Verify-guarded runner (executable installs)

**Files:**
- Create: `engine/devboost/runner.py`
- Create: `engine/devboost/log.py`
- Test: `engine/tests/test_runner.py`

**Interfaces:**
- Consumes: `PlannedModule`.
- Produces:
  - `class Executor(Protocol): def run(self, cmd: str) -> int: ...`
  - `class SubprocessExecutor: def run(self, cmd: str) -> int` — runs `bash -lc cmd`, returns exit code (the real install path).
  - `@dataclass class RunResult: name: str; status: str` where `status ∈ {"ok","skip","fail"}`.
  - `run_plan(plan: list[PlannedModule], executor: Executor, *, dry_run: bool, force: bool) -> list[RunResult]` — for each module: honor `skip_reason`; else if not `force` and `verify` passes ⇒ skip; else (dry-run logs and marks ok) try each step until `verify` passes ⇒ ok, otherwise fail.

- [ ] **Step 1: Write failing tests**

Create `engine/tests/test_runner.py`:

```python
from devboost.plan import PlannedModule
from devboost.runner import RunResult, run_plan


class FakeExecutor:
    """verify returns nonzero until an install step has run; installs succeed."""

    def __init__(self, installed: set[str] | None = None) -> None:
        self.installed = installed or set()
        self.calls: list[str] = []

    def run(self, cmd: str) -> int:
        self.calls.append(cmd)
        if cmd.startswith("verify:"):
            return 0 if cmd[len("verify:"):] in self.installed else 1
        self.installed.add(cmd)  # any install "command" marks itself installed
        return 0


def _pm(name: str, steps: tuple[str, ...], skip: str | None = None) -> PlannedModule:
    return PlannedModule(name, f"verify:{name}", steps, skip)


def test_runs_install_when_verify_red() -> None:
    ex = FakeExecutor()
    # verify:eza red -> runs step "eza" -> but verify checks 'eza' membership, step adds 'eza'
    plan = [_pm("eza", ("eza",))]
    results = run_plan(plan, ex, dry_run=False, force=False)
    assert results == [RunResult("eza", "ok")]
    assert "eza" in ex.calls


def test_skips_when_verify_green() -> None:
    ex = FakeExecutor(installed={"eza"})
    results = run_plan([_pm("eza", ("eza",))], ex, dry_run=False, force=False)
    assert results == [RunResult("eza", "skip")]


def test_honors_skip_reason() -> None:
    ex = FakeExecutor()
    results = run_plan([_pm("ghostty", ("g",), skip="headless-gui")], ex, dry_run=False, force=False)
    assert results == [RunResult("ghostty", "skip")]
    assert ex.calls == []


def test_dry_run_executes_nothing() -> None:
    ex = FakeExecutor()
    results = run_plan([_pm("eza", ("eza",))], ex, dry_run=True, force=False)
    assert results == [RunResult("eza", "ok")]
    assert ex.calls == []


def test_fallback_step_used_when_first_fails() -> None:
    class FirstFails(FakeExecutor):
        def run(self, cmd: str) -> int:
            self.calls.append(cmd)
            if cmd.startswith("verify:"):
                return 0 if "good" in self.installed else 1
            if cmd == "bad":
                return 1
            self.installed.add("good")
            return 0

    ex = FirstFails()
    results = run_plan([_pm("eza", ("bad", "good"))], ex, dry_run=False, force=False)
    assert results == [RunResult("eza", "ok")]
    assert ex.calls == ["verify:eza", "bad", "good", "verify:eza"]
```

- [ ] **Step 2: Run — verify fail**

Run: `cd engine && pytest tests/test_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: devboost.runner`.

- [ ] **Step 3: Implement logging + runner**

Create `engine/devboost/log.py`:

```python
import typer


def info(msg: str) -> None:
    typer.echo(msg)


def ok(msg: str) -> None:
    typer.secho(msg, fg=typer.colors.GREEN)


def skip(msg: str) -> None:
    typer.secho(msg, fg=typer.colors.YELLOW)


def error(msg: str) -> None:
    typer.secho(msg, fg=typer.colors.RED, err=True)
```

Create `engine/devboost/runner.py`:

```python
import subprocess
from dataclasses import dataclass
from typing import Protocol

from devboost import log
from devboost.plan import PlannedModule


class Executor(Protocol):
    def run(self, cmd: str) -> int: ...


class SubprocessExecutor:
    def run(self, cmd: str) -> int:
        return subprocess.run(["bash", "-lc", cmd], check=False).returncode


@dataclass
class RunResult:
    name: str
    status: str


def run_plan(
    plan: list[PlannedModule],
    executor: Executor,
    *,
    dry_run: bool,
    force: bool,
) -> list[RunResult]:
    results: list[RunResult] = []
    for pm in plan:
        if pm.skip_reason is not None:
            log.skip(f"skip {pm.name} ({pm.skip_reason})")
            results.append(RunResult(pm.name, "skip"))
            continue
        if not force and executor.run(pm.verify) == 0:
            log.skip(f"skip {pm.name} (already installed)")
            results.append(RunResult(pm.name, "skip"))
            continue
        if dry_run:
            log.info(f"would install {pm.name}: {' || '.join(pm.steps)}")
            results.append(RunResult(pm.name, "ok"))
            continue
        installed = False
        for step in pm.steps:
            executor.run(step)
            if executor.run(pm.verify) == 0:
                installed = True
                break
        if installed:
            log.ok(f"installed {pm.name}")
            results.append(RunResult(pm.name, "ok"))
        else:
            log.error(f"FAILED {pm.name}")
            results.append(RunResult(pm.name, "fail"))
    return results
```

- [ ] **Step 4: Run — verify pass + types**

Run: `cd engine && pytest tests/test_runner.py -v && mypy`
Expected: PASS; mypy clean.

- [ ] **Step 5: Commit**

```bash
git add engine/devboost/runner.py engine/devboost/log.py engine/tests/test_runner.py
git commit -m "feat(engine): verify-guarded runner with injectable executor + dry-run"
```

---

## Task 7: Typer CLI wiring (terminal/devtools/install/verify/list)

**Files:**
- Modify: `engine/devboost/cli.py`
- Test: `engine/tests/test_cli.py` (extend)

**Interfaces:**
- Consumes: every prior module.
- Produces console commands:
  - `devboost terminal [--dry-run] [--force] [--root PATH]`
  - `devboost devtools [--dry-run] [--force] [--root PATH]`
  - `devboost install PROFILES... [--dry-run] [--force] [--root PATH]`
  - `devboost list PROFILES...` (prints resolved install order)
  - `devboost verify PROFILES...` (runs each verify, reports installed/missing)
  - Helper `_run(profiles, root, dry_run, force) -> list[RunResult]` shared by the tier commands.
  - `--root` defaults to `Path(__file__).resolve().parents[2]` (repo root) and reads `modules/` + `profiles.toml` there.

- [ ] **Step 1: Write failing tests (extend test_cli.py)**

Append to `engine/tests/test_cli.py`:

```python
from pathlib import Path

import pytest


@pytest.fixture
def repo(modules_dir: Path) -> Path:
    root = modules_dir.parent
    (root / "profiles.toml").write_text(
        '[profiles]\nterminal = ["eza", "ghostty"]\ndevtools = ["fzf"]\n'
    )
    return root


def test_list_resolves_order(repo: Path) -> None:
    result = runner.invoke(app, ["list", "terminal", "--root", str(repo)])
    assert result.exit_code == 0
    # eza requires fzf -> fzf precedes eza; ghostty present
    out = result.stdout
    assert out.index("fzf") < out.index("eza")
    assert "ghostty" in out


def test_terminal_dry_run(repo: Path) -> None:
    result = runner.invoke(app, ["terminal", "--dry-run", "--root", str(repo)])
    assert result.exit_code == 0
    assert "would install" in result.stdout


def test_terminal_dry_run_skips_gui_when_headless(repo: Path, monkeypatch) -> None:
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    result = runner.invoke(app, ["terminal", "--dry-run", "--root", str(repo)])
    assert "skip ghostty (headless-gui)" in result.stdout
```

- [ ] **Step 2: Run — verify fail**

Run: `cd engine && pytest tests/test_cli.py -v`
Expected: FAIL — no `list`/`terminal` commands.

- [ ] **Step 3: Implement CLI**

Replace `engine/devboost/cli.py` with:

```python
from pathlib import Path
from typing import Annotated, Optional

import typer

from devboost import __version__, log, osinfo
from devboost.graph import toposort
from devboost.manifest import load_modules
from devboost.plan import build_plan
from devboost.profile import expand, load_profiles
from devboost.runner import RunResult, SubprocessExecutor, run_plan

app = typer.Typer(help="dev-boost portable installer", no_args_is_help=True)

_DEFAULT_ROOT = Path(__file__).resolve().parents[2]
RootOpt = Annotated[Path, typer.Option(help="Repo root holding modules/ + profiles.toml")]
DryOpt = Annotated[bool, typer.Option("--dry-run", help="Preview without executing")]
ForceOpt = Annotated[bool, typer.Option("--force", help="Reinstall even if verify passes")]


def _version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        Optional[bool], typer.Option("--version", callback=_version, is_eager=True)
    ] = None,
) -> None:
    """dev-boost CLI root."""


def _order(profiles: list[str], root: Path) -> tuple[list[str], dict]:
    modules = load_modules(root / "modules")
    profs = load_profiles(root / "profiles.toml")
    return toposort(expand(profiles, profs, modules), modules), modules


def _run(profiles: list[str], root: Path, dry_run: bool, force: bool) -> list[RunResult]:
    order, modules = _order(profiles, root)
    plan = build_plan(order, modules, osinfo.detect(), osinfo.is_headless())
    results = run_plan(plan, SubprocessExecutor(), dry_run=dry_run, force=force)
    if any(r.status == "fail" for r in results):
        raise typer.Exit(code=1)
    return results


@app.command()
def install(
    profiles: list[str], root: RootOpt = _DEFAULT_ROOT, dry_run: DryOpt = False, force: ForceOpt = False
) -> None:
    """Install one or more tiers/profiles."""
    _run(profiles, root, dry_run, force)


@app.command()
def terminal(root: RootOpt = _DEFAULT_ROOT, dry_run: DryOpt = False, force: ForceOpt = False) -> None:
    """Install the terminal tier (any OS, headless-aware)."""
    _run(["terminal"], root, dry_run, force)


@app.command()
def devtools(root: RootOpt = _DEFAULT_ROOT, dry_run: DryOpt = False, force: ForceOpt = False) -> None:
    """Install the devtools tier (runtimes + frameworks)."""
    _run(["devtools"], root, dry_run, force)


@app.command(name="list")
def list_(profiles: list[str], root: RootOpt = _DEFAULT_ROOT) -> None:
    """Print the resolved install order for the given profiles."""
    order, _ = _order(profiles, root)
    for name in order:
        typer.echo(name)


@app.command()
def verify(profiles: list[str], root: RootOpt = _DEFAULT_ROOT) -> None:
    """Report which modules of the given profiles are already installed."""
    order, modules = _order(profiles, root)
    ex = SubprocessExecutor()
    for name in order:
        status = "installed" if ex.run(modules[name].verify) == 0 else "missing"
        log.info(f"{name}: {status}")
```

- [ ] **Step 4: Run — verify pass + types**

Run: `cd engine && pytest tests/test_cli.py -v && mypy`
Expected: PASS; mypy clean.

- [ ] **Step 5: Manual smoke (real executable)**

Run: `cd engine && devboost list terminal --root "$(git rev-parse --show-toplevel)"`
Expected: prints an ordered module list (after Task 8 adds the profiles to the real `profiles.toml`).

- [ ] **Step 6: Commit**

```bash
git add engine/devboost/cli.py engine/tests/test_cli.py
git commit -m "feat(cli): terminal/devtools/install/list/verify commands"
```

---

## Task 8: Wire the real `terminal` + `devtools` profiles + parity pattern

**Files:**
- Modify: `profiles.toml`
- Modify: `modules/eza.toml`, `modules/zoxide.toml` (add `debian`/`[fallback]` as the parity exemplar)
- Test: `engine/tests/test_integration_profiles.py`

**Interfaces:**
- Consumes: the engine via `CliRunner` against the real repo root.
- Produces: real `[profiles] terminal` / `[profiles] devtools` arrays; two modules demonstrating the distro+fallback pattern Plan 2 will roll out everywhere.

- [ ] **Step 1: Write failing integration test**

Create `engine/tests/test_integration_profiles.py`:

```python
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_real_terminal_profile_lists_core_tools() -> None:
    out = subprocess.run(
        ["devboost", "list", "terminal", "--root", str(ROOT)],
        capture_output=True, text=True, check=True,
    ).stdout
    for tool in ("zoxide", "fzf", "starship", "bat", "eza"):
        assert tool in out


def test_real_devtools_profile_nonempty() -> None:
    out = subprocess.run(
        ["devboost", "list", "devtools", "--root", str(ROOT)],
        capture_output=True, text=True, check=True,
    ).stdout
    assert out.strip() != ""
```

- [ ] **Step 2: Run — verify fail**

Run: `cd engine && pytest tests/test_integration_profiles.py -v`
Expected: FAIL — `terminal`/`devtools` not in `profiles.toml` (KeyError) or tools missing.

- [ ] **Step 3: Add profiles to `profiles.toml`**

Add these two arrays under `[profiles]` in `/home/dev/repos/dev-boost/profiles.toml`:

```toml
terminal = ["coreutils","git","curl","wget","unzip","jq","mise","chezmoi",
            "ripgrep","fd","fzf","bat","eza","btop","zoxide","atuin","direnv",
            "delta","lazygit","dust","duf","sd","yq","gh","tealdeer","fastfetch",
            "tmux","fresh","starship","bash-config","dotfiles","ghostty","nerd-fonts"]
devtools = ["web-runtimes","uv","python-lsp","web-lsp","dotnet-sdk","aspire",
            "dotnet-lsp","ddev"]
```

- [ ] **Step 4: Add the parity pattern to two modules**

In `modules/eza.toml` ensure both keys + fallback exist:

```toml
[install]
fedora = "sudo dnf install -y eza"
debian = "sudo apt-get install -y eza"

[fallback]
mise = "aqua:eza-community/eza"
```

In `modules/zoxide.toml`:

```toml
[install]
fedora = "sudo dnf install -y zoxide"
debian = "sudo apt-get install -y zoxide"

[fallback]
script = "https://raw.githubusercontent.com/ajeetdsouza/zoxide/main/install.sh"
```

Mark GUI modules so headless skip works — add `gui = true` to `modules/ghostty/module.toml` and `modules/nerd-fonts/*.toml` (whichever manifest form they use).

- [ ] **Step 5: Run — verify pass + types**

Run: `cd engine && pytest tests/test_integration_profiles.py -v && mypy && pytest`
Expected: integration PASS; full suite PASS; mypy clean.

- [ ] **Step 6: Commit**

```bash
git add profiles.toml modules/eza.toml modules/zoxide.toml modules/ghostty modules/nerd-fonts engine/tests/test_integration_profiles.py
git commit -m "feat: terminal + devtools profiles wired to typed engine (parity exemplar)"
```

---

## Self-Review

**Spec coverage (spec §2 decisions):**
1. Two tiers — Task 8 (`terminal`/`devtools` profiles). ✅
2. One engine reused — single `devboost` package; zero-config flow calls it later. ✅
3. Headless skip — Task 5 (`build_plan`) + Task 7 test + Task 8 `gui=true`. ✅
4. Distro-first + fallback ladder — Task 5 (`resolve_steps`) + Task 8 exemplars. ✅
5. Typed-Python — every task, mypy `--strict`. ✅
6. Frozen binary — **deferred to Plan 3** (noted in Global Constraints). ✅ (not regressed)
7. Typer CLI — Tasks 0/7. ✅
- Executable installs (user ask) — Task 6 `SubprocessExecutor` + Task 7 wiring. ✅
- Constitution amendment — Task 0 Step 1 (prerequisite gate). ✅

**Placeholder scan:** none — every code/step is concrete.

**Type consistency:** `Module`, `OsInfo`, `PlannedModule`, `RunResult`, `Executor`, `run_plan(..., *, dry_run, force)`, `resolve_steps`, `build_plan`, `expand`, `toposort`, `load_modules`, `load_profiles` — names/signatures identical across producing and consuming tasks. ✅

**Deferred scope is real, working software here:** after Task 8, `devboost terminal` resolves and installs the full terminal tier on Fedora today and on Ubuntu for any module given a `debian`/`[fallback]` key; Plan 2 completes parity for the rest.
