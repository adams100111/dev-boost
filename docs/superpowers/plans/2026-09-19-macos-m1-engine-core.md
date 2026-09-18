# macOS M1 — Engine Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the dev-boost engine run correctly on macOS (Apple Silicon, macOS 27/26): detect it, install through Homebrew, manage launchd jobs, report user-only steps as `blocked`, and handle credentials without plaintext tokens — with no catalog/profile content changes beyond what the engine needs.

**Architecture:** `macos` becomes a first-class OS family inside the existing typed seams: `OsMap.macos`, a `Brew` package manager behind `pkg.manager_for()`, a `launchd` primitive beside `systemd`, two new typed errors (`NeedsUser`, `PresentUnmanaged`) mapped by the runner, a `TccGrant` module field for privacy permissions, and a small `cli/host.py` for macOS invocation rules (root guard, Linux-only commands, sudo keepalive, keep-awake). All behaviour is injected/hermetic so tests run identically on Linux CI and on a Mac.

**Tech Stack:** Python ≥ 3.12, Typer, Pydantic, stdlib `plistlib`/`platform`/`threading`, pytest, mypy `--strict`, ruff; `uv` for the dev environment.

**Spec:** `docs/superpowers/specs/2026-09-18-macos-support-design.md` (§0, §1, §5, §8, §9, §10, §11-M1). Read it before starting.

## Global Constraints

- Apple Silicon only; macOS family id is `"macos"`; arch is normalized `arm64 → aarch64` on every OS.
- Supported macOS: 27 Golden Gate (primary), 26 Tahoe; 15 best-effort; ≤ 14 refused (M6 enforces in `get.sh`; the engine only records `version_id`).
- Brew is **never** run with `sudo`; every brew call passes env `HOMEBREW_NO_AUTO_UPDATE=1`, `HOMEBREW_NO_INSTALL_CLEANUP=1`, `HOMEBREW_NO_ENV_HINTS=1`, `NONINTERACTIVE=1`.
- Casks install with `brew install --cask -y --adopt`; a hand-installed app brew cannot adopt is reported `present-unmanaged`, never overwritten.
- launchd labels are `dev.devboost.<name>`.
- On macOS no GitHub token is ever written to `~/.git-credentials`.
- Merge gates (constitution): `uv run ruff check`, `uv run mypy`, `uv run pytest` all clean. Tests are hermetic: never depend on the host OS — inject `system=`/`os_info` instead.
- Linux behaviour must not change (every existing Linux test keeps passing unmodified in intent).
- All commands below run from `engine/` unless stated otherwise.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `engine/src/devboost/core/osinfo.py` (modify) | `OsMap.macos`, `normalize_arch`, Darwin detect + headless | 1 |
| `engine/src/devboost/core/plan.py` (modify) | `_supported` recognises `per_os.macos` | 1 |
| `engine/src/devboost/exec/executor.py` (modify) | Homebrew dirs on PATH on Darwin | 2 |
| `engine/src/devboost/core/errors.py` (modify) | `NeedsUser`, `PresentUnmanaged` | 3 |
| `engine/src/devboost/core/runner.py` (modify) | map new errors → `blocked` / `skip`; TCC gate | 3, 7 |
| `engine/src/devboost/model.py` (modify) | `BrewTap` source; `TccGrant`; `Module.tcc`, `Module.portable` | 4, 7, 11 |
| `engine/src/devboost/exec/primitives/pkg.py` (modify) | `Brew` manager + public `install_cask`/`cask_installed`/`upgrade` | 4 |
| `engine/src/devboost/exec/primitives/launchd.py` (create) | LaunchAgents / LaunchDaemons | 5 |
| `engine/src/devboost/modules/_pkgmodule.py` (modify) | `brew_pkg`/`brew_cask` + macOS branch | 6 |
| `engine/src/devboost/modules/apps.py` (modify) | `FlatpakApp.cask` + macOS branch; obsidian-sync token source | 6, 9 |
| `engine/src/devboost/exec/primitives/tcc.py` (create) | privacy-permission URLs + confirmation state | 7 |
| `engine/src/devboost/cli/permissions.py` (create) | `devboost permissions` command | 7 |
| `engine/src/devboost/cli/host.py` (create) | root guard, Linux-only commands, sudo keepalive, keep-awake | 8 |
| `engine/src/devboost/cli/app.py` (modify) | wire platform rules, default profile, sub-commands | 7, 8, 9 |
| `profiles.toml` (modify) | seed `macos` profile | 8 |
| `engine/src/devboost/modules/_credentials.py` (modify) | `github_credentials()` single token source | 9 |
| `engine/src/devboost/modules/secrets.py` (modify) | macOS gh-first/keychain; keychain age key | 9 |
| `engine/src/devboost/modules/ssh_setup.py` (modify) | token via `github_credentials()` | 9 |
| `engine/src/devboost/cli/secrets_cmd.py` (create) | `devboost secrets import-key` | 9 |
| `engine/src/devboost/cli/doctor.py` (modify) | macOS deps/probe, keychain key, TCC listing | 10 |
| `engine/tests/core/test_macos_contract.py` (create) | catalog contract test | 11 |
| `.specify/memory/constitution.md`, `docs/architecture.md`, `docs/adding-a-module.md`, `docs/credentials.md`, spec (modify) | docs | 12 |

---

### Task 0: macOS dev environment + baseline

**Files:** none (environment only)

- [ ] **Step 1: Install uv and sync the engine**

```bash
brew install uv
cd engine && uv sync
```
Expected: `.venv` created, no errors.

- [ ] **Step 2: Run the full gate once and save the baseline**

```bash
uv run ruff check; uv run mypy; uv run pytest 2>&1 | tail -40 | tee /tmp/devboost-m1-baseline.txt
```
Expected: ruff + mypy clean. pytest: some failures are expected **only** in tests that call `osinfo.detect()` / `osinfo.is_headless()` without injecting the OS (they now see Darwin) — `tests/core/test_osinfo.py` and `tests/modules/test_omarchy.py::test_detect_parses_id_like`. Task 1 fixes those. Any **other** failing test is a host-dependence bug: fix it in the task that touches that code by injecting the OS/`system="Linux"` explicitly (the pattern Task 1 establishes); if none of Tasks 1–11 touches it, fix it in Task 1's commit. Do not proceed past Task 1 with red tests.

---

### Task 1: OS detection — `OsMap.macos`, arch normalization, Darwin detect/headless

**Files:**
- Modify: `engine/src/devboost/core/osinfo.py`
- Modify: `engine/src/devboost/core/plan.py` (`_supported`)
- Modify: `engine/tests/core/test_osinfo.py`, `engine/tests/modules/test_omarchy.py` (pin Linux)
- Test: `engine/tests/core/test_osinfo.py`

**Interfaces:**
- Produces: `OsMap.macos: T | None`; `normalize_arch(machine: str) -> str`; `is_headless(env=None, default_target_link=..., system: str | None = None) -> bool`; `detect(os_release_path=..., machine=None, env=None, default_target_link=..., system: str | None = None, mac_version: str | None = None) -> OsInfo`. On Darwin: `OsInfo(distro="macos", family="macos", arch=<normalized>, version_id=<"27.0">)`.

- [ ] **Step 1: Write the failing tests** (append to `tests/core/test_osinfo.py`)

```python
from devboost.core.osinfo import normalize_arch


def test_normalize_arch_maps_apple_and_amd_aliases() -> None:
    assert normalize_arch("arm64") == "aarch64"
    assert normalize_arch("amd64") == "x86_64"
    assert normalize_arch("aarch64") == "aarch64"
    assert normalize_arch("x86_64") == "x86_64"


def test_detect_darwin_reports_macos_family_version_and_normalized_arch(tmp_path: Path) -> None:
    info = detect(
        os_release_path=str(tmp_path / "absent"), machine="arm64", env={},
        default_target_link=str(tmp_path / "absent"), system="Darwin", mac_version="27.0",
    )
    assert (info.distro, info.family, info.arch, info.version_id) == (
        "macos", "macos", "aarch64", "27.0"
    )
    assert info.headless is False


def test_is_headless_darwin_only_over_ssh(tmp_path: Path) -> None:
    missing = str(tmp_path / "missing")
    assert is_headless({}, missing, system="Darwin") is False
    assert is_headless({"SSH_CONNECTION": "1.2.3.4 5 6.7.8.9 22"}, missing, system="Darwin")
    assert is_headless({"SSH_TTY": "/dev/ttys001"}, missing, system="Darwin")


def test_osmap_macos_resolves_by_family() -> None:
    mac = OsInfo("macos", "macos", "aarch64")
    m: OsMap[str] = OsMap(fedora="fd-find", macos="fd", default="x")
    assert m.get(mac) == "fd"
    assert OsMap[str](default="x").get(mac) == "x"
```

Also pin every **existing** call in this file to Linux: add `system="Linux"` to each `detect(...)` call and to each `is_headless(...)` call (e.g. `is_headless({}, str(link), system="Linux")`, `detect(os_release_path=str(p), machine="x86_64", env={}, default_target_link=..., system="Linux")`). Do the same for the `detect(...)` call in `tests/modules/test_omarchy.py::test_detect_parses_id_like`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/core/test_osinfo.py -v`
Expected: FAIL — `ImportError: cannot import name 'normalize_arch'` / unexpected keyword `system`.

- [ ] **Step 3: Implement** in `core/osinfo.py`

Add after `_FAMILY`:

```python
_ARCH_ALIASES = {"arm64": "aarch64", "amd64": "x86_64"}


def normalize_arch(machine: str) -> str:
    """One arch vocabulary on every OS: macOS reports ``arm64``, Linux ``aarch64``.

    Release assets, catalog pins and self-update all key on ``aarch64``/``x86_64``.
    """
    return _ARCH_ALIASES.get(machine.lower(), machine)
```

Change `is_headless` signature and add the Darwin branch as its first statement after `e = ...`:

```python
def is_headless(
    env: Mapping[str, str] | None = None,
    default_target_link: str = "/etc/systemd/system/default.target",
    system: str | None = None,
) -> bool:
    e = os.environ if env is None else env
    if (system or platform.system()) == "Darwin":
        # A Mac is a GUI machine unless we are reaching it over SSH; there is no
        # systemd default target to consult (its absence would wrongly mean "headless").
        return bool(e.get("SSH_CONNECTION") or e.get("SSH_TTY"))
    if e.get("DISPLAY") or e.get("WAYLAND_DISPLAY"):
        ...  # existing body unchanged from here
```

Change `detect`:

```python
def detect(
    os_release_path: str = "/etc/os-release",
    machine: str | None = None,
    env: Mapping[str, str] | None = None,
    default_target_link: str = "/etc/systemd/system/default.target",
    system: str | None = None,
    mac_version: str | None = None,
) -> OsInfo:
    sysname = system or platform.system()
    distro = "unknown"
    version_id = ""
    codename = ""
    id_like: tuple[str, ...] = ()
    if sysname == "Darwin":
        distro = "macos"
        version_id = mac_version if mac_version is not None else platform.mac_ver()[0]
    else:
        ...  # existing os-release parsing unchanged
    return OsInfo(
        distro=distro,
        family=family_of(distro, id_like),
        arch=normalize_arch(machine or platform.machine()),
        headless=is_headless(env, default_target_link, sysname),
        version_id=version_id,
        codename=codename,
        id_like=id_like,
    )
```

In `OsMap`: add field `macos: T | None = None` after `arch`, and in `get()` use
`by_distro = {"fedora": self.fedora, "debian": self.debian, "arch": self.arch, "macos": self.macos}`.

In `core/plan.py::_supported` include macOS:

```python
def _supported(cls: type[Module], os_info: OsInfo) -> bool:
    """A per-OS module is unsupported when its per_os map has no entry for this OS."""
    p = cls.per_os
    if not (p.fedora or p.debian or p.arch or p.macos or p.default):
        return True  # uniform module — supported everywhere it can run
    return p.get(os_info) is not None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/core tests/modules/test_omarchy.py -v && uv run mypy`
Expected: PASS, mypy clean.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/core/osinfo.py src/devboost/core/plan.py tests/core/test_osinfo.py tests/modules/test_omarchy.py
git commit -m "feat(osinfo): macOS family, arm64→aarch64 normalization, Darwin headless"
```

