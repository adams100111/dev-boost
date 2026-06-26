# Contract — CLI command surface (`devboost`)

The public interface of the platform is the `devboost` CLI (Typer, fully type-annotated
`Annotated[...]` params; hermetic tests via `typer.testing.CliRunner`). Behavior/exit-code parity
with today's Fedora behavior. Verbs are ported at their milestone; this is the end-state surface.

## Global

- Entry point: `devboost = devboost.cli.app:main`. On targets, the frozen binary *is* `devboost`.
- Exit codes: `0` success; `1` failure (one or more modules failed, or a validation/preflight error).
- Common options where applicable: `--profile a,b` (repeatable/comma list; default `full`),
  `--dry-run`, `--force`.

## Verbs

| Verb | Signature (typed) | Behavior | Exit |
|---|---|---|---|
| `install` | `install(profiles: list[str] = ["full"], *, dry_run=False, force=False)` | Expand → toposort → verify-guarded idempotent install; regenerate `devboost.lock`. | 0 / 1 |
| `verify` | `verify(profiles: list[str] = ["full"])` | Report each module installed/missing (no mutation). | 0 / 1 |
| `list` | `list(profiles: list[str] = ["full"])` | Print resolved install order. | 0 |
| `doctor` | `doctor(*, gpu: bool = False)` | Environment preflight (OS detect, deps `jq`/`age`, modules dir, secrets state, mise-drift); `--gpu` runs the NVIDIA-stack diagnostics. Replaces `install.sh`'s dep-ensure. | 0 / 1 |
| `add` | `add(name: str, *, folder: bool = False)` | Scaffold a new typed module file. | 0 / 1 |
| `export` | `export()` | Snapshot actual installed state. | 0 |
| `diff` | `diff(profiles: list[str] = ["full"])` | Declared vs actual drift. | 0 / ≠0 on drift |
| `update` | `update(profiles: list[str] = ["full"])` | Propose pinned bumps + `devboost.lock` (no commit). | 0 |
| `self-update` | `self_update()` | Update dev-boost + re-validate. | 0 / 1 |
| `terminal` | `terminal(*, dry_run=False, force=False)` | Install the `terminal` tier (headless-aware). | 0 / 1 |
| `devtools` | `devtools(*, dry_run=False, force=False)` | Install the `devtools` tier. | 0 / 1 |
| `dev` | `dev(action: Literal["status","gc","down"])` | Dev-resource hygiene. | 0 / 1 |

## Contract guarantees (tested)

- `list --profile X` prints exactly the toposorted module names for X (deterministic order).
- `install` is idempotent: a second run with all verifies passing performs no installs and exits 0.
- A failed module makes `install` exit 1 with a message naming the module + the exact failing command.
- `--dry-run` performs no side effects (asserted via `FakeExecutor` recording zero mutating calls).
- Unknown profile/module or dependency cycle ⇒ exit 1 with a clear validation error, before side effects.
- All params are fully type-annotated; `mypy --strict` clean (FR-011, FR-014).
