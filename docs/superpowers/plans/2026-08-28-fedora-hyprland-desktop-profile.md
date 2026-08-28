# Fedora Hyprland Desktop Profile — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in `hyprland` desktop profile (Wayland tiling) to the dev-boost engine as a curated side session that coexists with GNOME, themed by a single base16 palette through the existing chezmoi dotfiles path.

**Architecture:** A new `engine/src/devboost/modules/hyprland.py` holds 16 `@register`ed modules (mostly trivial `PackageModule`s) following the existing `verify()`/`install()` + `ctx.os.family` OS-dispatch pattern. Hyprland core comes from `copr:eddievs/hyprland`; peripherals from official Fedora repos. All themeable config ships as chezmoi templates under `dotfiles/` (rendered by the existing `Dotfiles` module from a single `.chezmoidata/palette.toml`); GPU- and monitor-specific config lives in a chezmoi-ignored `~/.config/hypr/local.d/*.conf` glob written per-machine. GNOME stays the default `full` desktop and fallback; GDM (base Workstation) offers the session at login.

**Tech Stack:** Python 3.12 (typed, `mypy --strict`), pytest with `FakeExecutor`, ruff; Hyprland + waybar + fuzzel + mako + hyprlock/hypridle/hyprpaper/hyprpolkitagent; chezmoi templating; matugen (opt-in).

## Global Constraints

- **Merge gates (verbatim):** `uv run mypy` (whole tree, incl. tests) + `uv run ruff check` + `uv run pytest` must all pass; tests run at 80 columns. Run from `engine/`.
- **Module contract:** every module is `@register`-decorated, subclasses `Module` or `PackageModule` (from `devboost.modules._pkgmodule`), sets `name`/`category`/`description`/`profiles`, and implements `verify(ctx)`/`install(ctx)` unless it is a plain `PackageModule`.
- **OS dispatch:** branch on `ctx.os.family` (`"fedora"` / `"debian"`); this delivery targets Fedora, but keep the debian path from raising where trivial.
- **COPR source is a single constant:** `_HYPR_COPR = "eddievs/hyprland"` defined once at the top of `hyprland.py`; every COPR module references it. Mirrored in `catalog.toml` with a re-verify note. (solopasha/hyprland is rawhide-only — do NOT use it for F44.)
- **`self_updating = False`** on every module that installs from `_HYPR_COPR` (compositor + companions + portal). Official-repo `PackageModule`s keep the default `True`.
- **chezmoi is the sole writer of `~/.config`** for themed files. The ONLY exception is the machine-local `~/.config/hypr/local.d/*.conf` glob, written by modules and listed in `.chezmoiignore`.
- **No profile name may equal a module name** (registry rule): profile `hyprland` vs modules `hyprland-*`; profile `hyprland-theme` vs module `hyprland-theme-bundle`.
- **Primitives to use (exact signatures):**
  - `pkg.install(ctx, *names: str) -> None` → fedora emits `["sudo","dnf","install","-y",*names]`
  - `pkg.installed(ctx, name: str) -> bool` → fedora runs `["rpm","-q",name]`, true iff `.ok`
  - `copr.enable(ctx, repo: str) -> None` → emits `["sudo","dnf","copr","enable","-y",repo]`
  - `gpu.detect(ctx) -> Gpus` with bool fields `.intel/.amd/.nvidia/.any`
  - `fs.exists(ctx, path: str) -> bool`; `fs.write(ctx, path, content, *, sudo=False)` (text only)
  - `resource_path(*parts) -> Path` (repo root in source; `_MEIPASS` when frozen)
- **Test harness:** `FakeExecutor()` records argv (sudo-prefixed) in `.calls`; `scripts={cmd: Result(code,stdout)}` stubs the first argv token; `present={cmd}` drives `which`. Import `Result`/`FakeExecutor` from `devboost.exec.executor`, `Ctx` from `devboost.model`, `OsInfo` from `devboost.core.osinfo`. Fedora ctx: `Ctx(os=OsInfo("fedora","fedora","x86_64"), ex=FakeExecutor())`.

---

## File Structure

**Engine (Python):**
- Create `engine/src/devboost/modules/hyprland.py` — all 16 modules.
- Create `engine/tests/modules/test_hyprland.py` — fake-Executor unit tests.
- Create `engine/tests/dotfiles/test_hyprland_theme_templates.py` — the config-parse/palette-coverage smoke gate.
- Modify `profiles.toml` — add `hyprland`, `hyprland-theme`, `hyprland-matugen`.
- Modify `engine/tests/conftest.py` — add the three new profiles to `profiles_file`.
- Modify `catalog.toml` — add the `[hyprland]` COPR pin (tooling entry).

**chezmoi dotfiles source (`dotfiles/`), rendered by the existing `Dotfiles` module:**
- Create `dotfiles/.chezmoidata/palette.toml` — the base16 palette (`[palette]` table).
- Create `dotfiles/.chezmoiignore` addition — ignore `.config/hypr/local.d/**`.
- Create `dotfiles/dot_config/hypr/hyprland.conf` — static: keybinds, rules, `exec-once`, `monitor` default, `source` lines.
- Create `dotfiles/dot_config/hypr/colors.conf.tmpl`, `hyprlock.conf.tmpl` — palette-driven.
- Create `dotfiles/dot_config/hypr/hypridle.conf`, `hyprpaper.conf`, `env.conf` — static.
- Create `dotfiles/dot_config/waybar/config`, `style.css.tmpl`; `fuzzel/fuzzel.ini.tmpl`; `mako/config.tmpl`; `btop/themes/devboost.theme.tmpl`; `xdg-desktop-portal/hyprland-portals.conf`.
- Modify `dotfiles/dot_config/wezterm/…` — add a palette-driven colors template (unified palette).
- Create `dotfiles/dot_local/share/backgrounds/devboost-default.png` — bundled wallpaper (binary, chezmoi-copied).

> **Wallpaper note:** shipped through the chezmoi source (not `data/`) because `fs.write` is text-only and chezmoi copies binary files losslessly — keeping a single owner for `~/.local/share/backgrounds`.

---

## Task 1: Profiles, catalog pin, and test fixture

**Files:**
- Modify: `profiles.toml`
- Modify: `catalog.toml`
- Modify: `engine/tests/conftest.py:60-95` (the `profiles_file` fixture)
- Test: `engine/tests/modules/test_hyprland.py` (new)

**Interfaces:**
- Produces: the three profile names `hyprland`, `hyprland-theme`, `hyprland-matugen` used by every module's `profiles=` in later tasks.

- [ ] **Step 1: Write the failing test** — assert the profiles are declared.

Create `engine/tests/modules/test_hyprland.py`:

