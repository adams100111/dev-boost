# Phase 0 Research — Bash → Python Migration

Resolves the design doc's open questions (§13) and locks the version-sensitive tech choices. Most of
the architecture was settled in the brainstorming + grilling sessions (see spec Clarifications and
design §2); this records the remaining plan-level decisions.

## R1 — Tracer module for M0

**Decision**: Two-step tracer in M0 — (a) a trivial CLI tool whose install is a single
`pkg.install(ctx, <name>)` (e.g. `ripgrep`), then (b) one module that exercises a per-OS `Source`
(e.g. `ddev`: writes a third-party repo, installs, runs a follow-up command).

**Rationale**: (a) validates the full vertical (registry → plan → run → primitive → `Executor` →
`FakeExecutor` test) with the simplest possible module, proving the contract end-to-end before any
scale. (b) immediately stresses the layer-3 `Source`/`OsMap` machinery and the `add_repo` primitive,
so the primitives API is designed against a real, non-trivial caller (per design §2 #12). Doing both
in M0 means the typed model is proven across the two most common module shapes before the bulk port.

**Alternatives considered**: A single trivial tracer (under-validates the per-OS path — defers the
riskier API design to M1); starting with a per-OS-`Installer` (layer 4) module (over-engineers the
first tracer; layer 4 is rare and can wait for a real layer-4 module in its group).

## R2 — Membership of the new `full` profile

**Decision**: `full` = the production aggregate = union of the default-on profiles:
`base, cli, shell, gnome, multimedia, editors, python, web, laravel, dotnet, data, devops,
react-native, apps, system, dev-hygiene`. **Excluded** (opt-in / off the production path):
`gnome-aesthetics, gnome-theme, hardware-nvidia, optional-editors, security-cli`, and the portable
subsets `terminal`/`devtools` (which are *alternative* entry points, not part of `full`).

**Rationale**: Matches the mission's "production" definition (builds Laravel/.NET+Aspire/Python/
Next.js+React/React-Native; editors + GUI apps + shell/desktop). `hardware-nvidia` is applied by GPU
auto-detection (`gpu-detect` in `system`), not by listing it in `full`. Opt-in aesthetic/security
profiles stay opt-in.

**Alternatives considered**: A meta "expand to every profile" rule (would pull in opt-in/aesthetic
and conflicting sets); leaving `full` undefined (the current latent bug — rejected in spec Q1).

**Note**: Finalize the exact list against `profiles.toml` in tasks; it is declarative data, trivially
adjustable, and validated on load.

## R3 — `Ctx` concretion and threading of `force`/`dry_run`

**Decision**: `Ctx` is a **frozen Pydantic/dataclass value object** carrying `os: OsInfo`,
`ex: Executor`, `force: bool`, `dry_run: bool` (and a `resources` accessor). `Installer`/`Module`
methods receive it as their single parameter; primitives take `ctx` first. `dry_run` is honored
**inside the `RealExecutor`** (and primitives that must preview), so module/primitive code stays
declarative and isn't littered with `if dry_run` branches.

**Rationale**: A single immutable context object is the cleanest DI carrier (mirrors pyreview's
injected dependencies), keeps signatures uniform, and centralizing `dry_run` in the executor means
"preview vs. perform" is one well-tested decision point rather than scattered conditionals.

**Alternatives considered**: Passing `os`/`ex`/flags as separate args (verbose, error-prone);
threading `dry_run` through every primitive (duplicated branching); a mutable/global context (breaks
testability and the frozen-value discipline).

## R4 — Registry discovery

**Decision**: **Package-scan auto-discovery** — `registry.load()` imports every `devboost.modules.*`
submodule; classes decorated with `@register` self-register. `load()` then validates the whole graph
(every `requires` reference resolves, every `profiles` name exists in `profiles.toml`, no cycles,
GUI/headless consistency) before any side effect.

**Rationale**: "Adding a tool = one file" is the platform principle; auto-discovery means a new
module needs no edit to a central import list. Validation at load makes the convenience safe. With
~55 modules an explicit registry would be a constant merge-conflict and drift source.

**Alternatives considered**: Explicit central import/registry list (defeats the one-file principle;
drift-prone); entry-point plugin discovery (overkill for an in-tree, frozen single binary).