---

### Task 2: Executor — Homebrew on PATH on Darwin

**Files:**
- Modify: `engine/src/devboost/exec/executor.py` (`_prepend_mise_dirs`)
- Test: `engine/tests/exec/test_executor.py`

**Interfaces:**
- Produces: `_prepend_mise_dirs(path: str, system: str | None = None) -> str` — on Darwin also prepends `/opt/homebrew/bin` and `/opt/homebrew/sbin` (after the user dirs). `RealExecutor` behaviour otherwise unchanged. Later tasks invoke brew as argv `["brew", ...]` and rely on this.

- [ ] **Step 1: Write the failing test** (append to `tests/exec/test_executor.py`)

```python
from devboost.exec.executor import _prepend_mise_dirs


def test_darwin_path_includes_homebrew_after_user_dirs() -> None:
    out = _prepend_mise_dirs("/usr/bin", system="Darwin").split(":")
    assert out.index("/opt/homebrew/bin") < out.index("/usr/bin")
    assert "/opt/homebrew/sbin" in out
    assert out[0].endswith(".local/share/mise/shims")


def test_linux_path_has_no_homebrew() -> None:
    assert "/opt/homebrew/bin" not in _prepend_mise_dirs("/usr/bin", system="Linux")


def test_homebrew_not_duplicated() -> None:
    out = _prepend_mise_dirs("/opt/homebrew/bin:/usr/bin", system="Darwin").split(":")
    assert out.count("/opt/homebrew/bin") == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/exec/test_executor.py -v`
Expected: FAIL — unexpected keyword `system`.

- [ ] **Step 3: Implement**

```python
import platform  # add to imports

_HOMEBREW_DIRS = ("/opt/homebrew/bin", "/opt/homebrew/sbin")


def _prepend_mise_dirs(path: str, system: str | None = None) -> str:
    """Return *path* with the user tool dirs (and, on macOS, Homebrew) prepended.

    ...keep the existing docstring text, then add:
    On macOS a ``curl | bash`` run has no brew shellenv yet, so Homebrew's prefix is
    added too — brew and everything it installs resolve without a new login shell.
    """
    try:
        home = Path.home()
    except RuntimeError:
        return path
    prepend = [
        str(home / ".local" / "share" / "mise" / "shims"),
        str(home / ".local" / "bin"),
        str(home / ".dotnet" / "tools"),
    ]
    if (system or platform.system()) == "Darwin":
        prepend.extend(_HOMEBREW_DIRS)
    existing = path.split(os.pathsep) if path else []
    new_parts = [p for p in prepend if p not in existing]
    return os.pathsep.join([*new_parts, *existing]) if new_parts else path
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/exec -v && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/exec/executor.py tests/exec/test_executor.py
git commit -m "feat(executor): put Homebrew on PATH on macOS"
```

---

### Task 3: `NeedsUser` / `PresentUnmanaged` errors and runner mapping

**Files:**
- Modify: `engine/src/devboost/core/errors.py`, `engine/src/devboost/core/runner.py`
- Test: `engine/tests/core/test_runner_macos.py` (create)

**Interfaces:**
- Produces:
  - `class NeedsUser(DevbootError)`: `__init__(self, reason: str, how_to_fix: str)`; attributes `reason`, `how_to_fix`.
  - `class PresentUnmanaged(DevbootError)`: `__init__(self, item: str)`; attribute `item`.
  - Runner: `NeedsUser` raised from `install()` → `RunResult(name, "blocked", "needs-user: <reason> → <how_to_fix>")`; `PresentUnmanaged` → `RunResult(name, "skip", "present-unmanaged")`. Other exceptions unchanged (`fail`).

- [ ] **Step 1: Write the failing tests** — `tests/core/test_runner_macos.py`

```python
from __future__ import annotations

from typing import ClassVar

from devboost.core.errors import NeedsUser, PresentUnmanaged
from devboost.core.osinfo import OsInfo
from devboost.core.plan import PlannedModule
from devboost.core.runner import run_plan
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx, Module

MAC = OsInfo("macos", "macos", "aarch64")


class _NeedsUserMod(Module):
    name: ClassVar[str] = "needs-user-mod"

    def verify(self, ctx: Ctx) -> bool:
        return False

    def install(self, ctx: Ctx) -> None:
        raise NeedsUser("Apple ID required", "export XCODES_USERNAME=… and re-run")


class _UnmanagedMod(Module):
    name: ClassVar[str] = "unmanaged-mod"

    def verify(self, ctx: Ctx) -> bool:
        return False

    def install(self, ctx: Ctx) -> None:
        raise PresentUnmanaged("visual-studio-code")


class _Dependent(Module):
    name: ClassVar[str] = "dependent-mod"
    requires = (_NeedsUserMod,)

    def verify(self, ctx: Ctx) -> bool:
        return True

    def install(self, ctx: Ctx) -> None:  # pragma: no cover — never reached
        raise AssertionError


def _run(*mods: type[Module]) -> dict[str, tuple[str, str]]:
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    plan = [PlannedModule(m.name) for m in mods]
    res = run_plan(plan, {m.name: m for m in mods}, ctx)
    return {r.name: (r.status, r.detail) for r in res}


def test_needs_user_is_blocked_with_fix_hint() -> None:
    out = _run(_NeedsUserMod)
    assert out["needs-user-mod"] == (
        "blocked", "needs-user: Apple ID required → export XCODES_USERNAME=… and re-run"
    )


def test_needs_user_blocks_dependents() -> None:
    out = _run(_NeedsUserMod, _Dependent)
    assert out["dependent-mod"][0] == "blocked"


def test_present_unmanaged_is_a_skip_not_a_failure() -> None:
    assert _run(_UnmanagedMod)["unmanaged-mod"] == ("skip", "present-unmanaged")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/core/test_runner_macos.py -v`
Expected: FAIL — `ImportError: cannot import name 'NeedsUser'`.

- [ ] **Step 3: Implement**

`core/errors.py` (after `UnsupportedOS`):

```python
class NeedsUser(DevbootError):
    """A step only a human can perform (sign in, approve, grant a permission).

    Reported as ``blocked`` with the exact fix, never as a failure: the rest of the plan
    keeps going, and the next run picks up where the human left off.
    """

    def __init__(self, reason: str, how_to_fix: str) -> None:
        self.reason = reason
        self.how_to_fix = how_to_fix
        super().__init__(f"{reason} — {how_to_fix}")


class PresentUnmanaged(DevbootError):
    """The thing is already installed outside dev-boost and must not be overwritten."""

    def __init__(self, item: str) -> None:
        self.item = item
        super().__init__(f"{item} is installed but not managed by dev-boost")
```

`core/runner.py`: import `from devboost.core.errors import NeedsUser, PresentUnmanaged` and replace the install `try/except` in `_run_one` with:

```python
    try:
        mod.install(ctx)
    except NeedsUser as exc:
        log.warn(f"{pm.name}: needs you — {exc.reason}. Fix: {exc.how_to_fix}")
        return RunResult(pm.name, "blocked", f"needs-user: {exc.reason} → {exc.how_to_fix}")
    except PresentUnmanaged as exc:
        log.skip(f"{pm.name} ({exc.item} already installed outside dev-boost — left untouched)")
        return RunResult(pm.name, "skip", "present-unmanaged")
    except Exception as exc:  # noqa: BLE001 — surface any module failure as a fail result
        log.error(f"{pm.name}: {exc}")
        return RunResult(pm.name, "fail", str(exc))
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/core -v && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/core/errors.py src/devboost/core/runner.py tests/core/test_runner_macos.py
git commit -m "feat(runner): NeedsUser → blocked, PresentUnmanaged → skip"
```

---

### Task 4: `BrewTap` source and the `Brew` package manager

**Files:**
- Modify: `engine/src/devboost/model.py`, `engine/src/devboost/exec/primitives/pkg.py`
- Test: `engine/tests/primitives/test_pkg_brew.py` (create)

**Interfaces:**
- Consumes: `NeedsUser`/`PresentUnmanaged` (Task 3), Darwin PATH (Task 2).
- Produces:
  - `model.BrewTap(name: str, url: str | None = None)` (frozen dataclass); `model.Source = OsMap[DnfRepo | AptRepo | BrewTap | Script]`.
  - `pkg.Repo = DnfRepo | AptRepo | BrewTap`; `pkg.Source = OsMap[Repo]`; `PackageManager.add_repo(ctx, repo: Repo)`.
  - `pkg.BREW_ENV: dict[str, str]`.
  - `class pkg.Brew` with `install(ctx, *pkgs)`, `install_cask(ctx, *casks)`, `installed(ctx, pkg) -> bool`, `cask_installed(ctx, cask) -> bool`, `upgrade(ctx, *pkgs)`, `add_repo(ctx, repo)`.
  - Public: `pkg.install_cask(ctx, *casks)`, `pkg.cask_installed(ctx, cask) -> bool`, `pkg.upgrade(ctx, *pkgs)` — raise `UnsupportedOS` off macOS (`cask_installed` returns `False` off macOS).
  - `pkg.manager_for()` returns `Brew()` for family `macos`; `pkg.refresh_index()` runs one best-effort `brew update` on macOS.

- [ ] **Step 1: Write the failing tests** — `tests/primitives/test_pkg_brew.py`

```python
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from devboost.core.errors import InstallError, PresentUnmanaged, UnsupportedOS
from devboost.core.osinfo import OsInfo, OsMap
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import pkg
from devboost.model import BrewTap, Ctx, DnfRepo

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")


@dataclass
class _EnvRecorder(FakeExecutor):
    """FakeExecutor that also records the env passed to each call."""

    envs: list[dict[str, str]] = field(default_factory=list)

    def run(self, argv: Sequence[str], *, sudo: bool = False, stdin: str | None = None, env: Mapping[str, str] | None = None, cwd: Path | None = None, interactive: bool = False) -> Result:
        self.envs.append(dict(env or {}))
        return super().run(argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive)


def test_manager_for_macos_is_brew() -> None:
    assert isinstance(pkg.manager_for(MAC), pkg.Brew)


def test_install_formula_argv_env_and_never_sudo() -> None:
    ex = _EnvRecorder()
    pkg.install(Ctx(os=MAC, ex=ex), "git", "jq")
    assert ex.calls == [["brew", "install", "--formula", "-y", "git", "jq"]]
    assert ex.envs[0] == pkg.BREW_ENV


def test_install_formula_failure_raises_install_error() -> None:
    ex = FakeExecutor(scripts={"brew": Result(1, stderr="No available formula")})
    with pytest.raises(InstallError):
        pkg.install(Ctx(os=MAC, ex=ex), "nope")


def test_install_cask_uses_adopt() -> None:
    ex = FakeExecutor()
    pkg.install_cask(Ctx(os=MAC, ex=ex), "ghostty")
    assert ex.calls == [["brew", "install", "--cask", "-y", "--adopt", "ghostty"]]


def test_install_cask_hand_installed_app_is_present_unmanaged() -> None:
    err = "Error: It seems there is already an App at '/Applications/Visual Studio Code.app'."
    ex = FakeExecutor(scripts={"brew": Result(1, stderr=err)})
    with pytest.raises(PresentUnmanaged):
        pkg.install_cask(Ctx(os=MAC, ex=ex), "visual-studio-code")


def test_install_cask_other_failure_raises_install_error() -> None:
    ex = FakeExecutor(scripts={"brew": Result(1, stderr="Download failed")})
    with pytest.raises(InstallError):
        pkg.install_cask(Ctx(os=MAC, ex=ex), "ghostty")


def test_installed_and_cask_installed_query_brew_list() -> None:
    ex = FakeExecutor()
    ctx = Ctx(os=MAC, ex=ex)
    assert pkg.installed(ctx, "git") is True
    assert pkg.cask_installed(ctx, "ghostty") is True
    assert ex.calls == [
        ["brew", "list", "--formula", "--versions", "git"],
        ["brew", "list", "--cask", "--versions", "ghostty"],
    ]
    missing = Ctx(os=MAC, ex=FakeExecutor(scripts={"brew": Result(1)}))
    assert pkg.installed(missing, "git") is False


def test_upgrade_formula() -> None:
    ex = FakeExecutor()
    pkg.upgrade(Ctx(os=MAC, ex=ex), "git")
    assert ex.calls == [["brew", "upgrade", "--formula", "git"]]


def test_brew_tap_source_taps_then_installs() -> None:
    ex = FakeExecutor()
    src: pkg.Source = OsMap[pkg.Repo](macos=BrewTap("ddev/ddev"))
    pkg.install(Ctx(os=MAC, ex=ex), "ddev/ddev/ddev", source=src)
    assert ex.calls == [
        ["brew", "tap", "ddev/ddev"],
        ["brew", "install", "--formula", "-y", "ddev/ddev/ddev"],
    ]


def test_brew_tap_with_url() -> None:
    ex = FakeExecutor()
    pkg.Brew().add_repo(Ctx(os=MAC, ex=ex), BrewTap("me/tap", "https://example.com/tap.git"))
    assert ex.calls == [["brew", "tap", "me/tap", "https://example.com/tap.git"]]


def test_brew_rejects_dnf_repo() -> None:
    with pytest.raises(TypeError):
        pkg.Brew().add_repo(Ctx(os=MAC, ex=FakeExecutor()), DnfRepo("x", "https://x"))


def test_cask_helpers_are_macos_only() -> None:
    ctx = Ctx(os=FEDORA, ex=FakeExecutor())
    with pytest.raises(UnsupportedOS):
        pkg.install_cask(ctx, "ghostty")
    with pytest.raises(UnsupportedOS):
        pkg.upgrade(ctx, "git")
    assert pkg.cask_installed(ctx, "ghostty") is False


def test_refresh_index_runs_brew_update_once_on_macos() -> None:
    ex = FakeExecutor()
    pkg.refresh_index(Ctx(os=MAC, ex=ex))
    assert ex.calls == [["brew", "update"]]


def test_refresh_index_failure_is_not_raised_on_macos() -> None:
    pkg.refresh_index(Ctx(os=MAC, ex=FakeExecutor(scripts={"brew": Result(1)})))
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/primitives/test_pkg_brew.py -v`
Expected: FAIL — `ImportError: cannot import name 'BrewTap'`.