```python
from __future__ import annotations

import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_profiles_declare_hyprland_trio() -> None:
    data = tomllib.loads((_REPO_ROOT / "profiles.toml").read_text(encoding="utf-8"))
    profiles = data["profiles"]
    assert set(profiles["hyprland"]) >= {
        "hyprland-core", "hyprland-portal", "hyprland-bar", "hyprland-launcher",
        "hyprland-notify", "hyprland-lock", "hyprland-idle", "hyprland-wallpaper",
        "hyprland-polkit", "hyprland-shot", "hyprland-tray", "hyprland-gtk",
        "hyprland-session", "hyprland-env",
    }
    assert profiles["hyprland-theme"] == ["hyprland-theme-bundle"]
    assert profiles["hyprland-matugen"] == ["hyprland-matugen"]


def test_full_profile_stays_gnome_not_hyprland() -> None:
    data = tomllib.loads((_REPO_ROOT / "profiles.toml").read_text(encoding="utf-8"))
    assert "hyprland" not in data["profiles"]["full"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/modules/test_hyprland.py -v`
Expected: FAIL with `KeyError: 'hyprland'`.

- [ ] **Step 3: Add the profiles to `profiles.toml`**

Add these three keys inside `[profiles]` (leave `full` unchanged):

```toml
hyprland = ["hyprland-core","hyprland-portal","hyprland-bar","hyprland-launcher",
            "hyprland-notify","hyprland-lock","hyprland-idle","hyprland-wallpaper",
            "hyprland-polkit","hyprland-shot","hyprland-tray","hyprland-gtk",
            "hyprland-session","hyprland-env"]
hyprland-theme   = ["hyprland-theme-bundle"]
hyprland-matugen = ["hyprland-matugen"]
```

- [ ] **Step 4: Add the COPR pin to `catalog.toml`**

Append (tooling entry — excluded from OS-catalog validation, like `[ventoy]`):

```toml
[hyprland]
# Hyprland core is NOT in Fedora 44 official repos, and solopasha/hyprland is
# rawhide-only. eddievs/hyprland builds F44 x86_64 + aarch64. Re-verify chroots
# before each release: https://copr.fedorainfracloud.org/coprs/eddievs/hyprland/
# Fallback of equal coverage: eli-xciv/hyprland.
copr = "eddievs/hyprland"
```

- [ ] **Step 5: Add the profiles to the test fixture**

In `engine/tests/conftest.py`, inside the `profiles_file` fixture's written TOML, add these lines (any members that resolve to a registered module are fine; load-time validation only checks that each module's declared profile exists as a key):

```python
        'hyprland = ["hyprland-core"]\n'
        'hyprland-theme = ["hyprland-theme-bundle"]\n'
        'hyprland-matugen = ["hyprland-matugen"]\n'
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd engine && uv run pytest tests/modules/test_hyprland.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add profiles.toml catalog.toml engine/tests/conftest.py engine/tests/modules/test_hyprland.py
git commit -m "feat(hyprland): declare hyprland profiles + eddievs COPR pin"
```

---

## Task 2: Module file + `hyprland-core`

**Files:**
- Create: `engine/src/devboost/modules/hyprland.py`
- Test: `engine/tests/modules/test_hyprland.py`

**Interfaces:**
- Produces: `_HYPR_COPR: str`; class `HyprlandCore` (module name `"hyprland-core"`, `copr_repo=_HYPR_COPR`, `self_updating=False`, `cmd="Hyprland"`). Later COPR modules reuse `_HYPR_COPR`.

- [ ] **Step 1: Write the failing test**

Append to `engine/tests/modules/test_hyprland.py`:

```python
import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx

FEDORA = OsInfo("fedora", "fedora", "x86_64")
UBUNTU = OsInfo(distro="ubuntu", family="debian", arch="x86_64")


def _fedora_ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_hyprland_core_installs_from_eddievs_copr_on_fedora() -> None:
    from devboost.modules.hyprland import HyprlandCore, _HYPR_COPR

    assert _HYPR_COPR == "eddievs/hyprland"
    ctx = _fedora_ctx()
    HyprlandCore().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "dnf", "copr", "enable", "-y", "eddievs/hyprland"] in calls
    assert ["sudo", "dnf", "install", "-y", "hyprland"] in calls


def test_hyprland_core_never_self_updates_and_is_gui() -> None:
    from devboost.modules.hyprland import HyprlandCore

    assert HyprlandCore.self_updating is False
    assert HyprlandCore.gui is True


def test_hyprland_core_verify_uses_which() -> None:
    from devboost.modules.hyprland import HyprlandCore

    ctx = _fedora_ctx(present={"Hyprland"})
    assert HyprlandCore().verify(ctx) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/modules/test_hyprland.py -k core -v`
Expected: FAIL with `ModuleNotFoundError: devboost.modules.hyprland`.

- [ ] **Step 3: Create `hyprland.py` with the header + `HyprlandCore`**

```python
"""hyprland profile — opt-in Wayland tiling side session (coexists with GNOME).

Core + hypr* companions come from the eddievs/hyprland COPR (Hyprland is not in
Fedora 44 official repos; solopasha/hyprland is rawhide-only). Peripherals
(waybar/fuzzel/mako/grim/slurp/...) are official Fedora packages. Themeable config
ships as chezmoi templates applied by the `dotfiles` module.
"""

from __future__ import annotations

from devboost.core.registry import register
from devboost.exec.primitives import gpu, pkg
from devboost.exec.primitives import fs
from devboost.model import Ctx, Module
from devboost.modules._pkgmodule import PackageModule

#: Single source of truth for the Hyprland COPR (mirrored in catalog.toml [hyprland]).
_HYPR_COPR = "eddievs/hyprland"

#: Machine-local hyprland config dir (chezmoi-ignored); sourced via glob by hyprland.conf.
_LOCAL_D = "~/.config/hypr/local.d"


@register
class HyprlandCore(PackageModule):
    name = "hyprland-core"
    category = "hyprland"
    description = "Hyprland Wayland compositor (from eddievs/hyprland COPR on Fedora)."
    gui = True
    profiles = ("hyprland",)
    cmd = "Hyprland"
    fedora_pkg = "hyprland"
    debian_pkg = "hyprland"
    copr_repo = _HYPR_COPR
    self_updating = False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd engine && uv run pytest tests/modules/test_hyprland.py -k core -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/modules/hyprland.py engine/tests/modules/test_hyprland.py
git commit -m "feat(hyprland): hyprland-core module from eddievs COPR"
```

---

## Task 3: Trivial PackageModules (bar, launcher, notify, lock, idle, polkit)

**Files:**
- Modify: `engine/src/devboost/modules/hyprland.py`
- Test: `engine/tests/modules/test_hyprland.py`

**Interfaces:**
- Consumes: `_HYPR_COPR`, `PackageModule`.
- Produces: `HyprlandBar`/`HyprlandLauncher`/`HyprlandNotify` (official), `HyprlandLock`/`HyprlandIdle`/`HyprlandPolkit` (COPR, `self_updating=False`).

- [ ] **Step 1: Write the failing test**

Append to the test file:

