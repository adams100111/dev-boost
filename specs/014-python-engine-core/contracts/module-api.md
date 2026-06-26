# Contract — Internal module-authoring API (the stable seam)

The interfaces a module author and the engine rely on. This is the **contract built first** (design
§2 #12); the primitives library and modules are implementations on top of it. All signatures are
typed; `mypy --strict` is a gate.

## `Ctx` (injected context)

```python
class Ctx(Protocol):
    os: OsInfo          # detected host
    ex: Executor        # injected; all side effects flow through it
    force: bool         # reinstall even if verify passes
    dry_run: bool       # preview only (honored inside the executor)
    resources: Resources  # resolves bundled data paths (source + frozen)
```

## `Executor` (the side-effect seam)

```python
@dataclass(frozen=True)
class Result:
    code: int; stdout: str; stderr: str

@runtime_checkable
class Executor(Protocol):
    def run(self, argv: Sequence[str], *, sudo: bool = False,
            stdin: str | None = None, env: Mapping[str, str] | None = None) -> Result: ...
    def which(self, cmd: str) -> bool: ...
```

**Contract**: argv lists only (never a shell string); `RealExecutor` honors `dry_run`; `FakeExecutor`
records `calls` and returns scripted `Result`s. Modules and primitives MUST NOT call `subprocess`
directly — only through `ctx.ex` (FR-003).

## `Installer` (per-OS strategy interface)

```python
@runtime_checkable
class Installer(Protocol):
    def install(self, ctx: Ctx) -> None: ...
    def verify(self, ctx: Ctx) -> bool: ...
```

## `Module` (base; a Module IS an Installer)

```python
class Module:
    name: ClassVar[str]; category: ClassVar[str]; description: ClassVar[str]
    requires: ClassVar[tuple[type["Module"], ...]] = ()     # class references — type-checked
    profiles: ClassVar[tuple[str, ...]] = ()
    gui: ClassVar[bool] = False
    per_os: ClassVar["OsMap[Installer]"] = OsMap()          # opt-in per-OS strategies

    def verify(self, ctx: Ctx) -> bool: ...   # default → self._strategy(ctx).verify(ctx)
    def install(self, ctx: Ctx) -> None: ...  # default → self._strategy(ctx).install(ctx)
```

**Authoring contract** — choose one shape:
1. **Uniform**: override `install`/`verify`, OS-agnostic, compose primitives.
2. **Per-OS**: declare `per_os = OsMap(fedora=…, debian=…)` of `Installer`s; don't override.

The engine ONLY calls `verify(ctx)`/`install(ctx)` + reads metadata. `@register` enrolls the class.

## Primitive vocabulary (typed, idempotent, OS-aware)

Functions over `Ctx`, the first arg always `ctx`. Examples (full set grown on demand):

```python
# pkg.py  — package manager selected from ctx.os (Dnf implemented; Apt/Pacman are seams)
def install(ctx: Ctx, *pkgs: Pkg, source: Source | None = None, refresh: bool = False) -> None: ...
def installed(ctx: Ctx, pkg: str) -> bool: ...
# config.py
def json_merge(ctx: Ctx, path: str, patch: Mapping[str, object]) -> None: ...
def ensure_line(ctx: Ctx, path: str, line: str) -> None: ...
# dconf.py / mise.py / flatpak.py / copr.py / systemd.py / age.py / github.py / fs.py
def load(ctx: Ctx, schema_root: str, dump: str) -> None: ...        # dconf.load
def use(ctx: Ctx, tool: str, version: str) -> None: ...             # mise.use
# shell.py — the explicit, greppable escape hatch
def run(ctx: Ctx, *argv: str) -> Result: ...
```

**Contract guarantees (tested per primitive)**:
- **Idempotent**: re-invoking with the same args performs no redundant change.
- **OS-dispatched**: `pkg.*` resolves the manager from `ctx.os`; no primitive names `dnf`/`apt`.
- **Pure data via stdlib**: JSON/TOML handled in-process (`json`/`tomllib`); GitHub API via stdlib
  HTTP; only *system tools* go through `ctx.ex`.
- **`dry_run`-safe**: mutations route through `ctx.ex`, so `dry_run` previews without side effects.

## Registry

```python
def register(cls: type[Module]) -> type[Module]: ...   # decorator
def load() -> Registry: ...   # auto-scan devboost.modules.*, then validate the whole graph
```

**Validation (load-time, before any side effect)**: unique `name`s; every `requires` resolves; every
`profiles` name exists in `profiles.toml`; no dependency cycles; GUI/headless consistency. Failures
raise typed errors (`ManifestError`/`ProfileError`).