- [ ] **Step 3: Implement**

`model.py` — after `AptRepo`:

```python
@dataclass(frozen=True)
class BrewTap:
    """A Homebrew tap (third-party formula/cask repository), e.g. ``ddev/ddev``."""

    name: str
    url: str | None = None
```

and change `Source = OsMap[DnfRepo | AptRepo | Script]` to `Source = OsMap[DnfRepo | AptRepo | BrewTap | Script]`.

`pkg.py`:
- import `BrewTap` from `devboost.model`, `PresentUnmanaged` from `devboost.core.errors`.
- replace the `Source` alias with:

```python
# A third-party install source per OS.
Repo = DnfRepo | AptRepo | BrewTap
Source = OsMap[Repo]
```

- change every `add_repo(self, ctx: Ctx, repo: DnfRepo | AptRepo)` annotation (Protocol, `Dnf`, `Apt`, `Pacman`) to `repo: Repo` (bodies unchanged — their `isinstance` checks already reject foreign repo types).
- add before `manager_for`:

```python
#: Every brew call runs with these. Auto-update is replaced by one explicit `brew update`
#: per run (refresh_index); cleanup and hints are noise in an unattended install.
BREW_ENV: dict[str, str] = {
    "HOMEBREW_NO_AUTO_UPDATE": "1",
    "HOMEBREW_NO_INSTALL_CLEANUP": "1",
    "HOMEBREW_NO_ENV_HINTS": "1",
    "NONINTERACTIVE": "1",
}

# brew's message when a cask's app already exists and --adopt cannot take it over
# (e.g. a different version was dragged into /Applications by hand).
_ALREADY_PRESENT = "already an App at"


class Brew:
    """macOS. Formulae and casks via Homebrew — never under sudo (brew refuses root).

    ``brew`` is invoked by name: the executor puts ``/opt/homebrew/bin`` on PATH on
    macOS, so this works before the user's shell has brew's shellenv.
    """

    def _brew(self, ctx: Ctx, *args: str) -> Result:
        return ctx.ex.run(["brew", *args], env=BREW_ENV)

    def install(self, ctx: Ctx, *pkgs: str) -> None:
        if not pkgs:
            return
        res = self._brew(ctx, "install", "--formula", "-y", *pkgs)
        if not res.ok:
            raise InstallError("brew", f"brew install --formula -y {' '.join(pkgs)}", res.code)

    def install_cask(self, ctx: Ctx, *casks: str) -> None:
        if not casks:
            return
        res = self._brew(ctx, "install", "--cask", "-y", "--adopt", *casks)
        if res.ok:
            return
        if _ALREADY_PRESENT in f"{res.stdout}\n{res.stderr}":
            raise PresentUnmanaged(", ".join(casks))
        raise InstallError("brew", f"brew install --cask -y --adopt {' '.join(casks)}", res.code)

    def installed(self, ctx: Ctx, pkg: str) -> bool:
        return self._brew(ctx, "list", "--formula", "--versions", pkg).ok

    def cask_installed(self, ctx: Ctx, cask: str) -> bool:
        return self._brew(ctx, "list", "--cask", "--versions", cask).ok

    def upgrade(self, ctx: Ctx, *pkgs: str) -> None:
        if not pkgs:
            return
        res = self._brew(ctx, "upgrade", "--formula", *pkgs)
        if not res.ok:
            raise InstallError("brew", f"brew upgrade --formula {' '.join(pkgs)}", res.code)

    def add_repo(self, ctx: Ctx, repo: Repo) -> None:
        if not isinstance(repo, BrewTap):
            raise TypeError(f"Brew.add_repo expects BrewTap, got {type(repo).__name__}")
        args = ["tap", repo.name, *([repo.url] if repo.url else [])]
        res = self._brew(ctx, *args)
        if not res.ok:
            raise InstallError("brew", f"brew {' '.join(args)}", res.code)
```

(add `from devboost.exec.executor import Result` to imports.)

- in `manager_for`, before the final `raise`: `if os_info.family == "macos": return Brew()`.
- add public helpers after `install_aur`:

```python
def _brew_or_raise(ctx: Ctx, what: str) -> Brew:
    mgr = manager_for(ctx.os)
    if not isinstance(mgr, Brew):
        raise UnsupportedOS(f"{what} is macOS-only; detected {ctx.os.distro!r}")
    return mgr


def install_cask(ctx: Ctx, *casks: str) -> None:
    """Install Homebrew casks (GUI apps). macOS only."""
    _brew_or_raise(ctx, "casks").install_cask(ctx, *casks)


def cask_installed(ctx: Ctx, cask: str) -> bool:
    """True when the cask is installed; always False off macOS (never raises)."""
    if ctx.os.family != "macos":
        return False
    return Brew().cask_installed(ctx, cask)


def upgrade(ctx: Ctx, *pkgs: str) -> None:
    """Upgrade formulae in place (`devboost install --update` on macOS)."""
    _brew_or_raise(ctx, "brew upgrade").upgrade(ctx, *pkgs)
```

- in `refresh_index`, replace the first line `if ctx.os.family != "debian": return` with:

```python
    if ctx.os.family == "macos":
        # One explicit update per run (auto-update is disabled on every other brew call).
        res = ctx.ex.run(["brew", "update"])
        if not res.ok:
            log.warn(f"brew update failed (code {res.code}); using the existing index")
        return
    if ctx.os.family != "debian":
        return
```

and extend its docstring with one sentence: "On macOS it is a single best-effort `brew update`."

- [ ] **Step 4: Run to verify pass (and no Linux regression)**

Run: `uv run pytest tests/primitives -v && uv run mypy`
Expected: PASS (existing `test_pkg.py` included).

- [ ] **Step 5: Commit**

```bash
git add src/devboost/model.py src/devboost/exec/primitives/pkg.py tests/primitives/test_pkg_brew.py
git commit -m "feat(pkg): Homebrew manager — formulae, casks (--adopt), taps, upgrade"
```

---

### Task 5: `launchd` primitive

**Files:**
- Create: `engine/src/devboost/exec/primitives/launchd.py`
- Test: `engine/tests/primitives/test_launchd.py` (create)

**Interfaces:**
- Produces (all in `devboost.exec.primitives.launchd`):
  - `label(name: str) -> str` → `"dev.devboost.<name>"`
  - `user_agent(ctx, label, program_args: Sequence[str], *, start_interval: int | None = None, start_calendar: Mapping[str, int] | None = None, run_at_load: bool = False, env: Mapping[str, str] | None = None) -> bool` (True = changed)
  - `system_daemon(ctx, label, program_args, *, run_at_load: bool = True, start_interval: int | None = None) -> bool`
  - `agent_loaded(ctx, label) -> bool`, `daemon_loaded(ctx, label) -> bool`, `remove_agent(ctx, label) -> None`
  - module attribute `DAEMONS_DIR: Path` (tests monkeypatch it).

- [ ] **Step 1: Write the failing tests** — `tests/primitives/test_launchd.py`

```python
from __future__ import annotations

import os
import plistlib
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from devboost.core.errors import InstallError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import launchd
from devboost.model import Ctx

MAC = OsInfo("macos", "macos", "aarch64")
UID = os.getuid()


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(launchd, "DAEMONS_DIR", tmp_path / "LaunchDaemons")
    return tmp_path


def test_label_namespacing() -> None:
    assert launchd.label("pass-sync") == "dev.devboost.pass-sync"


def test_user_agent_writes_plist_and_bootstraps(home: Path) -> None:
    ex = FakeExecutor()  # no plist yet → written and bootstrapped
    changed = launchd.user_agent(
        Ctx(os=MAC, ex=ex), "dev.devboost.x", ["/usr/bin/true", "a"],
        start_interval=900, env={"K": "V"}, run_at_load=True,
    )
    plist = home / "Library" / "LaunchAgents" / "dev.devboost.x.plist"
    data = plistlib.loads(plist.read_bytes())
    assert data == {
        "Label": "dev.devboost.x",
        "ProgramArguments": ["/usr/bin/true", "a"],
        "StartInterval": 900,
        "RunAtLoad": True,
        "EnvironmentVariables": {"K": "V"},
    }
    assert changed is True
    assert ["launchctl", "bootstrap", f"gui/{UID}", str(plist)] in ex.calls


def test_user_agent_idempotent_when_unchanged_and_loaded(home: Path) -> None:
    ctx = Ctx(os=MAC, ex=FakeExecutor())  # launchctl print → ok (loaded)
    launchd.user_agent(ctx, "dev.devboost.x", ["/usr/bin/true"])
    ex2 = FakeExecutor()
    assert launchd.user_agent(Ctx(os=MAC, ex=ex2), "dev.devboost.x", ["/usr/bin/true"]) is False
    assert ex2.calls == [["launchctl", "print", f"gui/{UID}/dev.devboost.x"]]


def test_user_agent_calendar(home: Path) -> None:
    launchd.user_agent(
        Ctx(os=MAC, ex=FakeExecutor()), "dev.devboost.y", ["/bin/echo"],
        start_calendar={"Hour": 3, "Minute": 0},
    )
    data = plistlib.loads((home / "Library/LaunchAgents/dev.devboost.y.plist").read_bytes())
    assert data["StartCalendarInterval"] == {"Hour": 3, "Minute": 0}


def test_user_agent_bootstrap_failure_raises(home: Path) -> None:
    ex = FakeExecutor(scripts={"launchctl": Result(5)})
    with pytest.raises(InstallError):
        launchd.user_agent(Ctx(os=MAC, ex=ex), "dev.devboost.z", ["/bin/echo"])


def test_system_daemon_writes_via_sudo_and_bootstraps_system_domain(home: Path) -> None:
    path = home / "LaunchDaemons" / "dev.devboost.limits.plist"
    # not loaded: make `launchctl print` fail but bootstrap succeed
    calls: list[list[str]] = []

    class _Ex(FakeExecutor):
        def run(self, argv: Sequence[str], *, sudo: bool = False, stdin: str | None = None, env: Mapping[str, str] | None = None, cwd: Path | None = None, interactive: bool = False) -> Result:
            calls.append((["sudo"] if sudo else []) + list(argv))
            return Result(1) if argv[:2] == ["launchctl", "print"] else Result(0)

    launchd.system_daemon(Ctx(os=MAC, ex=_Ex()), "dev.devboost.limits", ["/bin/launchctl", "limit"])
    assert ["sudo", "tee", str(path)] in calls
    assert ["sudo", "chown", "root:wheel", str(path)] in calls
    assert ["sudo", "chmod", "644", str(path)] in calls
    assert ["sudo", "launchctl", "bootstrap", "system", str(path)] in calls


def test_remove_agent_bootouts_and_deletes(home: Path) -> None:
    launchd.user_agent(Ctx(os=MAC, ex=FakeExecutor()), "dev.devboost.x", ["/bin/echo"])
    ex = FakeExecutor()
    launchd.remove_agent(Ctx(os=MAC, ex=ex), "dev.devboost.x")
    assert ["launchctl", "bootout", f"gui/{UID}/dev.devboost.x"] in ex.calls
    assert not (home / "Library/LaunchAgents/dev.devboost.x.plist").exists()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/primitives/test_launchd.py -v`
