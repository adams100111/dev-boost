# Quickstart — validating the bash → Python migration

Runnable scenarios that prove the rebuilt platform works end-to-end. References
[contracts/cli.md](./contracts/cli.md), [contracts/module-api.md](./contracts/module-api.md), and
[data-model.md](./data-model.md) — no implementation code is duplicated here.

## Prerequisites

- The typed project under `engine/` (src-layout `uv` project), Python 3.12, `uv` installed.
- For end-to-end parity runs: a throwaway Fedora VM/container (root/sudo, network).
- Unit/type/lint runs need neither network nor system package tools.

## Setup (from source)

```bash
cd engine
uv sync                      # install deps + dev tools (pytest, mypy, ruff)
uv run devboost --version    # CLI smoke
```

## Scenario 1 — Hermetic test suite is green (gates)

Proves: typed engine + primitives + modules + CLI verbs behave correctly with no real system access.

```bash
cd engine
uv run pytest                # all unit tests pass; FakeExecutor → no real dnf/flatpak/network
uv run mypy --strict src     # zero type errors
uv run ruff check src        # lint clean
```

Expected: all three pass. (Maps to SC-004, SC-005; FR-014, FR-016.)

## Scenario 2 — Resolution, dry-run, idempotency (no system needed)

Proves: profile expansion, dependency ordering, and the verify-guarded loop, all without mutation.

```bash
uv run devboost list --profile laravel     # prints toposorted order (docker before ddev, …)
uv run devboost install --profile laravel --dry-run   # prints intended actions; mutates nothing
```

Expected: `list` prints a deterministic dependency order; `--dry-run` records zero mutating calls
(asserted in tests via `FakeExecutor`). (Maps to SC-009; FR-005, FR-010.)

## Scenario 3 — Catalog validation catches bad authoring (no system needed)

Proves: a typo'd dependency / unknown profile / cycle is rejected before any side effect.

```bash
# (in a test or scratch module) declare requires=(Nonexistent,) or profiles=("nope",)
uv run mypy --strict src     # bad class reference fails type-check
uv run devboost list --profile full   # load-time validation rejects unknown profile / cycle, exit 1
```

Expected: type-checker and/or load-time validation reject it with a clear error. (Maps to SC-008;
FR-006.)

## Scenario 4 — End-to-end Fedora parity (throwaway VM)

Proves: a fresh Fedora machine reaches the same workstation, idempotently. Run as module groups
complete (per profile) and fully at M10.

```bash
# on a clean Fedora VM, with the frozen binary (or `uv run devboost`)
devboost install --profile base && devboost verify --profile base   # per-group as M1 lands
# ...
devboost install full && devboost verify full     # final acceptance (M10): fully green
devboost install full                               # second run: idempotent no-op (0 installs)
```

Expected: `verify full` fully green; the workstation builds Laravel/.NET+Aspire/Python/Next.js+React/
React-Native out of the box; second `install` changes nothing. (Maps to SC-001, SC-002; FR-005.)

## Scenario 5 — Frozen binary, cold start (no Python on target)

Proves: zero-runtime delivery is preserved.

```bash
# CI builds per-arch with PyInstaller (scripts/build-bundle.sh / release.yml)
./dist/devboost --version
./dist/devboost list --profile terminal    # smoke on x86_64 and aarch64
# bootstrap path on a cold box:
curl -fsSL <release>/get.sh | bash          # detect arch → download → SHA256-verify → exec
```

Expected: the binary runs with no Python installed; both arches pass the smoke test. (Maps to SC-006;
FR-015.)

## Scenario 6 — Bash is gone (end-state check)

Proves: only the bootstrap stub remains as bash.

```bash
# from repo root, at M10
! ls lib/*.sh 2>/dev/null            # no lib shell
! find . -name '*.bats' | grep .     # no bats
! find modules -name '*.sh' 2>/dev/null | grep .   # no per-module shell
ls get.sh ventoy/ks.cfg              # the only remaining bash (bootstrap stub + Kickstart %post)
```

Expected: no `lib/*.sh`, no `module.toml`, no per-module `.sh`, no `.bats`; only `get.sh` + Kickstart
`%post` remain. (Maps to SC-003; FR-001.)
