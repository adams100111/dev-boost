# Bash → Python Migration — Engine, Modules, and Tests — Design

**Status:** Draft spec (not yet approved for implementation)
**Date:** 2026-06-26 (revised after a grilling session — supersedes the strangler/phased-specs draft)
**Author:** brainstorming + grilling session
**Constitution:** aligns with `.specify/memory/constitution.md` v3.0.0 (typed Python +
Typer as the single engine/command language; bash only as a non-logic bootstrap stub)
**Supersedes/affects:** the bash engine (`lib/*.sh`) and per-module `install.sh`/
`verify.sh` described in `docs/superpowers/specs/2026-06-19-devboost-platform-design.md`;
extends the engine direction in `2026-06-25-portable-two-tier-installer-design.md`.

---

## 1. Summary

Rewrite dev-boost from a **bash-based** platform (≈9.6k LOC of `lib/*.sh` + ~55 modules
each carrying `install.sh`/`verify.sh`, 1,104 bats tests) into a **typed-Python** platform,
keeping bash only where it is genuinely irreducible. The result is a single, strictly-typed,
comprehensively-tested Python codebase that an expert Python developer can read, navigate, and
debug end-to-end — delivered to cold targets unchanged as a frozen per-arch binary.

This is a **greenfield rewrite shipped as one deliverable**: the repository is not yet in use,
nothing is published until the migration is complete, so the work is free to restructure the repo
and is **not** constrained to keep a running product alive mid-flight. The existing bash engine,
modules, and 1,104 bats tests are the **behavioral specification** — the install knowledge to port
into typed Python and re-assert in pytest — not code to preserve.

The migration is performed as a **direct, incremental rewrite**: build the typed engine and the
typed module/primitive foundation first (validated immediately by one tracer module), then port
modules group-by-group into pure typed Python, deleting the corresponding bash and porting its
bats to pytest as each group lands. Milestones keep the build tractable and green; there is **no
intermediate release** — only Fedora is implemented (parity with today), with OS-dispatch seams in
place so Ubuntu is a thin later spec.

The house style follows the author's reference project `pyapps/pyreview`: src-layout, `uv` +
`uv_build`, Python 3.12+, Typer, Pydantic v2 models for all structured data, pydantic-settings,
dependency injection for testability, custom exception hierarchy with chaining, loguru, pytest with
markers and fixtures — plus `mypy --strict` and ruff as required by the constitution.

---

## 2. Decisions locked (brainstorming + grilling)