Expected: FAIL — `ImportError: cannot import name 'launchd'`.

- [ ] **Step 3: Implement** `exec/primitives/launchd.py`

```python
"""launchd primitive — per-user LaunchAgents and system LaunchDaemons (macOS).

The macOS counterpart of ``systemd.py``. Plists are built with stdlib ``plistlib`` and
(re)loaded with the modern ``launchctl bootstrap``/``bootout`` verbs. Every writer is
idempotent: an unchanged plist that is already loaded is left alone.
"""

from __future__ import annotations

import os
import plistlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from devboost.core.errors import InstallError
from devboost.model import Ctx

#: System daemons live here (root-owned). Module attribute so tests can redirect it.
DAEMONS_DIR = Path("/Library/LaunchDaemons")


def label(name: str) -> str:
    return f"dev.devboost.{name}"


def _agents_dir() -> Path:
    return Path(os.environ["HOME"]) / "Library" / "LaunchAgents"


def _gui_domain() -> str:
    return f"gui/{os.getuid()}"


def _plist(
    lbl: str,
    program_args: Sequence[str],
    *,
    start_interval: int | None,
    start_calendar: Mapping[str, int] | None,
    run_at_load: bool,
    env: Mapping[str, str] | None,
) -> bytes:
    data: dict[str, Any] = {"Label": lbl, "ProgramArguments": list(program_args)}
    if start_interval is not None:
        data["StartInterval"] = start_interval
    if start_calendar is not None:
        data["StartCalendarInterval"] = dict(start_calendar)
    if run_at_load:
        data["RunAtLoad"] = True
    if env:
        data["EnvironmentVariables"] = dict(env)
    return plistlib.dumps(data)


def agent_loaded(ctx: Ctx, lbl: str) -> bool:
    return ctx.ex.run(["launchctl", "print", f"{_gui_domain()}/{lbl}"]).ok


def daemon_loaded(ctx: Ctx, lbl: str) -> bool:
    return ctx.ex.run(["launchctl", "print", f"system/{lbl}"]).ok


def user_agent(
    ctx: Ctx,
    lbl: str,
    program_args: Sequence[str],
    *,
    start_interval: int | None = None,
    start_calendar: Mapping[str, int] | None = None,
    run_at_load: bool = False,
    env: Mapping[str, str] | None = None,
) -> bool:
    """Install/refresh a per-user LaunchAgent. Returns True when anything changed."""
    path = _agents_dir() / f"{lbl}.plist"
    body = _plist(lbl, program_args, start_interval=start_interval,
                  start_calendar=start_calendar, run_at_load=run_at_load, env=env)
    if path.exists() and path.read_bytes() == body and agent_loaded(ctx, lbl):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    ctx.ex.run(["launchctl", "bootout", f"{_gui_domain()}/{lbl}"])  # not loaded → ignored
    res = ctx.ex.run(["launchctl", "bootstrap", _gui_domain(), str(path)])
    if not res.ok:
        raise InstallError("launchd", f"launchctl bootstrap {_gui_domain()} {path}", res.code)
    return True


def system_daemon(
    ctx: Ctx,
    lbl: str,
    program_args: Sequence[str],
    *,
    run_at_load: bool = True,
    start_interval: int | None = None,
) -> bool:
    """Install/refresh a root LaunchDaemon (root:wheel 644, as launchd requires)."""
    path = DAEMONS_DIR / f"{lbl}.plist"
    body = _plist(lbl, program_args, start_interval=start_interval,
                  start_calendar=None, run_at_load=run_at_load, env=None)
    if path.exists() and path.read_bytes() == body and daemon_loaded(ctx, lbl):
        return False
    ctx.ex.run(["tee", str(path)], sudo=True, stdin=body.decode("utf-8"))
    ctx.ex.run(["chown", "root:wheel", str(path)], sudo=True)
    ctx.ex.run(["chmod", "644", str(path)], sudo=True)
    ctx.ex.run(["launchctl", "bootout", f"system/{lbl}"], sudo=True)
    res = ctx.ex.run(["launchctl", "bootstrap", "system", str(path)], sudo=True)
    if not res.ok:
        raise InstallError("launchd", f"launchctl bootstrap system {path}", res.code)
    return True


def remove_agent(ctx: Ctx, lbl: str) -> None:
    ctx.ex.run(["launchctl", "bootout", f"{_gui_domain()}/{lbl}"])
    (_agents_dir() / f"{lbl}.plist").unlink(missing_ok=True)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/primitives/test_launchd.py -v && uv run mypy && uv run ruff check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/exec/primitives/launchd.py tests/primitives/test_launchd.py
git commit -m "feat(launchd): LaunchAgent/LaunchDaemon primitive"
```

---

### Task 6: Module contract — `brew_pkg`/`brew_cask` and `FlatpakApp.cask`

**Files:**
- Modify: `engine/src/devboost/modules/_pkgmodule.py`, `engine/src/devboost/modules/apps.py` (`FlatpakApp` only)
- Test: `engine/tests/modules/test_macos_contract_fields.py` (create)

**Interfaces:**
- Consumes: `pkg.installed`, `pkg.install`, `pkg.install_cask`, `pkg.cask_installed`, `pkg.upgrade` (Task 4).
- Produces: `PackageModule.brew_pkg: ClassVar[str | None]` (None → module `name`), `PackageModule.brew_cask: ClassVar[str | None]`; on macOS `verify` = brew list, `install` = formula install, or `upgrade` when `ctx.force` and already installed (this is how `--update` upgrades on macOS). `FlatpakApp.cask: ClassVar[str | None]`; macOS verify = `cask_installed`, install = `install_cask`, missing `cask` → `UnsupportedOS` naming the module (verify returns False).

- [ ] **Step 1: Write the failing tests** — `tests/modules/test_macos_contract_fields.py`

```python
from __future__ import annotations

from typing import ClassVar

import pytest

from devboost.core.errors import UnsupportedOS
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules._pkgmodule import PackageModule
from devboost.modules.apps import FlatpakApp

MAC = OsInfo("macos", "macos", "aarch64")


class _Delta(PackageModule):
    name: ClassVar[str] = "delta"
    cmd: ClassVar[str] = "delta"
    fedora_pkg: ClassVar[str] = "git-delta"
    brew_pkg: ClassVar[str | None] = "git-delta"


class _Jq(PackageModule):
    name: ClassVar[str] = "jq"
    cmd: ClassVar[str] = "jq"
    fedora_pkg: ClassVar[str] = "jq"


class _CaskTool(PackageModule):
    name: ClassVar[str] = "caskt"
    cmd: ClassVar[str] = "caskt"
    fedora_pkg: ClassVar[str] = "caskt"
    brew_cask: ClassVar[str | None] = "caskt-app"


class _App(FlatpakApp):
    name: ClassVar[str] = "someapp"
    app_id: ClassVar[str] = "org.some.App"
    cask: ClassVar[str | None] = "some-app"


class _NoCaskApp(FlatpakApp):
    name: ClassVar[str] = "nocask"
    app_id: ClassVar[str] = "org.no.Cask"


def test_package_module_uses_brew_pkg_on_macos() -> None:
    ex = FakeExecutor()
    _Delta().install(Ctx(os=MAC, ex=ex))
    assert ex.calls[-1] == ["brew", "install", "--formula", "-y", "git-delta"]


def test_package_module_brew_name_defaults_to_module_name() -> None:
    ex = FakeExecutor(scripts={"brew": Result(1)})  # not installed
    assert _Jq().verify(Ctx(os=MAC, ex=ex)) is False
    assert ex.calls == [["brew", "list", "--formula", "--versions", "jq"]]


def test_package_module_force_upgrades_when_installed() -> None:
    ex = FakeExecutor()  # brew list → ok (installed)
    _Jq().install(Ctx(os=MAC, ex=ex, force=True))
    assert ex.calls[-1] == ["brew", "upgrade", "--formula", "jq"]


def test_package_module_cask_variant() -> None:
    ex = FakeExecutor()
    _CaskTool().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [["brew", "install", "--cask", "-y", "--adopt", "caskt-app"]]
    assert _CaskTool().verify(Ctx(os=MAC, ex=FakeExecutor())) is True


def test_flatpak_app_installs_cask_on_macos() -> None:
    ex = FakeExecutor()
    _App().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [["brew", "install", "--cask", "-y", "--adopt", "some-app"]]


def test_flatpak_app_without_cask_is_unsupported_on_macos() -> None:
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    assert _NoCaskApp().verify(ctx) is False
    with pytest.raises(UnsupportedOS, match="nocask"):
        _NoCaskApp().install(ctx)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_macos_contract_fields.py -v`
Expected: FAIL — brew argv not produced (dnf path taken / `brew_pkg` unknown).

- [ ] **Step 3: Implement**

`_pkgmodule.py` — add fields after `copr_repo`:

```python
    #: Homebrew formula on macOS; None → the module ``name`` (brew names usually match).
    brew_pkg: ClassVar[str | None] = None
    #: Homebrew cask on macOS, for tools that ship only as an app. Wins over brew_pkg.
    brew_cask: ClassVar[str | None] = None
```

and replace `verify`/`install` with:

```python
    def _brew_name(self) -> str:
        return self.brew_pkg or self.name

    def verify(self, ctx: Ctx) -> bool:
        if ctx.os.family == "macos":
            # Ask brew, not PATH: macOS ships its own (old) git/curl/… that would
            # otherwise satisfy a `which` check and never be replaced.
            if self.brew_cask is not None:
                return pkg.cask_installed(ctx, self.brew_cask)
            return pkg.installed(ctx, self._brew_name())
        return ctx.ex.which(self._resolve_cmd(ctx))

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "macos":
            if self.brew_cask is not None:
                pkg.install_cask(ctx, self.brew_cask)
                return
            name = self._brew_name()
            # `brew install` of an installed formula is a no-op; `--update` (force) means
            # "bring it current", which on brew is an explicit upgrade.
            if ctx.force and pkg.installed(ctx, name):
                pkg.upgrade(ctx, name)
            else:
                pkg.install(ctx, name)
            return
        if ctx.os.family == "fedora" and self.copr_repo is not None:
            copr.enable(ctx, self.copr_repo)
        # An AUR-only tool declares aur_pkg and no arch_pkg: route it to the helper.
        if ctx.os.family == "arch" and self.arch_pkg is None and self.aur_pkg is not None:
            pkg.install_aur(ctx, self.aur_pkg)
            return
        pkg.install(ctx, self._resolve_pkg(ctx))
```