```python
def test_official_peripherals_no_copr() -> None:
    from devboost.modules.hyprland import (
        HyprlandBar, HyprlandLauncher, HyprlandNotify,
    )

    for cls, pkg_name, cmd in [
        (HyprlandBar, "waybar", "waybar"),
        (HyprlandLauncher, "fuzzel", "fuzzel"),
        (HyprlandNotify, "mako", "mako"),
    ]:
        ctx = _fedora_ctx()
        cls().install(ctx)
        calls = ctx.ex.calls  # type: ignore[attr-defined]
        assert ["sudo", "dnf", "install", "-y", pkg_name] in calls
        assert not any("copr" in c for c in calls)
        assert cls.self_updating is True
        assert cls.cmd == cmd


def test_copr_companions_enable_copr_and_pin() -> None:
    from devboost.modules.hyprland import (
        HyprlandIdle, HyprlandLock, HyprlandPolkit,
    )

    for cls, pkg_name in [
        (HyprlandLock, "hyprlock"),
        (HyprlandIdle, "hypridle"),
        (HyprlandPolkit, "hyprpolkitagent"),
    ]:
        ctx = _fedora_ctx()
        cls().install(ctx)
        calls = ctx.ex.calls  # type: ignore[attr-defined]
        assert ["sudo", "dnf", "copr", "enable", "-y", "eddievs/hyprland"] in calls
        assert ["sudo", "dnf", "install", "-y", pkg_name] in calls
        assert cls.self_updating is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/modules/test_hyprland.py -k "peripherals or companions" -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Add the six modules to `hyprland.py`**

```python
@register
class HyprlandBar(PackageModule):
    name = "hyprland-bar"
    category = "hyprland"
    description = "Waybar status bar."
    gui = True
    profiles = ("hyprland",)
    cmd = "waybar"
    fedora_pkg = "waybar"
    debian_pkg = "waybar"


@register
class HyprlandLauncher(PackageModule):
    name = "hyprland-launcher"
    category = "hyprland"
    description = "Fuzzel application launcher."
    gui = True
    profiles = ("hyprland",)
    cmd = "fuzzel"
    fedora_pkg = "fuzzel"
    debian_pkg = "fuzzel"


@register
class HyprlandNotify(PackageModule):
    name = "hyprland-notify"
    category = "hyprland"
    description = "Mako notification daemon."
    gui = True
    profiles = ("hyprland",)
    cmd = "mako"
    fedora_pkg = "mako"
    debian_pkg = "mako-notifier"


@register
class HyprlandLock(PackageModule):
    name = "hyprland-lock"
    category = "hyprland"
    description = "hyprlock screen locker (eddievs COPR)."
    gui = True
    profiles = ("hyprland",)
    cmd = "hyprlock"
    fedora_pkg = "hyprlock"
    debian_pkg = "hyprlock"
    copr_repo = _HYPR_COPR
    self_updating = False


@register
class HyprlandIdle(PackageModule):
    name = "hyprland-idle"
    category = "hyprland"
    description = "hypridle idle daemon (eddievs COPR)."
    gui = True
    profiles = ("hyprland",)
    cmd = "hypridle"
    fedora_pkg = "hypridle"
    debian_pkg = "hypridle"
    copr_repo = _HYPR_COPR
    self_updating = False


@register
class HyprlandPolkit(PackageModule):
    name = "hyprland-polkit"
    category = "hyprland"
    description = "hyprpolkitagent authentication agent (eddievs COPR)."
    gui = True
    profiles = ("hyprland",)
    cmd = "hyprpolkitagent"
    fedora_pkg = "hyprpolkitagent"
    debian_pkg = "hyprpolkitagent"
    copr_repo = _HYPR_COPR
    self_updating = False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd engine && uv run pytest tests/modules/test_hyprland.py -k "peripherals or companions" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/modules/hyprland.py engine/tests/modules/test_hyprland.py
git commit -m "feat(hyprland): bar/launcher/notify + lock/idle/polkit modules"
```

---

## Task 4: `hyprland-portal` (screen-share backend + portals.conf)

**Files:**
- Modify: `engine/src/devboost/modules/hyprland.py`
- Test: `engine/tests/modules/test_hyprland.py`

**Interfaces:**
- Consumes: `_HYPR_COPR`, `pkg`, `fs`, `Module`, `HyprlandCore`.
- Produces: `HyprlandPortal` (installs `xdg-desktop-portal-hyprland` + `xdg-desktop-portal-gtk`; `verify` = both packages present AND rendered `~/.config/xdg-desktop-portal/hyprland-portals.conf` exists).

- [ ] **Step 1: Write the failing test**

```python
def test_portal_installs_backends_and_enables_copr() -> None:
    from devboost.modules.hyprland import HyprlandPortal

    ctx = _fedora_ctx()
    HyprlandPortal().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "dnf", "copr", "enable", "-y", "eddievs/hyprland"] in calls
    assert [
        "sudo", "dnf", "install", "-y",
        "xdg-desktop-portal-hyprland", "xdg-desktop-portal-gtk",
    ] in calls
    assert HyprlandPortal.self_updating is False
    assert HyprlandPortal in ()  or HyprlandPortal.requires  # requires HyprlandCore


def test_portal_verify_requires_pkgs_and_portals_conf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from devboost.modules import hyprland as H

    ctx = _fedora_ctx(scripts={"rpm": Result(0)})  # rpm -q -> installed
    monkeypatch.setattr(H.fs, "exists", lambda ctx, path: "hyprland-portals.conf" in path)
    assert H.HyprlandPortal().verify(ctx) is True

    ctx2 = _fedora_ctx(scripts={"rpm": Result(0)})
    monkeypatch.setattr(H.fs, "exists", lambda ctx, path: False)
    assert H.HyprlandPortal().verify(ctx2) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/modules/test_hyprland.py -k portal -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Add `HyprlandPortal`**

```python
@register
class HyprlandPortal(Module):
    name = "hyprland-portal"
    category = "hyprland"
    description = "xdg-desktop-portal-hyprland — deterministic screen-share/screenshot."
    gui = True
    requires = (HyprlandCore,)
    profiles = ("hyprland",)
    self_updating = False

    def verify(self, ctx: Ctx) -> bool:
        return (
            pkg.installed(ctx, "xdg-desktop-portal-hyprland")
            and fs.exists(ctx, "~/.config/xdg-desktop-portal/hyprland-portals.conf")
        )

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "fedora":
            from devboost.exec.primitives import copr

            copr.enable(ctx, _HYPR_COPR)
        pkg.install(ctx, "xdg-desktop-portal-hyprland", "xdg-desktop-portal-gtk")
        # The hyprland-portals.conf itself ships via the chezmoi dotfiles source
        # (Task 9) and is applied by the `dotfiles` module; verify() gates on it.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd engine && uv run pytest tests/modules/test_hyprland.py -k portal -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/modules/hyprland.py engine/tests/modules/test_hyprland.py
git commit -m "feat(hyprland): xdg-desktop-portal-hyprland module"
```

---

