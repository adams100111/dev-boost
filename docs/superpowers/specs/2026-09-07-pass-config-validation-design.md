# pass-config validation — design

**Date:** 2026-09-07
**Status:** Design approved (brainstormed); small follow-up to the Claude config module.

## Problem

When the `claude`/`security-cli` profile is selected but the operator forgot to configure the
`pass` store, provisioning failed **silently**: `PassStore.install` (`modules/optional.py`) fell back
to `pass init ""` (empty GPG id → broken/empty store), ignored the result, and the downstream claude
modules just `log.warn`ed "`pass show …` missing — skipping token". No clear signal that
`DEVBOOST_PASS_REPO` was unset. `doctor` validates the age bundle but nothing about `pass`.

## Decision (from brainstorming)

Hard-fail on **missing config** and **clone failure**; a missing single *entry* still degrades+warns
(unchanged); `doctor` surfaces the config state upfront (informational, never blocks).

## Changes

1. **`PassStore.install` hardening** (`engine/src/devboost/modules/optional.py`):
   - `DEVBOOST_PASS_REPO` set → `git clone`; **raise `ConfigError`** if the clone fails (was a
     non-blocking warn).
   - else `DEVBOOST_PASS_GPG_ID` set → `pass init <id>`; **raise `ConfigError`** if it fails.
   - else (neither) → **raise `ConfigError`** with an actionable message ("set `DEVBOOST_PASS_REPO`
     to clone your pass repo, or `DEVBOOST_PASS_GPG_ID` to init a new store").
   Profile-gated by construction: `PassStore` only runs when a profile selects it.

2. **New `ConfigError`** in `engine/src/devboost/core/errors.py` (subclass of `DevbootError`) —
   "a required configuration value or environment variable is missing/invalid".

3. **`doctor` `pass-config` check** (`engine/src/devboost/cli/doctor.py`): append a `Check`,
   **`ok=True` always** (informational — pass is opt-in and `doctor` doesn't know the selected
   profile; enforcement is `PassStore` at install time). Detail = configured-via-repo /
   configured-via-gpg-id / "not set — pass-backed secrets (claude/security-cli profile) will fail to
   provision; set `DEVBOOST_PASS_REPO`". Mirrors how the existing `secrets` check reports a missing
   bundle as visible-but-non-fatal.

**Unchanged:** the claude modules' per-*entry* degrade (`pass show <x>` missing → warn+skip).

## Tests

- `test_optional_ubuntu.py` (PassStore): neither-set → raises `ConfigError`; `DEVBOOST_PASS_REPO`
  set + clone fails (`scripts={"git": Result(1)}`) → raises. (Existing repo-clone-ok / gpg-init-ok
  tests keep passing — default `FakeExecutor` returns `Result(0)`.)
- `test_doctor_resources.py`: `pass-config` check present, `ok is True`, detail says "not set" when
  neither env var is set.

Gate: `uv run ruff check && uv run mypy && COLUMNS=80 uv run pytest -q` from `engine/`.