`apps.py` — in `FlatpakApp` add the field and macOS branches (Linux branches unchanged):

```python
    #: Homebrew cask on macOS (Flathub does not exist there).
    cask: ClassVar[str | None] = None

    def verify(self, ctx: Ctx) -> bool:
        if ctx.os.family == "macos":
            return self.cask is not None and pkg.cask_installed(ctx, self.cask)
        if ctx.os.family == "arch":
            name = self._arch_name()
            return name is not None and pkg.installed(ctx, name)
        return ctx.ex.run(["flatpak", "info", self.app_id]).ok

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "macos":
            if self.cask is None:
                raise UnsupportedOS(f"{self.name}: no macOS cask declared (set cask)")
            pkg.install_cask(ctx, self.cask)
            return
        ...  # existing arch + flatpak body unchanged
```

Update the class docstring's first line to: "A GUI application: Flathub on Fedora/Ubuntu, a native package on Arch, a Homebrew cask on macOS."

- [ ] **Step 4: Run to verify pass (Linux paths unchanged)**

Run: `uv run pytest tests/modules -v && uv run mypy`
Expected: PASS (incl. existing `test_apps.py`, `test_omarchy.py`).

- [ ] **Step 5: Commit**

```bash
git add src/devboost/modules/_pkgmodule.py src/devboost/modules/apps.py tests/modules/test_macos_contract_fields.py
git commit -m "feat(modules): brew_pkg/brew_cask and FlatpakApp.cask for macOS"
```

---

### Task 7: Privacy permissions (TCC) — model field, state, runner gate, `devboost permissions`

**Files:**
- Modify: `engine/src/devboost/model.py`, `engine/src/devboost/core/runner.py`, `engine/src/devboost/cli/app.py`
- Create: `engine/src/devboost/exec/primitives/tcc.py`, `engine/src/devboost/cli/permissions.py`
- Test: `engine/tests/primitives/test_tcc.py`, `engine/tests/cli/test_permissions.py` (create)

**Interfaces:**
- Produces:
  - `model.TccService = Literal["Accessibility", "ListenEvent", "Microphone", "ScreenCapture"]` (these are System Settings anchor ids; `ListenEvent` = Input Monitoring, `ScreenCapture` = Screen Recording).
  - `model.TccGrant(service: TccService, app: str)` frozen dataclass; `Module.tcc: ClassVar[tuple[TccGrant, ...]] = ()`.
  - `tcc.settings_url(service) -> str`, `tcc.label(service) -> str`, `tcc.pending(module: str, grants: Sequence[TccGrant]) -> list[TccGrant]`, `tcc.confirm(module: str, grants: Sequence[TccGrant]) -> None`, `tcc.fix_hint(grants: Sequence[TccGrant]) -> str`, `tcc.state_file() -> Path`.
  - Runner: on macOS, a module that finishes `ok` or `skip/already-installed` but has unconfirmed grants → `RunResult(name, "blocked", "needs-user: grant permissions → <fix_hint>")`.
  - CLI: `devboost permissions` (list + open panes + confirm interactively) and `devboost permissions --confirm <module>`.

- [ ] **Step 1: Write the failing tests**

`tests/primitives/test_tcc.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from devboost.exec.primitives import tcc
from devboost.model import TccGrant

GRANTS = (TccGrant("Accessibility", "AeroSpace"), TccGrant("ListenEvent", "Voxtype"))


@pytest.fixture(autouse=True)
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    return tmp_path


def test_settings_url_and_label() -> None:
    assert tcc.settings_url("ListenEvent") == (
        "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
    )
    assert tcc.label("ListenEvent") == "Input Monitoring"
    assert tcc.label("ScreenCapture") == "Screen Recording"


def test_pending_until_confirmed(state: Path) -> None:
    assert tcc.pending("aerospace", GRANTS) == list(GRANTS)
    tcc.confirm("aerospace", GRANTS[:1])
    assert tcc.pending("aerospace", GRANTS) == [GRANTS[1]]
    assert tcc.state_file() == state / "devboost" / "tcc.json"


def test_fix_hint_names_app_setting_and_url() -> None:
    hint = tcc.fix_hint(GRANTS[:1])
    assert "AeroSpace" in hint and "Accessibility" in hint
    assert "Privacy_Accessibility" in hint
```

`tests/cli/test_permissions.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest

from devboost.core.osinfo import OsInfo
from devboost.core.plan import PlannedModule
from devboost.core.runner import run_plan
from devboost.exec.executor import FakeExecutor
from devboost.exec.primitives import tcc
from devboost.model import Ctx, Module, TccGrant

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")


class _NeedsA11y(Module):
    name: ClassVar[str] = "needs-a11y"
    tcc: ClassVar[tuple[TccGrant, ...]] = (TccGrant("Accessibility", "Tiler"),)

    def verify(self, ctx: Ctx) -> bool:
        return True

    def install(self, ctx: Ctx) -> None:  # pragma: no cover
        pass


@pytest.fixture(autouse=True)
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))


def _status(os: OsInfo) -> tuple[str, str]:
    r = run_plan([PlannedModule("needs-a11y")], {"needs-a11y": _NeedsA11y},
                 Ctx(os=os, ex=FakeExecutor()))[0]
    return r.status, r.detail


def test_unconfirmed_grant_blocks_on_macos() -> None:
    status, detail = _status(MAC)
    assert status == "blocked"
    assert "Privacy_Accessibility" in detail


def test_confirmed_grant_passes() -> None:
    tcc.confirm("needs-a11y", _NeedsA11y.tcc)
    assert _status(MAC) == ("skip", "already-installed")


def test_tcc_ignored_off_macos() -> None:
    assert _status(FEDORA) == ("skip", "already-installed")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/primitives/test_tcc.py tests/cli/test_permissions.py -v`
Expected: FAIL — `ImportError: cannot import name 'TccGrant'`.

- [ ] **Step 3: Implement**

`model.py` — add `Literal` to the `typing` import, then after `Script`:

```python
#: System Settings → Privacy & Security anchor ids. ListenEvent = "Input Monitoring",
#: ScreenCapture = "Screen Recording".
TccService = Literal["Accessibility", "ListenEvent", "Microphone", "ScreenCapture"]


@dataclass(frozen=True)
class TccGrant:
    """A macOS privacy permission an app needs; only the user can grant it."""

    service: TccService
    app: str
```

and in `Module` after `provided_by`:

```python
    #: macOS privacy permissions this module's app needs (scripts cannot grant them;
    #: the runner reports them as `blocked` with a one-click fix until confirmed).
    tcc: ClassVar[tuple[TccGrant, ...]] = ()
```

`exec/primitives/tcc.py`:

```python
"""macOS privacy permissions (TCC): deep links + a record of what the user confirmed.

macOS offers no supported way for a script to grant or reliably read these grants, so
dev-boost opens the exact System Settings pane and remembers the user's confirmation.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path

from devboost.model import TccGrant, TccService

_LABELS: dict[str, str] = {
    "Accessibility": "Accessibility",
    "ListenEvent": "Input Monitoring",
    "Microphone": "Microphone",
    "ScreenCapture": "Screen Recording",
}


def label(service: TccService) -> str:
    return _LABELS[service]


def settings_url(service: TccService) -> str:
    return f"x-apple.systempreferences:com.apple.preference.security?Privacy_{service}"


def state_file() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path(os.environ["HOME"]) / ".local" / "state")
    return Path(base) / "devboost" / "tcc.json"


def _key(module: str, g: TccGrant) -> str:
    return f"{module}:{g.service}:{g.app}"


def _load() -> set[str]:
    try:
        return set(json.loads(state_file().read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return set()


def pending(module: str, grants: Sequence[TccGrant]) -> list[TccGrant]:
    done = _load()
    return [g for g in grants if _key(module, g) not in done]


def confirm(module: str, grants: Sequence[TccGrant]) -> None:
    done = _load() | {_key(module, g) for g in grants}
    path = state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(done), indent=2) + "\n", encoding="utf-8")


def fix_hint(grants: Sequence[TccGrant]) -> str:
    return "; ".join(
        f"allow {g.app} in {label(g.service)}: open '{settings_url(g.service)}'"
        for g in grants
    )
```

`core/runner.py` — add import `from devboost.exec.primitives import tcc`, a helper, and use it on the two success paths:

```python
def _tcc_gate(pm: PlannedModule, mod: Module, ctx: Ctx, ok: RunResult) -> RunResult:
    """On macOS, a module is only done once the user has granted its app's permissions."""
    if ctx.os.family != "macos" or not type(mod).tcc:
        return ok
    missing = tcc.pending(pm.name, type(mod).tcc)
    if not missing:
        return ok
    hint = tcc.fix_hint(missing)
    log.warn(
        f"{pm.name}: needs permissions — {hint}; "
        f"then `devboost permissions --confirm {pm.name}`"
    )
    return RunResult(pm.name, "blocked", f"needs-user: grant permissions → {hint}")
```

In `_run_one`: replace `return RunResult(pm.name, "skip", "already-installed")` with
`return _tcc_gate(pm, mod, ctx, RunResult(pm.name, "skip", "already-installed"))` and replace the post-install `return RunResult(pm.name, "ok")` with `return _tcc_gate(pm, mod, ctx, RunResult(pm.name, "ok"))`.

`cli/permissions.py`:

```python
"""`devboost permissions` — walk the user through macOS privacy grants."""

from __future__ import annotations

import sys
from typing import Annotated

import typer

from devboost.core import log, osinfo
from devboost.core.registry import load
from devboost.exec.executor import RealExecutor
from devboost.exec.primitives import tcc
from devboost.model import Ctx


def permissions(
    confirm: Annotated[
        str | None, typer.Option("--confirm", help="record that MODULE's grants are done")
    ] = None,
) -> None:
    """List (and open) the macOS privacy permissions installed apps still need."""
    ctx = Ctx(os=osinfo.detect(), ex=RealExecutor())
    if ctx.os.family != "macos":
        log.info("permissions: nothing to do (macOS only)")
        return
    modules = load()
    if confirm is not None:
        if confirm not in modules or not modules[confirm].tcc:
            raise typer.BadParameter(f"{confirm!r} has no privacy permissions to confirm")
        tcc.confirm(confirm, modules[confirm].tcc)
        log.ok(f"permissions: recorded {confirm}")
        return
    todo = {
        name: tcc.pending(name, cls.tcc)
        for name, cls in sorted(modules.items())
        if cls.tcc and cls().verify(ctx)
    }
    todo = {n: g for n, g in todo.items() if g}
    if not todo:
        log.ok("permissions: all granted")
        return
    for name, grants in todo.items():
        for g in grants:
            log.warn(f"{name}: allow {g.app} in {tcc.label(g.service)}")
            ctx.ex.run(["open", tcc.settings_url(g.service)])
        if sys.stdin.isatty() and typer.confirm(f"Granted everything for {name}?", default=False):
            tcc.confirm(name, grants)
```

`cli/app.py` — import `from devboost.cli.permissions import permissions as _permissions` and register next to `installer`: `app.command(name="permissions")(_permissions)`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -v tests/primitives/test_tcc.py tests/cli/test_permissions.py tests/core && uv run mypy && uv run ruff check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/model.py src/devboost/exec/primitives/tcc.py src/devboost/core/runner.py src/devboost/cli/permissions.py src/devboost/cli/app.py tests/primitives/test_tcc.py tests/cli/test_permissions.py
git commit -m "feat(macos): TCC privacy-permission grants — blocked until confirmed; devboost permissions"
```

---

### Task 8: macOS invocation rules — root guard, Linux-only commands, sudo keepalive, keep-awake, default profile

**Files:**
- Create: `engine/src/devboost/cli/host.py`
- Modify: `engine/src/devboost/cli/app.py`, `profiles.toml` (repo root)
- Test: `engine/tests/cli/test_host.py` (create); `engine/tests/modules/test_omarchy.py` (add default-profile assertion)

**Interfaces:**
- Produces (in `devboost.cli.host`):
  - `LINUX_ONLY: frozenset[str] = frozenset({"installer", "accounts", "brain"})`
  - `invocation_error(os_info: OsInfo, subcommand: str | None, euid: int) -> str | None`
  - `class SudoKeepalive` — context manager; `__init__(self, run: Callable[[list[str]], int] = <subprocess>, interval: float = 60.0)`; on enter runs `["sudo", "-v"]` once, then `["sudo", "-n", "-v"]` every `interval` seconds on a daemon thread until exit.
  - `keep_awake(popen: Callable[[list[str]], object] = subprocess.Popen) -> object | None` — starts `["caffeinate", "-dimsu", "-w", str(os.getpid())]` (it exits by itself when devboost exits).
  - `mac_session(os_info, *, dry_run: bool)` — context manager combining both; no-op off macOS or when `dry_run`.
  - `app.default_profile(OsInfo("macos",...)) == "macos"`.

- [ ] **Step 1: Write the failing tests** — `tests/cli/test_host.py`

```python
from __future__ import annotations

