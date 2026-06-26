# Phase 1 Data Model — Bash → Python Migration

The "data" here is the typed domain model of the engine: the entities the engine reasons over and the
typed objects modules are built from. All are strictly typed; structured data uses Pydantic v2 or
frozen dataclasses (value objects). Field types are indicative; finalize signatures in implementation.

## OsInfo  *(frozen value object)*

The detected host environment that drives dispatch.

| Field | Type | Notes |
|---|---|---|
| `distro` | `str` | e.g. `fedora`, `ubuntu`; `unknown` if undetectable |
| `family` | `str` | `fedora` / `debian` / `arch` / `macos` — via the distro→family table |
| `arch` | `str` | `x86_64` / `aarch64` |
| `headless` | `bool` | no display server present |

- **Detection**: `osinfo.detect()` reads `/etc/os-release` (path injectable for tests).
- **Validation**: family resolved from a fixed mapping; unknown distro keeps `family == distro`.

## OsMap[T]  *(generic frozen value object)*

Per-OS values resolved by `distro → family → default`. The typed form of the constitution's cross-OS
precedence.

| Field | Type | Notes |
|---|---|---|
| `fedora` / `debian` / `arch` | `T | None` | per-family value |
| `default` | `T | None` | fallback |

- **`get(os: OsInfo) -> T | None`**: tries `distro`, then `family`, then `default`.
- **Rule**: a `None` result (no match, no default) ⇒ planner marks the consuming module
  `unsupported-os` (skip), never a crash.
- **Specializations**: `Source = OsMap[DnfRepo | AptRepo | Script]` (per-OS install source);
  `OsMap[Installer]` (per-OS install strategy); `OsMap[str]` (per-OS package name).

## Repo sources  *(frozen value objects)*

Typed third-party install sources (layer-3 OS divergence).

- **`DnfRepo`**: `name: str`, `baseurl: str`, `gpgcheck: bool = True`, `gpgkey: str | None`.
- **`AptRepo`** *(seam — not implemented for Fedora-only delivery)*: `list_line: str`, `key_url: str`.
- **`Script`**: `url: str` (curl-pipe install fallback), optional checksum.

## Executor  *(Protocol + implementations)*

The single side-effect seam. **All system-tool invocation passes through it.**

| Member | Signature | Notes |
|---|---|---|
| `run` | `(argv: Sequence[str], *, sudo=False, stdin=None, env=None) -> Result` | argv lists only — never a shell string |
| `which` | `(cmd: str) -> bool` | PATH lookup |

- **`Result`** *(frozen)*: `code: int`, `stdout: str`, `stderr: str`.
- **`RealExecutor`**: `subprocess`; honors `ctx.dry_run` (preview, no mutation); injects
  `DEVBOOST_*`/`OS_*` env where needed.
- **`FakeExecutor`** *(tests)*: records `calls: list[list[str]]`, returns scripted `Result`s; asserts
  the exact command sequence; never touches the real system.

## Ctx  *(frozen value object — the injected context)*

Carried into every `install`/`verify`/primitive call.

| Field | Type | Notes |
|---|---|---|
| `os` | `OsInfo` | detected host |
| `ex` | `Executor` | real or fake |
| `force` | `bool` | reinstall even if verify passes |
| `dry_run` | `bool` | preview only (honored in the executor) |
| `resources` | `Resources` | resolves bundled data paths (source + frozen) |

## Installer  *(Protocol)*

The per-OS install-strategy interface.

| Member | Signature |
|---|---|
| `install` | `(ctx: Ctx) -> None` |
| `verify` | `(ctx: Ctx) -> bool` |

## Module  *(base class — a Module IS an Installer)*

One per installable tool; the unit of the catalog.

| Field/Method | Type | Notes |
|---|---|---|
| `name` | `ClassVar[str]` | unique id; primary key in the registry |
| `category` | `ClassVar[str]` | for the README table |
| `description` | `ClassVar[str]` | for the README table |
| `requires` | `ClassVar[tuple[type[Module], ...]]` | **class references** (type-checked) |
| `profiles` | `ClassVar[tuple[str, ...]]` | profile names it belongs to |
| `gui` | `ClassVar[bool]` | GUI-only ⇒ skipped headless |
| `per_os` | `ClassVar[OsMap[Installer]]` | opt-in per-OS strategies (layer 4) |
| `verify(ctx)` | `-> bool` | default delegates to `_strategy(ctx)` |
| `install(ctx)` | `-> None` | default delegates to `_strategy(ctx)` |
| `_strategy(ctx)` | `-> Installer` | `per_os.get(ctx.os) or self` |

- **Identity/uniqueness**: `name` unique across the registry (load-time check).
- **Relationships**: `requires` → other `Module` classes (directed acyclic — cycles rejected);
  `profiles` → `Profile` names (must exist in `profiles.toml`).
- **Authoring shapes**: *uniform* (override `install`/`verify`, OS-agnostic via primitives) or
  *per-OS* (declare `per_os`). The engine only ever calls `verify`/`install` + reads metadata.
- **Registration**: `@register` adds the class to the registry.

## Primitive  *(typed functions, not a stored entity)*

The shared, idempotent, OS-aware vocabulary modules compose (over `Ctx`/`Executor`): `pkg`,
`flatpak`, `copr`, `config`, `dconf`, `mise`, `systemd`, `age`, `github`, `gpu`, `fs`, `shell`.
`pkg.*` selects a `PackageManager` (`Dnf` implemented; `Apt`/`Pacman` seams) from `ctx.os`.

## Profile  *(declarative data in `profiles.toml`)*

A named set of modules — the operator's selection knob.

| Field | Type | Notes |
|---|---|---|
| `name` | `str` | e.g. `base`, `laravel`, `full`, `terminal` |
| `members` | `list[str]` | module names **or** other profile names (expanded transitively) |

- **Validation**: loaded + validated by a Pydantic model; every member resolves to a known module or
  profile; `full` (production aggregate, see research R2) is the default install target.

## Plan / PlannedModule  *(derived, in-memory)*

The ordered decision list for a run, produced before execution.

| Field | Type | Notes |
|---|---|---|
| `name` | `str` | module name |
| `skip_reason` | `str | None` | `headless-gui` / `unsupported-os` / `already-installed` / None |
| (decision) | — | install / skip, derived in `runner.run_plan` |

- **Lifecycle**: `expand profiles → toposort(requires) → build_plan(apply skips) → run_plan`
  (verify-guarded). `RunResult{name, status: ok|skip|fail}` per module; a `fail` names the module +
  failing command.

## Settings  *(pydantic-settings)*

Engine configuration from `DEVBOOST_*` env (e.g. `DEVBOOST_ROOT`, dotfiles repo, secrets path),
typed with defaults — the one runtime config surface (analogous to pyreview's settings).

## Entity relationships (summary)

```
Profile ──(members)──▶ Module ──(requires)──▶ Module        (DAG; cycles rejected at load)
                         │
                         ├─(per_os)──▶ OsMap[Installer] ──▶ Installer (per-OS steps)
                         └─(composes)─▶ Primitive ──▶ Executor ──▶ Result
Ctx{ os: OsInfo, ex: Executor, force, dry_run, resources }   (injected into every install/verify)
registry.load() ⇒ validate(names unique, requires resolve, profiles exist, no cycles, gui rules)
```
