# macOS M2 — Shell, Terminal & Dotfiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `devboost install terminal`, run from a clone on an Apple Silicon Mac (macOS 27/26), installs every module in the terminal set through Homebrew and leaves a working zsh + Ghostty setup from the chezmoi dotfiles. On every OS, Ghostty becomes the default terminal and WezTerm moves to the opt-in `optional-terminals` profile.

**Architecture:** Most of the work is data and dotfiles. The engine gets one small generic addition: two Homebrew `Installer` strategies (`BrewFormula`, `BrewCask`) that a module declares as `per_os = OsMap(macos=…)`, a `Module.os_strategy()` accessor so modules that implement their own Linux install still defer to that entry, and a `plan._supported` fix so a module with its own `install()` stays supported on the OSes its `per_os` map does not name. `PackageModule` gets `install_linux`/`verify_linux` hooks so its subclasses with a custom Linux path keep the Homebrew path for free. The shell config is split into a POSIX `env.sh`, a bash-and-zsh `aliases.sh`, and the per-shell `shell.bash` / `shell.zsh`. On macOS, `~/.zshrc`, `~/.zprofile` and `~/.bash_profile` load them, and `.chezmoiignore` decides which files each OS gets. One shared probe script, `devboost-resources`, feeds the RAM/disk gauges in tmux, starship, WezTerm and the Claude status line on both OSes.

**Tech Stack:** Python ≥ 3.12, Typer, Pydantic, pytest, mypy `--strict`, ruff, `uv`; chezmoi 2.72 templates; POSIX sh / bash / zsh; Ghostty 1.3 config; WezTerm Lua; starship TOML.

**Spec:** `docs/superpowers/specs/2026-09-18-macos-support-design.md`. This plan covers §3 (all of it except AeroSpace), the M2 row of §11, the M2 part of §10 (`docs/macos.md` starts here), the `shell`/`terminal`/`optional-terminals` lines of §2 Profiles, and the §2 macOS strategies for the modules in the terminal set. Read the spec before starting. Format exemplar: `docs/superpowers/plans/2026-09-19-macos-m1-engine-core.md`.

## Global Constraints

- Apple Silicon only; the macOS family id is `"macos"`; Homebrew prefix `/opt/homebrew`. Supported: macOS 27 Golden Gate (primary, this Mac), 26 Tahoe.
- Brew is **never** run with `sudo`. Every brew call goes through `devboost.exec.primitives.pkg` (`install`, `installed`, `upgrade`, `install_cask`, `cask_installed`). Casks install with `--adopt`; a hand-installed app brew cannot adopt is `present-unmanaged` (M1 behaviour).
- **No terminal config may bind Ctrl+V.** `herdr --remote` owns image paste (spec §3).
- `env.sh` is strict POSIX `sh` (checked with `sh -n` and run under `sh`, `bash`, `zsh`). `aliases.sh` is the common subset of bash and zsh. `shell.bash` is bash. `shell.zsh`, `~/.zshrc` and `~/.zprofile` are zsh.
- Every managed dotfile carries the marker `devboost — managed by chezmoi`.
- Every default is free for commercial use (checked 2026-09-19): Ghostty MIT; WezTerm MIT; zsh-autosuggestions MIT; zsh-syntax-highlighting BSD-3-Clause; fzf MIT; starship ISC; chezmoi MIT; JetBrains Mono OFL-1.1 + Nerd Fonts MIT; fresh GPL-2.0-or-later (a tool, used unmodified); GNU bash / coreutils GPL-3.0 (tools).
- Linux behaviour does not change beyond what the spec asks for: Ghostty becomes the default terminal and WezTerm becomes opt-in, the env/aliases split, the `fzf --bash` fallback, the `.chezmoiignore` guard, and the shared resource probe. Every existing Linux test keeps its intent.
- Merge gates (constitution): `uv run ruff check`, `uv run mypy`, `uv run pytest`, all clean. Tests are hermetic. They never read the host OS; they inject `OsInfo`. A test that needs an external binary (`chezmoi`, `zsh`, `shellcheck`, `luac`, `ghostty`, `jq`) **skips** when that binary is absent. Task 0 installs them on the Mac, so they run here.
- Commit messages: Conventional Commits, **no `Co-Authored-By` trailer, no Claude/Anthropic attribution** (constitution). Every commit step below follows this.
- All commands run from `engine/` unless a step says otherwise. Repo-relative paths in `git add` are written from `engine/` (`../dotfiles/...`).

## Decisions

The spec is silent on these points, or they refine it. Each one is recorded here, then carried into the spec in Task 13.