import time

from devboost.cli import host as plat
from devboost.cli.app import default_profile
from devboost.core.osinfo import OsInfo

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")


def test_root_is_refused_on_macos_only() -> None:
    assert plat.invocation_error(MAC, "install", euid=0) is not None
    assert "Homebrew" in (plat.invocation_error(MAC, "install", euid=0) or "")
    assert plat.invocation_error(FEDORA, "install", euid=0) is None


def test_linux_only_commands_refused_on_macos() -> None:
    for cmd in ("installer", "accounts", "brain"):
        msg = plat.invocation_error(MAC, cmd, euid=501)
        assert msg is not None and "Linux-only" in msg
    assert plat.invocation_error(MAC, "install", euid=501) is None
    assert plat.invocation_error(FEDORA, "installer", euid=1000) is None


def test_sudo_keepalive_validates_then_refreshes() -> None:
    seen: list[list[str]] = []
    with plat.SudoKeepalive(run=lambda argv: seen.append(argv) or 0, interval=0.01):
        time.sleep(0.05)
    assert seen[0] == ["sudo", "-v"]
    assert ["sudo", "-n", "-v"] in seen[1:]
    count = len(seen)
    time.sleep(0.03)
    assert len(seen) == count  # thread stopped on exit


def test_keep_awake_waits_on_our_pid() -> None:
    started: list[list[str]] = []
    plat.keep_awake(popen=lambda argv: started.append(argv))
    assert started[0][:3] == ["caffeinate", "-dimsu", "-w"]


def test_mac_session_is_noop_off_macos_and_in_dry_run() -> None:
    with plat.mac_session(FEDORA, dry_run=False):
        pass
    with plat.mac_session(MAC, dry_run=True):
        pass


def test_default_profile_on_macos() -> None:
    assert default_profile(MAC) == "macos"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cli/test_host.py -v`
Expected: FAIL — `ImportError: cannot import name 'host'` from `devboost.cli`.

- [ ] **Step 3: Implement**

`cli/host.py`:

```python
"""macOS invocation rules: who may run devboost, which commands exist, and the session.

Kept out of the Typer wiring so each rule is a plain, testable function.
"""

from __future__ import annotations

import os
import subprocess
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from types import TracebackType

from devboost.core import log
from devboost.core.osinfo import OsInfo

LINUX_ONLY: frozenset[str] = frozenset({"installer", "accounts", "brain"})


def invocation_error(os_info: OsInfo, subcommand: str | None, euid: int) -> str | None:
    """Why this invocation must not proceed on this OS, or None."""
    if os_info.family != "macos":
        return None
    if euid == 0:
        return (
            "don't run devboost as root on macOS — Homebrew refuses to run as root. "
            "Run it as your user; dev-boost asks for sudo itself when a step needs it."
        )
    if subcommand in LINUX_ONLY:
        return f"`devboost {subcommand}` is Linux-only"
    return None


def _run_quiet(argv: list[str]) -> int:
    return subprocess.run(argv, check=False).returncode


class SudoKeepalive:
    """Ask for the sudo password once, then keep the timestamp fresh until exit.

    The same approach the Homebrew installer uses: the user types their password at the
    start and can walk away instead of being prompted again mid-run.
    """

    def __init__(self, run: Callable[[list[str]], int] = _run_quiet, interval: float = 60.0):
        self._run = run
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> SudoKeepalive:
        if self._run(["sudo", "-v"]) != 0:
            log.warn("sudo not granted — steps that need it will ask again or fail")
            return self
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            self._run(["sudo", "-n", "-v"])

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)


def keep_awake(popen: Callable[[list[str]], object] = subprocess.Popen) -> object | None:
    """Stop the Mac sleeping mid-install; caffeinate exits on its own when we do."""
    try:
        return popen(["caffeinate", "-dimsu", "-w", str(os.getpid())])
    except OSError:
        log.warn("caffeinate unavailable — the Mac may sleep during a long install")
        return None


@contextmanager
def mac_session(os_info: OsInfo, *, dry_run: bool) -> Iterator[None]:
    """Keep-awake + one sudo prompt for a real install run on macOS; no-op otherwise."""
    if os_info.family != "macos" or dry_run:
        yield
        return
    keep_awake()
    with SudoKeepalive():
        yield
```

`cli/app.py`:
- `_DEFAULT_PROFILE = {"omarchy": "omarchy", "macos": "macos"}` and update the comment above it to mention macOS.
- import `import os` and `from devboost.cli import host as plat`.
- in `main_callback`, before `_maybe_warn_update()` block:

```python
    problem = plat.invocation_error(osinfo.detect(), ctx.invoked_subcommand, os.geteuid())
    if problem is not None:
        log.error(problem)
        raise typer.Exit(code=2)
```

- in `_run`, wrap the refresh + run:

```python
    with plat.mac_session(ctx.os, dry_run=dry_run):
        if offline:
            plan = _apply_offline_filter(plan, modules)
        elif not dry_run:
            pkg.refresh_index(ctx)
        results = run_plan(plan, modules, ctx)
```

`profiles.toml` — add after the `omarchy` entry:

```toml
# macOS workstation default (`devboost install` on a Mac). M1 seeds it with the
# portable `terminal` set; M3 expands it to the full Mac workstation (spec §2 Profiles).
macos = ["terminal"]
```

`tests/conftest.py::profiles_file` — add the line `'macos = ["ripgrep"]\n'` (the fixture must declare every profile referenced anywhere).

`tests/conftest.py` (root, so it also covers `tests/core/test_selfupdate.py`, `tests/media/test_cli_installer.py` and `tests/modules/test_omarchy.py`, which drive the CLI too) — code under test calls `osinfo.detect()` with no arguments; on a Mac that now means macOS rules (Linux-only commands refused, `macos` default profile). Pin such calls to a Linux host; calls that name the OS explicitly (`system=...`, as the osinfo tests do) still reach the real function. Add:

```python
from typing import Any

from devboost.core import osinfo

_REAL_DETECT = osinfo.detect