| # | Question | Decision |
|---|----------|----------|
| 1 | How much Python? | **Maximize Python.** Everything executable becomes typed Python. Bash survives only as a non-logic bootstrap stub. |
| 2 | Module model | **Pure-Python modules.** One `.py` per module; metadata is a typed declaration; logic composes a typed primitives library. No `module.toml`, no per-module `.sh`. |
| 3 | `profiles.toml` | **Stays declarative config** (the user-facing "which modules form a profile" knob), validated by a Pydantic model on load. A real **`full`** profile (production aggregate) is added (data-only). |
| 4 | Module dependencies | **References, not strings** — `requires = (Docker,)` references the depended-on module class, so `mypy --strict` proves the graph and the IDE refactors/navigates it. |
| 5 | Side-effects | **Injected `Executor`** wraps all subprocess/filesystem/network. Real executor in production; a recording fake in tests (mirrors pyreview's injected `Cache[T]`). No module calls `subprocess` directly. |
| 6 | External tools | **Shell out via the `Executor`** for system tools (`dnf`/`flatpak`/`mise`/`chezmoi`/`age`/`dconf`/`git`/`mkcert`); use stdlib in-process only for **pure data** (`json`/`tomllib`) and the **GitHub API** (`urllib`/`httpx`). Keeps the frozen binary lean and every call testable. |
| 7 | OS dispatch | **Spectrum, opt-in per module (§4.4).** No module names `dnf`/`apt`; `pkg.*` picks a `PackageManager` from `ctx.os`. Per-OS *names/sources* → typed `OsMap`. Per-OS *procedures* → opt-in `per_os = OsMap[Installer]` Strategy interface. |
| 8 | OS scope | **Fedora implemented (parity); architecture Ubuntu-ready.** Land the OS-dispatch seams but implement + validate Fedora only. Ubuntu (apt names/sources for all modules + a Ubuntu VM matrix) is a thin **later spec**. |
| 9 | Migration strategy | **Direct incremental rewrite** (greenfield). Build the typed foundation + a tracer module first; port modules group-by-group into pure typed Python; delete bash + port bats→pytest per group. **No strangler, no legacy adapter, no bash bridges.** |
| 10 | Existing `engine/` code | **Rewrite clean** to the house style, cribbing the proven *algorithms* (Kahn toposort, OS detect, verify-guarded plan/run) as reference. Discard `module.toml` loading and the `bash -lc` runner. |
| 11 | Delivery shape | **One spec, one deliverable, no intermediate publish.** Milestones (§10) are *internal* build steps, not release points; the repo is greenfield and unused until complete. |
| 12 | Build/typed-model timing | **Contract first, implementations on real callers.** Define the stable seam (`Ctx`, `Executor`, `Module`/`Installer` Protocol, registry, engine flow) up front; grow the primitives library + `OsMap` + modules on top, validated by a first tracer module (no blind API design). |
| 13 | Sync vs async | **Synchronous engine.** Installs are dependency-ordered, side-effectful, and package managers serialize anyway; sync is simpler, safer, and freezes more cleanly. |
| 14 | Frozen-binary delivery | **Unchanged** — PyInstaller single-file per-arch binary (x86_64 + aarch64); `get.sh` downloads + SHA256-verifies + execs it. |
| 15 | Repo layout | **src-layout `uv` project under `engine/` during the rewrite**, **hoisted to repo root at the end** once the bash tree is gone (avoids colliding with the shrinking bash tree + root bats suite mid-flight). |

---

## 3. Goals / Non-goals

**Goals**
- One typed-Python codebase for the engine, all commands, and all module logic.
- `mypy --strict` clean; comprehensive pytest coverage (commands, typed I/O, error paths).
- Behavioral parity with today's shipped Fedora behavior (the bash engine + bats are the spec).
- Cold-start delivery unchanged: zero runtime dependency on the target (frozen binary).
- Bash reduced to an auditable, logic-free bootstrap stub.
- OS-dispatch seams present so Ubuntu is a thin later add.

**Non-goals**
- Not delivering/validating Ubuntu (or other OSes) in this migration — Fedora only (architecture-ready for the rest).
- Not adding new platform features/tools — parity first; features later.
- Not changing the GUI app catalog, secrets/age provisioning model, or profile semantics (beyond adding `full`).
- Not becoming a fleet/config-management tool (no Ansible/Salt model).
- Not rewriting `get.sh`/Kickstart into Python (they are the irreducible bootstrap).
- Not preserving the bash engine/modules/bats as code — they are reference/spec, deleted as ported.

---

## 4. Target architecture

### 4.1 Package layout (src-layout, `uv`)

```
engine/                         # the typed project during the rewrite; hoisted to repo root at the end
  pyproject.toml                # uv_build, py>=3.12, typer/pydantic/pydantic-settings/loguru/tenacity; dev: pytest/mypy/ruff
  .python-version               # 3.12
  src/devboost/
    __init__.py
    cli/                        # Typer app — one file per command group
      app.py                    # builds the Typer app; entry point devboost = devboost.cli.app:main
      install.py  verify.py  list.py  doctor.py
      lifecycle.py              # add / export / diff / update / self-update
      devhygiene.py             # dev status / gc / down
    core/
      settings.py               # pydantic-settings (DEVBOOST_* env)
      osinfo.py                 # OsInfo + detect()       (cribbed from engine/osinfo.py)
      graph.py                  # Kahn toposort           (cribbed from engine/graph.py)
      plan.py                   # PlannedModule + build_plan
      runner.py                 # run_plan over the injected Executor
      registry.py               # module registry + load-time validation
      profiles.py               # profiles.toml loader (pydantic-validated)
      errors.py                 # exception hierarchy
      log.py                    # loguru config
    exec/
      executor.py               # Executor Protocol, RealExecutor, FakeExecutor
      primitives/               # the typed primitives library (grown on demand, tested once)
        pkg.py flatpak.py copr.py config.py dconf.py mise.py systemd.py
        age.py github.py gpu.py fs.py shell.py    # shell.py = the escape hatch
    modules/                    # ~55 typed modules, one file each (e.g. ddev.py)
    model.py                    # Module base / Installer Protocol + @register
  tests/                        # pytest mirror of the package (conftest = FakeExecutor + fixtures)
    primitives/  modules/  cli/  core/
  data/                         # static data bundled in the binary (profiles.toml, dconf dumps, repo defs, templates/)
get.sh                          # bash bootstrap stub (download + verify + exec)
ventoy/ks.cfg                   # Kickstart %post calls the binary directly (rewritten)
```

During the rewrite the bash tree (`modules/` bash, `lib/`, root `tests/` bats) coexists at repo
root as **reference/spec**, shrinking to nothing as groups port. At the end the project hoists to
the repo root.

### 4.2 The `Module` model

A module is one typed Python class: declarative metadata as class attributes, two methods.

```python
# src/devboost/model.py
from typing import ClassVar, Protocol, runtime_checkable

class Ctx(Protocol):
    os: OsInfo
    ex: Executor          # injected; all side-effects go through it
    force: bool
    dry_run: bool

@runtime_checkable
class Installer(Protocol):                     # the per-OS install strategy interface
    def install(self, ctx: Ctx) -> None: ...
    def verify(self, ctx: Ctx) -> bool: ...

class Module:
    name:        ClassVar[str]
    category:    ClassVar[str]
    description: ClassVar[str]
    requires:    ClassVar[tuple[type["Module"], ...]] = ()   # references, not strings
    profiles:    ClassVar[tuple[str, ...]] = ()
    gui:         ClassVar[bool] = False

    # A module IS an Installer. Author it ONE of two ways:
    #   (1) Uniform — override install()/verify() directly (OS-agnostic; uses dispatching primitives).
    #   (2) Per-OS  — declare per_os strategies; the base install()/verify() delegate to the
    #                 Installer resolved for ctx.os (distro → family → default).
    per_os: ClassVar["OsMap[Installer]"] = OsMap()

    def verify(self, ctx: Ctx) -> bool:        # default: delegate to the per-OS strategy
        return self._strategy(ctx).verify(ctx)
    def install(self, ctx: Ctx) -> None:       # default: delegate to the per-OS strategy
        self._strategy(ctx).install(ctx)
    def _strategy(self, ctx: Ctx) -> Installer:
        return self.per_os.get(ctx.os) or self  # per-OS impl if declared, else self (uniform)
```

The **engine only ever calls `module.verify(ctx)` and `module.install(ctx)`** plus reads metadata.
`per_os`/`OsMap`/primitives are *how a typed module implements those two methods* — invisible to the
engine. This is the stable contract built first (§2 #12); everything else grows on top of it.

- **`requires` as class references**: a wrong dependency fails `mypy --strict`; `Docker` is
  rename-/find-references-able across the whole graph.
- **`@register`** adds the class to the registry; `registry.load()` validates at startup (every
  `profiles` name exists in `profiles.toml`; no dependency cycles; GUI/headless rules).
- **`verify` returns `bool`** (a real predicate), not a shell exit code.
- **A missing strategy is data, not a crash:** if `per_os` has no entry for `ctx.os` (and no
  `default`), the planner marks the module `unsupported-os` and skips it (Principle II/VI).

### 4.3 The `Executor` and the typed primitives library

The single dependency-injection seam — the pyreview `Cache[T]` pattern applied to side-effects.
All **system tools** are invoked through it (§2 #6); **pure data + the GitHub API** are in-process.

```python
# src/devboost/exec/executor.py
@dataclass(frozen=True)
class Result:
    code: int
    stdout: str
    stderr: str

@runtime_checkable
class Executor(Protocol):
    def run(self, argv: Sequence[str], *, sudo: bool = False,
            stdin: str | None = None, env: Mapping[str, str] | None = None) -> Result: ...
    def which(self, cmd: str) -> bool: ...

class RealExecutor:    # subprocess, argv lists only — no shell, no bash -c
    ...
class FakeExecutor:    # records calls, returns scripted Results; used in every unit test
    calls: list[list[str]]
```

Primitives are thin, typed, idempotent, OS-aware functions over the `Ctx`/`Executor`, grown the
first time a module needs them and tested once: `pkg.install/installed`, `flatpak.install`,
`copr.enable`, `config.write_ini/json_merge/ensure_line`, `dconf.load`, `mise.use`,
`systemd.enable_user_unit`, `age.decrypt`, `github.upload_key` (stdlib HTTP), `fs.write/exists`,
and `shell.run(...)` — the explicit, greppable escape hatch for the rare irreducible one-liner.
`jq` disappears (native `json`/`tomllib`); `bash -c` strings disappear (argv lists).

### 4.4 OS dispatch: primitives by default, a per-OS `Installer` interface when steps diverge

The package manager is **never named in a module** — selected once from `ctx.os`, the primitive
dispatches. **Fedora (`Dnf`) is implemented; `Apt`/`Pacman` are pluggable seams** for later specs.

```python
# src/devboost/exec/primitives/pkg.py
class PackageManager(Protocol):
    def install(self, ctx: Ctx, *pkgs: str) -> None: ...
    def installed(self, ctx: Ctx, pkg: str) -> bool: ...
    def add_repo(self, ctx: Ctx, repo: Repo) -> None: ...

class Dnf(PackageManager): ...      # implemented now (fedora family)
class Apt(PackageManager): ...      # seam — implemented when Ubuntu is delivered (later spec)
class Pacman(PackageManager): ...   # seam

def manager_for(os: OsInfo) -> PackageManager:   # distro → family → default precedence (Principle VI)
    ...
```

A **spectrum** covers OS differences, smallest blast-radius first; a module escalates only when it
must (most never leave layer 1):

1. **Same name everywhere (most modules):** `pkg.install(ctx, "git")` — Ubuntu later = zero module edits.
2. **Name differs per OS:** a typed `OsMap[T]` (`distro → family → default`): `pkg.install(ctx, OsMap(fedora="fd-find", default="fd"))`.
3. **Install *source* differs (repo/script, same shape):** the module declares a typed per-OS `Source`.
4. **Install *procedure* differs (different steps per OS):** opt-in `per_os = OsMap[Installer]` — the GoF Strategy pattern, each OS's steps in their own typed, independently-testable class.

```python
@dataclass(frozen=True)
class OsMap(Generic[T]):
    fedora: T | None = None; debian: T | None = None; arch: T | None = None
    default: T | None = None
    def get(self, os: OsInfo) -> T | None: ...   # distro → family → default; missing+no default ⇒ unsupported-os skip

Source = OsMap[DnfRepo | AptRepo | Script]
```

The per-OS interface is **opt-in**, so adding Ubuntu later is one `Apt` class + `debian=` entries
only in modules that truly diverge — never an across-the-board per-module change.

### 4.5 Engine flow (algorithms cribbed from `engine/`, rewritten clean)

`registry.load()` → `profiles.expand()` → `graph.toposort()` → `plan.build_plan()` (applies
headless/GUI + unsupported-OS skips) → `runner.run_plan()` which, per module: skip if `verify(ctx)`
and not `force`; else `install(ctx)`; re-`verify`; record ok/skip/fail. A failure names the module
and the failing primitive (Principle II).

### 4.6 CLI, settings, logging, errors

- **CLI:** Typer, one file per command, composed in `app.py` (pyreview's `app.command()(fn)`),
  typed `Annotated[...]` params. Verbs: `install`, `verify`, `list`, `doctor` (+`--gpu`), `add`,
  `export`, `diff`, `update`, `self-update`, `terminal`, `devtools`, `dev status|gc|down`. Each is
  ported to Python at its module-group milestone (no bash delegation; before its milestone a verb
  simply doesn't exist — acceptable, nothing is used until complete).
- **Settings:** pydantic-settings, `DEVBOOST_` prefix.
- **Logging:** loguru, preserving `info/ok/skip/error` semantics.
- **Errors:** `DevbootError` base → `ManifestError`, `ProfileError`, `InstallError`,
  `SecretsError`, `GpuError`, … with chaining (`raise InstallError(...) from e`), rendered by the
  CLI as the failed module + command.

### 4.7 Entrypoints (greenfield — rewritten)

- **Targets:** `get.sh` installs the **frozen binary as `devboost`** on PATH — it *is* the
  entrypoint. `ventoy/ks.cfg` `%post` and `devboost-firstboot.service` call the binary directly
  (rewritten; no `install.sh`).
- **Source/dev/CI:** `uv run devboost …` (or `python -m devboost`).
- `install.sh`'s dependency-ensure logic moves into a **Python preflight** (`doctor`); `bin/devboost`
  (bash) is removed.

---

## 5. Concrete example (`ddev`)

**Today** — three artifacts: `modules/ddev/module.toml` + `install.sh` (≈55 lines of bash: idempotent
fast-path, write `ddev.repo` heredoc, `dnf install --refresh`, `mkcert -install`) + a `verify` string.

**After** — one typed file (Fedora implemented; the `debian=` source is the architecture-ready seam,
not validated in this migration):

```python
# src/devboost/modules/ddev.py
from devboost.model import Module, Ctx, register
from devboost.exec.primitives import pkg
from devboost.modules.docker import Docker

DDEV_SOURCE: Source = OsMap(
    fedora=DnfRepo(name="ddev", baseurl="https://pkg.ddev.com/yum/", gpgcheck=False),
    # debian=AptRepo(...)   # seam: filled when Ubuntu is delivered (later spec)
)

@register
class Ddev(Module):
    name = "ddev"
    category = "dev-stacks"
    description = "Container-based Laravel/PHP dev orchestrator (no host php/composer)."
    requires = (Docker,)              # static-checked reference
    profiles = ("laravel",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("ddev")

    def install(self, ctx: Ctx) -> None:
        pkg.install(ctx, "ddev", source=DDEV_SOURCE, refresh=True)   # OS-dispatched, idempotent
        ctx.ex.run(["mkcert", "-install"])                          # trust local CA
```

Its test (pyreview style — `FakeExecutor`, no real `dnf`; OS pinned by the fixture):

```python
def test_ddev_installs_on_fedora(fake_ctx_fedora):
    Ddev().install(fake_ctx_fedora)
    assert ["dnf", "install", "--refresh", "-y", "ddev"] in fake_ctx_fedora.ex.calls
    assert ["mkcert", "-install"] in fake_ctx_fedora.ex.calls
```

---

## 6. How parity is preserved without a running bash engine

There is no legacy adapter and the bash engine is not kept runnable. Parity is preserved by
**porting the behavioral spec, not the code**:

- Each module's existing `install.sh`/`verify.sh` + its bats test are read as the **specification**
  of what the typed module must do; the typed module reproduces that behavior and the bats
  assertions are **ported to pytest** (against a `FakeExecutor`) as the regression guard.
- The bash source for a group is **deleted** once its Python replacement + pytest land.
- End-to-end correctness is validated by **real installs on a throwaway Fedora VM/container** — per
  profile as its modules' group completes, and a full `install full` + `verify full` at the end.

---

## 7. What stays bash (the boundary, end state)

| Stays bash | Why irreducible | Size |
|---|---|---|
| `get.sh` | The public `curl … | bash` one-liner cannot itself be the frozen binary; it bootstraps it. | ~25 lines |
| Kickstart `%post` | Anaconda runs shell in `%post`; it only fetches + execs the binary. | ~5 lines |

Both contain only: detect arch → download the matching binary → SHA256-verify → exec. No
capability, module, or decision logic — exactly the constitution v3.0.0 "non-logic bootstrap stub"
rule. `devboost-firstboot.service` is a systemd unit (ini) whose `ExecStart` calls the binary.
Everything else is Python.

> During the rewrite, additional bash exists transiently as **reference/spec** (`lib/*.sh`, the
> not-yet-ported modules, the bats suite). It is deleted group-by-group and is gone at completion.

---

## 8. Test strategy

- **bats is the behavioral spec, ported per group.** Read a group's bats as the contract, write
  pytest asserting the same observable behavior against a `FakeExecutor`, then delete that group's
  bats. End state: pytest only.
- **pytest conventions (pyreview):** `tests/` mirrors the package; `conftest.py` provides
  `fake_ctx`/`FakeExecutor`; `unit` (default, hermetic) and `integration` markers; error paths via
  `pytest.raises`; `tmp_path` for filesystem; no real `dnf`/`flatpak`/network in unit tests.
- **Gates (constitution):** `pytest` green **and** `mypy --strict` clean **and** ruff clean before
  any merge; a **frozen-binary smoke test** (built binary's `--version`/`list`) in CI.
- **Coverage:** comprehensive across commands, typed I/O contracts, primitives, and error paths.

---

## 9. Delivery (unchanged)

PyInstaller `--onefile`, built natively per arch (x86_64 + aarch64) in `release.yml`; static data
(`data/`: `profiles.toml`, `templates/`, dconf dumps, repo definitions) bundled via PyInstaller
datas and resolved through a `resources` helper so paths work from source and frozen. `get.sh`
downloads `/latest/`, SHA256-verifies, installs, execs. No `python3` required on the target.

---

## 10. Milestones (internal build order — one deliverable, no intermediate release)

Each milestone keeps `main` green and the test suite passing; **none is a release point** — the
product ships only after the last. Order follows the existing roadmap's dependency structure.

| Milestone | Scope | Deletes (bash reference) |
|---|---|---|
| **M0 — Foundation + tracer** | src-layout `engine/`; `Ctx`/`Executor`(+Fake)/`Module`/`Installer` contract; registry + load-time validation; engine flow (toposort/plan/run, cribbed); `pkg`/`config`/`fs` primitives (Dnf); **one tracer module** end-to-end to validate the model; `install`/`verify`/`list` + Python `doctor` preflight; `profiles.toml` loader + add `full`; rewrite `get.sh`/`ks.cfg`/firstboot to call the binary. | `bin/devboost`, `install.sh`, `lib/{log,os,toml,module,depsort,profile,install}.sh` |
| **M1 — secrets + github** | `age`, `github` (stdlib HTTP) primitives; port `secrets`/`ssh-setup`; doctor secrets preflight in Python. **First**, so credential-dependent modules (`chezmoi-repo`, `obsidian-sync`, private dev-stack repos) can rely on it. | `lib/secrets.sh`, `lib/github.sh` |
| **M2 — base** | `copr`/`mise`/`flatpak` primitives; port `base` modules (rpmfusion, dnf-tune, flatpak, build-tools, mise, chezmoi, `chezmoi-repo`, CLI tools; `docker` already done by the M0 tracer). | `lib/pkg.sh`, base modules |
| **M3 — cli + shell** | port `cli`/`shell` (starship, ghostty, nerd-fonts, dotfiles). | those modules |
| **M4 — gnome** | `dconf` primitive; port gnome modules. | `lib/gnome.sh` |
| **M5 — multimedia + editors** | va-hwaccel, VS Code, `fresh` + LSP wiring. | `lib/fresh.sh` |
| **M6 — dev-stacks** | laravel/dotnet/python/web/react-native/devops/data + templates. | those modules |
| **M7 — apps + obsidian** | flatpak apps + obsidian-sync (deploy key, systemd user timer). | `lib/vault.sh` |
| **M8 — lifecycle + devhygiene** | `add/export/diff/update/self-update`, lockfile, `dev status/gc/down`. | `lib/lifecycle.sh`, `lib/devhygiene.sh` |
| **M9 — system + gpu** | system-resilience modules; `gpu`/MOK state machine; `doctor --gpu`. | `lib/gpu.sh` |
| **M10 — finish** | delete any remaining `lib/*.sh` + bats; hoist project to repo root; constitution clarification (§12); full-`full` Fedora VM acceptance + frozen-binary release build. | `lib/`, `tests/*.bats` |

M0 is the keystone (it sets the contract + proves it with the tracer). M1–M9 follow the roadmap
dependency order. M10 closes out and is the single release point.

---

## 11. Risks & mitigations

- **Behavioral drift bash → Python.** Mitigation: bats-as-spec ported to pytest per group; real
  per-profile VM installs as groups complete; full `full` VM install at M10.
- **Designing the primitives API blind.** Mitigation: contract-first + the M0 tracer module forces
  the first primitives into existence with a real consumer before scaling.
- **Root/idempotency edge cases** (sudo, repo files, partial installs). Mitigation: primitives
  centralize idempotency + sudo; tested once; integration smoke on a throwaway VM/container.
- **Frozen-binary resource paths.** Mitigation: a `resources` resolver + a frozen-binary smoke test
  in CI.
- **Large single deliverable / long stretch.** Mitigation: milestone-paced, always-green build with
  early architecture validation (M0 tracer); each milestone independently reviewable.
- **Scope creep (features or Ubuntu).** Mitigation: parity-only + Fedora-only rules (§3 non-goals).

---

## 12. Constitution alignment

Consistent with v3.0.0 (typed Python + Typer; frozen binary; bash as non-logic stub; pytest +
`mypy --strict`). One **clarification** to schedule (a PATCH amendment, M10): Principle I and the
constraints describe modules via TOML "`[install]` keys"/"module manifest". Under this design a
module is a **typed Python declaration** (still self-contained, still "one file to add a tool,"
capability still declarative — now type-checked). Reword Principle I's manifest language and the
TOML-key phrasing accordingly; `profiles.toml` remains the one declarative data file.

---

## 13. Open questions (resolve in the plan)

- The **tracer module** choice for M0 (lean toward a trivial `pkg.install`-only CLI tool to validate
  the simplest path, then a per-OS-`Source` module like `ddev` to exercise layer 3).
- Exact membership of the new **`full`** profile (production aggregate).
- `Ctx` concretion (frozen dataclass vs Protocol) and how `force`/`dry_run` thread through primitives.
- Registry discovery: explicit imports vs package-scan auto-discovery of `modules/*.py`.
- Whether `profiles.toml`'s table-driving metadata (category/description) moves onto the module
  classes (single source) with `profiles.toml` holding only profile→module sets.