| # | Decision | Why |
|---|---|---|
| D1 | **M2 gives every module in the terminal set a macOS path**, and removes those names from `KNOWN_GAPS`: atuin, chezmoi, claude-statusline, dotfiles, dust, eza, fastfetch, fresh, gh, ghostty, lazydocker, lazygit, mise, nerd-fonts, ripgrep, sd, starship, tealdeer, wezterm, yq, bash-config. The `macos` profile (currently `["terminal"]`) therefore installs cleanly on a Mac by the end of M2. Every other gap stays: M3 (catalog: `homebrew`, `xcode-clt`, `rosetta`, herdr, casks, claude-notify's `osascript`, …), M4 (docker, launchd timers), M5 (desktop, AeroSpace config, voxtype). | The acceptance test is `devboost install terminal` on this Mac, and M1's review asked that `macos` install cleanly. It is cheap: almost everything is a brew formula. `lazydocker` is not in the terminal set, but it gets the same one-line hook change as its neighbours in `cli_tools.py`. |
| D2 | M2 assumes **Homebrew and the Command Line Tools are already installed**. The `homebrew` / `xcode-clt` modules are M3; `get.sh` bootstraps them in M6. Task 0 checks for them. | Spec §11 puts them in M3. They are present on this Mac. |
| D3 | macOS strategies are **data**: `per_os = OsMap(macos=BrewFormula("x"))` or `BrewCask("x")`. A module that implements its own (Linux) `install`/`verify` starts both with `if (s := self.os_strategy(ctx)) is not None: return s.…(ctx)`. `plan._supported` treats a module's own `install()` as the fallback for OSes its `per_os` does not name. Before this fix, `per_os = OsMap(macos=…)` would have marked the module `unsupported-os` on Linux. | Spec §1: "custom-install modules get an explicit `per_os.macos` strategy". No module declared `per_os` before, so the plan bug was latent. |
| D4 | A `PackageModule` subclass with a custom Linux path overrides the new hooks `install_linux` / `verify_linux`, not `install` / `verify`. The base class keeps macOS on Homebrew (`brew_pkg` / `brew_cask`). | The M1 contract test treats an overridden `install` as "needs its own macOS answer". The hooks make the brew path automatic and the contract rule stays true. |
| D5 | `ripgrep`, `starship`, `chezmoi`, `mise` and `fresh` **stay plain `Module`s** with `per_os.macos`. They are not converted to `PackageModule`. | Converting them would silently change Linux `--offline` / `--update` semantics (`cli/app.py` keys both on `PackageModule`). |
| D6 | The macOS rc files are **plain files**: `dot_zshrc`, `dot_zprofile`, `dot_bash_profile`. `.chezmoiignore` keeps them off Linux. The spec named them `.tmpl`. | Nothing in them varies. Apple Silicon only means `/opt/homebrew` is fixed. |
| D7 | A pre-existing, foreign `~/.zshrc` / `~/.zprofile` / `~/.bash_profile` is **moved to `<name>.pre-devboost`** by the `dotfiles` module (Python) before `chezmoi apply`. It is never overwritten; later ones become `.pre-devboost.1`, `.2`, …. Its content is **not** migrated automatically. `~/.zshrc` sources `~/.zshrc.local` and `~/.zprofile` sources `~/.zprofile.local`, for machine-specific and installer lines. | The spec wants a backup. Doing it in Python keeps logic out of chezmoi `run_` scripts (constitution: no logic in shell). Auto-merging foreign rc files (oh-my-zsh, conda…) would be guesswork. |
| D8 | `aliases.sh` is the **bash ∩ zsh subset**, not strict POSIX. It uses `local`, arrays and here-strings. It is checked with `bash -n` and `zsh -n`. The zsh-unsafe local name `path` (tied to `$PATH` in zsh) in `img2ssh` is renamed `rpath`. | The existing functions (`pw-mcp`, `tsdev-sync`) need arrays and here-strings. The spec's "POSIX" was aspirational. |
| D9 | **One probe for RAM/disk everywhere:** `~/.local/bin/devboost-resources` (POSIX sh) prints `<ram_used%> <disk_used%> <disk_free_GiB>`. On Linux it reads `/proc/meminfo`; on Darwin it reads `sysctl hw.memsize` + `vm_stat` (free+inactive+speculative pages). Both use `df -Pk`, on `/System/Volumes/Data` on Darwin. tmux, WezTerm, starship and the Claude status line all call it. **starship keeps its tmux-gated three-tier custom modules** and only swaps their probe. It does not switch to the built-in `memory_usage` module (a deviation from spec §3). | `df -Pk` is POSIX on both OSes, so no GNU `-BG`. On a Mac, `/` is the sealed system volume (it showed 2% used against 8% on the data volume on this Mac). `memory_usage` can neither hide inside tmux nor colour by threshold, which regresses the existing design. |
| D10 | `ghostty/config` becomes the chezmoi template `config.tmpl`. Darwin gets `macos-option-as-alt = left`, `macos-titlebar-style = tabs` (not `window-decoration = none`, which drops the traffic lights and rounded corners) and a `super+…` twin of every Ctrl(+Shift) binding. All OSes get `shell-integration = detect`, `shell-integration-features = ssh-env,ssh-terminfo`, `notify-on-command-finish = unfocused`. Two existing bugs are fixed: `theme = catppuccin-mocha` → `Catppuccin Mocha` (Title Case theme names since Ghostty 1.2), and the unknown action `toggle_zoom` → `toggle_split_zoom`. | Spec §3, checked against the current Ghostty docs (Context7, ghostty.org). Ghostty 1.3.1's `+validate-config` accepted both rendered configs (exit 0). Today's file fails it with `keybind: InvalidAction` and `theme "catppuccin-mocha" not found`. `ssh-terminfo` removes the "unknown terminal xterm-ghostty" failure on fleet servers. |
| D11 | WezTerm (now opt-in and deprecated): `config/paste.lua` and its Ctrl+V binding are **deleted**. On Darwin, the leader is `Ctrl+A`, left Option is Alt, and there are `SUPER` twins of the `CTRL|SHIFT` bindings. `img2ssh` stays Linux-only in `aliases.sh` (guarded by `wl-paste`, not ported). | Spec §3 ("retired with WezTerm", "not ported"). |
| D12 | `zsh-config` **requires** `zsh-plugins`. The spec lists the plugins only in `shell`, but the terminal tier on a Mac should autosuggest too. Both modules are `families = ("macos",)`. | One `requires` edge. Linux drops both. |
| D13 | The zsh plugins come from **Homebrew formulae**. This supersedes the unimplemented 2026-07-29 zsh-optional-shell design (vendored plugins at pinned git refs). There is no plugin manager. `--update` upgrades them (`self_updating = True`). | Spec §2 lists them as formulae. brew already pins and updates them. |
| D14 | A new `bash` module (`PackageModule`, `families = ("macos",)`), in `shell` and `terminal`. It installs brew bash 5 as a tool, not as the login shell. | Spec §3. The portable scripts and `bash -lc` launchers need a modern bash, and `/bin/bash` is 3.2. |
| D15 | `curl`, `unzip` and `wl-clipboard` get `provided_by = ("macos",)` now, not in M3. `delta` gets `brew_pkg = "git-delta"` now. | They are in the terminal/shell sets. Without this, brew would install a keg-only curl or unzip, or fail on `delta` / `wl-clipboard`. |
| D16 | In `shell.zsh`, `ulimit -n 524288` falls back to `kern.maxfilesperproc` (92160 on this Mac) until `macos-limits` (M5) raises the kernel cap. | Otherwise every shell start prints an error until M5. |
| D17 | `compinit -i -d "$XDG_CACHE_HOME/zsh/zcompdump-$ZSH_VERSION"`. | `-i` never prompts about "insecure directories", and the dump stays out of `$HOME`. |
| D18 | Setting `herdr`'s `keys.remote_image_paste` is **M3** (the herdr module and its macOS pin land there). AeroSpace config is **M5**. `claude-notify`'s native notification is **M3**. | These are not in the terminal set, and their tools are not installed at M2 acceptance. |
| D19 | Dotfile tests render or apply the real chezmoi source for a chosen OS with `chezmoi … --override-data '{"chezmoi":{"os":…,"osRelease":{"id":…}}}'`. With chezmoi 2.72.2 on this Mac, it was verified that `.chezmoi.os` / `.chezmoi.osRelease` can be overridden this way, that `and` short-circuits, and that today's `.chezmoiignore` fails on Darwin with `map has no entry for key "id"`. | Hermetic per-OS rendering on any host. |
| D20 | `devboost.lock` is **not** regenerated in M2. | It is a deterministic name list that is already out of date with the catalog. Refreshing it is `devboost update`'s job, and doing it here would be an unrelated diff. |

**Pre-validation.** Every test and implementation snippet in Tasks 1–12 was applied to a scratch copy of `main` @ `41448b2` on this Mac (macOS 27.0, Homebrew 7.0.4, chezmoi 2.72.2, system zsh). There, `ruff check`, `mypy --strict` and the full suite passed: 1047 passed, and 2 skipped only because Ghostty and luac were not installed. If a snippet fails for you, first suspect drift from P1/Z1 (Task 0), not the snippet.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `engine/src/devboost/modules/_brew.py` (create) | `BrewFormula`, `BrewCask` install strategies | 1 |
| `engine/src/devboost/model.py` (modify) | `Module.os_strategy()` | 1 |
| `engine/src/devboost/core/plan.py` (modify) | `_supported`: a module's own `install()` is the fallback | 1 |
| `engine/src/devboost/modules/_pkgmodule.py` (modify) | macOS through the strategies; `install_linux` / `verify_linux` hooks | 1 |
| `engine/src/devboost/modules/cli_tools.py` (modify) | hooks for eza/atuin/lazygit/lazydocker/dust/sd/yq/tealdeer/fastfetch/gh; `delta` brew name; `curl`/`unzip`/`wl-clipboard` provided on macOS; new `bash` | 2 |
| `engine/src/devboost/modules/{ripgrep,base,mise,editors}.py`, `modules/shell.py` (`Starship`) (modify) | `per_os.macos` brew formula | 3 |
| `engine/src/devboost/modules/shell.py` (`Ghostty`, `Wezterm`, `NerdFonts`), `profiles.toml`, `engine/tests/conftest.py`, `engine/tests/cli/test_lifecycle_devhygiene.py`, `engine/tests/modules/test_omarchy.py` (modify) | Ghostty default everywhere; WezTerm → `optional-terminals`; macOS casks | 4 |
| `dotfiles/dot_config/devboost/env.sh` (create or modify), `aliases.sh` (create), `shell.bash` (modify) | env / aliases split; fzf fallback | 5 |
| `dotfiles/dot_config/devboost/shell.zsh`, `dotfiles/dot_zshrc`, `dotfiles/dot_zprofile`, `dotfiles/dot_bash_profile` (create) | zsh on macOS; login env for `bash -lc` | 6 |
| `dotfiles/.chezmoiignore` (modify) | Darwin-safe Omarchy guard; per-OS file sets | 7 |
| `engine/tests/dotfiles/conftest.py` (create) | shared fixtures: hermetic chezmoi render/apply, fake-bin helper, fragment home | 5 |
| `engine/src/devboost/modules/shell.py` (`ZshPlugins`, `ZshConfig`, `Dotfiles`, `BashConfig`, `ClaudeStatusline`), `profiles.toml` (modify) | zsh modules; foreign rc backup; Linux-only bash-config | 8 |
| `dotfiles/dot_local/bin/executable_devboost-resources` (create); `dot_config/tmux/executable_resources.sh`, `executable_pw-autoregister.sh`, `dot_config/wezterm/config/status.lua`, `dot_config/starship.toml`, `private_dot_claude/executable_statusline.sh` (modify) | portable scripts | 9 |
| `dotfiles/dot_config/ghostty/config` → `config.tmpl`; `dot_config/wezterm/config/keys.lua`, `wezterm.lua`, `README.md` (modify); `dot_config/wezterm/config/paste.lua` (delete) | terminal keys | 10 |
| `engine/src/devboost/modules/_credentials.py` (modify) | `git -c core.askPass= credential fill` | 11 |
| `engine/tests/core/test_macos_contract.py` (modify) | the terminal set plans cleanly on macOS and on Fedora | 12 |
| `docs/macos.md` (create); `docs/adding-a-module.md`, `docs/architecture.md`, `README.md`, `CLAUDE.md`, `CHANGELOG.md`, spec (modify) | docs | 13 |

---

### Task 0: Branch, Mac dev tools, baseline, shared-file re-check

A parallel effort (P1: pass multi-device, Linux; Z1: Zed default editor, Linux) merges to `main` before M2 runs. Both touch files M2 also edits. This task records their state so later tasks merge onto it instead of overwriting it.

**Files:** none (environment only)

- [ ] **Step 1: Branch from the current main** (repo root)

```bash
git fetch origin
git checkout -b feat/macos-m2-shell origin/main
```

- [ ] **Step 2: Check the prerequisites and install the tools the skip-if-absent tests need**

```bash
xcode-select -p && brew --version | head -1
brew install uv chezmoi shellcheck lua jq
```
Expected: a CLT path, `Homebrew 7.x`, then the installs succeed. zsh is `/bin/zsh`. Ghostty is installed later by the acceptance run (Task 13), and its validation test skips until then.

- [ ] **Step 3: Baseline gate** (from `engine/`)

```bash
cd engine && uv sync
uv run ruff check && uv run mypy && uv run pytest 2>&1 | tail -3
```
Expected: all green. If anything is red on a clean `main`, stop and report it. M2 must start green.

- [ ] **Step 4: Re-check the shared files against main**

```bash
git log --oneline -20 origin/main
ls ../dotfiles/dot_config/devboost/ tests/dotfiles/
grep -n 'env.sh' ../dotfiles/dot_config/devboost/shell.bash
grep -nE '^(base|shell|terminal|editors|optional-editors|security-cli|optional-terminals) ' ../profiles.toml
grep -n '^class \|profiles = ' src/devboost/modules/editors.py
grep -c '^    "' tests/core/test_macos_contract.py
```

Write down what you see. Later tasks refer to it:

- **Z1 merged** (expected): `../dotfiles/dot_config/devboost/env.sh` exists and holds the `EDITOR` / `VISUAL` block, `shell.bash` sources it after its PATH block, and `tests/dotfiles/test_env_sh.py` exists. Task 5 keeps Z1's editor block **byte-for-byte** and changes exactly one Z1 assertion (the PATH-order one). If Z1 has **not** merged, Task 5 creates `env.sh` with the same editor block (it is reproduced in Task 5). Whichever PR merges second resolves the conflict by keeping M2's superset file.
- **P1 merged** (expected): `base` ends with `"pass","pass-store"` and `security-cli` is an alias. M2 never edits those two lines. Apply Task 4's and Task 8's `profiles.toml` edits to the lines as they are on main.
- **`editors.py`**: Z1 adds a `Zed` class and changes `editors` to `["zed","fresh","fresh-lsp"]`. Task 3 edits only `class Fresh`.
- **`KNOWN_GAPS`**: note the count. Tasks 2–8 delete names from it, and each deletion is listed in its task.

No commit.

---
### Task 1: Engine — Homebrew strategies, `os_strategy`, plan fallback, `PackageModule` hooks

**Files:**
- Create: `engine/src/devboost/modules/_brew.py`
- Modify: `engine/src/devboost/model.py` (`Module`), `engine/src/devboost/core/plan.py` (`_supported`), `engine/src/devboost/modules/_pkgmodule.py`
- Test: `engine/tests/modules/test_brew_strategies.py` (create), `engine/tests/core/test_plan_per_os.py` (create)

**Interfaces:**
- Produces:
  - `BrewFormula(*formulae: str)`: a frozen dataclass with field `formulae: tuple[str, ...]`, and `verify(ctx) -> bool` / `install(ctx) -> None`. Without `--update` it runs one `brew install --formula -y <all>`. With `ctx.force` it runs `brew upgrade --formula <installed…>`, then `brew install` for the missing ones. An empty argument list raises `ValueError`.
  - `BrewCask(cask: str)`: a frozen dataclass; `verify` → `pkg.cask_installed`, `install` → `pkg.install_cask` (with `--adopt`).
  - `Module.os_strategy(self, ctx: Ctx) -> Installer | None`: the `per_os` entry for `ctx.os`, else `None`.
  - `plan._supported(cls, os_info)`: a module with its own `install()` is supported wherever its `per_os` map has no entry.
  - `PackageModule.brew_strategy() -> Installer`, `PackageModule.install_linux(ctx) -> None`, `PackageModule.verify_linux(ctx) -> bool`. Subclasses override the two hooks, never `install` / `verify`.

- [ ] **Step 1: Write the failing tests**

`tests/modules/test_brew_strategies.py`:

```python
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import ClassVar

import pytest

from devboost.core.osinfo import OsInfo, OsMap
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx, Installer, Module
from devboost.modules._brew import BrewCask, BrewFormula
from devboost.modules._pkgmodule import PackageModule

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")


class _Listed(FakeExecutor):
    """`brew list …` succeeds only for names in ``installed``; every other call is ok."""

    def __init__(self, installed: set[str]) -> None:
        super().__init__()
        self.installed = installed

    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        interactive: bool = False,
    ) -> Result:
        super().run(argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive)
        if list(argv[:2]) == ["brew", "list"]:
            return Result(0) if argv[-1] in self.installed else Result(1)
        return Result(0)


def test_formula_installs_every_formula_in_one_call() -> None:
    ex = FakeExecutor()
    BrewFormula("zsh-autosuggestions", "zsh-syntax-highlighting").install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [
        ["brew", "install", "--formula", "-y", "zsh-autosuggestions", "zsh-syntax-highlighting"]
    ]


def test_formula_verify_needs_every_formula() -> None:
    assert BrewFormula("a", "b").verify(Ctx(os=MAC, ex=_Listed({"a", "b"}))) is True
    assert BrewFormula("a", "b").verify(Ctx(os=MAC, ex=_Listed({"a"}))) is False


def test_formula_update_upgrades_present_and_installs_missing() -> None:
    ex = _Listed({"a"})
    BrewFormula("a", "b").install(Ctx(os=MAC, ex=ex, force=True))
    assert ["brew", "upgrade", "--formula", "a"] in ex.calls
    assert ex.calls[-1] == ["brew", "install", "--formula", "-y", "b"]


def test_formula_needs_a_name() -> None:
    with pytest.raises(ValueError, match="at least one"):
        BrewFormula()


def test_formula_equality_is_by_names() -> None:
    assert BrewFormula("x") == BrewFormula("x")
    assert BrewFormula("x") != BrewFormula("y")


def test_cask_installs_with_adopt_and_verifies_the_cask() -> None:
    ex = FakeExecutor()
    BrewCask("ghostty").install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [["brew", "install", "--cask", "-y", "--adopt", "ghostty"]]
    ex = FakeExecutor(scripts={"brew": Result(1)})
    assert BrewCask("ghostty").verify(Ctx(os=MAC, ex=ex)) is False
    assert ex.calls == [["brew", "list", "--cask", "--versions", "ghostty"]]


def test_strategies_are_installers() -> None:
    assert isinstance(BrewFormula("x"), Installer)
    assert isinstance(BrewCask("x"), Installer)


class _WithMacStrategy(Module):
    name: ClassVar[str] = "with-mac-strategy"
    per_os = OsMap(macos=BrewFormula("thing"))


def test_os_strategy_only_on_the_declared_os() -> None:
    mod = _WithMacStrategy()
    assert mod.os_strategy(Ctx(os=MAC, ex=FakeExecutor())) == BrewFormula("thing")
    assert mod.os_strategy(Ctx(os=FEDORA, ex=FakeExecutor())) is None


class _CustomLinux(PackageModule):
    name: ClassVar[str] = "customlinux"
    cmd: ClassVar[str] = "cl"
    fedora_pkg: ClassVar[str] = "cl"

    def install_linux(self, ctx: Ctx) -> None:
        ctx.ex.run(["sh", "-c", "custom-installer"])

    def verify_linux(self, ctx: Ctx) -> bool:
        return ctx.ex.which("cl-alt")


def test_hooked_package_module_keeps_brew_on_macos() -> None:
    ex = FakeExecutor()
    _CustomLinux().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [["brew", "install", "--formula", "-y", "customlinux"]]


def test_hooked_package_module_runs_its_hooks_on_linux() -> None:
    ex = FakeExecutor(present={"cl-alt"})
    ctx = Ctx(os=FEDORA, ex=ex)
    _CustomLinux().install(ctx)
    assert ex.calls == [["sh", "-c", "custom-installer"]]
    assert _CustomLinux().verify(ctx) is True


def test_hooked_subclass_keeps_the_base_install_and_verify() -> None:
    # The macOS contract test reads exactly this to decide "brew-backed".
    assert _CustomLinux.install is PackageModule.install
    assert _CustomLinux.verify is PackageModule.verify
```

`tests/core/test_plan_per_os.py`:

```python
"""per_os entries decide on their OS; a module's own install() covers the rest."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from devboost.core.osinfo import OsInfo, OsMap
from devboost.core.plan import build_plan
from devboost.model import Ctx, Module
from devboost.modules._brew import BrewFormula

FEDORA = OsInfo("fedora", "fedora", "x86_64")
MAC = OsInfo("macos", "macos", "aarch64")


class _OwnInstall(Module):
    name: ClassVar[str] = "own-install-probe"
    per_os = OsMap(macos=BrewFormula("probe"))

    def verify(self, ctx: Ctx) -> bool:
        return False

    def install(self, ctx: Ctx) -> None:
        return None


class _StrategyOnly(Module):
    name: ClassVar[str] = "strategy-only-probe"
    per_os = OsMap(macos=BrewFormula("probe"))


MODULES: dict[str, type[Module]] = {
    "own-install-probe": _OwnInstall,
    "strategy-only-probe": _StrategyOnly,
}


def test_own_install_is_the_fallback_off_the_declared_os(tmp_path: Path) -> None:
    plan = build_plan(list(MODULES), MODULES, FEDORA, gpu_marker=tmp_path / "none")
    assert {p.name: p.skip_reason for p in plan} == {
        "own-install-probe": None,
        "strategy-only-probe": "unsupported-os",
    }


def test_declared_os_is_supported_for_both(tmp_path: Path) -> None:
    plan = build_plan(list(MODULES), MODULES, MAC, gpu_marker=tmp_path / "none")
    assert {p.name: p.skip_reason for p in plan} == {
        "own-install-probe": None,
        "strategy-only-probe": None,
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/modules/test_brew_strategies.py tests/core/test_plan_per_os.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'devboost.modules._brew'`.

- [ ] **Step 3: Implement**

Create `engine/src/devboost/modules/_brew.py`:

```python
"""Homebrew install strategies — the ``per_os.macos`` answer for most modules.

A strategy is an ``Installer`` (``install``/``verify`` over ``Ctx``). Declare one as
``per_os = OsMap(macos=BrewFormula("starship"))``. A module whose own ``install``/``verify``
implement the Linux path hands off to it first, via ``Module.os_strategy`` (model.py).
"""

from __future__ import annotations

from dataclasses import dataclass

from devboost.exec.primitives import pkg
from devboost.model import Ctx


@dataclass(frozen=True, init=False)
class BrewFormula:
    """One or more Homebrew formulae, verified with ``brew list`` — never ``which``.

    macOS ships its own old git/curl/bash/…, so a PATH lookup would report a tool as
    installed that brew never installed. ``--update`` (``ctx.force``) upgrades in place.
    """

    formulae: tuple[str, ...]

    def __init__(self, *formulae: str) -> None:
        if not formulae:
            raise ValueError("BrewFormula needs at least one formula")
        object.__setattr__(self, "formulae", formulae)

    def verify(self, ctx: Ctx) -> bool:
        return all(pkg.installed(ctx, f) for f in self.formulae)

    def install(self, ctx: Ctx) -> None:
        if not ctx.force:
            # `brew install` of an installed formula is a no-op — no pre-check needed.
            pkg.install(ctx, *self.formulae)
            return
        present = [f for f in self.formulae if pkg.installed(ctx, f)]
        if present:
            pkg.upgrade(ctx, *present)
        missing = [f for f in self.formulae if f not in present]
        if missing:
            pkg.install(ctx, *missing)


@dataclass(frozen=True)
class BrewCask:
    """A Homebrew cask (an app). Casks with ``auto_updates`` update themselves (spec §6)."""

    cask: str

    def verify(self, ctx: Ctx) -> bool:
        return pkg.cask_installed(ctx, self.cask)

    def install(self, ctx: Ctx) -> None:
        pkg.install_cask(ctx, self.cask)
```

In `engine/src/devboost/model.py`, `class Module`: replace `_strategy` with the two methods below. The body of `_strategy` changes to use `os_strategy`; nothing else in the class changes.

```python
    def os_strategy(self, ctx: Ctx) -> Installer | None:
        """The ``per_os`` strategy declared for the running OS, or None.

        A module whose own install()/verify() implement its Linux path calls this first,
        so a declared entry such as ``per_os = OsMap(macos=BrewFormula("x"))`` still
        decides on that OS::

            def install(self, ctx: Ctx) -> None:
                if (s := self.os_strategy(ctx)) is not None:
                    s.install(ctx)
                    return
                ...  # the Linux path
        """
        return self.per_os.get(ctx.os)

    def _strategy(self, ctx: Ctx) -> Installer:
        return self.os_strategy(ctx) or self
```

In `engine/src/devboost/core/plan.py`, replace `_supported`:

```python
def _supported(cls: type[Module], os_info: OsInfo) -> bool:
    """Is there an install path for this OS?

    A uniform module (no per_os) runs everywhere. Otherwise the per_os entry for this OS
    decides; when there is none, a module that implements install() itself falls back to
    it (e.g. ``per_os = OsMap(macos=...)`` on a module whose own install is the Linux path).
    """
    p = cls.per_os
    if not (p.fedora or p.debian or p.arch or p.macos or p.default):
        return True
    if p.get(os_info) is not None:
        return True
    return cls.install is not Module.install
```

Replace `engine/src/devboost/modules/_pkgmodule.py` with:

```python
"""Shared base for trivial package-install modules (verify = which; install = pkg)."""

from __future__ import annotations

from typing import ClassVar

from devboost.core.osinfo import OsMap
from devboost.exec.primitives import copr, pkg
from devboost.model import Ctx, Installer, Module
from devboost.modules._brew import BrewCask, BrewFormula


class PackageModule(Module):
    """A module installed from a single package, verified by a command on PATH.

    macOS always goes through Homebrew (``brew_pkg`` / ``brew_cask``). A subclass that
    needs a custom *Linux* path overrides ``install_linux`` / ``verify_linux`` — never
    ``install`` / ``verify`` — so the Homebrew path stays automatic.
    """

    cmd: ClassVar[str]
    fedora_pkg: ClassVar[str]
    debian_pkg: ClassVar[str | None] = None   # apt package name; None → fedora_pkg
    debian_cmd: ClassVar[str | None] = None   # binary on Debian/Ubuntu; None → cmd
    arch_pkg: ClassVar[str | None] = None     # pacman package name; None → fedora_pkg
    arch_cmd: ClassVar[str | None] = None     # binary on Arch/Omarchy; None → cmd
    #: AUR package name, used only when the tool is absent from the official Arch repos.
    #: Set this *instead of* arch_pkg — it opts the module into unreviewed third-party
    #: PKGBUILDs, so it is spelled out per module rather than inferred.
    aur_pkg: ClassVar[str | None] = None
    copr_repo: ClassVar[str | None] = None
    #: Homebrew formula on macOS; None → the module ``name`` (brew names usually match).
    brew_pkg: ClassVar[str | None] = None
    #: Homebrew cask on macOS, for tools that ship only as an app. Wins over brew_pkg.
    brew_cask: ClassVar[str | None] = None
    # A single-package/single-binary install is safe to re-run for an in-place upgrade,
    # so package modules opt into `devboost install --update` by default. A specific
    # subclass with install-time side effects may override this back to False.
    self_updating: ClassVar[bool] = True

    def _resolve_cmd(self, ctx: Ctx) -> str:
        names: OsMap[str] = OsMap(
            debian=self.debian_cmd, arch=self.arch_cmd, default=self.cmd
        )
        return names.get(ctx.os) or self.cmd

    def _resolve_pkg(self, ctx: Ctx) -> str:
        names: OsMap[str] = OsMap(
            fedora=self.fedora_pkg,
            debian=self.debian_pkg,
            arch=self.arch_pkg,
            default=self.fedora_pkg,
        )
        return names.get(ctx.os) or self.fedora_pkg

    def _brew_name(self) -> str:
        return self.brew_pkg or self.name

    def brew_strategy(self) -> Installer:
        """How this tool installs on macOS: its cask if it has one, else its formula."""
        if self.brew_cask is not None:
            return BrewCask(self.brew_cask)
        return BrewFormula(self._brew_name())

    def verify(self, ctx: Ctx) -> bool:
        if ctx.os.family == "macos":
            # Ask brew, not PATH: macOS ships its own (old) git/curl/… that would
            # otherwise satisfy a `which` check and never be replaced.
            return self.brew_strategy().verify(ctx)
        return self.verify_linux(ctx)

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "macos":
            self.brew_strategy().install(ctx)
            return
        self.install_linux(ctx)

    def verify_linux(self, ctx: Ctx) -> bool:
        """Linux: the tool's command is on PATH. Override for a different check."""
        return ctx.ex.which(self._resolve_cmd(ctx))

    def install_linux(self, ctx: Ctx) -> None:
        """Linux: the distro package (COPR / AUR aware). Override for a custom path."""
        if ctx.os.family == "fedora" and self.copr_repo is not None:
            copr.enable(ctx, self.copr_repo)
        # An AUR-only tool declares aur_pkg and no arch_pkg: route it to the helper.
        if ctx.os.family == "arch" and self.arch_pkg is None and self.aur_pkg is not None:
            pkg.install_aur(ctx, self.aur_pkg)
            return
        pkg.install(ctx, self._resolve_pkg(ctx))
```

- [ ] **Step 4: Run the tests to verify they pass, plus the M1 regressions**

Run: `uv run pytest tests/modules/test_brew_strategies.py tests/core/test_plan_per_os.py tests/modules/test_macos_contract_fields.py tests/core -v && uv run mypy && uv run ruff check`
Expected: PASS. The M1 `test_package_module_*` tests pass unchanged: a non-force formula is one `brew install`, force + installed ends in `brew upgrade`, and a cask is one `brew install --cask -y --adopt`. mypy is clean. An unannotated `per_os = OsMap(macos=BrewFormula(...))` in a subclass infers `OsMap[Installer]` from the base declaration (checked).

- [ ] **Step 5: Commit**

```bash
git add src/devboost/modules/_brew.py src/devboost/model.py src/devboost/core/plan.py src/devboost/modules/_pkgmodule.py tests/modules/test_brew_strategies.py tests/core/test_plan_per_os.py
git commit -m "feat(engine): Homebrew install strategies, per_os fallback to a module's own install"
```

---

### Task 2: Terminal-set package tools on macOS (`cli_tools.py`)

**Files:**
- Modify: `engine/src/devboost/modules/cli_tools.py`
- Modify: `engine/tests/core/test_macos_contract.py` (`KNOWN_GAPS`)
- Test: `engine/tests/modules/test_cli_tools_macos.py` (create)

**Interfaces:**
- Consumes: `PackageModule.install_linux` / `verify_linux` (Task 1).
- Produces: `Eza`, `Atuin`, `Lazygit`, `Lazydocker`, `Dust`, `Sd`, `Yq`, `Fastfetch`, `Gh` override `install_linux`; `Tealdeer` overrides `verify_linux`. `Delta.brew_pkg = "git-delta"`. `Curl`, `Unzip`, `WlClipboard` have `provided_by = ("macos",)`. New `Bash` (`name = "bash"`, `families = ("macos",)`, `profiles = ("shell",)`), which is added to the profiles in Task 8.

- [ ] **Step 1: Write the failing tests** — `tests/modules/test_cli_tools_macos.py`

```python
from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules._pkgmodule import PackageModule
from devboost.modules.cli_tools import (
    Atuin,
    Bash,
    Curl,
    Delta,
    Dust,
    Eza,
    Fastfetch,
    Gh,
    Lazydocker,
    Lazygit,
    Sd,
    Tealdeer,
    Unzip,
    WlClipboard,
    Yq,
)

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
UBUNTU = OsInfo("ubuntu", "debian", "x86_64")

BREW_BACKED: list[tuple[type[PackageModule], str]] = [
    (Eza, "eza"),
    (Atuin, "atuin"),
    (Lazygit, "lazygit"),
    (Lazydocker, "lazydocker"),
    (Dust, "dust"),
    (Sd, "sd"),
    (Yq, "yq"),
    (Tealdeer, "tealdeer"),
    (Fastfetch, "fastfetch"),
    (Gh, "gh"),
    (Delta, "git-delta"),
    (Bash, "bash"),
]


@pytest.mark.parametrize(("cls", "formula"), BREW_BACKED)
def test_installs_its_formula_on_macos(cls: type[PackageModule], formula: str) -> None:
    ex = FakeExecutor()
    cls().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [["brew", "install", "--formula", "-y", formula]]


@pytest.mark.parametrize(("cls", "formula"), BREW_BACKED)
def test_verifies_through_brew_on_macos(cls: type[PackageModule], formula: str) -> None:
    ex = FakeExecutor(scripts={"brew": Result(1)})
    assert cls().verify(Ctx(os=MAC, ex=ex)) is False
    assert ex.calls == [["brew", "list", "--formula", "--versions", formula]]


def test_linux_install_paths_are_unchanged() -> None:
    ex = FakeExecutor()
    Lazygit().install(Ctx(os=FEDORA, ex=ex))
    assert ["sudo", "dnf", "copr", "enable", "-y", "atim/lazygit"] in ex.calls
    ex = FakeExecutor()
    Eza().install(Ctx(os=UBUNTU, ex=ex))
    assert ex.calls[0][:2] == ["sh", "-c"]
    assert Tealdeer().verify(Ctx(os=UBUNTU, ex=FakeExecutor(present={"tealdeer"}))) is True


def test_macos_already_provides_curl_unzip_and_the_clipboard(tmp_path: Path) -> None:
    for cls in (Curl, Unzip, WlClipboard):
        assert "macos" in cls.provided_by, cls.name
    modules = load()
    plan = build_plan(["curl", "unzip", "wl-clipboard"], modules, MAC, gpu_marker=tmp_path / "x")
    assert {p.name: p.skip_reason for p in plan} == {
        "curl": "provided-by-macos",
        "unzip": "provided-by-macos",
        "wl-clipboard": "provided-by-macos",
    }


def test_bash_is_a_macos_only_tool() -> None:
    assert Bash.families == ("macos",)
    assert Bash.self_updating is True
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_cli_tools_macos.py -v`
Expected: FAIL: `ImportError: cannot import name 'Bash'`.

- [ ] **Step 3: Implement** in `engine/src/devboost/modules/cli_tools.py`

Add `from typing import ClassVar` to the imports.

Rename the Linux overrides to the hooks. Each body stays byte-identical; only the `def` line changes:
- `Eza`, `Atuin`, `Lazygit`, `Lazydocker`, `Dust`, `Sd`, `Yq`, `Fastfetch`, `Gh`: `def install(self, ctx: Ctx) -> None:` → `def install_linux(self, ctx: Ctx) -> None:`
- `Tealdeer`: `def verify(self, ctx: Ctx) -> bool:` → `def verify_linux(self, ctx: Ctx) -> bool:`

For example, `Eza` becomes:

```python
@register
class Eza(PackageModule):
    name = "eza"
    category = "cli"
    profiles = ("cli",)
    cmd = "eza"
    fedora_pkg = "eza"

    def install_linux(self, ctx: Ctx) -> None:
        if ctx.os.family == "debian":
            # Not in Ubuntu 24.04 apt — install the latest GitHub release binary.
            ctx.ex.run(["sh", "-c", _EZA_DEBIAN])
        else:
            pkg.install(ctx, self._resolve_pkg(ctx))
```

Add these class attributes:

```python
# class Curl(PackageModule):
    # brew's curl is keg-only (never on PATH); macOS ships a current curl in /usr/bin.
    provided_by: ClassVar[tuple[str, ...]] = ("macos",)

# class Unzip(PackageModule):
    # /usr/bin/unzip ships with macOS; brew's unzip is keg-only.
    provided_by: ClassVar[tuple[str, ...]] = ("macos",)

# class WlClipboard(PackageModule):
    # macOS has pbcopy/pbpaste built in; herdr reads clipboard images via osascript.
    provided_by: ClassVar[tuple[str, ...]] = ("macos",)

# class Delta(PackageModule):
    brew_pkg = "git-delta"  # Homebrew's formula name (`delta` is a different project)
```

Add after `Direnv`:

```python
@register
class Bash(PackageModule):
    name = "bash"
    category = "shell"
    description = "bash 5 as a tool on macOS (/bin/bash is 3.2); zsh stays the login shell."
    profiles = ("shell",)
    # Linux distros ship a current bash; only macOS needs brew's.
    families: ClassVar[tuple[str, ...]] = ("macos",)
    cmd = "bash"
    fedora_pkg = "bash"
```

In `tests/core/test_macos_contract.py`, delete these lines from `KNOWN_GAPS`: `"atuin"`, `"dust"`, `"eza"`, `"fastfetch"`, `"gh"`, `"lazydocker"`, `"lazygit"`, `"sd"`, `"tealdeer"`, `"yq"`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/modules tests/core -v && uv run mypy && uv run ruff check`
Expected: PASS, including `test_known_gaps_are_still_gaps` (the ten names now resolve and are no longer listed) and every existing Fedora/Ubuntu/Arch test for these tools.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/modules/cli_tools.py tests/modules/test_cli_tools_macos.py tests/core/test_macos_contract.py
git commit -m "feat(cli-tools): Homebrew path on macOS for the custom-install CLI tools; bash module"
```

---
### Task 3: Custom-install tools on macOS — ripgrep, chezmoi, starship, mise, fresh

**Files:**
- Modify: `engine/src/devboost/modules/ripgrep.py`, `engine/src/devboost/modules/base.py` (`Chezmoi`), `engine/src/devboost/modules/mise.py` (`Mise`), `engine/src/devboost/modules/shell.py` (`Starship`), `engine/src/devboost/modules/editors.py` (`Fresh` only)
- Modify: `engine/tests/core/test_macos_contract.py` (`KNOWN_GAPS`)
- Test: `engine/tests/modules/test_macos_custom_tools.py` (create)

**Interfaces:**
- Consumes: `BrewFormula` (Task 1), `Module.os_strategy` (Task 1), the `plan._supported` fallback (Task 1).
- Produces: each of the five classes declares `per_os = OsMap(macos=BrewFormula(<formula>))`, with formulae `ripgrep`, `chezmoi`, `starship`, `mise`, `fresh-editor`. On Linux their own `install` / `verify` are unchanged. `Fresh` seeds `~/.config/fresh/config.json` on every OS.

- [ ] **Step 1: Write the failing tests** — `tests/modules/test_macos_custom_tools.py`

```python
from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx, Module
from devboost.modules.base import Chezmoi
from devboost.modules.editors import Fresh
from devboost.modules.mise import Mise
from devboost.modules.ripgrep import Ripgrep
from devboost.modules.shell import Starship

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")

CASES: list[tuple[type[Module], str]] = [
    (Ripgrep, "ripgrep"),
    (Chezmoi, "chezmoi"),
    (Starship, "starship"),
    (Mise, "mise"),
    (Fresh, "fresh-editor"),
]


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))


@pytest.mark.parametrize(("cls", "formula"), CASES)
def test_installs_the_formula_on_macos(cls: type[Module], formula: str) -> None:
    ex = FakeExecutor()
    cls().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [["brew", "install", "--formula", "-y", formula]]


@pytest.mark.parametrize(("cls", "formula"), CASES)
def test_verifies_through_brew_on_macos(cls: type[Module], formula: str) -> None:
    on_path = {"rg", "chezmoi", "starship", "mise", "fresh"}
    ex = FakeExecutor(scripts={"brew": Result(1)}, present=on_path)
    assert cls().verify(Ctx(os=MAC, ex=ex)) is False  # on PATH is not enough on a Mac
    assert ex.calls == [["brew", "list", "--formula", "--versions", formula]]


def test_fresh_seeds_its_config_on_macos(tmp_path: Path) -> None:
    Fresh().install(Ctx(os=MAC, ex=FakeExecutor()))
    assert (tmp_path / ".config" / "fresh" / "config.json").is_file()


def test_linux_keeps_its_installers_and_stays_supported(tmp_path: Path) -> None:
    ex = FakeExecutor()
    Chezmoi().install(Ctx(os=FEDORA, ex=ex))
    assert any("get.chezmoi.io" in " ".join(c) for c in ex.calls)
    names = [cls.name for cls, _ in CASES]
    plan = build_plan(names, load(), FEDORA, gpu_marker=tmp_path / "none")
    assert all(p.skip_reason is None for p in plan), plan
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_macos_custom_tools.py -v`
Expected: FAIL. On MAC the five modules still run their Linux installers (`sh -c curl …` / `dnf`), so the `brew` assertions fail.

- [ ] **Step 3: Implement.** Each module gets the same two-part change: a `per_os` line, and an `os_strategy` hand-off at the top of `verify` and `install`. The Linux bodies are unchanged.

`modules/ripgrep.py`:

```python
"""Tracer A — the simplest module shape: a single pkg.install (Homebrew on macOS)."""

from __future__ import annotations

from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import Ctx, Module
from devboost.modules._brew import BrewFormula


@register
class Ripgrep(Module):
    name = "ripgrep"
    category = "cli"
    description = "Fast recursive search (rg)."
    profiles = ("cli",)
    per_os = OsMap(macos=BrewFormula("ripgrep"))

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        return ctx.ex.which("rg")

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
        pkg.install(ctx, "ripgrep")
```

`modules/base.py`: add `from devboost.core.osinfo import OsMap` and `from devboost.modules._brew import BrewFormula`, then in `class Chezmoi`:

```python
    # macOS: the brew formula (kept current by `devboost install --update`); Linux keeps the
    # upstream installer into ~/.local/bin.
    per_os = OsMap(macos=BrewFormula("chezmoi"))

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        return ctx.ex.which("chezmoi")

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
        bindir = Path(os.environ["HOME"]) / ".local" / "bin"
        bindir.mkdir(parents=True, exist_ok=True)
        # Upstream installer is a curl|sh one-liner (escape hatch — no native package).
        ctx.ex.run(["sh", "-c", f"curl -fsLS get.chezmoi.io | sh -s -- -b {bindir}"])
```

`modules/mise.py`: add the same two imports. In `class Mise`:

```python
    # macOS: brew's formula. The nvm/sdkman migrations below edit ~/.bashrc blocks that
    # a Mac (zsh) does not have, so they are Linux-only.
    per_os = OsMap(macos=BrewFormula("mise"))

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        return ctx.ex.which("mise")

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
        if ctx.os.family == "debian":
            self._cleanup_legacy_apt_source(ctx)
        if not ctx.ex.which("mise"):
            # Official cross-distro installer → ~/.local/bin (on PATH), no root. mise is not
            # in Fedora's default repos (`dnf install mise` fails), so use the script on every OS.
            ctx.ex.run(["sh", "-c", _MISE_INSTALL])
        self._migrate_nvm(ctx)
        self._migrate_sdkman(ctx)
```

`modules/shell.py`: add `from devboost.core.osinfo import OsMap` and `from devboost.modules._brew import BrewFormula` (Task 4 extends this import with `BrewCask`). In `class Starship`:

```python
    per_os = OsMap(macos=BrewFormula("starship"))

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        return ctx.ex.which("starship")

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
        # Not in Ubuntu apt OR Fedora's default repos — the official installer drops the binary
        # into ~/.local/bin (on PATH), no sudo, on any distro. The installer's -b doesn't create
        # the dir, so ensure it exists (fresh boxes may not have ~/.local/bin yet).
        bindir = _home() / ".local" / "bin"
        bindir.mkdir(parents=True, exist_ok=True)
        ctx.ex.run(
            ["sh", "-c",
             f"curl -sS https://starship.rs/install.sh | sh -s -- -y -b {bindir}"]
        )
```

`modules/editors.py`: add `from devboost.modules._brew import BrewFormula` (`OsMap` is already imported). In `class Fresh`:

```python
    # macOS: Homebrew's `fresh-editor` formula (the binary is still `fresh`).
    per_os = OsMap(macos=BrewFormula("fresh-editor"))

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        return ctx.ex.which("fresh")

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
        else:
            # Upstream installer (rpm asset + post-install script); curl|sh escape hatch.
            ctx.ex.run(["sh", "-c", f"curl -fsSL {_FRESH_INSTALL} | sh"])
        # Seed the base config so the editor is configured even in a bare `terminal`
        # install (no LSP module present to seed it). Idempotent: only writes if absent.
        seed_base_config()
```

In `tests/core/test_macos_contract.py`, delete from `KNOWN_GAPS`: `"chezmoi"`, `"fresh"`, `"mise"`, `"ripgrep"`, `"starship"`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/modules tests/core -v && uv run mypy && uv run ruff check`
Expected: PASS, including the existing Linux tests (`test_ripgrep_installs_via_dnf`, `test_starship_installs_via_official_installer_on_fedora`, `test_fresh_uses_upstream_installer`, the mise migration tests).

- [ ] **Step 5: Commit**

```bash
git add src/devboost/modules/ripgrep.py src/devboost/modules/base.py src/devboost/modules/mise.py src/devboost/modules/shell.py src/devboost/modules/editors.py tests/modules/test_macos_custom_tools.py tests/core/test_macos_contract.py
git commit -m "feat(macos): brew formulae for ripgrep, chezmoi, starship, mise and fresh"
```

---

### Task 4: Ghostty is the default terminal on every OS; WezTerm → `optional-terminals`

**Files:**
- Modify: `engine/src/devboost/modules/shell.py` (`Ghostty`, `Wezterm`, `NerdFonts`)
- Modify: `profiles.toml`
- Modify: `engine/tests/conftest.py`, `engine/tests/cli/test_lifecycle_devhygiene.py` (declare the new profile in their synthetic `profiles.toml`)
- Modify: `engine/tests/modules/test_shell.py` (two tests change intent: Ghostty default, WezTerm opt-in), `engine/tests/modules/test_omarchy.py` (line asserting `wezterm` is `provided-by-omarchy`), `engine/tests/core/test_macos_contract.py`
- Test: `engine/tests/cli/test_terminal_profiles.py` (create), additions to `engine/tests/modules/test_shell.py`

**Interfaces:**
- Consumes: `BrewCask` (Task 1).
- Produces: `Ghostty.profiles == ("shell",)`, `Ghostty.provided_by == ("omarchy",)`, `Ghostty.per_os.macos == BrewCask("ghostty")`. `Wezterm.profiles == ("optional-terminals",)`, `Wezterm.per_os.macos == BrewCask("wezterm@nightly")`. `NerdFonts.per_os.macos == BrewCask("font-jetbrains-mono-nerd-font")`. New profile `optional-terminals = ["wezterm"]`.

- [ ] **Step 1: Write the failing tests**

`tests/cli/test_terminal_profiles.py`:

```python
from __future__ import annotations

from pathlib import Path

from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_ghostty_is_the_default_terminal_and_wezterm_is_opt_in() -> None:
    profiles = load_profiles(REPO_ROOT / "profiles.toml")
    modules = load()
    for name in ("shell", "terminal", "full", "omarchy"):
        members = expand([name], profiles, modules)
        assert "ghostty" in members, name
        assert "wezterm" not in members, name
    assert expand(["optional-terminals"], profiles, modules) == ["wezterm"]
```

In `tests/modules/test_shell.py`, add `MAC = OsInfo("macos", "macos", "aarch64")` next to the existing `FEDORA` / `UBUNTU` constants, then **replace** `test_ghostty_is_now_optional` and `test_wezterm_is_default_terminal_and_installs_nightly_appimage` with:

```python
def test_ghostty_is_the_default_terminal() -> None:
    assert Ghostty.profiles == ("shell",)
    assert Ghostty.provided_by == ("omarchy",)  # Omarchy keeps foot


def test_ghostty_is_a_cask_on_macos() -> None:
    ex = FakeExecutor()
    Ghostty().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [["brew", "install", "--cask", "-y", "--adopt", "ghostty"]]
    ex = FakeExecutor(scripts={"brew": Result(1)}, present={"ghostty"})
    assert Ghostty().verify(Ctx(os=MAC, ex=ex)) is False
    assert ex.calls == [["brew", "list", "--cask", "--versions", "ghostty"]]


def test_wezterm_is_opt_in_and_still_installs_the_nightly_appimage_on_linux(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert Wezterm.gui is True
    assert Wezterm.profiles == ("optional-terminals",)
    assert "deprecated" in Wezterm.description
    ctx = _ctx()
    Wezterm().install(ctx)
    joined = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert any("WezTerm-nightly" in j and "AppImage" in j for j in joined)


def test_wezterm_is_the_nightly_cask_on_macos() -> None:
    ex = FakeExecutor()
    Wezterm().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [["brew", "install", "--cask", "-y", "--adopt", "wezterm@nightly"]]


def test_nerd_fonts_is_a_cask_on_macos() -> None:
    ex = FakeExecutor()
    NerdFonts().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [
        ["brew", "install", "--cask", "-y", "--adopt", "font-jetbrains-mono-nerd-font"]
    ]
    ex = FakeExecutor()
    assert NerdFonts().verify(Ctx(os=MAC, ex=ex)) is True
    assert ex.calls == [["brew", "list", "--cask", "--versions", "font-jetbrains-mono-nerd-font"]]
```

In `tests/modules/test_omarchy.py`, change the last assertion of the omarchy plan test from `reasons.get("wezterm")` to:

```python
    assert reasons.get("ghostty") == "provided-by-omarchy"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cli/test_terminal_profiles.py tests/modules/test_shell.py tests/modules/test_omarchy.py -v`
Expected: FAIL. `ghostty` is not in `shell`, `optional-terminals` is an unknown profile, and the macOS casks are not declared.

- [ ] **Step 3: Implement**

`modules/shell.py`: extend the `_brew` import to `from devboost.modules._brew import BrewCask, BrewFormula`.

Replace `class Ghostty`:

```python
@register
class Ghostty(Module):
    name = "ghostty"
    category = "shell"
    description = "GPU-accelerated terminal — the default on every OS (Omarchy keeps foot)."
    gui = True
    profiles = ("shell",)
    # Omarchy ships foot as the default terminal, themed by `omarchy theme set` and
    # routed through xdg-terminal-exec. Installing a second "default terminal" fights
    # the platform's theming and its terminal-launch chain.
    provided_by: ClassVar[tuple[str, ...]] = ("omarchy",)
    # macOS: the cask is the app bundle (no CLI on PATH), so verify asks brew.
    per_os = OsMap(macos=BrewCask("ghostty"))

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        if ctx.os.family == "debian":
            return "com.mitchellh.ghostty" in ctx.ex.run(
                ["flatpak", "list", "--app", "--columns=application"]
            ).stdout
        return ctx.ex.which("ghostty")

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
        if ctx.os.family == "debian":
            flatpak.install(ctx, "com.mitchellh.ghostty")
        else:
            copr.enable(ctx, "scottames/ghostty")
            pkg.install(ctx, "ghostty")
```

In `class Wezterm`: change the description and profiles, and add `per_os`. Add the hand-off as the first lines of `verify` and `install`; the AppImage script is unchanged:

```python
    description = (
        "GPU terminal + multiplexer (nightly) — opt-in, deprecated: Ghostty is the default "
        "and herdr the multiplexer."
    )
    gui = True
    profiles = ("optional-terminals",)
    # (provided_by = ("omarchy",) and its comment stay as they are)
    # macOS: the nightly cask (the last stable release is Feb 2024).
    per_os = OsMap(macos=BrewCask("wezterm@nightly"))

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        return ctx.ex.which("wezterm")

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
        # … the existing AppImage body, unchanged …
```

In `class NerdFonts`, add the declaration and the hand-offs:

```python
    # macOS: the Homebrew font cask (tracks the latest Nerd Fonts; Linux pins v3.2.1).
    per_os = OsMap(macos=BrewCask("font-jetbrains-mono-nerd-font"))

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        return "JetBrainsMono Nerd Font" in ctx.ex.run(["fc-list"]).stdout

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
        # … the existing download/unzip/fc-cache body, unchanged …
```

Update the module docstring's first line to `"""shell profile — starship, ghostty (default), wezterm (opt-in), fonts, dotfiles, bash/zsh."""`.

`profiles.toml`:
- In the `shell` line, replace `"wezterm"` with `"ghostty"`.
- In the `terminal` list, replace `"wezterm"` with `"ghostty"`.
- After the `optional-editors` line, add:

```toml
# optional-terminals — WezTerm (nightly), kept for people who want its multiplexer/SSH
# domains. Deprecated: Ghostty is the default terminal on every OS, herdr the multiplexer.
optional-terminals = ["wezterm"]
```

- In the `full` header comment, add `optional-terminals` to the list of excluded opt-in profiles.

Add `'optional-terminals = ["wezterm"]\n'` to the synthetic profiles in `tests/conftest.py` (`profiles_file` fixture, after the `optional-editors` line) and in `tests/cli/test_lifecycle_devhygiene.py` (`test_write_lock_is_sorted_and_deterministic`, after `optional-editors`). Load-time validation rejects any module whose `profiles` names an undeclared profile.

In `tests/core/test_macos_contract.py`, delete from `KNOWN_GAPS`: `"ghostty"`, `"nerd-fonts"`, `"wezterm"`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -v tests/cli tests/modules tests/core && uv run mypy && uv run ruff check`
Expected: PASS. The Fedora test `test_ghostty_is_gui_and_uses_copr` and the Ubuntu Flatpak path still pass (Linux is unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/devboost/modules/shell.py ../profiles.toml tests/conftest.py tests/cli/test_lifecycle_devhygiene.py tests/cli/test_terminal_profiles.py tests/modules/test_shell.py tests/modules/test_omarchy.py tests/core/test_macos_contract.py
git commit -m "feat(terminal): Ghostty default on every OS, WezTerm opt-in (optional-terminals), macOS casks"
```

---
### Task 5: Shell split — POSIX `env.sh`, shared `aliases.sh`, slimmer `shell.bash` with the fzf fallback

**Files:**
- Create or modify: `dotfiles/dot_config/devboost/env.sh` (Z1 created it with the editor block; see Task 0)
- Create: `dotfiles/dot_config/devboost/aliases.sh`
- Modify: `dotfiles/dot_config/devboost/shell.bash`
- Create: `engine/tests/dotfiles/conftest.py` (fixtures shared by Tasks 5–10)
- Test: `engine/tests/dotfiles/test_env_paths.py`, `engine/tests/dotfiles/test_shell_split.py` (create)
- Modify: `engine/tests/dotfiles/test_env_sh.py` (Z1; one assertion), `engine/tests/modules/test_shell.py` (`test_bashrc_puts_dotnet_tools_on_path` now reads `env.sh`)

**Interfaces:**
- Produces:
  - `~/.config/devboost/env.sh`: POSIX. Prepends `~/.local/bin` and `~/.dotnet/tools` once each, and only if present. Sets `RIPGREP_CONFIG_PATH`. On Darwin it also sets `LANG` (default `en_US.UTF-8`), rewrites a bare `LC_CTYPE=UTF-8`, and sets `XDG_CONFIG_HOME` and `ANDROID_HOME` (`~/Library/Android/sdk`). If `$ANDROID_HOME/platform-tools` exists, it goes on PATH. Then the Z1 `EDITOR` / `VISUAL` block.
  - `~/.config/devboost/aliases.sh`: `dev`, `expose`/`exposed`/`unexpose`/`tsdev-sync`, `pw-server`/`pw-connect`/`pw-mcp`, `pw-workstation`, `img2ssh`, and the eza aliases. Valid in bash and zsh.
  - `shell.bash` sources `env.sh` first and `aliases.sh` last. It uses `fzf --bash` when supported and falls back to the distro's scripts otherwise.
  - Test fixtures in `tests/dotfiles/conftest.py`: `DOT` (path), `bin_dir`, `make_bin(name, body) -> Path`, `frag_home -> Path`, `chezmoi_render(template, os, distro) -> str`, `chezmoi_apply(os, distro) -> Path`.

- [ ] **Step 1: Create the shared test fixtures** — `tests/dotfiles/conftest.py`

```python
"""Fixtures for dotfile tests: fake binaries, a HOME with the shell fragments, and
hermetic chezmoi render/apply of the real source for a chosen OS (no real $HOME touched)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

DOT = Path(__file__).resolve().parents[3] / "dotfiles"
FRAGMENTS = DOT / "dot_config" / "devboost"
CHEZMOI = shutil.which("chezmoi")

MakeBin = Callable[[str, str], Path]
Render = Callable[[Path, str, str], str]
Apply = Callable[[str, str], Path]


@pytest.fixture
def bin_dir(tmp_path: Path) -> Path:
    d = tmp_path / "bin"
    d.mkdir()
    return d


@pytest.fixture
def make_bin(bin_dir: Path) -> MakeBin:
    """Write an executable ``#!/bin/sh`` fake named *name* into ``bin_dir``."""

    def make(name: str, body: str) -> Path:
        p = bin_dir / name
        p.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
        p.chmod(0o755)
        return p

    return make


@pytest.fixture
def frag_home(tmp_path: Path) -> Path:
    """A HOME with dev-boost's shell fragments where the rc files look for them."""
    home = tmp_path / "home"
    dest = home / ".config" / "devboost"
    dest.mkdir(parents=True)
    for f in FRAGMENTS.iterdir():
        if f.is_file():
            shutil.copy(f, dest / f.name)
    return home


def _data(os_name: str, distro: str) -> str:
    return json.dumps({"chezmoi": {"os": os_name, "osRelease": {"id": distro}}})


@pytest.fixture
def chezmoi_render(tmp_path: Path) -> Render:
    """Render one source template as chezmoi would on *os_name* / *distro*."""
    if CHEZMOI is None:
        pytest.skip("chezmoi not installed")
    exe = CHEZMOI

    def render(template: Path, os_name: str, distro: str) -> str:
        res = subprocess.run(
            [exe, "execute-template", "--source", str(DOT),
             "--config", str(tmp_path / "chezmoi.toml"),
             "--override-data", _data(os_name, distro)],
            input=template.read_text(encoding="utf-8"),
            capture_output=True, text=True, check=True,
        )
        return res.stdout

    return render


@pytest.fixture
def chezmoi_apply(tmp_path: Path) -> Apply:
    """Apply the whole source into a fresh HOME as chezmoi would on *os_name*/*distro*."""
    if CHEZMOI is None:
        pytest.skip("chezmoi not installed")
    exe = CHEZMOI

    def apply(os_name: str, distro: str) -> Path:
        tag = f"{os_name}-{distro}"
        home = tmp_path / f"home-{tag}"
        home.mkdir()
        subprocess.run(
            [exe, "apply", "--force", "--no-tty", "--source", str(DOT),
             "--destination", str(home), "--config", str(tmp_path / "chezmoi.toml"),
             "--persistent-state", str(tmp_path / f"{tag}.boltdb"),
             "--cache", str(tmp_path / f"cache-{tag}"),
             "--override-data", _data(os_name, distro)],
            env={**os.environ, "HOME": str(home)},
            capture_output=True, text=True, check=True,
        )
        return home

    return apply
```

- [ ] **Step 2: Write the failing tests**

`tests/dotfiles/test_env_paths.py`:

```python
"""env.sh: PATH once and only for real dirs, ripgrep config, the macOS environment."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from .conftest import FRAGMENTS, MakeBin

ENV_SH = FRAGMENTS / "env.sh"
SHELLS = [s for s in ("sh", "bash", "zsh") if shutil.which(s)]
KEYS = ("PATH", "LANG", "LC_CTYPE", "XDG_CONFIG_HOME", "ANDROID_HOME", "RIPGREP_CONFIG_PATH")


def _env(shell: str, home: Path, bin_dir: Path, make_bin: MakeBin, *,
         uname: str = "Linux", extra: dict[str, str] | None = None) -> dict[str, str]:
    make_bin("uname", f"echo {uname}")
    fields = " ".join(f'"${{{k}-<unset>}}"' for k in KEYS)
    script = f'. "{ENV_SH}"; . "{ENV_SH}"; printf "%s\\n" {fields}'
    out = subprocess.run(
        [shell, "-c", script],
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(home), **(extra or {})},
        capture_output=True, text=True, check=True,
    )
    return dict(zip(KEYS, out.stdout.splitlines(), strict=True))


@pytest.mark.parametrize("shell", SHELLS)
def test_user_bins_come_first_once_each(shell: str, tmp_path: Path, bin_dir: Path,
                                        make_bin: MakeBin) -> None:
    (tmp_path / ".local" / "bin").mkdir(parents=True)
    (tmp_path / ".dotnet" / "tools").mkdir(parents=True)
    path = _env(shell, tmp_path, bin_dir, make_bin)["PATH"].split(":")
    assert path[:2] == [f"{tmp_path}/.local/bin", f"{tmp_path}/.dotnet/tools"]
    assert path.count(f"{tmp_path}/.local/bin") == 1  # sourced twice, added once


@pytest.mark.parametrize("shell", SHELLS)
def test_missing_dirs_stay_off_path(shell: str, tmp_path: Path, bin_dir: Path,
                                    make_bin: MakeBin) -> None:
    path = _env(shell, tmp_path, bin_dir, make_bin)["PATH"]
    assert ".local/bin" not in path and ".dotnet/tools" not in path


@pytest.mark.parametrize("shell", SHELLS)
def test_ripgrep_reads_the_managed_config(shell: str, tmp_path: Path, bin_dir: Path,
                                          make_bin: MakeBin) -> None:
    got = _env(shell, tmp_path, bin_dir, make_bin)["RIPGREP_CONFIG_PATH"]
    assert got == f"{tmp_path}/.config/ripgrep/ripgreprc"


@pytest.mark.parametrize("shell", SHELLS)
def test_darwin_environment(shell: str, tmp_path: Path, bin_dir: Path,
                            make_bin: MakeBin) -> None:
    tools = tmp_path / "Library" / "Android" / "sdk" / "platform-tools"
    tools.mkdir(parents=True)
    env = _env(shell, tmp_path, bin_dir, make_bin, uname="Darwin", extra={"LC_CTYPE": "UTF-8"})
    assert env["LANG"] == "en_US.UTF-8"
    assert env["LC_CTYPE"] == "en_US.UTF-8"  # a bare UTF-8 breaks ssh/mosh to Linux
    assert env["XDG_CONFIG_HOME"] == f"{tmp_path}/.config"
    assert env["ANDROID_HOME"] == f"{tmp_path}/Library/Android/sdk"
    assert str(tools) in env["PATH"].split(":")


@pytest.mark.parametrize("shell", SHELLS)
def test_darwin_keeps_a_chosen_locale(shell: str, tmp_path: Path, bin_dir: Path,
                                      make_bin: MakeBin) -> None:
    env = _env(shell, tmp_path, bin_dir, make_bin, uname="Darwin",
               extra={"LANG": "de_DE.UTF-8", "LC_CTYPE": "de_DE.UTF-8"})
    assert (env["LANG"], env["LC_CTYPE"]) == ("de_DE.UTF-8", "de_DE.UTF-8")


@pytest.mark.parametrize("shell", SHELLS)
def test_linux_environment_is_left_alone(shell: str, tmp_path: Path, bin_dir: Path,
                                         make_bin: MakeBin) -> None:
    env = _env(shell, tmp_path, bin_dir, make_bin)
    assert env["LANG"] == env["XDG_CONFIG_HOME"] == env["ANDROID_HOME"] == "<unset>"


def test_env_sh_is_posix() -> None:
    assert subprocess.run(["sh", "-n", str(ENV_SH)], capture_output=True).returncode == 0
    if shutil.which("shellcheck"):
        res = subprocess.run(["shellcheck", "-s", "sh", str(ENV_SH)], capture_output=True,
                             text=True)
        assert res.returncode == 0, res.stdout
```

`tests/dotfiles/test_shell_split.py`:

```python
"""shell.bash loads env.sh + aliases.sh; fzf ≥ 0.48 integration with a fallback; the
shared aliases.sh is valid bash and zsh."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from .conftest import FRAGMENTS, MakeBin

SHELL_BASH = FRAGMENTS / "shell.bash"
ALIASES = FRAGMENTS / "aliases.sh"
ZSH = shutil.which("zsh")


BASH = shutil.which("bash") or "bash"  # resolved here: the child PATH is minimal


def _bash(home: Path, bin_dir: Path, script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [BASH, "-c", f'source "$HOME/.config/devboost/shell.bash"; {script}'],
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(home)},
        capture_output=True, text=True,
    )


def test_fragments_parse() -> None:
    for f in (SHELL_BASH, ALIASES):
        res = subprocess.run(["bash", "-n", str(f)], capture_output=True, text=True)
        assert res.returncode == 0, (f, res.stderr)
    if ZSH:
        res = subprocess.run([ZSH, "-n", str(ALIASES)], capture_output=True, text=True)
        assert res.returncode == 0, res.stderr


def test_shell_bash_loads_env_and_aliases(frag_home: Path, bin_dir: Path,
                                          make_bin: MakeBin) -> None:
    make_bin("ssh", "exit 0")
    make_bin("eza", "exit 0")
    res = _bash(frag_home, bin_dir, 'type -t dev; alias ls; printf "%s\\n" "$RIPGREP_CONFIG_PATH"')
    assert res.returncode == 0, res.stderr
    lines = res.stdout.splitlines()
    assert lines[0] == "function"
    assert "eza --group-directories-first" in lines[1]
    assert lines[2] == f"{frag_home}/.config/ripgrep/ripgreprc"


def test_modern_fzf_prints_its_own_bash_integration(frag_home: Path, bin_dir: Path,
                                                    make_bin: MakeBin) -> None:
    make_bin("fzf", '[ "$1" = "--bash" ] && { echo "FZF_BASH_INIT=new"; exit 0; }; exit 2')
    res = _bash(frag_home, bin_dir, 'printf "%s" "${FZF_BASH_INIT-<unset>}"')
    assert res.stdout == "new"


def test_old_fzf_falls_back_quietly(frag_home: Path, bin_dir: Path, make_bin: MakeBin) -> None:
    make_bin("fzf", 'echo "unknown option: $1" >&2; exit 2')  # fzf < 0.48 (Ubuntu 24.04)
    res = _bash(frag_home, bin_dir, 'printf "%s" "${FZF_BASH_INIT-<unset>}"')
    assert res.stdout == "<unset>"
    assert "unknown option" not in res.stderr
    assert "/usr/share/fzf/shell/key-bindings.bash" in SHELL_BASH.read_text(encoding="utf-8")


def test_aliases_never_shadow_zsh_path() -> None:
    # In zsh `path` is tied to $PATH — `local path=…` inside a function breaks every lookup.
    assert "local path=" not in ALIASES.read_text(encoding="utf-8")


@pytest.mark.skipif(ZSH is None, reason="zsh not installed")
def test_aliases_define_the_helpers_in_zsh(frag_home: Path, bin_dir: Path,
                                           make_bin: MakeBin) -> None:
    assert ZSH is not None
    make_bin("ssh", "exit 0")
    make_bin("claude", "exit 0")
    script = f'source "{frag_home}/.config/devboost/aliases.sh"; whence -w dev pw-workstation'
    res = subprocess.run(
        [ZSH, "-c", script],
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(frag_home)},
        capture_output=True, text=True,
    )
    assert res.stdout.splitlines() == ["dev: function", "pw-workstation: function"]
```

In `tests/modules/test_shell.py`, replace `test_bashrc_puts_dotnet_tools_on_path` with:

```python
def test_env_puts_dotnet_tools_on_path() -> None:
    """`dotnet tool install -g` (aspire, csharp-ls, csharpier) installs into ~/.dotnet/tools.
    The shared env must add it to PATH or those tools are "not found" in an interactive
    shell — which is exactly what happened to `aspire` after `devboost install full`."""
    env = (_dotfiles_dir() / "dot_config" / "devboost" / "env.sh").read_text(encoding="utf-8")
    assert '_devboost_path_prepend "${HOME}/.dotnet/tools"' in env
```

In `tests/dotfiles/test_env_sh.py` (Z1), in `test_env_sh_is_posix_and_shell_bash_sources_it_after_path`, replace the line
`assert text.index(".local/bin") < text.index(line)  # \`command -v zed\` needs ~/.local/bin`
with:

```python
    env = ENV_SH.read_text(encoding="utf-8")
    assert env.index(".local/bin") < env.index("command -v zed")  # zed lookup needs ~/.local/bin
```

(If Z1 has not merged and this file does not exist, skip this edit.)

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/dotfiles tests/modules/test_shell.py -v`
Expected: FAIL. `aliases.sh` is missing, `env.sh` has no PATH/Darwin block, `RIPGREP_CONFIG_PATH` is unset when only `env.sh` is sourced, and the fzf test sees `<unset>`.

- [ ] **Step 4: Create `aliases.sh` from the helpers now in `shell.bash`** (run from `engine/`)

```bash
cd ../dotfiles/dot_config/devboost && python3 - <<'PY'
from pathlib import Path

src = Path("shell.bash").read_text(encoding="utf-8").splitlines(keepends=True)
start = next(i for i, ln in enumerate(src) if ln.startswith("# dev — hop onto a server")) - 1
assert src[start].startswith("# ----"), src[start]
body = "".join(src[start:])
for old, new in (
    ('local path="${dir}/paste-', 'local rpath="${dir}/paste-'),
    ("cat > '${path}'", "cat > '${rpath}'"),
    ("printf '%s' \"$path\"", "printf '%s' \"$rpath\""),
    ('echo "${path}  (path copied', 'echo "${rpath}  (path copied'),
):
    assert body.count(old) == 1, old
    body = body.replace(old, new)
header = """# ~/.config/devboost/aliases.sh — dev-boost's interactive helpers and aliases, shared by
# bash (shell.bash) and zsh (shell.zsh, macOS). Written in the subset both shells run
# (`local`, arrays, `[[ ]]`, here-strings) — it is not for plain sh.
#
# devboost — managed by chezmoi; edit dotfiles/dot_config/devboost/aliases.sh in the
# dev-boost repo. Do not edit this file manually.

"""
Path("aliases.sh").write_text(header + body, encoding="utf-8")
PY
cd -
```

Check: `head -12 ../dotfiles/dot_config/devboost/aliases.sh` shows the header, then the `# ----` rule and `# dev — hop onto a server…`, and `tail -3` shows the `lt=` eza alias and `fi`.

- [ ] **Step 5: Write `env.sh`** — `dotfiles/dot_config/devboost/env.sh` (full file). The `# Editors —` section is Z1's block, reproduced verbatim. If the block on main differs, keep main's version of that section and everything else as below.

```sh
# ~/.config/devboost/env.sh — dev-boost's POSIX environment, shared by every shell
# (sourced by shell.bash and shell.zsh; on macOS also by ~/.bash_profile so `bash -lc`
# launchers see the same PATH). POSIX sh only: no bashisms.
#
# devboost — managed by chezmoi; edit dotfiles/dot_config/devboost/env.sh in the dev-boost
# repo. Do not edit this file manually.

# ---------------------------------------------------------------------------
# PATH — user bins first. Each directory is added once (a nested shell re-sourcing this
# file does not grow PATH) and only if it exists.
# ---------------------------------------------------------------------------
_devboost_path_prepend() {
  [ -d "$1" ] || return 0
  case ":${PATH}:" in
    *":$1:"*) ;;
    *) PATH="$1:${PATH}" ;;
  esac
}
# `dotnet tool install -g` (aspire, csharp-ls, csharpier) installs here; without this on
# PATH the tools install but are "not found" in an interactive shell.
_devboost_path_prepend "${HOME}/.dotnet/tools"
_devboost_path_prepend "${HOME}/.local/bin"

# ---------------------------------------------------------------------------
# macOS — locale, XDG config dir, Android SDK location
# ---------------------------------------------------------------------------
if [ "$(uname -s)" = "Darwin" ]; then
  # macOS sends a bare LC_CTYPE=UTF-8 over ssh/mosh; Linux rejects it (mosh refuses to
  # start). A full locale name travels safely.
  export LANG="${LANG:-en_US.UTF-8}"
  if [ "${LC_CTYPE:-}" = "UTF-8" ]; then
    export LC_CTYPE=en_US.UTF-8
  fi
  # Without this, XDG-aware tools (lazygit, fresh, …) read ~/Library/Application Support
  # on macOS and never see the chezmoi-managed files in ~/.config.
  export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-${HOME}/.config}"
  export ANDROID_HOME="${ANDROID_HOME:-${HOME}/Library/Android/sdk}"
fi
if [ -n "${ANDROID_HOME:-}" ]; then
  _devboost_path_prepend "${ANDROID_HOME}/platform-tools"
fi
export PATH
unset -f _devboost_path_prepend

# ripgrep reads its config only from this variable.
export RIPGREP_CONFIG_PATH="${HOME}/.config/ripgrep/ripgreprc"

# ---------------------------------------------------------------------------
# Editors — fresh in every terminal; Zed as the *visual* editor only in a local GUI session.
# git has no core.editor, so it follows $VISUAL then $EDITOR (`zed --wait` returns when the
# tab is closed). Over SSH (even with a forwarded DISPLAY) Zed would open on the far screen.
# ---------------------------------------------------------------------------
export EDITOR=fresh
_devboost_gui=0
if [ -z "${SSH_CONNECTION:-}" ] && [ -z "${SSH_TTY:-}" ]; then
  if [ "$(uname -s)" = "Darwin" ]; then
    _devboost_gui=1
  elif [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; then
    _devboost_gui=1
  fi
fi
if [ "$_devboost_gui" = 1 ] && command -v zed >/dev/null 2>&1; then
  export VISUAL="zed --wait"
elif [ "${VISUAL:-}" = "zed --wait" ]; then
  # Inherited from a GUI parent (e.g. a tmux server started on the desktop) — useless here.
  unset VISUAL
fi
unset _devboost_gui
```

- [ ] **Step 6: Rewrite `shell.bash`** — `dotfiles/dot_config/devboost/shell.bash` (full file; the helpers now live in `aliases.sh`)

```bash
# ~/.config/devboost/shell.bash — dev-boost's portable interactive shell config.
#
# Kept SEPARATE from ~/.bashrc on purpose. On Fedora/Ubuntu dev-boost owns ~/.bashrc
# and it sources this file. On Omarchy the distro owns ~/.bashrc (it bootstraps
# OMARCHY_PATH and sources the Omarchy rc), so dev-boost appends a single guarded
# source line to the user-editable section instead of replacing the file. Same config
# either way, one copy of it, and no fight with `omarchy refresh`/`omarchy update`.
#
# The environment (PATH, EDITOR, …) is in env.sh and the dev/expose/pw-* helpers and
# aliases are in aliases.sh — both shared with zsh (shell.zsh on macOS). This file keeps
# what is bash-specific: shopt, bash-preexec and the bash tool initialisers.
#
# devboost — managed by chezmoi; edit dotfiles/dot_config/devboost/shell.bash in the
# dev-boost repo. Do not edit this file manually.

# ---------------------------------------------------------------------------
# Sensible defaults
# ---------------------------------------------------------------------------
HISTCONTROL=ignoredups:erasedups
HISTSIZE=100000
HISTFILESIZE=200000
shopt -s histappend
shopt -s checkwinsize
shopt -s globstar

# ---------------------------------------------------------------------------
# POSIX environment shared with other shells (PATH, RIPGREP_CONFIG_PATH, EDITOR / VISUAL, …)
# ---------------------------------------------------------------------------
[[ -r "${HOME}/.config/devboost/env.sh" ]] && source "${HOME}/.config/devboost/env.sh"

# ---------------------------------------------------------------------------
# Shell tool initialisers — managed by dev-boost (single copy; no duplication)
# ---------------------------------------------------------------------------

# fzf — sourced FIRST so atuin (below) binds Ctrl-R last and owns it; fzf keeps
# Ctrl-T (files) and Alt-C (cd). Sourcing fzf after atuin steals Ctrl-R from atuin.
# fzf >= 0.48 prints its own integration (`fzf --bash`); older builds (Ubuntu 24.04 ships
# 0.44) reject the flag, so fall back to the distro's script paths.
if command -v fzf &>/dev/null && _devboost_fzf=$(fzf --bash 2>/dev/null); then
  eval "$_devboost_fzf"
else
  [ -f /usr/share/fzf/shell/key-bindings.bash ] && source /usr/share/fzf/shell/key-bindings.bash
  [ -f /usr/share/fzf/shell/completion.bash ]   && source /usr/share/fzf/shell/completion.bash
  [ -f /usr/share/doc/fzf/examples/key-bindings.bash ] && source /usr/share/doc/fzf/examples/key-bindings.bash
  [ -f "${HOME}/.fzf.bash" ] && source "${HOME}/.fzf.bash"
fi
unset _devboost_fzf

# starship — cross-shell prompt
command -v starship &>/dev/null && eval "$(starship init bash)"

# atuin — shell history search.
# On bash, atuin appends its hooks to precmd_functions/preexec_functions, which
# only exist (and only get invoked) if bash-preexec (or ble.sh) is loaded first.
# Without it, `atuin init bash` binds Ctrl-R but NEVER records commands — atuin
# reads as "not configured". bash-preexec is vendored via dotfiles (dot_bash-preexec.sh)
# so this works on Fedora and Ubuntu alike, not just where atuin's installer drops it.
if command -v atuin &>/dev/null; then
  [ -f "${HOME}/.bash-preexec.sh" ] && source "${HOME}/.bash-preexec.sh"
  eval "$(atuin init bash)"
fi

# zoxide — smarter cd
command -v zoxide &>/dev/null && eval "$(zoxide init bash)"

# direnv — per-directory env
command -v direnv &>/dev/null && eval "$(direnv hook bash)"

# mise — polyglot runtime/version manager; puts managed runtimes (node/python/…)
# on PATH for interactive shells. Without this, mise-installed tools aren't found.
command -v mise &>/dev/null && eval "$(mise activate bash)"

# ---------------------------------------------------------------------------
# Helpers (dev, expose, pw-*, …) and aliases — shared with zsh
# ---------------------------------------------------------------------------
[[ -r "${HOME}/.config/devboost/aliases.sh" ]] && source "${HOME}/.config/devboost/aliases.sh"
```

(The old `Path additions` and `ripgrep` sections are now in `env.sh`. The Ubuntu `/usr/share/doc/fzf/examples/key-bindings.bash` fallback is new: Ubuntu 24.04's fzf 0.44 keeps its scripts there.)

- [ ] **Step 7: Run to verify pass**

Run: `uv run pytest tests/dotfiles tests/modules/test_shell.py -v && uv run ruff check && uv run mypy`
Expected: PASS. The zsh cases run on the Mac; on a host without zsh they skip. The Z1 env tests still pass.

- [ ] **Step 8: Commit**

```bash
git add ../dotfiles/dot_config/devboost/env.sh ../dotfiles/dot_config/devboost/aliases.sh ../dotfiles/dot_config/devboost/shell.bash tests/dotfiles tests/modules/test_shell.py
git commit -m "refactor(shell): split POSIX env.sh and shared aliases.sh out of shell.bash; fzf --bash with fallback"
```

---
### Task 6: zsh on macOS — `shell.zsh`, `~/.zshrc`, `~/.zprofile`, and `~/.bash_profile` for `bash -lc`

**Files:**
- Create: `dotfiles/dot_config/devboost/shell.zsh`, `dotfiles/dot_zshrc`, `dotfiles/dot_zprofile`, `dotfiles/dot_bash_profile`
- Test: `engine/tests/dotfiles/test_zsh.py` (create)

**Interfaces:**
- Consumes: `env.sh`, `aliases.sh` (Task 5); fixtures `frag_home`, `bin_dir`, `make_bin` (Task 5).
- Produces: `~/.zshrc` sources `~/.config/devboost/shell.zsh`, then `~/.zshrc.local`. `ZshConfig` (Task 8) checks for the literal line `[[ -r "${HOME}/.config/devboost/shell.zsh" ]] && source "${HOME}/.config/devboost/shell.zsh"`. `~/.zprofile` runs `brew shellenv` and `mise activate zsh --shims`, then sources `~/.zprofile.local`. `~/.bash_profile` gives `bash -lc` the same brew, mise-shims and `env.sh` environment. `.chezmoiignore` (Task 7) keeps all three rc files off Linux.

- [ ] **Step 1: Write the failing tests** — `tests/dotfiles/test_zsh.py`

```python
"""zsh on macOS: env + aliases load, fzf before atuin, plugins last (highlighting, then
autosuggestions), ~/.zshrc.local after everything; login files for zsh and `bash -lc`."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from .conftest import DOT, FRAGMENTS, MakeBin

ZSH = shutil.which("zsh")
BASH = shutil.which("bash") or "bash"
pytestmark = pytest.mark.skipif(ZSH is None, reason="zsh not installed")


def _zsh(home: Path, bin_dir: Path, script: str, *, brew: Path | None = None,
         login: bool = False) -> subprocess.CompletedProcess[str]:
    assert ZSH is not None
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": str(home),
        "ZDOTDIR": str(home),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "TERM": "dumb",
        "HOMEBREW_PREFIX": str(brew or home / "no-brew"),
    }
    flag = "-l" if login else "-i"
    return subprocess.run([ZSH, flag, "-c", script], env=env, capture_output=True, text=True,
                          timeout=30)


@pytest.fixture
def zsh_home(frag_home: Path, make_bin: MakeBin) -> Path:
    shutil.copy(DOT / "dot_zshrc", frag_home / ".zshrc")
    make_bin("ssh", "exit 0")  # `dev` is defined only where ssh exists
    return frag_home


def test_rc_files_parse() -> None:
    assert ZSH is not None
    for f in (FRAGMENTS / "shell.zsh", DOT / "dot_zshrc", DOT / "dot_zprofile"):
        res = subprocess.run([ZSH, "-n", str(f)], capture_output=True, text=True)
        assert res.returncode == 0, (f, res.stderr)
    res = subprocess.run([BASH, "-n", str(DOT / "dot_bash_profile")], capture_output=True,
                         text=True)
    assert res.returncode == 0, res.stderr


def test_every_managed_rc_file_carries_the_marker() -> None:
    for f in (FRAGMENTS / "shell.zsh", DOT / "dot_zshrc", DOT / "dot_zprofile",
              DOT / "dot_bash_profile"):
        assert "devboost — managed by chezmoi" in f.read_text(encoding="utf-8"), f


def test_zshrc_loads_env_and_aliases_then_the_local_file(zsh_home: Path, bin_dir: Path) -> None:
    (zsh_home / ".zshrc.local").write_text("typeset -g LOCAL_SAW_DEV=$+functions[dev]\n",
                                           encoding="utf-8")
    res = _zsh(zsh_home, bin_dir, 'print -r -- "$LOCAL_SAW_DEV|$RIPGREP_CONFIG_PATH"')
    assert res.stdout.strip() == f"1|{zsh_home}/.config/ripgrep/ripgreprc", res.stderr


def test_fzf_loads_before_atuin_so_atuin_owns_ctrl_r(zsh_home: Path, bin_dir: Path,
                                                    make_bin: MakeBin) -> None:
    make_bin("fzf", "[ \"$1\" = --zsh ] && echo 'typeset -g FZF_ZSH_INIT=1'")
    make_bin("atuin", "echo 'typeset -g ATUIN_SAW_FZF=$+FZF_ZSH_INIT'")
    res = _zsh(zsh_home, bin_dir, 'print -r -- "$ATUIN_SAW_FZF"')
    assert res.stdout.strip() == "1", res.stderr


def test_plugins_load_last_highlighting_before_autosuggestions(
    zsh_home: Path, bin_dir: Path, tmp_path: Path
) -> None:
    brew = tmp_path / "brew"
    hl = brew / "share" / "zsh-syntax-highlighting" / "zsh-syntax-highlighting.zsh"
    au = brew / "share" / "zsh-autosuggestions" / "zsh-autosuggestions.zsh"
    hl.parent.mkdir(parents=True)
    au.parent.mkdir(parents=True)
    hl.write_text("typeset -g HL_AFTER_ALIASES=$+functions[dev]\n", encoding="utf-8")
    au.write_text("typeset -g AS_AFTER_HL=$+HL_AFTER_ALIASES\n", encoding="utf-8")
    res = _zsh(zsh_home, bin_dir, 'print -r -- "$HL_AFTER_ALIASES|$AS_AFTER_HL"', brew=brew)
    assert res.stdout.strip() == "1|1", res.stderr


def test_history_completion_cache_and_open_files(zsh_home: Path, bin_dir: Path) -> None:
    res = _zsh(zsh_home, bin_dir,
               'print -r -- "$HISTSIZE $SAVEHIST"; [[ -o sharehistory ]] && print share; ulimit -n')
    lines = res.stdout.split()
    assert lines[:3] == ["100000", "100000", "share"], res.stderr
    assert list((zsh_home / ".cache" / "zsh").glob("zcompdump-*")), "compinit dump not cached"
    if sys.platform == "darwin":
        assert int(lines[3]) > 256  # raised from macOS's default soft limit


def test_zprofile_sources_its_local_file(zsh_home: Path, bin_dir: Path) -> None:
    shutil.copy(DOT / "dot_zprofile", zsh_home / ".zprofile")
    (zsh_home / ".zprofile.local").write_text("typeset -gx ZPROFILE_LOCAL=1\n",
                                              encoding="utf-8")
    res = _zsh(zsh_home, bin_dir, 'print -r -- "$ZPROFILE_LOCAL"', login=True)
    assert res.stdout.strip().splitlines()[-1] == "1", res.stderr


def test_bash_login_gets_the_shared_env(frag_home: Path, bin_dir: Path) -> None:
    shutil.copy(DOT / "dot_bash_profile", frag_home / ".bash_profile")
    res = subprocess.run(
        [BASH, "-l", "-c", 'printf "%s" "$RIPGREP_CONFIG_PATH"'],
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(frag_home), "TERM": "dumb"},
        capture_output=True, text=True, timeout=30,
    )
    assert res.stdout.endswith(f"{frag_home}/.config/ripgrep/ripgreprc"), res.stderr
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/dotfiles/test_zsh.py -v`
Expected: FAIL: `dot_zshrc` / `shell.zsh` do not exist (`FileNotFoundError`).

- [ ] **Step 3: Create the files**

`dotfiles/dot_config/devboost/shell.zsh`:

```zsh
# ~/.config/devboost/shell.zsh — dev-boost's interactive zsh config (macOS).
#
# Sourced by ~/.zshrc. The environment (env.sh) and the dev/expose/pw-* helpers and
# aliases (aliases.sh) are shared with bash (shell.bash); only zsh-specific parts live here.
#
# devboost — managed by chezmoi; edit dotfiles/dot_config/devboost/shell.zsh in the
# dev-boost repo. Do not edit this file manually.

[[ -r "${HOME}/.config/devboost/env.sh" ]] && source "${HOME}/.config/devboost/env.sh"

# ---------------------------------------------------------------------------
# History — shared live between sessions; atuin adds search on top.
# ---------------------------------------------------------------------------
HISTFILE="${HOME}/.zsh_history"
HISTSIZE=100000
SAVEHIST=100000
setopt share_history hist_ignore_all_dups hist_reduce_blanks extended_history
setopt interactive_comments

# ---------------------------------------------------------------------------
# Completion — Homebrew's site-functions (brew, gh, git, …) before compinit. The dump is
# cached per zsh version; -i skips insecure dirs instead of stopping to ask.
# ---------------------------------------------------------------------------
_devboost_brew="${HOMEBREW_PREFIX:-/opt/homebrew}"
[[ -d "${_devboost_brew}/share/zsh/site-functions" ]] &&
  fpath=("${_devboost_brew}/share/zsh/site-functions" $fpath)
_devboost_zcache="${XDG_CACHE_HOME:-${HOME}/.cache}/zsh"
[[ -d "$_devboost_zcache" ]] || mkdir -p "$_devboost_zcache"
autoload -Uz compinit
compinit -i -d "${_devboost_zcache}/zcompdump-${ZSH_VERSION}"

# ---------------------------------------------------------------------------
# Tool initialisers. fzf goes FIRST so atuin (below) binds Ctrl-R last and owns it;
# fzf keeps Ctrl-T (files) and Alt-C (cd).
# ---------------------------------------------------------------------------
(( $+commands[fzf] ))      && source <(fzf --zsh)
(( $+commands[mise] ))     && eval "$(mise activate zsh)"
(( $+commands[starship] )) && eval "$(starship init zsh)"
(( $+commands[atuin] ))    && eval "$(atuin init zsh)"
(( $+commands[zoxide] ))   && eval "$(zoxide init zsh)"
(( $+commands[direnv] ))   && eval "$(direnv hook zsh)"

# Helpers (dev, expose, pw-*, …) and aliases — shared with bash.
[[ -r "${HOME}/.config/devboost/aliases.sh" ]] && source "${HOME}/.config/devboost/aliases.sh"

# Open files for dev servers and file watchers. macos-limits raises the kernel cap to
# 524288; until then, take the current per-process maximum.
ulimit -n 524288 2>/dev/null ||
  ulimit -n "$(sysctl -n kern.maxfilesperproc 2>/dev/null || echo 10240)" 2>/dev/null

# ---------------------------------------------------------------------------
# Plugins LAST — they wrap every widget defined above. Syntax highlighting first, then
# autosuggestions (Homebrew formulae, installed by the zsh-plugins module).
# ---------------------------------------------------------------------------
[[ -r "${_devboost_brew}/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh" ]] &&
  source "${_devboost_brew}/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh"
[[ -r "${_devboost_brew}/share/zsh-autosuggestions/zsh-autosuggestions.zsh" ]] &&
  source "${_devboost_brew}/share/zsh-autosuggestions/zsh-autosuggestions.zsh"
unset _devboost_brew _devboost_zcache
```

`dotfiles/dot_zshrc`:

```zsh
# ~/.zshrc — dev-boost managed interactive zsh configuration (macOS).
# devboost — managed by chezmoi; edit dotfiles/dot_zshrc in the dev-boost repo.
# Do not edit this file manually: machine-specific lines go in ~/.zshrc.local.
# A ~/.zshrc that existed before dev-boost was kept as ~/.zshrc.pre-devboost.

[[ -r "${HOME}/.config/devboost/shell.zsh" ]] && source "${HOME}/.config/devboost/shell.zsh"
[[ -r "${HOME}/.zshrc.local" ]] && source "${HOME}/.zshrc.local"
```

`dotfiles/dot_zprofile`:

```zsh
# ~/.zprofile — dev-boost managed login environment (macOS).
# devboost — managed by chezmoi; edit dotfiles/dot_zprofile in the dev-boost repo.
# Do not edit this file manually: machine-specific lines go in ~/.zprofile.local.
#
# Login shells only — including the shells GUI apps (Zed, VS Code) start to read your
# environment. Interactive setup lives in ~/.zshrc → ~/.config/devboost/shell.zsh.

if [[ -x /opt/homebrew/bin/brew ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv zsh)"
fi
# mise's shims (no prompt hook): IDEs and other non-interactive consumers get the pinned
# node/python/…; interactive shells switch to `mise activate zsh` in shell.zsh.
if (( $+commands[mise] )); then
  eval "$(mise activate zsh --shims)"
fi
[[ -r "${HOME}/.zprofile.local" ]] && source "${HOME}/.zprofile.local"
```

`dotfiles/dot_bash_profile`:

```bash
# ~/.bash_profile — dev-boost managed (macOS). zsh is the login shell here; this file is
# for `bash -lc …` launchers (MCP servers, scripts), so they see brew, mise's shims and
# dev-boost's PATH like every other shell.
# devboost — managed by chezmoi; edit dotfiles/dot_bash_profile in the dev-boost repo.

if [ -x /opt/homebrew/bin/brew ]; then
  eval "$(/opt/homebrew/bin/brew shellenv bash)"
fi
if command -v mise >/dev/null 2>&1; then
  eval "$(mise activate bash --shims)"
fi
if [ -r "${HOME}/.config/devboost/env.sh" ]; then
  . "${HOME}/.config/devboost/env.sh"
fi
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/dotfiles -v && uv run ruff check && uv run mypy`
Expected: PASS on the Mac. On a host without zsh, the zsh tests skip.

- [ ] **Step 5: Commit**

```bash
git add ../dotfiles/dot_config/devboost/shell.zsh ../dotfiles/dot_zshrc ../dotfiles/dot_zprofile ../dotfiles/dot_bash_profile tests/dotfiles/test_zsh.py
git commit -m "feat(shell): zsh config for macOS — shell.zsh, zshrc/zprofile with .local hooks, bash_profile"
```

---

### Task 7: `.chezmoiignore` — Darwin-safe Omarchy guard and per-OS file sets

**Files:**
- Modify: `dotfiles/.chezmoiignore`
- Test: `engine/tests/dotfiles/test_chezmoiignore.py` (create)

**Interfaces:**
- Consumes: `chezmoi_apply` fixture (Task 5); the rc files (Task 6).
- Produces: Darwin never applies `.bashrc`, `.bash-preexec.sh`, `.config/systemd` or `.config/caddy`. Linux never applies `.zshrc`, `.zprofile`, `.bash_profile` or `.config/aerospace`. The Omarchy list is unchanged, and it is only evaluated on Linux.

- [ ] **Step 1: Write the failing tests** — `tests/dotfiles/test_chezmoiignore.py`

```python
"""The chezmoi source applies cleanly on each OS, with the right per-OS file set."""

from __future__ import annotations

from .conftest import DOT, Apply

MAC_ONLY = (".zshrc", ".zprofile", ".bash_profile")
LINUX_ONLY = (".bashrc", ".bash-preexec.sh", ".config/systemd")


def test_macos_apply_succeeds_with_the_zsh_files(chezmoi_apply: Apply) -> None:
    # Before the fix this failed: `.chezmoi.osRelease` does not exist on Darwin.
    home = chezmoi_apply("darwin", "macos")
    for f in (*MAC_ONLY, ".config/devboost/shell.zsh", ".config/devboost/env.sh"):
        assert (home / f).exists(), f
    for f in (*LINUX_ONLY, ".config/caddy"):
        assert not (home / f).exists(), f


def test_fedora_apply_has_bash_and_no_macos_files(chezmoi_apply: Apply) -> None:
    home = chezmoi_apply("linux", "fedora")
    assert (home / ".bashrc").exists()
    assert (home / ".tmux.conf").exists()
    for f in MAC_ONLY:
        assert not (home / f).exists(), f


def test_omarchy_keeps_its_own_files(chezmoi_apply: Apply) -> None:
    home = chezmoi_apply("linux", "omarchy")
    for f in (".bashrc", ".tmux.conf", ".config/starship.toml", ".config/ghostty", *MAC_ONLY):
        assert not (home / f).exists(), f
    assert (home / ".config" / "devboost" / "shell.bash").exists()


def test_omarchy_guard_is_evaluated_only_on_linux() -> None:
    text = (DOT / ".chezmoiignore").read_text(encoding="utf-8")
    assert '{{ if and (eq .chezmoi.os "linux") (eq .chezmoi.osRelease.id "omarchy") -}}' in text
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/dotfiles/test_chezmoiignore.py -v`
Expected: FAIL. `test_macos_apply_…` fails with `CalledProcessError` (stderr: `map has no entry for key "id"`), and the Fedora apply still writes `.zshrc`.

- [ ] **Step 3: Replace `dotfiles/.chezmoiignore`**

```
{{/*
   dev-boost chezmoi ignore list.

   1. Per-OS files. macOS runs zsh, so bash's rc files and the Linux-only services
      (systemd user units, caddy) are not applied there; Linux runs bash, so the macOS
      login files and the AeroSpace config are not applied there.

   2. Omarchy. The distro ships its own copies of the files listed in its block and
      REPLACES the user's version during `omarchy update`: migrations call
      `omarchy-refresh-config`, which does `cp -f <default> <user file>` (keeping a .bak).
      A chezmoi-managed file at one of these paths therefore loses the race on every
      update and shows as permanent drift afterwards. So on Omarchy dev-boost is a tenant
      in ~/.config, not the landlord: it skips the paths the platform owns and delivers its
      own shell config as ~/.config/devboost/shell.bash, which the bash-config module
      sources from Omarchy's own ~/.bashrc. Everything with no Omarchy counterpart
      (atuin, ripgrep, bat, fresh, caddy, fleet, systemd units, ~/.claude, ~/.local/bin)
      still applies normally.

   `.chezmoi.osRelease` exists only on Linux and a missing key is a template error, so the
   Omarchy test is guarded by the OS test (`and` stops at the first false argument).
*/ -}}
{{ if eq .chezmoi.os "darwin" -}}
.bashrc
.bash-preexec.sh
.config/systemd
.config/caddy
{{ else -}}
.zshrc
.zprofile
.bash_profile
.config/aerospace
{{ end -}}
{{ if and (eq .chezmoi.os "linux") (eq .chezmoi.osRelease.id "omarchy") -}}
.bashrc
.tmux.conf
.config/starship.toml
.config/btop
.config/lazygit
.config/herdr
.config/git/config
.config/ghostty
.config/wezterm
{{ end -}}
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/dotfiles tests/modules/test_shell.py -v`
Expected: PASS. The existing `test_chezmoiignore_protects_omarchy_owned_configs` still passes, because every Omarchy path is still on its own line and the guard still contains `.chezmoi.osRelease.id "omarchy"`.

- [ ] **Step 5: Commit**

```bash
git add ../dotfiles/.chezmoiignore tests/dotfiles/test_chezmoiignore.py
git commit -m "fix(dotfiles): chezmoiignore no longer fails on macOS; per-OS rc file sets"
```

---
### Task 8: zsh modules, foreign rc files set aside, Linux-only `bash-config`, profiles

**Files:**
- Modify: `engine/src/devboost/modules/shell.py` (new `ZshPlugins`, `ZshConfig`, `keep_foreign_rc_files`; `Dotfiles`, `BashConfig`)
- Modify: `profiles.toml` (`shell`, `terminal`)
- Modify: `engine/tests/core/test_macos_contract.py` (`KNOWN_GAPS`)
- Test: `engine/tests/modules/test_zsh_modules.py` (create)

**Interfaces:**
- Consumes: `BrewFormula` (Task 1), `Bash` (Task 2), `dot_zshrc` / `shell.zsh` (Task 6).
- Produces:
  - `ZshPlugins` (`zsh-plugins`): `families = ("macos",)`, `per_os.macos = BrewFormula("zsh-autosuggestions", "zsh-syntax-highlighting")`, `self_updating = True`.
  - `ZshConfig` (`zsh-config`): `families = ("macos",)`, `requires = (Dotfiles, ZshPlugins)`, `portable = True`. Verify: `~/.zshrc` has the managed marker and the `shell.zsh` source line, and `~/.config/devboost/shell.zsh` exists.
  - `keep_foreign_rc_files(home: Path) -> list[Path]`: moves each non-dev-boost `.zshrc` / `.zprofile` / `.bash_profile` to `<name>.pre-devboost` (or `.pre-devboost.N`) and returns the backups.
  - `Dotfiles.portable = True`; on macOS, `install` calls `keep_foreign_rc_files` before `chezmoi apply`.
  - `BashConfig.families = ("fedora", "debian", "arch")`.
  - `shell` and `terminal` contain `zsh-config` and `bash`; `shell` also contains `zsh-plugins`. `terminal` gets `zsh-plugins` through `ZshConfig.requires`.

- [ ] **Step 1: Write the failing tests** — `tests/modules/test_zsh_modules.py`

```python
from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules.shell import (
    BashConfig,
    Dotfiles,
    ZshConfig,
    ZshPlugins,
    keep_foreign_rc_files,
)

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
REPO_ROOT = Path(__file__).resolve().parents[3]
DOT = REPO_ROOT / "dotfiles"
MARKER = "devboost — managed by chezmoi"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


def test_zsh_plugins_are_brew_formulae_on_macos_only() -> None:
    assert ZshPlugins.families == ("macos",)
    assert ZshPlugins.self_updating is True
    ex = FakeExecutor()
    ZshPlugins().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [
        ["brew", "install", "--formula", "-y", "zsh-autosuggestions", "zsh-syntax-highlighting"]
    ]


def test_zsh_config_needs_the_dotfiles_and_the_plugins() -> None:
    assert ZshConfig.families == ("macos",)
    assert {Dotfiles, ZshPlugins} <= set(ZshConfig.requires)


def test_zsh_config_verify_reads_the_applied_files(home: Path) -> None:
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    assert ZshConfig().verify(ctx) is False
    frag = home / ".config" / "devboost" / "shell.zsh"
    frag.parent.mkdir(parents=True)
    frag.write_text("# fragment\n", encoding="utf-8")
    (home / ".zshrc").write_text((DOT / "dot_zshrc").read_text(encoding="utf-8"),
                                 encoding="utf-8")
    assert ZshConfig().verify(ctx) is True
    (home / ".zshrc").write_text("export ZSH=$HOME/.oh-my-zsh\n", encoding="utf-8")
    assert ZshConfig().verify(ctx) is False


def test_foreign_rc_files_are_kept_and_managed_ones_left(home: Path) -> None:
    (home / ".zshrc").write_text("mine\n", encoding="utf-8")
    (home / ".zprofile").write_text(f"# {MARKER}\n", encoding="utf-8")
    (home / ".bash_profile").symlink_to(home / "gone")  # a dangling link counts too
    kept = keep_foreign_rc_files(home)
    assert {p.name for p in kept} == {".zshrc.pre-devboost", ".bash_profile.pre-devboost"}
    assert (home / ".zshrc.pre-devboost").read_text(encoding="utf-8") == "mine\n"
    assert not (home / ".zshrc").exists()
    assert (home / ".zprofile").read_text(encoding="utf-8") == f"# {MARKER}\n"


def test_an_earlier_backup_is_never_overwritten(home: Path) -> None:
    (home / ".zshrc.pre-devboost").write_text("first\n", encoding="utf-8")
    (home / ".zshrc").write_text("second\n", encoding="utf-8")
    assert [p.name for p in keep_foreign_rc_files(home)] == [".zshrc.pre-devboost.1"]
    assert (home / ".zshrc.pre-devboost").read_text(encoding="utf-8") == "first\n"


def test_dotfiles_sets_a_foreign_zshrc_aside_on_macos_before_applying(home: Path) -> None:
    (home / ".zshrc").write_text("mine\n", encoding="utf-8")
    ex = FakeExecutor()
    Dotfiles().install(Ctx(os=MAC, ex=ex))
    assert (home / ".zshrc.pre-devboost").read_text(encoding="utf-8") == "mine\n"
    assert any(c[:2] == ["chezmoi", "apply"] for c in ex.calls)


def test_dotfiles_leaves_rc_files_alone_on_linux(home: Path) -> None:
    (home / ".zshrc").write_text("mine\n", encoding="utf-8")
    Dotfiles().install(Ctx(os=FEDORA, ex=FakeExecutor()))
    assert (home / ".zshrc").read_text(encoding="utf-8") == "mine\n"
    assert not (home / ".zshrc.pre-devboost").exists()


def test_bash_config_is_linux_only() -> None:
    assert BashConfig.families == ("fedora", "debian", "arch")


def test_terminal_and_shell_install_the_zsh_setup() -> None:
    profiles = load_profiles(REPO_ROOT / "profiles.toml")
    modules = load()
    for name in ("terminal", "shell"):
        planned = toposort(expand([name], profiles, modules), modules)
        for want in ("zsh-config", "zsh-plugins", "bash", "dotfiles", "ghostty"):
            assert want in planned, (name, want)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_zsh_modules.py -v`
Expected: FAIL: `ImportError: cannot import name 'ZshConfig'`.

- [ ] **Step 3: Implement** in `engine/src/devboost/modules/shell.py`

Add after the `_home()` helper:

```python
#: Every dev-boost managed dotfile carries this marker (dot_zshrc, dot_bashrc, …).
_MANAGED_MARKER = "devboost — managed by chezmoi"
#: macOS login/rc files the dotfiles take over (spec §3). A pre-existing one that is not
#: dev-boost's is set aside before `chezmoi apply --force` would overwrite it.
_TAKEN_OVER = (".zshrc", ".zprofile", ".bash_profile")


def keep_foreign_rc_files(home: Path) -> list[Path]:
    """Move each foreign rc file to ``<name>.pre-devboost`` and return the backups.

    An earlier backup is never replaced: a later foreign file becomes
    ``<name>.pre-devboost.1``, ``.2``, … Content is not merged — the managed files source
    ``~/.zshrc.local`` / ``~/.zprofile.local`` for machine-specific lines.
    """
    kept: list[Path] = []
    for name in _TAKEN_OVER:
        path = home / name
        if not (path.is_file() or path.is_symlink()):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""  # a dangling symlink: nothing of ours, set it aside too
        if _MANAGED_MARKER in text:
            continue
        backup = home / f"{name}.pre-devboost"
        n = 0
        while backup.exists() or backup.is_symlink():
            n += 1
            backup = home / f"{name}.pre-devboost.{n}"
        path.rename(backup)
        kept.append(backup)
    return kept
```

In `class Dotfiles`, add under `profiles`:

```python
    # Runs unchanged on macOS: chezmoi comes from brew, and the source picks each OS's
    # files itself (.chezmoiignore). install() also sets aside foreign zsh/bash rc files.
    portable = True
```

In `Dotfiles.install`, add directly after the `if not src.is_dir(): … return` block, before the `--force` comment:

```python
        if ctx.os.family == "macos":
            for backup in keep_foreign_rc_files(_home()):
                log.ok(
                    f"dotfiles: kept your previous ~/{backup.name.split('.pre-devboost')[0]}"
                    f" as ~/{backup.name} — machine-specific lines belong in"
                    " ~/.zshrc.local or ~/.zprofile.local"
                )
```

In `class BashConfig`, add under `profiles`:

```python
    # bash is the interactive shell on Linux only; macOS runs zsh (zsh-config).
    families: ClassVar[tuple[str, ...]] = ("fedora", "debian", "arch")
```

Add after `BashConfig`:

```python
@register
class ZshPlugins(Module):
    name = "zsh-plugins"
    category = "shell"
    description = "zsh-autosuggestions + zsh-syntax-highlighting (sourced by shell.zsh)."
    profiles = ("shell",)
    # zsh is the interactive shell only on macOS (bash on Linux) — spec §2.
    families: ClassVar[tuple[str, ...]] = ("macos",)
    self_updating = True  # `devboost install --update` → brew upgrade
    per_os = OsMap(macos=BrewFormula("zsh-autosuggestions", "zsh-syntax-highlighting"))


#: The line dot_zshrc uses to load dev-boost's zsh config (checked by zsh-config).
_ZSH_SOURCE_LINE = (
    '[[ -r "${HOME}/.config/devboost/shell.zsh" ]] && source "${HOME}/.config/devboost/shell.zsh"'
)


@register
class ZshConfig(Module):
    name = "zsh-config"
    category = "shell"
    description = "Check dev-boost's zsh config is live (~/.zshrc → shell.zsh) — macOS."
    requires = (Dotfiles, ZshPlugins)
    profiles = ("shell",)
    families: ClassVar[tuple[str, ...]] = ("macos",)
    # Written for macOS: it only reads the files the dotfiles module applied.
    portable = True

    def verify(self, ctx: Ctx) -> bool:
        zshrc = _home() / ".zshrc"
        if not zshrc.is_file() or not (_home() / ".config/devboost/shell.zsh").is_file():
            return False
        text = zshrc.read_text(encoding="utf-8")
        return _MANAGED_MARKER in text and _ZSH_SOURCE_LINE in text

    def install(self, ctx: Ctx) -> None:
        # ~/.zshrc is written by the dotfiles module (a marker check, like bash-config).
        log.warn(
            "zsh-config: ~/.zshrc is not dev-boost's — run `devboost install dotfiles --force`"
        )
```

`profiles.toml`:
- `shell`: add `"zsh-config","zsh-plugins","bash"` after `"bash-config"`, so the line reads `shell = ["starship","bash-config","zsh-config","zsh-plugins","bash","ghostty","nerd-fonts","dotfiles","claude-statusline",` (the rest unchanged).
- `terminal`: add `"zsh-config","bash"` after `"bash-config"`.

In `tests/core/test_macos_contract.py`, delete from `KNOWN_GAPS`: `"bash-config"`, `"dotfiles"`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/modules tests/core tests/cli -v && uv run mypy && uv run ruff check`
Expected: PASS. `test_bash_config_appends_source_line_on_omarchy` and `test_bash_config_verify` pass: they call the module directly, and `families` only filters the plan.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/modules/shell.py ../profiles.toml tests/modules/test_zsh_modules.py tests/core/test_macos_contract.py
git commit -m "feat(shell): zsh-config and zsh-plugins for macOS; keep foreign rc files; bash-config Linux-only"
```

---
### Task 9: Portable scripts — one resource probe for tmux, starship, WezTerm and the Claude status line

**Files:**
- Create: `dotfiles/dot_local/bin/executable_devboost-resources`
- Modify: `dotfiles/dot_config/tmux/executable_resources.sh`, `dotfiles/dot_config/tmux/executable_pw-autoregister.sh`, `dotfiles/dot_config/starship.toml`, `dotfiles/dot_config/wezterm/config/status.lua`, `dotfiles/dot_config/wezterm/README.md`, `dotfiles/private_dot_claude/executable_statusline.sh`
- Modify: `engine/src/devboost/modules/shell.py` (`ClaudeStatusline.portable`), `engine/tests/core/test_macos_contract.py` (`KNOWN_GAPS`)
- Test: `engine/tests/dotfiles/test_portable_scripts.py` (create)

**Interfaces:**
- Consumes: fixtures `bin_dir`, `make_bin` (Task 5).
- Produces: `~/.local/bin/devboost-resources` prints one line, `<ram_used%> <disk_used%> <disk_free_GiB>` (integers). It honours `DEVBOOST_MEMINFO` (default `/proc/meminfo`) as a test seam. Every gauge reads it: tmux `resources.sh`, the starship `custom.*` modules, WezTerm `status.lua` (`wezterm.home_dir .. "/.local/bin/devboost-resources"`), and `statusline.sh`. `pw-autoregister.sh` uses `timeout`, else `gtimeout`, else skips.

- [ ] **Step 1: Write the failing tests** — `tests/dotfiles/test_portable_scripts.py`

```python
"""The resource probe on Linux and macOS, and every surface that reads it."""

from __future__ import annotations

import json
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from .conftest import DOT, MakeBin

PROBE = DOT / "dot_local" / "bin" / "executable_devboost-resources"
RESOURCES = DOT / "dot_config" / "tmux" / "executable_resources.sh"
PW_AUTO = DOT / "dot_config" / "tmux" / "executable_pw-autoregister.sh"
STATUSLINE = DOT / "private_dot_claude" / "executable_statusline.sh"
STARSHIP = DOT / "dot_config" / "starship.toml"
STATUS_LUA = DOT / "dot_config" / "wezterm" / "config" / "status.lua"
BASH = shutil.which("bash") or "bash"

DF = ("echo 'Filesystem 1024-blocks Used Available Capacity Mounted on'; "
      "echo '/dev/disk3s5 971298980 68717056 875921296 8% /System/Volumes/Data'")


def _probe(bin_dir: Path, extra: dict[str, str]) -> str:
    return subprocess.run(
        ["sh", str(PROBE)], env={"PATH": f"{bin_dir}:/usr/bin:/bin", **extra},
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def test_probe_on_macos(bin_dir: Path, make_bin: MakeBin) -> None:
    make_bin("uname", "echo Darwin")
    make_bin("sysctl", "echo 25769803776")  # 24 GiB
    make_bin("vm_stat", "cat <<'EOF'\n"
             "Mach Virtual Memory Statistics: (page size of 16384 bytes)\n"
             "Pages free:                                    37107.\n"
             "Pages active:                                 631665.\n"
             "Pages inactive:                               629739.\n"
             "Pages speculative:                               466.\n"
             "EOF")
    make_bin("df", DF)
    # used = total - (free + inactive + speculative) * page size → 57 %; 875921296 KiB → 835 G
    assert _probe(bin_dir, {}) == "57 8 835"


def test_probe_on_linux(bin_dir: Path, make_bin: MakeBin, tmp_path: Path) -> None:
    make_bin("uname", "echo Linux")
    make_bin("df", DF)
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:       16000000 kB\nMemAvailable:    4000000 kB\n",
                       encoding="utf-8")
    assert _probe(bin_dir, {"DEVBOOST_MEMINFO": str(meminfo)}) == "75 8 835"


@pytest.fixture
def probe_home(tmp_path: Path) -> tuple[Path, Path]:
    """A HOME whose devboost-resources prints whatever ``<home>/probe.out`` holds."""
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    fake = home / ".local" / "bin" / "devboost-resources"
    fake.write_text(f'#!/bin/sh\ncat "{home}/probe.out"\n', encoding="utf-8")
    fake.chmod(0o755)
    return home, home / "probe.out"


def _tmux_segment(home: Path) -> str:
    return subprocess.run(["sh", str(RESOURCES)], env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
                          capture_output=True, text=True, check=True).stdout


def test_tmux_segment_colors_and_alert(probe_home: tuple[Path, Path]) -> None:
    home, out = probe_home
    out.write_text("40 50 100\n", encoding="utf-8")
    seg = _tmux_segment(home)
    assert "#a6e3a1]󰍛 40%" in seg and "#94e2d5]󰋊 100G" in seg
    out.write_text("65 85 100\n", encoding="utf-8")
    seg = _tmux_segment(home)
    assert "#f9e2af]󰍛 65%" in seg and "#f38ba8]󰋊 100G" in seg
    out.write_text("85 50 5\n", encoding="utf-8")
    assert "⚠" in _tmux_segment(home)
    out.write_text("", encoding="utf-8")  # probe failed → print nothing, never an error
    assert _tmux_segment(home) == ""


def _starship_module(name: str, home: Path, out: Path, value: str) -> tuple[bool, str]:
    mod = tomllib.loads(STARSHIP.read_text(encoding="utf-8"))["custom"][name]
    out.write_text(value + "\n", encoding="utf-8")
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
    when = subprocess.run(["sh", "-c", mod["when"]], env=env).returncode == 0
    cmd = subprocess.run(["sh", "-c", mod["command"]], env=env, capture_output=True, text=True)
    return when, cmd.stdout


def test_starship_gauges_read_the_probe(probe_home: tuple[Path, Path]) -> None:
    home, out = probe_home
    assert _starship_module("ram_ok", home, out, "40 50 100") == (True, "40%")
    assert _starship_module("ram_warn", home, out, "40 50 100")[0] is False
    assert _starship_module("ram_warn", home, out, "65 50 100")[0] is True
    assert _starship_module("ram_crit", home, out, "85 50 100")[0] is True
    assert _starship_module("disk_ok", home, out, "40 50 100") == (True, "100G")
    assert _starship_module("disk_crit", home, out, "40 85 100")[0] is True
    assert _starship_module("res_alert", home, out, "40 50 100")[0] is False
    assert _starship_module("res_alert", home, out, "85 50 5") == (True, "RAM 85% · DISK 5G")


def test_no_surface_reads_proc_or_gnu_df_directly() -> None:
    for f in (RESOURCES, STARSHIP, STATUS_LUA, STATUSLINE):
        text = f.read_text(encoding="utf-8")
        assert "/proc/meminfo" not in text and "-BG" not in text, f
        assert "devboost-resources" in text, f


@pytest.mark.skipif(shutil.which("jq") is None, reason="jq not installed")
def test_claude_statusline_uses_the_probe(probe_home: tuple[Path, Path], tmp_path: Path) -> None:
    home, out = probe_home
    payload = json.dumps({"model": {"display_name": "Opus"}, "cwd": str(tmp_path),
                          "context_window": {"used_percentage": 10},
                          "cost": {"total_cost_usd": 0.5}})
    env = {"HOME": str(home), "PATH": "/opt/homebrew/bin:/usr/bin:/bin", "COLUMNS": "200"}
    out.write_text("40 50 100\n", encoding="utf-8")
    line = subprocess.run([BASH, str(STATUSLINE)], input=payload, env=env,
                          capture_output=True, text=True, check=True).stdout
    assert "40%" in line and "100G" in line
    out.write_text("85 50 100\n", encoding="utf-8")
    line = subprocess.run([BASH, str(STATUSLINE)], input=payload, env=env,
                          capture_output=True, text=True, check=True).stdout
    assert "48;2;243;139;168" in line  # the whole row flooded red when critical


def _pw_autoregister(bin_dir: Path, make_bin: MakeBin, tmp_path: Path, timeout_name: str | None,
                     ) -> str:
    log = tmp_path / "claude.log"
    make_bin("tmux", "echo 'SSH_CONNECTION=100.64.0.7 50000 100.64.0.1 22'")
    make_bin("claude", f'echo "$*" >> "{log}"')
    if timeout_name:
        make_bin(timeout_name, "exit 0")  # the MCP port "answers"
    subprocess.run([BASH, str(PW_AUTO)], env={"PATH": str(bin_dir), "HOME": str(tmp_path)},
                   check=True)
    return log.read_text(encoding="utf-8") if log.exists() else ""


@pytest.mark.parametrize("name", ["timeout", "gtimeout"])
def test_pw_autoregister_uses_timeout_or_gtimeout(name: str, bin_dir: Path, make_bin: MakeBin,
                                                  tmp_path: Path) -> None:
    log = _pw_autoregister(bin_dir, make_bin, tmp_path, name)
    assert "http://100.64.0.7:8931/mcp" in log


def test_pw_autoregister_skips_without_any_timeout(bin_dir: Path, make_bin: MakeBin,
                                                   tmp_path: Path) -> None:
    assert _pw_autoregister(bin_dir, make_bin, tmp_path, None) == ""


def test_scripts_parse_and_lint() -> None:
    for f in (PROBE, RESOURCES):
        assert subprocess.run(["sh", "-n", str(f)]).returncode == 0, f
    for f in (PW_AUTO, STATUSLINE):
        assert subprocess.run([BASH, "-n", str(f)]).returncode == 0, f
    if shutil.which("shellcheck"):
        res = subprocess.run(["shellcheck", "-S", "warning", str(PROBE), str(RESOURCES),
                              str(PW_AUTO)], capture_output=True, text=True)
        assert res.returncode == 0, res.stdout
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/dotfiles/test_portable_scripts.py -v`
Expected: FAIL. The probe file does not exist, the surfaces still read `/proc/meminfo`, and `pw-autoregister` calls `timeout` unconditionally.

- [ ] **Step 3: Create the probe** — `dotfiles/dot_local/bin/executable_devboost-resources`

```sh
#!/bin/sh
# devboost-resources — print "<ram_used%> <disk_used%> <disk_free_GiB>" on one line.
#
# The single RAM/disk probe behind every dev-boost gauge: the tmux status line, the
# starship prompt, WezTerm's status bar and the Claude Code status line.
#   Linux: /proc/meminfo (MemTotal − MemAvailable) + df on /.
#   macOS: sysctl hw.memsize − (free + inactive + speculative pages) from vm_stat, + df on
#          the data volume (/ is the sealed system volume there and reads almost empty).
# `df -Pk` is POSIX on both, so no GNU-only flags.
#
# devboost — managed by chezmoi; edit dotfiles/dot_local/bin/executable_devboost-resources.
set -eu

if [ "$(uname -s)" = "Darwin" ]; then
  total=$(sysctl -n hw.memsize)
  ram=$(vm_stat | awk -v total="$total" '
    /page size of/        { ps = $8 }
    /^Pages free:/        { f = $3 + 0 }
    /^Pages inactive:/    { i = $3 + 0 }
    /^Pages speculative:/ { s = $3 + 0 }
    END { printf "%d", (total - (f + i + s) * ps) * 100 / total }')
  mnt=/System/Volumes/Data
  [ -d "$mnt" ] || mnt=/
else
  ram=$(awk '/^MemTotal:/ { t = $2 } /^MemAvailable:/ { a = $2 } END { printf "%d", (t - a) * 100 / t }' \
    "${DEVBOOST_MEMINFO:-/proc/meminfo}")
  mnt=/
fi

df -Pk "$mnt" | awk -v ram="$ram" 'NR == 2 { sub("%", "", $5); printf "%s %s %d\n", ram, $5, $4 / 1048576 }'
```

- [ ] **Step 4: Rewrite `dotfiles/dot_config/tmux/executable_resources.sh`** (full file)

```sh
#!/bin/sh
# RAM/disk gauges for the tmux status line — the persistent surface that stays visible
# while a full-screen app (fresh, vim, less, htop, lazygit) fills the pane, unlike the
# shell prompt. tmux interprets the #[...] style directives in this output (tmux >= 2.9).
#
# Same probe and thresholds as the starship prompt, WezTerm's status.lua and the Claude
# status line — all read ~/.local/bin/devboost-resources (Linux and macOS):
#   RAM  󰍛 used%   green <60 · yellow 60-79 · red >=80
#   DISK 󰋊 free-G  teal, red at >=80% used
# Critical (RAM >=80 or free <10G) flips the whole segment to a red badge, matching the
# alerts on the other surfaces. Refreshed on status-interval.
set -u

# shellcheck disable=SC2046 # splitting the probe's three numbers into $1 $2 $3 is the point
set -- $("${HOME}/.local/bin/devboost-resources" 2>/dev/null)
[ "$#" -eq 3 ] || exit 0
ram=$1 used=$2 free=$3

green='#a6e3a1'; yellow='#f9e2af'; red='#f38ba8'; teal='#94e2d5'; base='#1e1e2e'

if [ "$ram" -ge 80 ] || [ "$free" -lt 10 ]; then
  # Critical → red badge (wezterm / Claude / starship parity).
  printf '#[fg=%s,bg=%s,bold] ⚠ 󰍛 %s%% 󰋊 %sG #[default]' "$base" "$red" "$ram" "$free"
else
  if [ "$ram" -ge 60 ]; then rc=$yellow; else rc=$green; fi
  if [ "$used" -ge 80 ]; then dc=$red; else dc=$teal; fi
  printf '#[fg=%s]󰍛 %s%%#[default]  #[fg=%s]󰋊 %sG#[default]' "$rc" "$ram" "$dc" "$free"
fi
```

- [ ] **Step 5: `pw-autoregister.sh`** — replace the single line
`timeout 1 bash -c "exec 3<>/dev/tcp/${host}/${port}" 2>/dev/null || exit 0`
with:

```bash
# GNU `timeout` on Linux; macOS has none, but coreutils (brew) installs it as `gtimeout`.
# With neither, skip rather than risk hanging the tmux hook on an unreachable host.
if command -v timeout >/dev/null 2>&1; then
  to=timeout
elif command -v gtimeout >/dev/null 2>&1; then
  to=gtimeout
else
  exit 0
fi
"$to" 1 bash -c "exec 3<>/dev/tcp/${host}/${port}" 2>/dev/null || exit 0
```

- [ ] **Step 6: `starship.toml`** — replace everything from the `# ───…` rule directly above `# System resource gauges` to the end of the file with:

```toml
# ─────────────────────────────────────────────────────────────────────────────
# System resource gauges — the WezTerm status-bar equivalent for a plain shell
# (headless server / SSH, where WezTerm's status.lua isn't running). Mirrors it:
#   RAM  󰍛  used%   green <60 · yellow 60–79 · red ≥80   (status.lua ram_color)
#   DISK 󰋊  free-G  teal, red when the disk is ≥80% used  (status.lua disk cell)
# Threshold coloring is done with mutually-exclusive `when`-gated modules — exactly
# one RAM tier and one DISK tier renders. Every module reads the shared probe
# ~/.local/bin/devboost-resources ("<ram%> <disk-used%> <free-G>"; Linux /proc + df,
# macOS sysctl/vm_stat + df) — the same numbers as tmux, WezTerm and the Claude line.

# Critical-resource badge — WezTerm's left-status alert for the prompt: a red ⚠ badge
# naming the cause when RAM >=80% or free disk <10G. A shell can't repaint the terminal
# bg like WezTerm's gradient, so this red badge at the far left is the prompt-side alert.
# Only renders when critical (gated); clears on recovery.
[custom.res_alert]
when    = '''set -- $("$HOME/.local/bin/devboost-resources"); test "$1" -ge 80 || test "$3" -lt 10'''
command = '''set -- $("$HOME/.local/bin/devboost-resources"); m=""; [ "$1" -ge 80 ] && m="RAM $1%"; [ "$3" -lt 10 ] && m="${m:+$m · }DISK $3G"; printf '%s' "$m"'''
# hex, not palette names: starship silently drops a style when a palette name is used
# as a background (`bg:red`), so the badge would render uncolored. #f38ba8/#1e1e2e are
# the catppuccin red / base.
style   = "bold fg:#1e1e2e bg:#f38ba8"
format  = "[ ⚠ $output ]($style) "

# Each gauge's `when` is gated on `test -z "$TMUX"` so the prompt gauges HIDE inside
# tmux — there the tmux status bar owns RAM/disk (and stays visible even while a
# full-screen app fills the pane). Outside tmux the prompt shows them. No duplication.
# The res_alert badge above is intentionally NOT gated: a critical alert is worth
# showing on every surface. (`{ …; }` keeps each gate's internal `;`/`&&` intact.)
[custom.ram_ok]
when    = '''test -z "$TMUX" && { set -- $("$HOME/.local/bin/devboost-resources"); test "$1" -lt 60; }'''
command = '''set -- $("$HOME/.local/bin/devboost-resources"); printf '%s%%' "$1"'''
symbol  = "󰍛 "
style   = "bold green"
format  = "[$symbol$output]($style) "

[custom.ram_warn]
when    = '''test -z "$TMUX" && { set -- $("$HOME/.local/bin/devboost-resources"); test "$1" -ge 60 && test "$1" -lt 80; }'''
command = '''set -- $("$HOME/.local/bin/devboost-resources"); printf '%s%%' "$1"'''
symbol  = "󰍛 "
style   = "bold yellow"
format  = "[$symbol$output]($style) "

[custom.ram_crit]
when    = '''test -z "$TMUX" && { set -- $("$HOME/.local/bin/devboost-resources"); test "$1" -ge 80; }'''
command = '''set -- $("$HOME/.local/bin/devboost-resources"); printf '%s%%' "$1"'''
symbol  = "󰍛 "
style   = "bold red"
format  = "[$symbol$output]($style) "

# disk free GB — teal normally, red when the disk is ≥80% used
[custom.disk_ok]
when    = '''test -z "$TMUX" && { set -- $("$HOME/.local/bin/devboost-resources"); test "$2" -lt 80; }'''
command = '''set -- $("$HOME/.local/bin/devboost-resources"); printf '%sG' "$3"'''
symbol  = "󰋊 "
style   = "bold teal"
format  = "[$symbol$output]($style)"

[custom.disk_crit]
when    = '''test -z "$TMUX" && { set -- $("$HOME/.local/bin/devboost-resources"); test "$2" -ge 80; }'''
command = '''set -- $("$HOME/.local/bin/devboost-resources"); printf '%sG' "$3"'''
symbol  = "󰋊 "
style   = "bold red"
format  = "[$symbol$output]($style)"
```

Near the top of the file, change `# Single-line layout via $fill so the right-hand context renders in plain bash` to `# Single-line layout via $fill so the right-hand context renders in plain bash and zsh`.

- [ ] **Step 7: `wezterm/config/status.lua`** — replace the `PROBE` definition (the comment line `-- Probe: prints …` and the `[[ … ]]` string) with:

```lua
-- Probe: the shared ~/.local/bin/devboost-resources prints "<ram_used%> <disk_used%>
-- <disk_free_GB>" (Linux /proc + df, macOS sysctl/vm_stat + df on the data volume) —
-- one implementation for WezTerm, tmux, starship and the Claude status line.
local PROBE = wezterm.home_dir .. "/.local/bin/devboost-resources"
```

and in `refresh_resources`, change `wezterm.run_child_process({ "bash", "-c", PROBE })` to `wezterm.run_child_process({ PROBE })`. In `dotfiles/dot_config/wezterm/README.md`, change "Read from a throttled probe (no per-tick process spawn)." to "Read from the shared `~/.local/bin/devboost-resources` probe, throttled (no per-tick process spawn)."

- [ ] **Step 8: `statusline.sh`** — change the Python import line `import json, os, re, unicodedata, sys` to `import json, os, re, subprocess, unicodedata, sys`, then replace the block that starts with the comment `# System resources — RAM used% …` and ends with the second `    pass` (after the `os.statvfs` try) with:

```python
# System resources — RAM used% (green<60·yellow60–79·red≥80) and free disk (teal, red
# when ≥80% used): the shared devboost-resources probe (Linux /proc + df, macOS
# sysctl/vm_stat + df) that tmux, starship and WezTerm read too. Blank on failure, so
# the layout simply omits them.
ram = dfree = dpct = None
try:
    _probe = os.path.expanduser("~/.local/bin/devboost-resources")
    _vals = subprocess.run([_probe], capture_output=True, text=True, timeout=2).stdout.split()
    if len(_vals) == 3:
        ram, dpct, dfree = (int(v) for v in _vals)
except (OSError, ValueError, subprocess.SubprocessError):
    pass
```

Also update the header comment line `# RAM/disk gauges mirror the WezTerm status bar / starship prompt, for headless &` so its sentence ends "…(all read ~/.local/bin/devboost-resources)".

- [ ] **Step 9: Mark the status-line module portable** — in `class ClaudeStatusline` (`modules/shell.py`), under `profiles`:

```python
    # A JSON merge into ~/.claude/settings.json; the script it points at is portable.
    portable = True
```

In `tests/core/test_macos_contract.py`, delete `"claude-statusline"` from `KNOWN_GAPS`.

- [ ] **Step 10: Run to verify pass**

Run: `uv run pytest tests/dotfiles tests/core tests/modules/test_shell.py -v && uv run mypy && uv run ruff check`
Expected: PASS. shellcheck (installed in Task 0) reports nothing at `-S warning`.

- [ ] **Step 11: Commit**

```bash
git add ../dotfiles/dot_local/bin/executable_devboost-resources ../dotfiles/dot_config/tmux ../dotfiles/dot_config/starship.toml ../dotfiles/dot_config/wezterm/config/status.lua ../dotfiles/dot_config/wezterm/README.md ../dotfiles/private_dot_claude/executable_statusline.sh src/devboost/modules/shell.py tests/dotfiles/test_portable_scripts.py tests/core/test_macos_contract.py
git commit -m "feat(dotfiles): one portable RAM/disk probe for tmux, starship, WezTerm and the Claude status line"
```

---
### Task 10: Terminal keys — Ghostty template (Option-as-Alt, Cmd twins, shell integration), WezTerm on Darwin, Ctrl+V retired

**Files:**
- Rename + modify: `dotfiles/dot_config/ghostty/config` → `dotfiles/dot_config/ghostty/config.tmpl` (`git mv`)
- Modify: `dotfiles/dot_config/wezterm/config/keys.lua`, `dotfiles/dot_config/wezterm/wezterm.lua`, `dotfiles/dot_config/wezterm/README.md`
- Delete: `dotfiles/dot_config/wezterm/config/paste.lua`
- Test: `engine/tests/dotfiles/test_terminal_configs.py` (create)

**Interfaces:**
- Consumes: `chezmoi_render` fixture (Task 5).
- Produces: `~/.config/ghostty/config`, rendered per OS. Darwin: `macos-option-as-alt = left`, `macos-titlebar-style = tabs`, and a `super+…` twin for every `ctrl+shift+…` bind. Every OS: `shell-integration = detect`, `shell-integration-features = ssh-env,ssh-terminfo`, `notify-on-command-finish = unfocused`, `theme = Catppuccin Mocha`. No terminal config binds a bare Ctrl+V.

- [ ] **Step 1: Write the failing tests** — `tests/dotfiles/test_terminal_configs.py`

```python
"""Terminal configs: Ghostty per OS (and valid, when Ghostty is installed); WezTerm on
Darwin; no terminal binds Ctrl+V (herdr --remote owns image paste)."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from .conftest import DOT, Render

GHOSTTY = DOT / "dot_config" / "ghostty" / "config.tmpl"
WEZ = DOT / "dot_config" / "wezterm"
_APP = Path("/Applications/Ghostty.app/Contents/MacOS/ghostty")
GHOSTTY_BIN = shutil.which("ghostty") or (str(_APP) if _APP.exists() else None)


def _settings(text: str) -> list[tuple[str, str]]:
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            out.append((key.strip(), value.strip()))
    return out


def _binds(settings: list[tuple[str, str]]) -> list[str]:
    return [v for k, v in settings if k == "keybind"]


def test_ghostty_macos(chezmoi_render: Render) -> None:
    s = _settings(chezmoi_render(GHOSTTY, "darwin", "macos"))
    assert ("macos-option-as-alt", "left") in s  # right Option keeps typing accents
    assert ("macos-titlebar-style", "tabs") in s
    assert ("window-decoration", "none") not in s
    binds = _binds(s)
    for b in binds:
        if b.startswith("ctrl+shift+"):
            rest = b.removeprefix("ctrl+shift+")
            assert f"super+{rest}" in binds or f"super+shift+{rest}" in binds, b


def test_ghostty_linux(chezmoi_render: Render) -> None:
    s = _settings(chezmoi_render(GHOSTTY, "linux", "fedora"))
    assert not any(k.startswith("macos-") for k, _ in s)
    assert not any(b.startswith("super+") for b in _binds(s))
    assert ("window-decoration", "none") in s


@pytest.mark.parametrize(("os_name", "distro"), [("darwin", "macos"), ("linux", "fedora")])
def test_ghostty_everywhere(chezmoi_render: Render, os_name: str, distro: str) -> None:
    s = _settings(chezmoi_render(GHOSTTY, os_name, distro))
    for pair in (("theme", "Catppuccin Mocha"), ("shell-integration", "detect"),
                 ("shell-integration-features", "ssh-env,ssh-terminfo"),
                 ("notify-on-command-finish", "unfocused")):
        assert pair in s, pair
    triggers = [b.partition("=")[0] for b in _binds(s)]
    assert "ctrl+v" not in triggers
    if os_name == "darwin":
        assert "super+v" in triggers
    assert all("toggle_zoom" not in b.replace("toggle_split_zoom", "") for b in _binds(s))


@pytest.mark.skipif(GHOSTTY_BIN is None, reason="ghostty not installed")
def test_ghostty_accepts_the_rendered_config(chezmoi_render: Render, tmp_path: Path) -> None:
    assert GHOSTTY_BIN is not None
    os_name, distro = ("darwin", "macos") if sys.platform == "darwin" else ("linux", "fedora")
    cfg = tmp_path / "config"
    cfg.write_text(chezmoi_render(GHOSTTY, os_name, distro), encoding="utf-8")
    res = subprocess.run([GHOSTTY_BIN, "+validate-config", f"--config-file={cfg}"],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stdout + res.stderr


def test_wezterm_never_binds_ctrl_v_and_paste_lua_is_gone() -> None:
    assert not (WEZ / "config" / "paste.lua").exists()
    assert "config.paste" not in (WEZ / "wezterm.lua").read_text(encoding="utf-8")
    for f in WEZ.rglob("*.lua"):
        text = f.read_text(encoding="utf-8")
        assert not re.search(r'key\s*=\s*"v",\s*mods\s*=\s*"CTRL"\s*,', text), f


def test_wezterm_darwin_keys() -> None:
    keys = (WEZ / "config" / "keys.lua").read_text(encoding="utf-8")
    assert 'wezterm.target_triple:find("darwin")' in keys
    assert '{ key = "a", mods = "CTRL", timeout_milliseconds = 1000 }' in keys  # macOS leader
    assert '{ key = "Space", mods = "CTRL", timeout_milliseconds = 1000 }' in keys
    assert "config.send_composed_key_when_left_alt_is_pressed = false" in keys
    assert 'mods = "SUPER|SHIFT", action = act.DetachDomain' in keys


@pytest.mark.skipif(shutil.which("luac") is None, reason="luac not installed")
def test_wezterm_lua_compiles() -> None:
    for f in WEZ.rglob("*.lua"):
        res = subprocess.run(["luac", "-p", str(f)], capture_output=True, text=True)
        assert res.returncode == 0, (f, res.stderr)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/dotfiles/test_terminal_configs.py -v`
Expected: FAIL. `config.tmpl` is missing (`FileNotFoundError`), `paste.lua` still exists, and `keys.lua` has no Darwin branch.

- [ ] **Step 3: Ghostty** (run from the repo root, then return to `engine/`)

```bash
git mv dotfiles/dot_config/ghostty/config dotfiles/dot_config/ghostty/config.tmpl
```

Replace the content of `dotfiles/dot_config/ghostty/config.tmpl` with:

```
# ~/.config/ghostty/config — dev-boost managed Ghostty configuration (the default terminal).
# devboost — managed by chezmoi; edit dotfiles/dot_config/ghostty/config.tmpl in the dev-boost
# repo. Rendered per OS by chezmoi: the macOS-only lines sit in the darwin blocks.

# Theme — Catppuccin Mocha (a built-in theme; theme names are Title Case since Ghostty 1.2)
theme = Catppuccin Mocha

# Font — JetBrainsMono Nerd Font (installed by the nerd-fonts module)
font-family = "JetBrainsMono Nerd Font Mono"
font-size = 13

window-padding-x = 8
window-padding-y = 8
{{- if eq .chezmoi.os "darwin" }}
# macOS: the tab bar lives in the native titlebar. (window-decoration = none would also
# remove the traffic lights and the rounded corners.)
macos-titlebar-style = tabs
# Left Option is Alt (readline, fzf and herdr Alt bindings); right Option keeps typing
# accents and special characters.
macos-option-as-alt = left
{{- else }}
window-decoration = none
gtk-single-instance = false
{{- end }}

# Shell integration — bash or zsh, detected. Over ssh, forward TERM/COLORTERM and install
# Ghostty's terminfo on the remote host, so tools there render correctly.
shell-integration = detect
shell-integration-features = ssh-env,ssh-terminfo
# A desktop notification when a long command finishes while Ghostty is not focused.
notify-on-command-finish = unfocused

# Key bindings. A bare Ctrl+V is deliberately NOT bound: `herdr --remote` owns image paste.
keybind = ctrl+shift+c=copy_to_clipboard
keybind = ctrl+shift+v=paste_from_clipboard
keybind = ctrl+shift+n=new_window
keybind = ctrl+shift+t=new_tab
keybind = ctrl+shift+right=next_tab
keybind = ctrl+shift+left=previous_tab
keybind = ctrl+shift+z=toggle_split_zoom
keybind = ctrl+equal=increase_font_size:1
keybind = ctrl+minus=decrease_font_size:1
keybind = ctrl+zero=reset_font_size
{{- if eq .chezmoi.os "darwin" }}
# macOS: the Cmd twin of every binding above — both work. Tabs use Cmd+Shift+arrow
# because Cmd+arrow is line start/end in the shell.
keybind = super+c=copy_to_clipboard
keybind = super+v=paste_from_clipboard
keybind = super+n=new_window
keybind = super+t=new_tab
keybind = super+shift+right=next_tab
keybind = super+shift+left=previous_tab
keybind = super+shift+z=toggle_split_zoom
keybind = super+equal=increase_font_size:1
keybind = super+minus=decrease_font_size:1
keybind = super+zero=reset_font_size
{{- end }}
```

- [ ] **Step 4: WezTerm** (opt-in, deprecated — only what the spec asks)

```bash
git rm dotfiles/dot_config/wezterm/config/paste.lua
```

In `dotfiles/dot_config/wezterm/wezterm.lua`, delete the header line `--   config/paste.lua       smart CTRL+V (…)` and the line `require("config.paste").apply(config)`.

In `dotfiles/dot_config/wezterm/config/keys.lua`:
- In the header comment, change the first line to `-- Leader-driven keymap. Leader = CTRL+Space (CTRL+A on macOS, which keeps Ctrl+Space for input sources).`, and add `--   (macOS: SUPER twins — CMD+SHIFT+D, CMD+F, CMD+click)` under the `CTRL+SHIFT+click` line.
- Add `local is_mac = wezterm.target_triple:find("darwin") ~= nil` after `local workspaces = require("config.workspaces")`.
- Replace the first line of `M.apply` (`config.leader = { key = "Space", mods = "CTRL", timeout_milliseconds = 1000 }`) with:

```lua
  -- macOS keeps Ctrl+Space for switching input sources, so the leader is Ctrl+A there.
  if is_mac then
    config.leader = { key = "a", mods = "CTRL", timeout_milliseconds = 1000 }
  else
    config.leader = { key = "Space", mods = "CTRL", timeout_milliseconds = 1000 }
  end
  -- Left Option is Alt (ALT+h/j/k/l pane keys, readline, fzf); right Option still composes
  -- accents. (The macOS default, made explicit.)
  config.send_composed_key_when_left_alt_is_pressed = false
  config.send_composed_key_when_right_alt_is_pressed = true
```

- Directly before `config.keys = keys` at the end of `M.apply`, insert:

```lua
  if is_mac then
    -- macOS: the Cmd twin of each CTRL+SHIFT binding (both work).
    table.insert(keys, { key = "D", mods = "SUPER|SHIFT", action = act.DetachDomain("CurrentPaneDomain") })
    table.insert(keys, { key = "f", mods = "SUPER", action = act.Search({ CaseInSensitiveString = "" }) })
    table.insert(config.mouse_bindings, {
      event = { Up = { streak = 1, button = "Left" } },
      mods = "SUPER",
      action = act.OpenLinkAtMouseCursor,
    })
  end
```

In `dotfiles/dot_config/wezterm/README.md`: replace every sentence about the smart Ctrl+V paste / `paste.lua` with "Image paste over SSH is herdr's job (`herdr --remote`, Ctrl+V); WezTerm binds no Ctrl+V." Add a first line under the title: "**Opt-in and deprecated** (`devboost install optional-terminals`) — Ghostty is the default terminal on every OS."

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/dotfiles -v`
Expected: PASS. `test_ghostty_accepts_the_rendered_config` and `test_wezterm_lua_compiles` run on the Mac (luac from Task 0). The Ghostty one is skipped until the acceptance run installs Ghostty (Task 13 re-runs it).

- [ ] **Step 6: Commit**

```bash
git add -A ../dotfiles/dot_config/ghostty ../dotfiles/dot_config/wezterm tests/dotfiles/test_terminal_configs.py
git commit -m "feat(terminal): Ghostty per-OS config (Option-as-Alt, Cmd twins, ssh terminfo); WezTerm Darwin keys; retire Ctrl+V paste"
```

---

### Task 11: `git credential fill` ignores `core.askPass` too

M1's final review deferred this item. The fill already blanks `GIT_ASKPASS` / `SSH_ASKPASS`. A user-level `core.askPass` could still pop a GUI prompt on some git builds, so it is neutralised explicitly as well.

**Files:**
- Modify: `engine/src/devboost/modules/_credentials.py` (`_from_git_credential_fill`)
- Modify: `engine/tests/modules/test_secrets_macos.py` (the four `("git", "credential", "fill")` prefixes)

**Interfaces:**
- Produces: the argv is `["git", "-c", "core.askPass=", "credential", "fill"]`. The env and stdin are unchanged.

- [ ] **Step 1: Update the tests first.** In `tests/modules/test_secrets_macos.py`, replace every occurrence of the tuple `("git", "credential", "fill")` (four places: lines ~228, ~241, ~340, ~351) with `FILL`, and add near the top, after `_GH_USER`:

```python
#: `-c core.askPass=` — no GUI prompt even when the user configured an askpass helper.
FILL = ("git", "-c", "core.askPass=", "credential", "fill")
```

In `test_github_credentials_falls_back_to_git_credential_fill`, change `fill = ("git", "credential", "fill")` to `fill = FILL`.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_secrets_macos.py -v`
Expected: FAIL. The fake executor's `FILL` prefix no longer matches `git credential fill`, so the keychain token is not found.

- [ ] **Step 3: Implement** in `_credentials.py`, `_from_git_credential_fill`:

```python
    res = ctx.ex.run(
        # `-c core.askPass=` plus the empty askpass vars: no GUI password dialog, whatever
        # the user configured, in an unattended run.
        ["git", "-c", "core.askPass=", "credential", "fill"],
        stdin="protocol=https\nhost=github.com\n\n",
        env={"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "", "SSH_ASKPASS": ""},
    )
```

Update the docstring's second paragraph to say: "`GIT_TERMINAL_PROMPT=0` makes git fail instead of prompting when no helper has one; `-c core.askPass=` and the empty askpass variables stop it popping a GUI password dialog in an unattended run."

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/modules -v && uv run mypy && uv run ruff check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/modules/_credentials.py tests/modules/test_secrets_macos.py
git commit -m "fix(credentials): neutralise core.askPass for git credential fill"
```

---
### Task 12: The terminal set plans cleanly on macOS and on Fedora

**Files:**
- Modify: `engine/tests/core/test_macos_contract.py` (module docstring; two new tests)

**Interfaces:**
- Consumes: everything above. This is the regression guard for the M2 acceptance run: the `macos` profile, which is still `["terminal"]`, has no gap and no `unsupported-os` on a Mac, and the Linux terminal plan is unchanged apart from Ghostty.

- [ ] **Step 1: Write the tests.** They should pass right away, because Tasks 2–9 did the work. If one fails, the list it prints names the module that is still missing a macOS answer; fix that module, not the test. In `tests/core/test_macos_contract.py`, merge these imports into the file's import block (ruff E402/I001 want them at the top, sorted):

```python
from pathlib import Path

from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.plan import PlannedModule, build_plan
from devboost.core.profiles import expand, load_profiles
```

then append at the end of the file:

```python
REPO_ROOT = Path(__file__).resolve().parents[3]
MAC = OsInfo("macos", "macos", "aarch64", headless=False)
FEDORA = OsInfo("fedora", "fedora", "x86_64", headless=False)


def _plan(profile: str, os_info: OsInfo, tmp_path: Path) -> list[PlannedModule]:
    modules = load()
    names = expand([profile], load_profiles(REPO_ROOT / "profiles.toml"), modules)
    return build_plan(toposort(names, modules), modules, os_info, gpu_marker=tmp_path / "none")


def test_the_macos_profile_plans_cleanly_on_a_mac(tmp_path: Path) -> None:
    modules = load()
    reasons = {p.name: p.skip_reason for p in _plan("macos", MAC, tmp_path)}
    assert not sorted(n for n in reasons if not resolvable_on_macos(modules[n]))
    assert not [n for n, r in reasons.items() if r == "unsupported-os"]
    for want in ("ghostty", "zsh-config", "zsh-plugins", "bash", "dotfiles", "starship",
                 "nerd-fonts", "fresh", "claude-statusline"):
        assert reasons.get(want, "missing") is None, want
    assert reasons["curl"] == reasons["unzip"] == "provided-by-macos"
    assert "bash-config" not in reasons and "wezterm" not in reasons


def test_the_terminal_profile_still_plans_cleanly_on_fedora(tmp_path: Path) -> None:
    reasons = {p.name: p.skip_reason for p in _plan("terminal", FEDORA, tmp_path)}
    assert not {n: r for n, r in reasons.items() if r is not None}
    assert "bash-config" in reasons and "ghostty" in reasons
    assert not {"zsh-config", "zsh-plugins", "bash"} & set(reasons)
```

Change the module docstring's second paragraph to: "KNOWN_GAPS is the list of modules with no macOS path yet. M2 cleared the `terminal` set (the `macos` profile); M3–M5 add the rest and delete names from it. It must be empty by the end of M5 (spec §9)."

- [ ] **Step 2: Run**

Run: `uv run pytest tests/core/test_macos_contract.py -v && uv run mypy && uv run ruff check`
Expected: PASS (4 tests).

- [ ] **Step 3: Commit**

```bash
git add tests/core/test_macos_contract.py
git commit -m "test(macos): the macos/terminal profile plans cleanly on a Mac and on Fedora"
```

---
### Task 13: Docs, spec sync, full gate, and the acceptance run on this Mac

**Files:**
- Create: `docs/macos.md`
- Modify: `docs/adding-a-module.md`, `docs/architecture.md`, `README.md`, `CLAUDE.md`, `CHANGELOG.md`, `docs/superpowers/specs/2026-09-18-macos-support-design.md`

- [ ] **Step 1: `docs/macos.md`** (new; M3–M6 extend it)

````markdown
# dev-boost on macOS

Apple Silicon Macs are a first-class dev-boost target (constitution v3.1.0, Principle VI).
Design: `docs/superpowers/specs/2026-09-18-macos-support-design.md`. This page grows with
each milestone. **Status: M2 — the terminal tier.** `devboost install terminal` (= the
`macos` profile for now) gives you the CLI toolset, zsh, Ghostty and the dotfiles.

## Requirements

- Apple Silicon (Intel is refused). macOS 27 Golden Gate or 26 Tahoe; 15 is best-effort.
- Until M3/M6 automate them: the Xcode Command Line Tools (`xcode-select --install`) and
  Homebrew (<https://brew.sh>) installed once by hand.
- Run as your normal user, never with `sudo`: Homebrew refuses root, and dev-boost asks for
  your password once when a step needs it.

## Install from a clone

```sh
git clone https://github.com/adams100111/dev-boost ~/repos/dev-boost
cd ~/repos/dev-boost/engine
brew install uv && uv sync
uv run devboost install terminal --dry-run   # see the plan
uv run devboost install terminal
```

Open a new Ghostty window afterwards. The next run skips everything that is already
installed.

## What you get

| Kind | Modules |
|---|---|
| Homebrew formulae | coreutils, git, wget, jq, mise, chezmoi, ripgrep, fd, fzf, bat, eza, btop, zoxide, atuin, direnv, delta (`git-delta`), lazygit, dust, duf, sd, yq, gh, tealdeer, fastfetch, tmux, fresh (`fresh-editor`), starship, bash (a tool — zsh stays your login shell), zsh-plugins (zsh-autosuggestions + zsh-syntax-highlighting) |
| Homebrew casks | ghostty, nerd-fonts (`font-jetbrains-mono-nerd-font`) |
| Provided by macOS (skipped) | curl, unzip, wl-clipboard (`pbcopy`/`pbpaste`) |
| Linux-only (not planned) | bash-config |
| Opt-in | `devboost install optional-terminals` → WezTerm nightly cask (deprecated) |

Tools come from Homebrew, never `which`: macOS ships old copies of git, curl and bash that
would otherwise look installed. `devboost install --update` upgrades the formulae; apps
such as Ghostty update themselves.

## Shell

zsh is the shell on macOS (bash on Linux). The files are shared where they can be:

| File | What it does |
|---|---|
| `~/.zprofile` | login shells, including the shells GUI apps start: `brew shellenv`, mise shims, then `~/.zprofile.local` |
| `~/.zshrc` | loads `~/.config/devboost/shell.zsh`, then `~/.zshrc.local` |
| `~/.config/devboost/env.sh` | POSIX env shared with bash: PATH, `LANG`, `XDG_CONFIG_HOME`, `ANDROID_HOME`, `RIPGREP_CONFIG_PATH`, `EDITOR`/`VISUAL` |
| `~/.config/devboost/aliases.sh` | `dev`, `expose`, `tsdev-sync`, `pw-*`, eza aliases — shared with bash |
| `~/.config/devboost/shell.zsh` | history, completion, fzf → mise → starship → atuin → zoxide → direnv, then the plugins |
| `~/.bash_profile` | for `bash -lc` launchers (MCP servers, scripts): brew, mise shims, `env.sh` |

**Your old files are kept.** The first install moves a `~/.zshrc`, `~/.zprofile` or
`~/.bash_profile` that dev-boost did not write to `<name>.pre-devboost`. It never
overwrites an earlier backup; a later one becomes `.pre-devboost.1`, and so on. Copy any
lines you still need into `~/.zshrc.local` or `~/.zprofile.local`, which dev-boost never
touches.

## Terminal — Ghostty

Ghostty is the default terminal on every OS. On macOS:

- **Left Option is Alt** (word jumps, fzf's Alt-C, herdr's Alt bindings). Right Option still
  types accents and special characters.
- **Cmd and Ctrl+Shift both work**: Cmd+C / Cmd+V copy and paste, Cmd+T new tab, Cmd+N new
  window, Cmd+Shift+→/← switch tabs, Cmd+Shift+Z zoom a split, Cmd+= / Cmd+- / Cmd+0 font
  size.
- **Ctrl+V is not bound.** Pasting an image into a remote agent is `herdr --remote`'s job.
- Over SSH, Ghostty installs its terminfo on the server (`ssh-terminfo`), so remote
  tools render correctly.
- A notification appears when a long command finishes while Ghostty is in the background.

RAM and disk gauges (tmux status line, starship prompt, Claude Code status line) read the
same probe, `~/.local/bin/devboost-resources`. On macOS it measures the data volume.

## One-time manual steps

None for the terminal tier. If you installed Ghostty by hand earlier and Homebrew cannot
adopt it, the run reports `ghostty` as present-unmanaged and leaves your copy alone.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `zsh compinit: insecure directories` | not shown by design (`compinit -i`); to use brew's completions, run `chmod go-w "$(brew --prefix)/share"` |
| `ulimit: … invalid argument` at shell start | cannot happen: `shell.zsh` falls back to `kern.maxfilesperproc` until `macos-limits` (M5) raises the limit |
| `mosh`/ssh to Linux complains about `LC_CTYPE=UTF-8` | open a new shell. `env.sh` sets `LANG=en_US.UTF-8` and replaces a bare `LC_CTYPE=UTF-8` |
| lazygit / fresh ignore `~/.config` | the shell sets `XDG_CONFIG_HOME`. An app started from the Dock does not read your shell, so start it from a terminal |
| want your old shell back | `mv ~/.zshrc.pre-devboost ~/.zshrc` (then dev-boost will set it aside again on the next `dotfiles` run) |

## Coming next

M3 — the full catalog on macOS (Homebrew and the CLT as modules, herdr, casks, the `macos`
profile). M4 — Docker runtimes (Colima default) and launchd timers. M5 — desktop layer.
M6 — `curl … | bash` on a fresh Mac.
````

- [ ] **Step 2: `docs/adding-a-module.md`** — replace the `## macOS` section with:

```markdown
## macOS

- Simple tools: `PackageModule` works as-is; set `brew_pkg` when the formula name differs
  from the module name (e.g. `delta` → `git-delta`), or `brew_cask` for app-only tools.
- A `PackageModule` that needs a custom **Linux** path overrides `install_linux` /
  `verify_linux` (never `install` / `verify`), so macOS stays on Homebrew automatically.
- GUI apps: set `cask` on your `FlatpakApp` subclass.
- Custom install logic: declare the macOS answer as data —
  `per_os = OsMap(macos=BrewFormula("tool"))` or `OsMap(macos=BrewCask("App"))` (from
  `modules/_brew.py`), or your own `Installer` strategy. A module whose own
  `install`/`verify` implement the Linux path hands off first:
  `if (s := self.os_strategy(ctx)) is not None: return s.install(ctx)`. The plan treats
  that own `install` as the fallback for OSes `per_os` does not name.
- Or: `families = ("fedora", "debian", "arch")` if the module cannot exist on a Mac,
  `provided_by = ("macos",)` if macOS already covers it, or `portable = True` once you have
  verified it runs unchanged.
- Background jobs: use `launchd.user_agent(...)` (label `launchd.label("<name>")`).
- Privacy permissions: `tcc = (TccGrant("Accessibility", "AppName"),)`.
- `tests/core/test_macos_contract.py` fails if you add a module with no macOS answer.
```

- [ ] **Step 3: `docs/architecture.md`** — at the end of the "OS dispatch" paragraph, add: "A module's `per_os` entry for the running OS wins (`Module.os_strategy`); for other OSes its own `install()` is the fallback. The common macOS entries are the `BrewFormula` / `BrewCask` strategies in `modules/_brew.py`."

- [ ] **Step 4: README and CLAUDE.md**

1. `README.md` line 8 and `CLAUDE.md` (Mission paragraph): `(wezterm + starship + tmux + GNOME)` → `(Ghostty + starship + tmux + GNOME; zsh on macOS)`.
2. Regenerate the tables between the README markers (from the repo root):

```bash
uv run --project engine python - <<'PY'
import subprocess
from pathlib import Path

readme = Path("README.md")
text = readme.read_text(encoding="utf-8")
begin = "<!-- BEGIN generated profiles table (scripts/gen_profiles_table.py) -->"
end = "<!-- END generated profiles table -->"
table = subprocess.run(
    ["uv", "run", "--project", "engine", "python", "scripts/gen_profiles_table.py"],
    capture_output=True, text=True, check=True,
).stdout
head, rest = text.split(begin, 1)
_, tail = rest.split(end, 1)
readme.write_text(f"{head}{begin}\n\n{table}\n{end}{tail}", encoding="utf-8")
PY
git diff --stat README.md
```

Expected: the `shell`/`terminal` rows show `ghostty`, `zsh-config` and `bash`; a new `optional-terminals` row appears; the module table gains `bash`, `zsh-config` and `zsh-plugins`, and the new `ghostty`/`wezterm` descriptions.

3. In "Bundled tool configs": change the `wezterm` row to start with "**opt-in, deprecated** (`optional-terminals`):" and drop its "smart paste (…)" clause. Change the `ghostty` row to: "default terminal on every OS: Catppuccin Mocha, JetBrainsMono Nerd Font, `ssh-terminfo`, finish notifications; macOS: left Option = Alt and Cmd twins of the Ctrl+Shift keys; no Ctrl+V binding (herdr owns image paste) (`dot_config/ghostty/config.tmpl`)". Add a row: "| zsh (macOS) | `~/.zshrc` → `shell.zsh` (history, completion, fzf/atuin/zoxide/direnv/mise/starship, autosuggestions + syntax highlighting), shared `env.sh`/`aliases.sh`, `~/.zshrc.local` for machine-specific lines (`dot_zshrc`, `dot_config/devboost/`) |".
4. Under the install section, add one line: "**macOS (Apple Silicon):** preview — see [docs/macos.md](docs/macos.md) (`devboost install terminal` from a clone; `curl … | bash` lands in M6)."

- [ ] **Step 5: `CHANGELOG.md`** — under `## [Unreleased]`:

```markdown
### Added
- **macOS shell, terminal & dotfiles (M2)** — `devboost install terminal` runs on an
  Apple Silicon Mac: every terminal-set module installs through Homebrew
  (`BrewFormula`/`BrewCask` strategies, `per_os.macos`), zsh config (`shell.zsh`,
  `~/.zshrc`/`~/.zprofile` with `.local` hooks, `zsh-config`, `zsh-plugins`), brew `bash`,
  foreign rc files kept as `*.pre-devboost`, `docs/macos.md`.

### Changed
- **Ghostty is the default terminal on every OS**; WezTerm moved to the opt-in
  `optional-terminals` profile (deprecated) and its Ctrl+V smart paste was retired (herdr
  owns image paste).
- Shell config split into POSIX `env.sh` + shared `aliases.sh`; `shell.bash` uses
  `fzf --bash` when available (fallback for fzf < 0.48).
- One RAM/disk probe (`~/.local/bin/devboost-resources`, Linux + macOS) feeds tmux,
  starship, WezTerm and the Claude status line.

### Fixed
- `.chezmoiignore` no longer fails on macOS (`.chezmoi.osRelease` is Linux-only).
- Ghostty config: `theme = Catppuccin Mocha` (Title Case) and `toggle_split_zoom` — the old
  values were rejected by Ghostty 1.3.
- `git credential fill` also neutralises `core.askPass`.
```

- [ ] **Step 6: Spec sync** (`docs/superpowers/specs/2026-09-18-macos-support-design.md`)
  - §3 layout block: `dot_zprofile.tmpl` / `dot_zshrc.tmpl` / `dot_bash_profile.tmpl` → `dot_zprofile` / `dot_zshrc` / `dot_bash_profile` (plain files, OS-scoped by `.chezmoiignore`), and add `~/.zprofile.local` next to `~/.zshrc.local`.
  - §3 "Portable scripts" bullet: replace "`starship.toml` switches to starship's built-in `memory_usage` module" with "every gauge (tmux, starship, WezTerm, Claude status line) reads one probe, `~/.local/bin/devboost-resources` (`df -Pk`, the data volume on macOS); starship keeps its tmux-gated three-tier modules".
  - §2 Profiles: after "`shell` += `zsh-config`, `zsh-plugins`; `terminal` += `zsh-config`" add "(and `bash`; `zsh-config` requires `zsh-plugins`)".
  - §11 M2 row, Outcome column: "`devboost install terminal` from the clone (the terminal set's macOS strategies are pulled forward from M3)".

- [ ] **Step 7: Full gate** (from `engine/`)

Run: `uv run ruff check && uv run mypy && uv run pytest`
Expected: all green. On the Mac, only `test_ghostty_accepts_the_rendered_config` may skip at this point, because Ghostty is not installed yet.

- [ ] **Step 8: Acceptance — `devboost install terminal` from the clone on this Mac** (from `engine/`)

```bash
uv run devboost install terminal --dry-run
```
Expected: `would install …` lines for the brew formulae and the `ghostty` / `nerd-fonts` casks. `curl`, `unzip` → `provided-by-macos`. No `unsupported-os`, no traceback. `bash-config` and `wezterm` are not listed.

```bash
uv run devboost install terminal
```
Expected: one sudo prompt at most, then every module `ok` (or `skip` for provided ones). The log shows `dotfiles: kept your previous ~/.zshrc as ~/.zshrc.pre-devboost` (and the same for `~/.zprofile`; this Mac has both).

```bash
uv run devboost verify terminal
uv run devboost install terminal            # idempotent: everything reports skip
zsh -i -c 'print -r -- ok' 2>&1             # exactly "ok" — no warnings at shell start
/Applications/Ghostty.app/Contents/MacOS/ghostty +validate-config
uv run pytest tests/dotfiles -v             # now also runs the Ghostty validation test
```
Expected: verify is all ok, the second install skips everything, the zsh line prints only `ok`, `+validate-config` prints nothing and exits 0, and the tests pass with no skips.

Then, by hand in a new Ghostty window, check: left-Option+B/F jump words; Cmd+C / Cmd+V and Ctrl+Shift+C / V both copy and paste; typing a past command shows a grey autosuggestion; Ctrl+R opens atuin; Ctrl+T opens fzf; the starship prompt shows the RAM/disk gauges outside tmux; `tmux` shows the gauges in its status bar; `echo $LANG $XDG_CONFIG_HOME` prints `en_US.UTF-8 /Users/<you>/.config`. Write the results into the PR description.

- [ ] **Step 9: Commit**

```bash
cd .. && git add docs/macos.md docs/adding-a-module.md docs/architecture.md README.md CLAUDE.md CHANGELOG.md docs/superpowers/specs/2026-09-18-macos-support-design.md
git commit -m "docs: macOS shell & terminal (M2) — docs/macos.md, Ghostty default, module guide, changelog"
```

- [ ] **Step 10: Before merge (spec §9).** The shared shell files changed (`env.sh`, `aliases.sh`, `shell.bash`, `.chezmoiignore`, the tmux/starship scripts). Run the Fedora and Ubuntu VM rehearsal (`scripts/vm-test.sh`, see `docs/vm-testing.md`) with `devboost install terminal` and confirm a clean login shell there (`bash -i -c 'type -t dev; echo ok'`). Then hand off with superpowers:finishing-a-development-branch. PR title: `feat(macos): M2 — shell, terminal & dotfiles`. Commits and the PR carry no AI attribution (constitution).