@pytest.fixture(autouse=True)
def _linux_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests are host-independent: an argument-less detect() sees Fedora on any machine."""

    def _pinned(*args: Any, **kwargs: Any) -> osinfo.OsInfo:
        if "system" in kwargs:
            return _REAL_DETECT(*args, **kwargs)
        return osinfo.OsInfo("fedora", "fedora", "x86_64", headless=False)

    monkeypatch.setattr(osinfo, "detect", _pinned)
```

A test that needs macOS monkeypatches `osinfo.detect` itself.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -v tests/cli tests/modules/test_omarchy.py && uv run mypy && uv run ruff check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/cli/host.py src/devboost/cli/app.py tests/cli/test_host.py tests/conftest.py ../profiles.toml
git commit -m "feat(cli): macOS root guard, Linux-only commands, one sudo prompt, keep-awake, macos default profile"
```

---

### Task 9: Credentials on macOS — gh-first, no plaintext, keychain age key, one token source

**Files:**
- Modify: `engine/src/devboost/modules/_credentials.py`, `engine/src/devboost/modules/secrets.py`, `engine/src/devboost/modules/ssh_setup.py`, `engine/src/devboost/modules/apps.py` (`ObsidianSync.install`), `engine/src/devboost/cli/app.py`
- Create: `engine/src/devboost/cli/secrets_cmd.py`
- Test: `engine/tests/modules/test_secrets_macos.py` (create)

**Interfaces:**
- Consumes: `NeedsUser` (Task 3).
- Produces:
  - `secrets.KEYCHAIN_SERVICE = "devboost-age"`, `secrets.KEYCHAIN_ACCOUNT = "devboost"`.
  - `secrets.age_key(ctx) -> contextmanager[Path | None]` — yields the key file path: explicit file/env if it exists; else on macOS the keychain item written to a 0600 temp file (deleted on exit); else None.
  - `_credentials.github_credentials(ctx) -> Credentials | None` — bundle (via `age_key`) → authenticated gh (`from_gh`) → `~/.git-credentials` line → None.
  - macOS `Secrets.install`: never writes `~/.git-credentials`; gh source → `gh auth setup-git`; bundle/manual source → `credential.helper osxkeychain` + `git credential approve`.
  - `devboost secrets import-key PATH` stores an age key in the macOS keychain (via `security -i` on stdin, so the key never appears in argv).

- [ ] **Step 1: Write the failing tests** — `tests/modules/test_secrets_macos.py`

```python
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules import _credentials as creds
from devboost.modules import secrets
from devboost.modules.secrets import Secrets

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
_JSON = json.dumps({"GIT_USER": "alice", "GIT_EMAIL": "a@x", "GITHUB_PAT": "ghp_x"})
_GH_USER = json.dumps({"login": "alice", "email": "a@x"})


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")
    monkeypatch.setenv("DEVBOOST_BOOTSTRAP_DIR", str(tmp_path / "boot"))
    monkeypatch.delenv("DEVBOOST_SECRETS", raising=False)
    monkeypatch.delenv("DEVBOOST_SECRETS_KEY", raising=False)
    return tmp_path


class _GhEx(FakeExecutor):
    """gh authenticated as alice; no bundle."""

    def run(self, argv: Sequence[str], *, sudo: bool = False, stdin: str | None = None, env: Mapping[str, str] | None = None, cwd: Path | None = None, interactive: bool = False) -> Result:
        super().run(argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive)
        if list(argv[:3]) == ["gh", "api", "user"]:
            return Result(0, stdout=_GH_USER)
        if list(argv[:3]) == ["gh", "auth", "token"]:
            return Result(0, stdout="gho_tok\n")
        return Result(0)


def test_macos_gh_source_uses_gh_setup_git_and_no_plaintext(home: Path) -> None:
    ex = _GhEx(present={"gh"})
    Secrets().install(Ctx(os=MAC, ex=ex))
    assert ["gh", "auth", "setup-git"] in ex.calls
    assert ["git", "config", "--global", "credential.helper", "store"] not in ex.calls
    assert not (home / ".git-credentials").exists()


def test_macos_bundle_source_uses_osxkeychain(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    boot = home / "boot"
    boot.mkdir()
    (boot / "secrets.age").write_text("cipher", encoding="utf-8")
    (boot / "age-key.txt").write_text("AGE-SECRET-KEY-1X", encoding="utf-8")
    stdins: list[str | None] = []

    class _Ex(FakeExecutor):
        def run(self, argv: Sequence[str], *, sudo: bool = False, stdin: str | None = None, env: Mapping[str, str] | None = None, cwd: Path | None = None, interactive: bool = False) -> Result:
            super().run(argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive)
            stdins.append(stdin)
            return Result(0, stdout=_JSON) if argv[0] == "age" else Result(0)

    ex = _Ex(present={"age"})
    Secrets().install(Ctx(os=MAC, ex=ex))
    assert ["git", "config", "--global", "credential.helper", "osxkeychain"] in ex.calls
    i = ex.calls.index(["git", "credential", "approve"])
    assert stdins[i] == "protocol=https\nhost=github.com\nusername=alice\npassword=ghp_x\n\n"
    assert not (home / ".git-credentials").exists()


def test_linux_still_writes_git_credentials(home: Path) -> None:
    ex = _GhEx(present={"gh"})
    Secrets().install(Ctx(os=FEDORA, ex=ex))
    assert (home / ".git-credentials").read_text(encoding="utf-8").strip() == (
        "https://alice:gho_tok@github.com"
    )


def test_age_key_from_keychain_is_a_temp_0600_file_removed_after(home: Path) -> None:
    ex = FakeExecutor(scripts={"security": Result(0, stdout="AGE-SECRET-KEY-1Z\n")})
    with secrets.age_key(Ctx(os=MAC, ex=ex)) as key:
        assert key is not None
        assert key.read_text(encoding="utf-8").strip() == "AGE-SECRET-KEY-1Z"
        assert (key.stat().st_mode & 0o777) == 0o600
        kept = key
    assert not kept.exists()
    assert ["security", "find-generic-password", "-a", "devboost", "-s", "devboost-age", "-w"] in ex.calls


def test_age_key_none_when_nothing_available(home: Path) -> None:
    ex = FakeExecutor(scripts={"security": Result(44)})
    with secrets.age_key(Ctx(os=MAC, ex=ex)) as key:
        assert key is None


def test_github_credentials_order_gh_then_git_credentials(home: Path) -> None:
    assert creds.github_credentials(Ctx(os=MAC, ex=_GhEx(present={"gh"}))) == {
        "GIT_USER": "alice", "GIT_EMAIL": "a@x", "GITHUB_PAT": "gho_tok",
    }
    (home / ".git-credentials").write_text("https://bob:ghp_b@github.com\n", encoding="utf-8")
    no_gh = Ctx(os=FEDORA, ex=FakeExecutor())
    assert creds.github_credentials(no_gh) == {
        "GIT_USER": "bob", "GIT_EMAIL": "", "GITHUB_PAT": "ghp_b",
    }


def test_github_credentials_none(home: Path) -> None:
    assert creds.github_credentials(Ctx(os=FEDORA, ex=FakeExecutor())) is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_secrets_macos.py -v`
Expected: FAIL — `AttributeError: module 'devboost.modules.secrets' has no attribute 'age_key'`.

- [ ] **Step 3: Implement**

`secrets.py` — add imports `import tempfile`, `from collections.abc import Iterator`, `from contextlib import contextmanager`; add:

```python
KEYCHAIN_SERVICE = "devboost-age"
KEYCHAIN_ACCOUNT = "devboost"


@contextmanager
def age_key(ctx: Ctx) -> Iterator[Path | None]:
    """The age identity file to decrypt with, wherever it lives.

    A key file (env override or bootstrap dir) wins; off macOS the configured path is
    always returned. On macOS the key may instead live in the login keychain
    (`devboost secrets import-key`); it is then materialized as a 0600 temp file only for
    the duration of the decrypt, and None means "no key anywhere".
    """
    explicit = key_path()
    if explicit.exists() or ctx.os.family != "macos":
        # Off macOS this is exactly the old behaviour: the configured path, and `age`
        # itself reports a missing key.
        yield explicit
        return
    res = ctx.ex.run([
        "security", "find-generic-password",
        "-a", KEYCHAIN_ACCOUNT, "-s", KEYCHAIN_SERVICE, "-w",
    ])
    if not res.ok or not res.stdout.strip():
        yield None
        return
    fd, name = tempfile.mkstemp(prefix="devboost-age-")
    path = Path(name)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, (res.stdout.strip() + "\n").encode("utf-8"))
        os.close(fd)
        yield path
    finally:
        path.unlink(missing_ok=True)
```

and make `_resolve` also report where the credentials came from. Full replacement:

```python
    def _resolve(self, ctx: Ctx) -> tuple[dict[str, str], str]:
        """Credentials plus their source: "bundle", "gh" or "manual"."""
        if bundle_path().exists():
            if not ctx.ex.which("age"):
                pkg.install(ctx, "age")
            with age_key(ctx) as key:
                if key is None:
                    raise SecretsError(
                        "secrets bundle present but no age key (file, env, or keychain)"
                    )
                data = age.decrypt(ctx, bundle_path(), key)
            for field in age.REQUIRED_FIELDS:
                if not data.get(field):
                    raise SecretsError(f"missing required field {field}")
            return data, "bundle"

        from_gh = creds_src.from_gh(ctx) if creds_src.gh_is_authenticated(ctx) else None

        if creds_src.is_interactive():
            chosen = creds_src.resolve_interactively(ctx, existing=from_gh)
            if chosen:
                # "use-gh" returns the gh dict itself; "gh" signs in fresh via gh too.
                gh_token = ctx.ex.run(["gh", "auth", "token"]).stdout.strip()
                came_from_gh = chosen is from_gh or chosen["GITHUB_PAT"] == gh_token
                return chosen, "gh" if came_from_gh else "manual"
        elif from_gh:
            log.ok(f"secrets: using the authenticated GitHub CLI ({from_gh['GIT_USER']})")
            return from_gh, "gh"

        raise SecretsError(creds_src.NO_CREDENTIALS_HELP)
```

Replace `install` with:

```python
    def install(self, ctx: Ctx) -> None:
        data, source = self._resolve(ctx)
        ctx.ex.run(["git", "config", "--global", "user.name", data["GIT_USER"]])
        ctx.ex.run(["git", "config", "--global", "user.email", data["GIT_EMAIL"]])
        if ctx.os.family == "macos":
            self._install_macos(ctx, data, source)
            return
        ctx.ex.run(["git", "config", "--global", "credential.helper", "store"])
        ...  # existing ~/.git-credentials writing block, unchanged

    def _install_macos(self, ctx: Ctx, data: dict[str, str], source: str) -> None:
        """No plaintext token on disk: gh's helper, or the macOS keychain."""
        if source == "gh":
            ctx.ex.run(["gh", "auth", "setup-git"])
            return
        ctx.ex.run(["git", "config", "--global", "credential.helper", "osxkeychain"])
        ctx.ex.run(
            ["git", "credential", "approve"],
            stdin=(
                "protocol=https\nhost=github.com\n"
                f"username={data['GIT_USER']}\npassword={data['GITHUB_PAT']}\n\n"
            ),
        )
```

In `verify`, before the final `return`, add a macOS clause:

```python
        if ctx.os.family == "macos":
            helper = ctx.ex.run(["git", "config", "--global", "credential.helper"])
            if helper.ok and helper.stdout.strip() == "osxkeychain":
                return True
```

`_credentials.py` — add at the end of section 2:

```python
def _from_git_credentials() -> Credentials | None:
    path = Path(os.environ["HOME"]) / ".git-credentials"
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.endswith("@github.com") and line.startswith("https://") and ":" in line[8:]:
            user, _, rest = line[len("https://"):].partition(":")
            token = rest.rsplit("@", 1)[0]
            return {"GIT_USER": user, "GIT_EMAIL": "", "GITHUB_PAT": token}
    return None


def github_credentials(ctx: Ctx) -> Credentials | None:
    """The one place modules get a GitHub token: bundle → gh → ~/.git-credentials."""
    from devboost.exec.primitives import age
    from devboost.modules.secrets import age_key, bundle_path

    if bundle_path().exists():
        with age_key(ctx) as key:
            if key is not None:
                try:
                    return age.decrypt(ctx, bundle_path(), key)
                except Exception:  # noqa: BLE001 — fall through to the next source
                    log.warn("secrets bundle present but unreadable; trying gh")
    if gh_is_authenticated(ctx):
        found = from_gh(ctx)
        if found:
            return found
    return _from_git_credentials()
```

(add `from pathlib import Path` to imports.)

`ssh_setup.py` — replace `data = age.decrypt(ctx, bundle_path(), key_path())` with:

```python
        data = creds_src.github_credentials(ctx)
        if data is None:
            log.warn("ssh-setup: no GitHub credentials (bundle or gh) — key not uploaded yet")
            return  # non-blocking; retried next run
```

(import `from devboost.modules import _credentials as creds_src`; drop now-unused `age`, `bundle_path`, `key_path` imports.)

`apps.py::ObsidianSync.install` — replace `creds = age.decrypt(ctx, bundle_path(), key_path())` with:

```python
        creds = creds_src.github_credentials(ctx)
        if creds is None:
            log.warn("obsidian-sync: no GitHub credentials (bundle or gh) — skipping (non-blocking)")
            return