## R5 — Module metadata vs `profiles.toml` (single source for the README table)

**Decision**: Module **identity/behavior** metadata (`name`, `category`, `description`, `requires`,
`profiles`, `gui`) lives on the **typed module class** (single source of truth). `profiles.toml`
holds **only** the profile → module-name sets (the user-facing selection knob). The README profiles
table generator reads the typed registry (category/description from classes) + `profiles.toml`
(membership).

**Rationale**: Keeps each module's full truth in one file (the one-file principle), lets `mypy`/IDE
navigate it, and avoids duplicating category/description in two places. `profiles.toml` stays the one
human-facing declarative selection file (validated on load).

**Alternatives considered**: Keep all metadata in `profiles.toml`/per-module data (can't be
type-checked; splits a module's truth); duplicate metadata in both (drift). Deferring the table
generator rewrite to M10 is fine; until then it can read the registry.

## R6 — Build backend & freezing

**Decision**: `uv` + **`uv_build`** backend (matches `pyapps/pyreview`), Python **3.12** floor.
Freeze with **PyInstaller `--onefile`** per arch (x86_64 + aarch64), built natively on per-arch CI
runners — the path already proven in this repo (`scripts/build-bundle.sh`, `release.yml`). Bundled
static data via PyInstaller `datas`, resolved through a `resources` helper that works from source and
frozen.

**Rationale**: Reuses a working delivery pipeline; `uv_build` is the author's house standard;
PyInstaller cross-compilation is unsupported, so per-arch native builds (already in `release.yml`)
are correct. No native-extension deps (per spec FR-004: system tools shell out), keeping the freeze
clean.

**Alternatives considered**: Nuitka (smaller/faster but heavier toolchain; unnecessary given a
working PyInstaller path); shiv/PEX (needs a Python runtime on target — violates cold-start);
hatchling backend (pyreview standard is `uv_build`).

## R7 — Versions (verified via context7, not training data)

**Decision**: Pin to current majors at implementation time, verified live: **Typer** (context7
`/websites/typer_tiangolo`; `Annotated`-param + `CliRunner` testing patterns confirmed; current line
past 0.21 — pyreview uses `>=0.25.1`, adopt the current stable), **Pydantic v2**, **pydantic-settings
v2**, **loguru**, **pytest** (+ pytest-mock), **mypy**, **ruff**. The existing
`engine/pyproject.toml` pins `typer>=0.21,<0.22` — **bump to current** during M0.

**Rationale**: Per the project's version-pinning discipline, pin from live docs at build time, not
from memory. The `Annotated` typed-param style and `typer.testing.CliRunner` (hermetic CLI tests) are
the confirmed-current idioms and match the house style.

**Alternatives considered**: Keeping the stale `typer<0.22` pin (rejected — predates the current
line); Click directly (loses type-hint-native ergonomics + the house standard).

## R8 — Parity verification without a running bash engine (method)

**Decision**: Parity is verified by (1) **porting each module's bats assertions to pytest** against a
`FakeExecutor` (asserting the exact command sequence the bash module produced), and (2) **real
`install`/`verify` on a throwaway Fedora VM/container** per profile as its group completes, plus a
full `install full` + `verify full` at M10. The bash engine is **not** kept runnable for diffing.

**Rationale**: Greenfield + direct rewrite (spec Clarifications) means there's no shipped product to
diff against; the bash source + bats encode the behavioral spec, which is reproduced and re-asserted.
VM runs catch integration issues the hermetic fakes can't.

**Alternatives considered**: Plan-diffing the new engine against a still-runnable bash engine
(requires maintaining the bash engine in parallel — contradicts direct rewrite); trusting unit tests
alone (misses real-system integration).

## Cross-cutting decisions (already locked; recorded for completeness)

- **Logging**: loguru (`info/ok/skip/error` semantics preserved). **Errors**: `DevbootError` base +
  typed subclasses with chaining. **Concurrency**: synchronous. **External tools**: shell out via
  `Executor`; data via stdlib `json`/`tomllib`; GitHub API via stdlib HTTP. **OS dispatch**: `Dnf`
  implemented; `Apt`/`Pacman` are seams. (Design §2, §4.)