## Task 5: `hyprland-shot`, `hyprland-tray`, `hyprland-gtk`

**Files:**
- Modify: `engine/src/devboost/modules/hyprland.py`
- Test: `engine/tests/modules/test_hyprland.py`

**Interfaces:**
- Consumes: `pkg`, `Module`, `HyprlandCore`.
- Produces: `HyprlandShot` (grim+slurp), `HyprlandTray` (network-manager-applet+blueman), `HyprlandGtk` (adw-gtk3-theme+papirus-icon-theme, sets GTK/cursor via `gsettings`).

- [ ] **Step 1: Write the failing test**

```python
def test_shot_tray_install_official_multi_pkgs() -> None:
    from devboost.modules.hyprland import HyprlandShot, HyprlandTray

    ctx = _fedora_ctx()
    HyprlandShot().install(ctx)
    assert ["sudo", "dnf", "install", "-y", "grim", "slurp"] in ctx.ex.calls  # type: ignore[attr-defined]

    ctx2 = _fedora_ctx()
    HyprlandTray().install(ctx2)
    assert [
        "sudo", "dnf", "install", "-y", "network-manager-applet", "blueman",
    ] in ctx2.ex.calls  # type: ignore[attr-defined]


def test_gtk_installs_theme_and_sets_dark_gsettings() -> None:
    from devboost.modules.hyprland import HyprlandGtk

    ctx = _fedora_ctx()
    HyprlandGtk().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "dnf", "install", "-y", "adw-gtk3-theme", "papirus-icon-theme"] in calls
    assert [
        "gsettings", "set", "org.gnome.desktop.interface", "gtk-theme", "adw-gtk3-dark",
    ] in calls
    assert [
        "gsettings", "set", "org.gnome.desktop.interface", "color-scheme", "prefer-dark",
    ] in calls
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/modules/test_hyprland.py -k "shot_tray or gtk" -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Add the three modules**

```python
@register
class HyprlandShot(Module):
    name = "hyprland-shot"
    category = "hyprland"
    description = "grim + slurp screenshot tools."
    gui = True
    requires = (HyprlandCore,)
    profiles = ("hyprland",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("grim") and ctx.ex.which("slurp")

    def install(self, ctx: Ctx) -> None:
        pkg.install(ctx, "grim", "slurp")


@register
class HyprlandTray(Module):
    name = "hyprland-tray"
    category = "hyprland"
    description = "Network + Bluetooth tray applets (no GNOME control center in-session)."
    gui = True
    requires = (HyprlandCore,)
    profiles = ("hyprland",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("nm-applet") and ctx.ex.which("blueman-applet")

    def install(self, ctx: Ctx) -> None:
        pkg.install(ctx, "network-manager-applet", "blueman")


@register
class HyprlandGtk(Module):
    name = "hyprland-gtk"
    category = "hyprland"
    description = "Minimal GTK + cursor theming for a non-GNOME session (adw-gtk3 dark)."
    gui = True
    requires = (HyprlandCore,)
    profiles = ("hyprland",)

    def verify(self, ctx: Ctx) -> bool:
        return pkg.installed(ctx, "adw-gtk3-theme")

    def install(self, ctx: Ctx) -> None:
        theme_pkg = "adw-gtk3-theme" if ctx.os.family == "fedora" else "adw-gtk3"
        pkg.install(ctx, theme_pkg, "papirus-icon-theme")
        for key, value in (
            ("gtk-theme", "adw-gtk3-dark"),
            ("icon-theme", "Papirus-Dark"),
            ("color-scheme", "prefer-dark"),
        ):
            ctx.ex.run(["gsettings", "set", "org.gnome.desktop.interface", key, value])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd engine && uv run pytest tests/modules/test_hyprland.py -k "shot_tray or gtk" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/modules/hyprland.py engine/tests/modules/test_hyprland.py
git commit -m "feat(hyprland): screenshot, tray, and GTK/cursor theming modules"
```

---

## Task 6: `hyprland-wallpaper`

**Files:**
- Modify: `engine/src/devboost/modules/hyprland.py`
- Test: `engine/tests/modules/test_hyprland.py`

**Interfaces:**
- Consumes: `pkg`, `Module`, `HyprlandCore`.
- Produces: `HyprlandWallpaper` (installs `hyprpaper`; `verify` = `which("hyprpaper")`). The default wallpaper file + `hyprpaper.conf` ship via chezmoi (Task 9), so this module is a thin package install.

- [ ] **Step 1: Write the failing test**

```python
def test_wallpaper_installs_hyprpaper() -> None:
    from devboost.modules.hyprland import HyprlandWallpaper

    ctx = _fedora_ctx(present={"hyprpaper"})
    HyprlandWallpaper().install(ctx)
    assert ["sudo", "dnf", "install", "-y", "hyprpaper"] in ctx.ex.calls  # type: ignore[attr-defined]
    assert HyprlandWallpaper().verify(ctx) is True
    assert HyprlandWallpaper.self_updating is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/modules/test_hyprland.py -k wallpaper -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Add `HyprlandWallpaper`**

```python
@register
class HyprlandWallpaper(Module):
    name = "hyprland-wallpaper"
    category = "hyprland"
    description = "hyprpaper wallpaper daemon (default wallpaper ships via chezmoi)."
    gui = True
    requires = (HyprlandCore,)
    profiles = ("hyprland",)
    self_updating = False

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("hyprpaper")

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "fedora":
            from devboost.exec.primitives import copr

            copr.enable(ctx, _HYPR_COPR)
        pkg.install(ctx, "hyprpaper")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd engine && uv run pytest tests/modules/test_hyprland.py -k wallpaper -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/modules/hyprland.py engine/tests/modules/test_hyprland.py
git commit -m "feat(hyprland): hyprpaper wallpaper module"
```

---

## Task 7: `hyprland-session` (verify-only GDM gate)

**Files:**
- Modify: `engine/src/devboost/modules/hyprland.py`
- Test: `engine/tests/modules/test_hyprland.py`

**Interfaces:**
- Consumes: `fs`, `Module`, `HyprlandCore`.
- Produces: `HyprlandSession` (`verify` = the wayland-session `.desktop` exists; `install` = no-op — the `hyprland` package ships the file, GDM ships in base Workstation).

- [ ] **Step 1: Write the failing test**

```python
def test_session_verify_checks_wayland_session_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from devboost.modules import hyprland as H

    ctx = _fedora_ctx()
    monkeypatch.setattr(
        H.fs, "exists",
        lambda ctx, path: path == "/usr/share/wayland-sessions/hyprland.desktop",
    )
    assert H.HyprlandSession().verify(ctx) is True

    monkeypatch.setattr(H.fs, "exists", lambda ctx, path: False)
    assert H.HyprlandSession().verify(ctx) is False


def test_session_install_is_side_effect_free() -> None:
    from devboost.modules.hyprland import HyprlandSession

    ctx = _fedora_ctx()
    HyprlandSession().install(ctx)
    assert ctx.ex.calls == []  # type: ignore[attr-defined]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/modules/test_hyprland.py -k session -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Add `HyprlandSession`**

```python
@register
class HyprlandSession(Module):
    name = "hyprland-session"
    category = "hyprland"
    description = "Verify the Hyprland wayland session is selectable at GDM login."
    gui = True
    requires = (HyprlandCore,)
    profiles = ("hyprland",)

    def verify(self, ctx: Ctx) -> bool:
        # Shipped by the hyprland package; GDM (base Fedora Workstation) lists it.
        return fs.exists(ctx, "/usr/share/wayland-sessions/hyprland.desktop")

    def install(self, ctx: Ctx) -> None:
        # No action: the hyprland package provides the session file and GDM already
        # exists on Workstation. Present as an explicit verify gate with a clear
        # failure message if either is missing.
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd engine && uv run pytest tests/modules/test_hyprland.py -k session -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/modules/hyprland.py engine/tests/modules/test_hyprland.py
git commit -m "feat(hyprland): session verify-gate for GDM"
```

---

## Task 8: `hyprland-env` (base env static + GPU machine-local file)

**Files:**
- Modify: `engine/src/devboost/modules/hyprland.py`
- Test: `engine/tests/modules/test_hyprland.py`

**Interfaces:**
- Consumes: `gpu`, `fs`, `Module`, `HyprlandCore`, `_LOCAL_D`.
- Produces: `HyprlandEnv`. Base Wayland/Electron env ships via chezmoi (`env.conf`, Task 9). This module writes the NVIDIA env to `~/.config/hypr/local.d/env-gpu.conf` **only** when `gpu.detect(ctx).nvidia`; that dir is chezmoi-ignored and glob-`source`d by `hyprland.conf`.

- [ ] **Step 1: Write the failing test**

```python
def test_env_writes_nvidia_local_file_only_on_nvidia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from devboost.modules import hyprland as H

    written: dict[str, str] = {}
    monkeypatch.setattr(H.fs, "write", lambda ctx, path, content, **kw: written.__setitem__(path, content))

    # NVIDIA present -> lspci mentions NVIDIA
    ctx = _fedora_ctx(scripts={"lspci": Result(0, stdout="01:00.0 VGA compatible controller: NVIDIA Corp")})
    H.HyprlandEnv().install(ctx)
    assert any("env-gpu.conf" in p for p in written)
    body = next(v for p, v in written.items() if "env-gpu.conf" in p)
    assert "LIBVA_DRIVER_NAME,nvidia" in body

    # No NVIDIA -> no file written
    written.clear()
    ctx2 = _fedora_ctx(scripts={"lspci": Result(0, stdout="00:02.0 VGA compatible controller: Intel Corp")})
    H.HyprlandEnv().install(ctx2)
    assert not any("env-gpu.conf" in p for p in written)


def test_env_verify_true_when_not_nvidia(monkeypatch: pytest.MonkeyPatch) -> None:
    from devboost.modules import hyprland as H

    ctx = _fedora_ctx(scripts={"lspci": Result(0, stdout="Intel Corp VGA compatible controller")})
    monkeypatch.setattr(H.fs, "exists", lambda ctx, path: False)
    assert H.HyprlandEnv().verify(ctx) is True  # nothing required on non-nvidia
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/modules/test_hyprland.py -k env -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Add `HyprlandEnv`**

```python
_NVIDIA_ENV = """\
# devboost: written by hyprland-env only on NVIDIA GPUs (chezmoi-ignored local.d).
env = LIBVA_DRIVER_NAME,nvidia
env = __GLX_VENDOR_LIBRARY_NAME,nvidia
env = NVD_BACKEND,direct
"""


@register
class HyprlandEnv(Module):
    name = "hyprland-env"
    category = "hyprland"
    description = "Machine-local Hyprland env: NVIDIA vars when a NVIDIA GPU is detected."
    gui = True
    requires = (HyprlandCore,)
    profiles = ("hyprland",)

    def _gpu_file(self) -> str:
        return f"{_LOCAL_D}/env-gpu.conf"

    def verify(self, ctx: Ctx) -> bool:
        # Only NVIDIA machines need the extra file; others are always satisfied.
        if not gpu.detect(ctx).nvidia:
            return True
        return fs.exists(ctx, self._gpu_file())

    def install(self, ctx: Ctx) -> None:
        if gpu.detect(ctx).nvidia:
            fs.write(ctx, self._gpu_file(), _NVIDIA_ENV)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd engine && uv run pytest tests/modules/test_hyprland.py -k env -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/modules/hyprland.py engine/tests/modules/test_hyprland.py
git commit -m "feat(hyprland): GPU-aware machine-local env module"
```

---

## Task 9: chezmoi theming source (palette + templates + static configs)

**Files:**
- Create: `dotfiles/.chezmoidata/palette.toml`
- Modify: `dotfiles/.chezmoiignore`
- Create: `dotfiles/dot_config/hypr/hyprland.conf`, `colors.conf.tmpl`, `hyprlock.conf.tmpl`, `hypridle.conf`, `hyprpaper.conf`, `env.conf`
- Create: `dotfiles/dot_config/waybar/config`, `dotfiles/dot_config/waybar/style.css.tmpl`
- Create: `dotfiles/dot_config/fuzzel/fuzzel.ini.tmpl`, `dotfiles/dot_config/mako/config.tmpl`
- Create: `dotfiles/dot_config/btop/themes/devboost.theme.tmpl`
- Create: `dotfiles/dot_config/xdg-desktop-portal/hyprland-portals.conf`
- Create: `dotfiles/dot_config/wezterm/colors.lua.tmpl` (unified palette; wire into existing wezterm config)
- Create: `dotfiles/dot_local/share/backgrounds/devboost-default.png`

**Interfaces:**
- Produces: rendered `~/.config/hypr/colors.conf`, `hyprland-portals.conf`, etc. that later `verify()`s and the Task 12 smoke gate depend on. Palette keys: `base00..base0F`, `accent`, `bg`, `fg`.

- [ ] **Step 1: Create the palette data file** (`[palette]` table so templates use `{{ .palette.KEY }}` — a flat file would be `{{ .KEY }}`).

`dotfiles/.chezmoidata/palette.toml`:

```toml
# base16 palette (default: a dark scheme). Change these to retint the whole desktop.
[palette]
base00 = "#1e1e2e"  # background
base01 = "#181825"
base02 = "#313244"
base03 = "#45475a"
base04 = "#585b70"
base05 = "#cdd6f4"  # default foreground
base06 = "#f5e0dc"
base07 = "#b4befe"
base08 = "#f38ba8"  # red
base09 = "#fab387"  # orange
base0A = "#f9e2af"  # yellow
base0B = "#a6e3a1"  # green
base0C = "#94e2d5"  # cyan
base0D = "#89b4fa"  # blue (accent)
base0E = "#cba6f7"  # magenta
base0F = "#eba0ac"
accent = "#89b4fa"
bg     = "#1e1e2e"
fg     = "#cdd6f4"
```

- [ ] **Step 2: Ignore the machine-local dir** — append to `dotfiles/.chezmoiignore`:

```
.config/hypr/local.d/**
```

- [ ] **Step 3: Write the static `hyprland.conf`** (`dotfiles/dot_config/hypr/hyprland.conf`):

```ini
# devboost Hyprland config (static). Themeable colors + machine-local files are sourced.
monitor = ,preferred,auto,1

source = ~/.config/hypr/colors.conf
source = ~/.config/hypr/env.conf
source = ~/.config/hypr/local.d/*.conf   # env-gpu.conf (module), monitors.conf (user)

exec-once = waybar
exec-once = mako
exec-once = hyprpaper
exec-once = hypridle
exec-once = systemctl --user start hyprpolkitagent
exec-once = nm-applet --indicator
exec-once = blueman-applet

$mod = SUPER
bind = $mod, RETURN, exec, wezterm
bind = $mod, SPACE, exec, fuzzel
bind = $mod, Q, killactive,
bind = $mod, F, fullscreen,
bind = $mod, V, togglefloating,
bind = $mod, H, movefocus, l
bind = $mod, L, movefocus, r
bind = $mod, K, movefocus, u
bind = $mod, J, movefocus, d
bind = $mod, ESCAPE, exec, hyprlock
bind = , Print, exec, grim -g "$(slurp)" - | wl-copy
bind = SHIFT, Print, exec, grim - | wl-copy
bind = $mod, 1, workspace, 1
bind = $mod, 2, workspace, 2
bind = $mod, 3, workspace, 3
bind = $mod, 4, workspace, 4
bind = $mod, 5, workspace, 5
bind = $mod SHIFT, 1, movetoworkspace, 1
bind = $mod SHIFT, 2, movetoworkspace, 2
bind = $mod SHIFT, 3, movetoworkspace, 3
bind = $mod SHIFT, 4, movetoworkspace, 4
bind = $mod SHIFT, 5, movetoworkspace, 5
```

- [ ] **Step 4: Write the palette-driven templates.** Each references `{{ .palette.* }}`.

`dotfiles/dot_config/hypr/colors.conf.tmpl`:

```ini
general {
    col.active_border = rgb({{ .palette.accent | replace "#" "" }})
    col.inactive_border = rgb({{ .palette.base02 | replace "#" "" }})
}
```

`dotfiles/dot_config/hypr/hyprlock.conf.tmpl`:

```ini
background { color = rgb({{ .palette.base00 | replace "#" "" }}) }
input-field {
    outer_color = rgb({{ .palette.accent | replace "#" "" }})
    inner_color = rgb({{ .palette.base01 | replace "#" "" }})
    font_color  = rgb({{ .palette.fg | replace "#" "" }})
}
```

`dotfiles/dot_config/waybar/style.css.tmpl`:

```css
* { font-family: "JetBrainsMono Nerd Font"; }
window#waybar { background: {{ .palette.bg }}; color: {{ .palette.fg }}; }
#workspaces button.active { color: {{ .palette.accent }}; }
```

`dotfiles/dot_config/fuzzel/fuzzel.ini.tmpl`:

```ini
[colors]
background={{ .palette.bg | replace "#" "" }}ee
text={{ .palette.fg | replace "#" "" }}ff
selection={{ .palette.accent | replace "#" "" }}ff
```

`dotfiles/dot_config/mako/config.tmpl`:

```ini
background-color={{ .palette.bg }}
text-color={{ .palette.fg }}
border-color={{ .palette.accent }}
```

`dotfiles/dot_config/btop/themes/devboost.theme.tmpl`:

```
theme[main_bg]="{{ .palette.bg }}"
theme[main_fg]="{{ .palette.fg }}"
theme[hi_fg]="{{ .palette.accent }}"
```

`dotfiles/dot_config/wezterm/colors.lua.tmpl` (unified palette — Q1; wire `require` into the existing wezterm config so both sessions share it):

```lua
-- devboost: palette-driven wezterm colors (shared across GNOME + Hyprland sessions).
return {
  foreground = "{{ .palette.fg }}",
  background = "{{ .palette.bg }}",
  ansi = {
    "{{ .palette.base01 }}", "{{ .palette.base08 }}", "{{ .palette.base0B }}",
    "{{ .palette.base0A }}", "{{ .palette.base0D }}", "{{ .palette.base0E }}",
    "{{ .palette.base0C }}", "{{ .palette.base05 }}",
  },
}
```

- [ ] **Step 5: Write the static configs** — `hypridle.conf`, `hyprpaper.conf`, `env.conf`, `hyprland-portals.conf`:

`dotfiles/dot_config/hypr/hypridle.conf`:

```ini
general { lock_cmd = pidof hyprlock || hyprlock; before_sleep_cmd = loginctl lock-session }
listener { timeout = 300; on-timeout = loginctl lock-session }
listener { timeout = 330; on-timeout = hyprctl dispatch dpms off; on-resume = hyprctl dispatch dpms on }
```

`dotfiles/dot_config/hypr/hyprpaper.conf`:

```ini
preload = ~/.local/share/backgrounds/devboost-default.png
wallpaper = ,~/.local/share/backgrounds/devboost-default.png
```

`dotfiles/dot_config/hypr/env.conf`:

```ini
# devboost: base Wayland/Electron env (static, session-wide). GPU-specific env is in
# ~/.config/hypr/local.d/env-gpu.conf (written by the hyprland-env module on NVIDIA).
env = ELECTRON_OZONE_PLATFORM_HINT,auto
env = MOZ_ENABLE_WAYLAND,1
env = XDG_CURRENT_DESKTOP,Hyprland
```

`dotfiles/dot_config/xdg-desktop-portal/hyprland-portals.conf`:

```ini
[preferred]
default = hyprland;gtk
org.freedesktop.impl.portal.ScreenCast = hyprland
org.freedesktop.impl.portal.Screenshot = hyprland
```

- [ ] **Step 6: Add the bundled wallpaper**

Place a license-clean PNG at `dotfiles/dot_local/share/backgrounds/devboost-default.png`
(≈1080p, dark, matching the palette). If none is ready, generate a solid-base00 placeholder:

Run: `cd /home/dev/repos/dev-boost && python3 -c "import struct,zlib;\
w=h=16;raw=b''.join(b'\x00'+b'\x1e\x1e\x2e'*w for _ in range(h));\
comp=zlib.compress(raw);\
chunk=lambda t,d:struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d));\
png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',comp)+chunk(b'IEND',b'');\
open('dotfiles/dot_local/share/backgrounds/devboost-default.png','wb').write(png)"`
Expected: a small valid PNG written (replace with real art before release).

- [ ] **Step 7: Commit**

```bash
git add dotfiles/
git commit -m "feat(hyprland): chezmoi theming source (base16 palette + templates)"
```

---

## Task 10: `hyprland-theme-bundle`

**Files:**
- Modify: `engine/src/devboost/modules/hyprland.py`
- Test: `engine/tests/modules/test_hyprland.py`

**Interfaces:**
- Consumes: `Module`, `fs`, and the `Dotfiles` module (`devboost.modules.shell.Dotfiles`).
- Produces: `HyprlandThemeBundle` — `requires=(Dotfiles,)` so the chezmoi source (palette + templates) is applied; `verify` = rendered `~/.config/hypr/colors.conf` exists; `install` = no-op (the required `dotfiles` module renders it).

- [ ] **Step 1: Write the failing test**

```python
def test_theme_bundle_requires_dotfiles_and_verifies_colors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from devboost.modules import hyprland as H
    from devboost.modules.shell import Dotfiles

    assert Dotfiles in H.HyprlandThemeBundle.requires
    assert H.HyprlandThemeBundle.profiles == ("hyprland-theme",)

    ctx = _fedora_ctx()
    monkeypatch.setattr(H.fs, "exists", lambda ctx, path: path.endswith("hypr/colors.conf"))
    assert H.HyprlandThemeBundle().verify(ctx) is True
    H.HyprlandThemeBundle().install(ctx)  # no-op; must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/modules/test_hyprland.py -k theme_bundle -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Add `HyprlandThemeBundle`** (add the import at the top of `hyprland.py`: `from devboost.modules.shell import Dotfiles`):

```python
@register
class HyprlandThemeBundle(Module):
    name = "hyprland-theme-bundle"
    category = "hyprland"
    description = "base16 palette + templates (applied via the dotfiles/chezmoi source)."
    gui = True
    requires = (Dotfiles,)
    profiles = ("hyprland-theme",)

    def verify(self, ctx: Ctx) -> bool:
        return fs.exists(ctx, "~/.config/hypr/colors.conf")

    def install(self, ctx: Ctx) -> None:
        # The required `dotfiles` module runs `chezmoi apply`, which renders the palette
        # templates. Nothing else to do here.
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd engine && uv run pytest tests/modules/test_hyprland.py -k theme_bundle -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/modules/hyprland.py engine/tests/modules/test_hyprland.py
git commit -m "feat(hyprland): theme-bundle module (palette via dotfiles)"
```

---

## Task 11: `hyprland-matugen` (opt-in wallpaper-driven retheme)

**Files:**
- Modify: `engine/src/devboost/modules/hyprland.py`
- Create: `dotfiles/dot_config/matugen/config.toml`
- Create: `dotfiles/dot_config/matugen/templates/palette.toml` (the single matugen template → base16)
- Create: `dotfiles/dot_local/bin/executable_devboost-hyprland-retheme`
- Test: `engine/tests/modules/test_hyprland.py`

**Interfaces:**
- Consumes: `pkg`, `Module`.
- Produces: `HyprlandMatugen` (installs `matugen`; `verify` = `which("matugen")`). The retheme flow (matugen → `.chezmoidata/palette.toml` in the chezmoi source → `chezmoi apply`) ships as a chezmoi-managed script; matugen's ONLY output target is the chezmoi source palette (never `~/.config`).

- [ ] **Step 1: Write the failing test**

```python
def test_matugen_installs_and_output_targets_chezmoi_source() -> None:
    from devboost.modules.hyprland import HyprlandMatugen

    ctx = _fedora_ctx(present={"matugen"})
    HyprlandMatugen().install(ctx)
    assert ["sudo", "dnf", "install", "-y", "matugen"] in ctx.ex.calls  # type: ignore[attr-defined]
    assert HyprlandMatugen().verify(ctx) is True


def test_matugen_config_writes_only_palette_not_home() -> None:
    import tomllib
    cfg = tomllib.loads(
        (_REPO_ROOT / "dotfiles/dot_config/matugen/config.toml").read_text("utf-8")
    )
    outputs = [t["output_path"] for t in cfg["templates"].values()]
    assert outputs == ["{{ .chezmoi_source }}/.chezmoidata/palette.toml".replace(
        "{{ .chezmoi_source }}", cfg.get("_source_marker", "")) or outputs[0]]
    # every output must land in the chezmoi source palette, never ~/.config
    assert all(".chezmoidata/palette.toml" in o for o in outputs)
    assert not any("/.config/" in o for o in outputs)
```

> Note: the second assertion is the ownership guard — matugen must never target `~/.config`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/modules/test_hyprland.py -k matugen -v`
Expected: FAIL (`ImportError` / missing file).

- [ ] **Step 3: Add `HyprlandMatugen`**

```python
@register
class HyprlandMatugen(Module):
    name = "hyprland-matugen"
    category = "hyprland"
    description = "Opt-in wallpaper-driven retheme (matugen -> chezmoi palette -> apply)."
    gui = True
    profiles = ("hyprland-matugen",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("matugen")

    def install(self, ctx: Ctx) -> None:
        pkg.install(ctx, "matugen")
```

- [ ] **Step 4: Create the matugen config + template + retheme script**

`dotfiles/dot_config/matugen/config.toml` (single template; output is the chezmoi source palette):

```toml
[config]

[templates.palette]
input_path = "~/.config/matugen/templates/palette.toml"
output_path = "~/.local/share/chezmoi/.chezmoidata/palette.toml"
```

`dotfiles/dot_config/matugen/templates/palette.toml` (Material-3 → base16 mapping; matugen controls the output text):

```toml
[palette]
base00 = "{{colors.surface.default.hex}}"
base01 = "{{colors.surface_container.default.hex}}"
base02 = "{{colors.surface_container_high.default.hex}}"
base03 = "{{colors.outline_variant.default.hex}}"
base04 = "{{colors.outline.default.hex}}"
base05 = "{{colors.on_surface.default.hex}}"
base06 = "{{colors.on_surface_variant.default.hex}}"
base07 = "{{colors.inverse_surface.default.hex}}"
base08 = "{{colors.error.default.hex}}"
base09 = "{{colors.tertiary.default.hex}}"
base0A = "{{colors.secondary.default.hex}}"
base0B = "{{colors.tertiary_container.default.hex}}"
base0C = "{{colors.secondary_container.default.hex}}"
base0D = "{{colors.primary.default.hex}}"
base0E = "{{colors.primary_container.default.hex}}"
base0F = "{{colors.error_container.default.hex}}"
accent = "{{colors.primary.default.hex}}"
bg     = "{{colors.surface.default.hex}}"
fg     = "{{colors.on_surface.default.hex}}"
```

`dotfiles/dot_local/bin/executable_devboost-hyprland-retheme`:

```bash
#!/usr/bin/env bash
# Regenerate the base16 palette from a wallpaper, then re-apply via chezmoi.
# Matugen writes ONLY the chezmoi source palette; chezmoi remains sole ~/.config owner.
set -euo pipefail
wallpaper="${1:?usage: devboost-hyprland-retheme <wallpaper-image>}"
matugen image "$wallpaper" -m dark
chezmoi apply --force
echo "retheme complete: palette regenerated from $wallpaper"
```

- [ ] **Step 5: Fix the ownership-guard test to match the config**

Replace the body of `test_matugen_config_writes_only_palette_not_home` with the exact assertion:

```python
def test_matugen_config_writes_only_palette_not_home() -> None:
    import tomllib
    cfg = tomllib.loads(
        (_REPO_ROOT / "dotfiles/dot_config/matugen/config.toml").read_text("utf-8")
    )
    outputs = [t["output_path"] for t in cfg["templates"].values()]
    assert outputs, "matugen must define at least one template"
    assert all(o.endswith(".chezmoidata/palette.toml") for o in outputs)
    assert not any("/.config/" in o for o in outputs)  # never write into ~/.config
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd engine && uv run pytest tests/modules/test_hyprland.py -k matugen -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add engine/src/devboost/modules/hyprland.py dotfiles/dot_config/matugen dotfiles/dot_local/bin
git commit -m "feat(hyprland): opt-in matugen retheme (contained to chezmoi palette)"
```

---

## Task 12: Config-parse smoke gate (palette-key coverage)

**Files:**
- Create: `engine/tests/dotfiles/test_hyprland_theme_templates.py`

**Interfaces:**
- Consumes: `dotfiles/.chezmoidata/palette.toml` and the `.tmpl` files from Task 9.
- Produces: an automatable gate that fails on a typo'd palette key or a missing `source` target — the most likely template regression (the live `hyprland --verify` stays in the manual VM checklist).

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import re
import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DOTFILES = _REPO_ROOT / "dotfiles"
_PALETTE_REF = re.compile(r"\{\{-?\s*\.palette\.([A-Za-z0-9_]+)")


def _palette_keys() -> set[str]:
    data = tomllib.loads((_DOTFILES / ".chezmoidata/palette.toml").read_text("utf-8"))
    return set(data["palette"])


def test_every_palette_reference_is_defined() -> None:
    keys = _palette_keys()
    missing: list[str] = []
    for tmpl in _DOTFILES.rglob("*.tmpl"):
        for ref in _PALETTE_REF.findall(tmpl.read_text("utf-8")):
            if ref not in keys:
                missing.append(f"{tmpl.relative_to(_DOTFILES)}: .palette.{ref}")
    assert not missing, f"undefined palette keys: {missing}"


def test_hyprland_conf_source_targets_exist() -> None:
    conf = (_DOTFILES / "dot_config/hypr/hyprland.conf").read_text("utf-8")
    # colors.conf comes from colors.conf.tmpl; env.conf is static; local.d is a glob.
    assert "source = ~/.config/hypr/colors.conf" in conf
    assert (_DOTFILES / "dot_config/hypr/colors.conf.tmpl").is_file()
    assert (_DOTFILES / "dot_config/hypr/env.conf").is_file()
    assert "local.d/*.conf" in conf


def test_portals_conf_routes_screencast_to_hyprland() -> None:
    conf = (_DOTFILES / "dot_config/xdg-desktop-portal/hyprland-portals.conf").read_text("utf-8")
    assert "org.freedesktop.impl.portal.ScreenCast = hyprland" in conf
```

- [ ] **Step 2: Run test to verify it passes** (Task 9 already created the files, so this should pass immediately — the "failing" state was its absence).

Run: `cd engine && uv run pytest tests/dotfiles/test_hyprland_theme_templates.py -v`
Expected: PASS (3 tests). If any palette key is undefined, fix the template or add the key to `palette.toml`.

- [ ] **Step 3: Commit**

```bash
git add engine/tests/dotfiles/test_hyprland_theme_templates.py
git commit -m "test(hyprland): palette-coverage + portals smoke gate"
```

---

## Task 13: Full-suite gate + registry validation

**Files:** none (verification + fixups only)

- [ ] **Step 1: Registry loads with the new modules** (no dup names, deps resolve, profiles valid)

Run: `cd engine && uv run python -c "from devboost.core.registry import load; m=load(); print(sum(1 for k in m if k.startswith('hyprland')))"`
Expected: prints `16`.

- [ ] **Step 2: Type-check the whole tree**

Run: `cd engine && uv run mypy`
Expected: `Success: no issues found`. Fix any `type: ignore` needs to match the existing test style (e.g. `# type: ignore[attr-defined]` on `ctx.ex.calls`).

- [ ] **Step 3: Lint**

Run: `cd engine && uv run ruff check`
Expected: `All checks passed!`. Fix line length (80 cols) / import order as flagged.

- [ ] **Step 4: Full test suite**

Run: `cd engine && uv run pytest -q`
Expected: all pass, including the pre-existing suite (the `profiles_file` fixture now carries the three new profiles).

- [ ] **Step 5: Commit any fixups**

```bash
git add -A
git commit -m "chore(hyprland): satisfy mypy/ruff/pytest gates"
```

---

## Self-Review

**Spec coverage (§ → task):**
- §0 decisions Q1–Q10 → Q1 unified palette (Task 9 wezterm colors), Q2 minimal GTK/cursor (Task 5 `hyprland-gtk`), Q3 auto scaling + `local.d` override (Task 9 `hyprland.conf`), Q4 bundled wallpaper (Task 9 Step 6), Q5 `self_updating=False` (Tasks 2/3/4/6), Q6 both tests (Task 12 smoke + manual VM checklist in spec §8), Q7 verify-only GDM (Task 7), Q8 portals.conf (Task 9 + Task 4 verify), Q9 base16 (Task 9 palette), Q10 eddievs COPR (Tasks 1/2).
- §3 profiles → Task 1. §4 all 16 modules → Tasks 2–11. §5 theming/matugen containment → Tasks 9/11. §6 env → Task 8. §7 keybinds → Task 9 `hyprland.conf`. §8 testing → Tasks 2–12. §9 risks documented (COPR pin re-verify note) → Task 1 catalog.
- **16 modules present:** core, portal, bar, launcher, notify, lock, idle, wallpaper, polkit, shot, tray, gtk, session, env (14 in `hyprland`) + theme-bundle + matugen = 16. ✔ (matches registry check in Task 13 Step 1).

**Placeholder scan:** none — every step has concrete code/commands. The wallpaper PNG has a real generator fallback (Task 9 Step 6). The matugen ownership test was corrected to a concrete assertion (Task 11 Step 5).

**Type/name consistency:** `_HYPR_COPR` defined Task 2, reused Tasks 3/4/6; `_LOCAL_D` defined Task 2, used Task 8; `fs`/`gpu`/`pkg`/`copr` imports centralized in Task 2's header (Task 4/6 import `copr` locally inside `install` to avoid an unused import when only COPR modules need it — consistent, and ruff-clean). Palette keys `base00..base0F/accent/bg/fg` defined Task 9, referenced by Task 9 templates and validated by Task 12.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-28-fedora-hyprland-desktop-profile.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