```

(same import; drop unused imports.)

`cli/secrets_cmd.py`:

```python
"""`devboost secrets` — manage bootstrap-secret material on this machine."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Annotated

import typer

from devboost.core import log, osinfo
from devboost.exec.executor import RealExecutor
from devboost.modules.secrets import KEYCHAIN_ACCOUNT, KEYCHAIN_SERVICE

app = typer.Typer(help="bootstrap secrets (age key)", no_args_is_help=True)


@app.command("import-key")
def import_key(
    path: Annotated[Path, typer.Argument(help="age identity file (AGE-SECRET-KEY-…)")],
) -> None:
    """Store an age key in the macOS login keychain (then the file can be deleted)."""
    if osinfo.detect().family != "macos":
        raise typer.BadParameter("import-key is macOS-only; on Linux keep the key file")
    key = path.read_text(encoding="utf-8").strip()
    if not key.startswith("AGE-SECRET-KEY-"):
        raise typer.BadParameter(f"{path} does not look like an age secret key")
    # `security -i` reads the command from stdin, so the key never appears in argv / ps.
    cmd = (
        f"add-generic-password -U -a {KEYCHAIN_ACCOUNT} -s {KEYCHAIN_SERVICE} "
        f"-w {shlex.quote(key)}\n"
    )
    if not RealExecutor().run(["security", "-i"], stdin=cmd).ok:
        log.error("could not write the key to the keychain")
        raise typer.Exit(code=1)
    log.ok(f"age key stored in the login keychain ({KEYCHAIN_SERVICE}); you may delete {path}")
```

`cli/app.py` — `from devboost.cli import secrets_cmd as _secrets_cmd` and `app.add_typer(_secrets_cmd.app, name="secrets")`.

- [ ] **Step 4: Run to verify pass (Linux secrets tests unchanged)**

Run: `uv run pytest -v tests/modules/test_secrets_macos.py tests/modules/test_secrets_ssh.py tests/modules/test_credentials.py tests/modules/test_apps.py && uv run mypy && uv run ruff check`
Expected: PASS. If an existing test asserted `age.decrypt` being called from `ssh_setup`/`obsidian-sync`, update it to assert the equivalent via `github_credentials` (same bundle fixture still works — the bundle is the first source).

- [ ] **Step 5: Commit**

```bash
git add src/devboost/modules/_credentials.py src/devboost/modules/secrets.py src/devboost/modules/ssh_setup.py src/devboost/modules/apps.py src/devboost/cli/secrets_cmd.py src/devboost/cli/app.py tests/modules
git commit -m "feat(secrets): macOS gh-first/keychain credentials, keychain age key, single GitHub token source"
```

---

### Task 10: `doctor` on macOS

**Files:**
- Modify: `engine/src/devboost/cli/doctor.py`
- Test: `engine/tests/cli/test_doctor_macos.py` (create)

**Interfaces:**
- Consumes: `secrets.age_key` (Task 9), `tcc` + `Module.tcc` (Task 7), `registry.load`.
- Produces: `run_checks(ctx, root)` on macOS checks deps `curl`, `brew`, `xcode-select` (not `age`), probes `https://formulae.brew.sh/`, reads the secrets state through `age_key`, and adds an informational `permissions` check listing unconfirmed grants of installed modules. Linux output unchanged.

- [ ] **Step 1: Write the failing tests** — `tests/cli/test_doctor_macos.py`

```python
from __future__ import annotations

from pathlib import Path

import pytest

from devboost.cli.doctor import run_checks
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")


@pytest.fixture(autouse=True)
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("DEVBOOST_BOOTSTRAP_DIR", str(tmp_path / "boot"))


def _names(ctx: Ctx, root: Path) -> dict[str, bool]:
    return {c.name: c.ok for c in run_checks(ctx, root)}


def test_macos_deps_and_probe(tmp_path: Path) -> None:
    ex = FakeExecutor(present={"curl", "brew", "xcode-select"},
                      scripts={"security": Result(44)})
    names = _names(Ctx(os=MAC, ex=ex), tmp_path)
    assert names["dep:brew"] and names["dep:xcode-select"]
    assert "dep:age" not in names
    probe = [c for c in ex.calls if c[0] == "curl"][0]
    assert probe[-1] == "https://formulae.brew.sh/"
    assert "permissions" in names


def test_linux_keeps_fedora_probe_and_age_dep(tmp_path: Path) -> None:
    ex = FakeExecutor(present={"curl", "age"})
    names = _names(Ctx(os=FEDORA, ex=ex), tmp_path)
    assert "dep:age" in names and "permissions" not in names
    probe = [c for c in ex.calls if c[0] == "curl"][0]
    assert probe[-1] == "https://fedoraproject.org/"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cli/test_doctor_macos.py -v`
Expected: FAIL — `KeyError: 'dep:brew'`.

- [ ] **Step 3: Implement** in `cli/doctor.py`

```python
_REQUIRED_DEPS = ("curl", "age")
_REQUIRED_DEPS_MACOS = ("curl", "brew", "xcode-select")

_PROBE_URL = "https://fedoraproject.org/"
_PROBE_URL_MACOS = "https://formulae.brew.sh/"
```

In `run_checks`:
- `deps = _REQUIRED_DEPS_MACOS if ctx.os.family == "macos" else _REQUIRED_DEPS` and loop over `deps`.
- `probe = _PROBE_URL_MACOS if ctx.os.family == "macos" else _PROBE_URL` and use `probe` in the curl argv and the detail string.
- replace `state = age.doctor_state(ctx, bundle_path(), key_path())` with:

```python
    with age_key(ctx) as key:
        state = (
            age.doctor_state(ctx, bundle_path(), key)
            if key is not None
            else ("missing" if not bundle_path().exists() else "cannot-decrypt")
        )
```

(import `age_key` from `devboost.modules.secrets`; drop `key_path` import.)
- before `return checks`, add:

```python
    if ctx.os.family == "macos":
        checks.append(_permissions_check(ctx))
```

and the helper:

```python
def _permissions_check(ctx: Ctx) -> Check:
    """Informational: privacy grants the user still has to give (see `devboost permissions`)."""
    from devboost.core.registry import load
    from devboost.exec.primitives import tcc

    missing = [
        f"{name}: {g.app} → {tcc.label(g.service)}"
        for name, cls in sorted(load().items())
        if cls.tcc and cls().verify(ctx)
        for g in tcc.pending(name, cls.tcc)
    ]
    detail = "; ".join(missing) + " — run `devboost permissions`" if missing else "all granted"
    return Check("permissions", True, detail)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/cli -v && uv run mypy && uv run ruff check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/cli/doctor.py tests/cli/test_doctor_macos.py
git commit -m "feat(doctor): macOS deps, brew probe, keychain age key, permissions listing"
```

---

### Task 11: Catalog contract test (with a shrinking known-gaps list)

**Files:**
- Modify: `engine/src/devboost/model.py` (`Module.portable`)
- Create: `engine/tests/core/test_macos_contract.py`

**Interfaces:**
- Produces: `Module.portable: ClassVar[bool] = False` — set to `True` (in M3+) on a custom module verified to work unchanged on macOS. The test fails if a module becomes unresolvable (new gap) **or** if a listed gap gets fixed without being removed from `KNOWN_GAPS`.

- [ ] **Step 1: Add the field** — in `model.py::Module` after `tcc`:

```python
    #: True when a custom-install module is verified to work unchanged on macOS (no
    #: per_os.macos needed). Read by the macOS catalog contract test.
    portable: ClassVar[bool] = False
```

- [ ] **Step 2: Write the test** — `tests/core/test_macos_contract.py`

```python
"""Every module must have a macOS answer: installable, dropped, provided, or a known gap.

KNOWN_GAPS is the M1 baseline of modules with no macOS path yet. M3–M5 add macOS
strategies and delete names from it; it must be empty by the end of M5 (spec §9).
"""

from __future__ import annotations

from devboost.core.registry import load
from devboost.model import Module
from devboost.modules._pkgmodule import PackageModule
from devboost.modules.apps import FlatpakApp

KNOWN_GAPS: frozenset[str] = frozenset({
    # Paste the exact output of Step 3 here, one quoted name per line.
})


def resolvable_on_macos(cls: type[Module]) -> bool:
    if cls.families and "macos" not in cls.families:
        return True  # dropped from the plan on macOS
    if "macos" in cls.provided_by:
        return True
    if cls.per_os.macos is not None:
        return True
    if issubclass(cls, PackageModule):
        # Only the base behaviour is brew-aware; a subclass that overrides install/verify
        # (COPR, curl installers, …) needs its own macOS answer.
        return cls.install is PackageModule.install and cls.verify is PackageModule.verify
    if issubclass(cls, FlatpakApp):
        return cls.cask is not None
    return cls.portable


def unresolved() -> set[str]:
    return {name for name, cls in load().items() if not resolvable_on_macos(cls)}


def test_no_new_macos_gaps() -> None:
    new = unresolved() - KNOWN_GAPS
    assert not new, f"modules with no macOS path (add per_os.macos / families / cask): {sorted(new)}"


def test_known_gaps_are_still_gaps() -> None:
    fixed = KNOWN_GAPS - unresolved()
    assert not fixed, f"now resolvable — remove from KNOWN_GAPS: {sorted(fixed)}"
```

- [ ] **Step 3: Generate the baseline and paste it**

Run:

```bash
uv run python -c "import sys; sys.path.insert(0,'tests'); from core.test_macos_contract import unresolved; print('\n'.join(f'    \"{n}\",' for n in sorted(unresolved())))"
```

Paste the printed lines into `KNOWN_GAPS`. Sanity-check the list: it must **not** contain simple `PackageModule`s (e.g. `jq`, `bat`); it **must** contain the `PackageModule`s that override `install`/`verify` (`eza`, `atuin`, `lazygit`, `lazydocker`, `dust`, `sd`, `yq`, `fastfetch`, `gh`, `tealdeer`) or Linux-only modules that already declare `families` (e.g. `rpmfusion`, `dnf-tune`); it **should** contain custom modules such as `herdr`, `docker`, `ghostty`, `nerd-fonts`, `vscode`, `obsidian`/other `FlatpakApp`s (no `cask` yet), `aspire-gc`. If it looks wrong, fix `resolvable_on_macos`, not the list.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/core/test_macos_contract.py -v && uv run mypy`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/devboost/model.py tests/core/test_macos_contract.py
git commit -m "test(macos): catalog contract test with M1 known-gaps baseline"
```

---

### Task 12: Constitution v3.1.0, docs, spec sync, final gate

**Files:**
- Modify: `.specify/memory/constitution.md`, `docs/architecture.md`, `docs/adding-a-module.md`, `docs/credentials.md`, `docs/superpowers/specs/2026-09-18-macos-support-design.md`, `CHANGELOG.md`

- [ ] **Step 1: Constitution** (`.specify/memory/constitution.md`)
  - Principle VI heading → `### VI. Cross-OS via Data (Fedora is the reference Linux; macOS is a first-class family)`; add sentence to its body: "macOS (Apple Silicon) is a first-class family resolved through the same `OsMap` precedence (`macos=` entries); it is not a Linux derivative and never borrows Linux strategies."
  - The same heading text in the principles list near line 25.
  - Frozen-binary bullet: "(PyInstaller onefile, x86_64 + aarch64)" → "(PyInstaller onefile: Linux x86_64 + aarch64, macOS darwin-arm64)".
  - Footer: `**Version**: 3.1.0 | **Ratified**: 2026-06-19 | **Last Amended**: 2026-09-19`.
  - Prepend a SYNC IMPACT REPORT block: `v3.0.1 → v3.1.0 (MINOR): Principle VI extended — macOS first-class family; frozen-binary constraint adds darwin-arm64.`

- [ ] **Step 2: `docs/architecture.md`** — in "OS dispatch" replace the first sentence with: "The package manager is selected once from `ctx.os`: `Dnf` (Fedora), `Apt` (Debian/Ubuntu), `Pacman` (Arch/Omarchy), `Brew` (macOS — formulae, casks with `--adopt`, taps; never sudo)." Add to the primitives list: `launchd` (LaunchAgents/Daemons), `tcc` (macOS privacy grants). Add a paragraph "User-only steps": "`NeedsUser(reason, how_to_fix)` is reported `blocked` with the fix and never fails the run; `PresentUnmanaged` (an app installed outside dev-boost) is a `skip`. Modules declare macOS privacy needs as `tcc = (TccGrant(...),)`; the runner blocks them until `devboost permissions --confirm <module>`."

- [ ] **Step 3: `docs/adding-a-module.md`** — add a "macOS" section:

```markdown
## macOS

- Simple tools: `PackageModule` works as-is; set `brew_pkg` when the formula name differs
  from the module name (e.g. `delta` → `git-delta`), or `brew_cask` for app-only tools.
- GUI apps: set `cask` on your `FlatpakApp` subclass.
- Custom install logic: declare `per_os = OsMap(macos=YourMacStrategy())`, or
  `families = ("fedora", "debian", "arch")` if the module cannot exist on a Mac, or
  `provided_by = ("macos",)` if macOS already covers it, or `portable = True` once you have
  verified it runs unchanged.
- Background jobs: use `launchd.user_agent(...)` (label `launchd.label("<name>")`).
- Privacy permissions: `tcc = (TccGrant("Accessibility", "AppName"),)`.
- `tests/core/test_macos_contract.py` fails if you add a module with no macOS answer.
```

- [ ] **Step 4: `docs/credentials.md`** — add a "macOS" section: gh-first (`gh auth setup-git`), bundle/manual tokens go to the keychain via `credential.helper osxkeychain` (never `~/.git-credentials`), `devboost secrets import-key <file>` stores the age key in the login keychain, and modules obtain tokens only through `_credentials.github_credentials()` (bundle → gh → `~/.git-credentials`).

- [ ] **Step 5: Spec sync** — in `docs/superpowers/specs/2026-09-18-macos-support-design.md` §1 CLI, replace the two bullets with:

```markdown
- **Sudo once:** at the start of every non-dry-run install on macOS, `sudo -v` once, then
  refreshed (`sudo -n -v`) every 60 s on a background thread until exit.
- **No sleep:** a background `caffeinate -dimsu -w <devboost pid>` for the run's lifetime.
```

and in the §11 table add to M1: "`devboost permissions`, `devboost secrets import-key`".

- [ ] **Step 6: CHANGELOG** — under `## Unreleased` add: "macOS engine core (M1): macOS family + arm64 normalization, Homebrew manager (formulae/casks/taps), launchd primitive, NeedsUser/PresentUnmanaged, macOS privacy-permission tracking (`devboost permissions`), macOS invocation rules (no root, one sudo prompt, keep-awake), gh-first/keychain credentials (`devboost secrets import-key`), macOS doctor, catalog contract test. Constitution v3.1.0."

- [ ] **Step 7: Full gate (from `engine/`)**

Run: `uv run ruff check && uv run mypy && uv run pytest`
Expected: all green, including every pre-existing Linux test.

- [ ] **Step 8: Smoke on this Mac (from `engine/`)**

Run:

```bash
uv run devboost doctor
uv run devboost install --dry-run
uv run devboost list macos
uv run devboost installer --help; echo "exit=$?"
```

Expected: doctor shows `dep:brew` and a `permissions` line; `install --dry-run` resolves the `macos` profile (currently the `terminal` set) with `would install …` lines and no traceback; `installer` prints "`devboost installer` is Linux-only" with exit 2.

- [ ] **Step 9: Commit**

```bash
cd .. && git add .specify/memory/constitution.md docs CHANGELOG.md
git commit -m "docs: constitution v3.1.0 (macOS first-class), architecture/modules/credentials for macOS M1"
```
