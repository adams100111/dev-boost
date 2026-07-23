# Remote Fleet — M1: Tailnet Reach — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the laptops (`full` profile) first-class tailnet members with a resilient terminal — add a `mosh` module and a `remote` connectivity-spine profile, wired into `full`.

**Architecture:** A new one-file `Mosh` module (single `pkg.install`, mirroring the `Ripgrep` tracer) plus a new `remote` leaf profile `["tailscale", "mosh"]` that `full` includes. The existing `Tailscale` module gains `remote` in its `profiles`. This is the smallest independently-shippable slice of the remote-fleet spec (§3, §5.1); M2 (brain overlay) and M3 (DX + docs) are separate plans.

**Tech Stack:** Python ≥3.12, Typer/Pydantic engine, `pkg` OS-dispatch primitive (dnf/apt), injected `Executor` (`FakeExecutor` in tests), `uv` for build/test.

**Source spec:** `docs/superpowers/specs/2026-07-22-remote-fleet-workflow-design.md` (§3 Profile structure, §5.1 `mosh`, §2 layered model).

## Global Constraints

- Merge gates, all must pass from `engine/`: `uv run ruff check`, `uv run mypy` (`--strict`), `uv run pytest`.
- Every module is one typed file, `@register`-decorated, `mypy --strict` clean.
- `validate_profiles` invariant: every module's declared `profiles` tuple must name a profile key that exists in **every** validated profiles source — the live `profiles.toml` (checked by `tests/modules/test_base.py:144` and `test_system.py:266`) **and** the synthetic fixtures in `tests/conftest.py` and `tests/cli/test_lifecycle_devhygiene.py`.
- Profile names must differ from every module name (profile/module name-collision rule): `remote` is a profile, not a module — OK.
- Commit messages: no `Co-Authored-By: Claude` trailer, no Claude/Anthropic attribution of any kind.
- Ruff lint set: `E, F, I, UP, B` (line length 100). Modules use `from __future__ import annotations`.

---

## File Structure

- **Create** `engine/src/devboost/modules/mosh.py` — the `Mosh` module (one responsibility: install mosh).
- **Create** `engine/tests/modules/test_mosh.py` — hermetic unit tests for `Mosh`.
- **Modify** `profiles.toml` — add `remote` leaf; add `remote` to `full`.
- **Modify** `engine/src/devboost/modules/server.py` — `Tailscale.profiles` gains `remote`.
- **Modify** `engine/tests/conftest.py` — add `remote` key to the `profiles_file` fixture.
- **Modify** `engine/tests/cli/test_lifecycle_devhygiene.py` — add `remote` key to its synthetic profiles block.
- **Modify** `README.md` — regenerate the profiles table (adds the `remote` row).
- **Modify** `docs/roadmap.md` — note M1 shipped.

---

## Task 1: `mosh` module + `remote` profile spine

Single cohesive deliverable: laptops get the `remote` spine (Tailscale + Mosh). The module and the profile wiring land together so the full test suite is green at commit (creating the module alone would make `test_base`/`test_system` red until `remote` exists in `profiles.toml`).

**Files:**
- Create: `engine/src/devboost/modules/mosh.py`
- Create: `engine/tests/modules/test_mosh.py`
- Modify: `profiles.toml`
- Modify: `engine/src/devboost/modules/server.py` (the `Tailscale` class, `profiles = ("server",)`)
- Modify: `engine/tests/conftest.py` (`profiles_file` fixture)
- Modify: `engine/tests/cli/test_lifecycle_devhygiene.py` (synthetic `[profiles]` block)

**Interfaces:**
- Consumes: `pkg.install(ctx, "mosh")` (existing primitive, dnf/apt dispatch); `Module` base, `@register`, `Ctx`.
- Produces: `Mosh` module — `name = "mosh"`, `category = "remote"`, `profiles = ("remote",)`, `verify(ctx) -> bool` (via `ctx.ex.which("mosh")`), `install(ctx) -> None`. New profile key `remote = ["tailscale", "mosh"]`. `Tailscale.profiles == ("server", "remote")`.

- [ ] **Step 1: Write the failing test**

Create `engine/tests/modules/test_mosh.py`:

```python
from __future__ import annotations

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules.mosh import Mosh


def test_mosh_installs_via_dnf(fedora_ctx: Ctx) -> None:
    Mosh().install(fedora_ctx)
    assert ["sudo", "dnf", "install", "-y", "mosh"] in fedora_ctx.ex.calls  # type: ignore[attr-defined]


def test_mosh_installs_via_apt(ubuntu_os: OsInfo) -> None:
    ex = FakeExecutor()
    Mosh().install(Ctx(os=ubuntu_os, ex=ex))
    assert ["sudo", "apt-get", "install", "-y", "mosh"] in ex.calls


def test_mosh_verify_uses_which() -> None:
    ex = FakeExecutor(present={"mosh"})
    ctx = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=ex)
    assert Mosh().verify(ctx) is True
    assert Mosh().verify(Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor())) is False


def test_mosh_is_in_remote_profile_only() -> None:
    assert Mosh.profiles == ("remote",)
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `engine/`): `uv run pytest tests/modules/test_mosh.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'devboost.modules.mosh'`.

- [ ] **Step 3: Create the module**

Create `engine/src/devboost/modules/mosh.py`:

```python
"""mosh — roaming-resilient terminal transport (survives sleep / Wi-Fi→cellular)."""

from __future__ import annotations

from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import Ctx, Module


@register
class Mosh(Module):
    name = "mosh"
    category = "remote"
    description = "Mosh — roaming-resilient terminal transport (client + mosh-server)."
    profiles = ("remote",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("mosh")

    def install(self, ctx: Ctx) -> None:
        # One package ships both the `mosh` client and `mosh-server`. Its UDP range
        # (60000-61000) rides tailscale0, already allowed by server-firewall — no new
        # firewall rules are required.
        pkg.install(ctx, "mosh")
```

- [ ] **Step 4: Run the module test to verify it passes**

Run (from `engine/`): `uv run pytest tests/modules/test_mosh.py -q`
Expected: PASS (4 passed).

> Do NOT run the full suite yet — `test_base`/`test_system` will fail until the `remote` profile exists (next steps).

- [ ] **Step 5: Add the `remote` leaf profile and include it in `full`**

In `profiles.toml`, add a new leaf line (place it near the other leaf profiles, after the `shell` line) and add `remote` to the `full` array. The `full` line becomes:

```toml
full = ["base","cli","shell","gnome","multimedia","editors","python","web","laravel",
        "dotnet","data","devops","react-native","apps","system","dev-hygiene","remote"]
```

And add the leaf:

```toml
remote = ["tailscale","mosh"]
```

- [ ] **Step 6: Add `remote` to `Tailscale.profiles`**

In `engine/src/devboost/modules/server.py`, change the `Tailscale` class attribute:

```python
    profiles = ("server", "remote")
```

(from `profiles = ("server",)` — around line 42.)

- [ ] **Step 7: Add `remote` to the `conftest.py` fixture**

In `engine/tests/conftest.py`, inside the `profiles_file` fixture's `p.write_text(...)`, add this line alongside the other profile lines (e.g. right after the `'server = ["zram"]\n'` line):

```python
        'remote = ["tailscale","mosh"]\n'
```

- [ ] **Step 8: Add `remote` to the `test_lifecycle_devhygiene.py` synthetic profiles**

In `engine/tests/cli/test_lifecycle_devhygiene.py`, in the synthetic `[profiles]` string (the block containing `'optional-agents = ["herdr"]\n'` and `'server = ["zram"]\n'` around lines 28-40), add:

```python
        'remote = ["tailscale","mosh"]\n'
```

- [ ] **Step 9: Run the full gates**

Run (from `engine/`):
```
uv run pytest -q
uv run mypy
uv run ruff check
```
Expected: pytest all green (including `test_mosh.py`, `test_base.py`, `test_system.py`, `test_lifecycle_devhygiene.py`), mypy clean, ruff clean.

- [ ] **Step 10: Commit**

```bash
git add engine/src/devboost/modules/mosh.py engine/tests/modules/test_mosh.py \
        profiles.toml engine/src/devboost/modules/server.py \
        engine/tests/conftest.py engine/tests/cli/test_lifecycle_devhygiene.py
git commit -m "feat(remote): add mosh module + remote profile spine into full"
```

---

## Task 2: M1 documentation slice

**Files:**
- Modify: `README.md` (regenerated profiles table)
- Modify: `docs/roadmap.md`

**Interfaces:**
- Consumes: the `remote` profile + `Mosh`/`Tailscale` module metadata from Task 1 (the generator reads the typed registry + `profiles.toml`).
- Produces: README table with a `remote` row; roadmap note.

- [ ] **Step 1: Regenerate the README profiles table**

Run (from repo root): `uv run --project engine python scripts/gen_profiles_table.py`
This rewrites the table between the `BEGIN`/`END` markers in `README.md` from the typed registry + `profiles.toml`.

- [ ] **Step 2: Verify the table changed as expected**

Run: `git diff README.md`
Expected: the diff shows a new `remote` profile row (with `tailscale` + `mosh`) and `mosh` listed under `full`. If the diff is empty or wrong, the generator did not pick up Task 1 — re-check `profiles.toml` and `Mosh`/`Tailscale` `profiles`.

- [ ] **Step 3: Add the roadmap note**

In `docs/roadmap.md`, add a short bullet recording M1 (match the existing "Shipped" bullet style, e.g. the herdr line):

```markdown
- **Remote fleet — M1 (tailnet reach):** laptops (`full`) now join the tailnet and ship
  Mosh via the new `remote` spine profile. (M2 brain overlay + M3 DX/docs to follow.)
```

- [ ] **Step 4: Verify docs build/lint is unaffected**

Run (from `engine/`): `uv run pytest -q`
Expected: still all green (README/roadmap edits don't affect tests, but confirm nothing regressed).

- [ ] **Step 5: Commit**

```bash
git add README.md docs/roadmap.md
git commit -m "docs(remote): regenerate profiles table + roadmap note for M1 tailnet reach"
```

---

## Self-Review (completed during authoring)

**Spec coverage (M1 scope only):** §3 `remote` leaf + `full` inclusion → Task 1 steps 5-6. §5.1 `mosh` module (pkg install both ends, `which` verify, no firewall rules) → Task 1 steps 1-4. §10.2/§10.3 M1 doc slice (README rows + roadmap) → Task 2. M2 (brain overlay) and M3 (fleet/docs capstone) are explicitly out of this plan — separate plans.

**Placeholder scan:** none — every step has exact file paths, complete code, and exact commands with expected output.

**Type consistency:** `Mosh.profiles == ("remote",)` (Task 1 step 1 test ↔ step 3 module ↔ spec §5.1). `Tailscale.profiles == ("server", "remote")` (step 6). The `remote` key is added to all three validated profiles sources (live `profiles.toml` step 5, `conftest.py` step 7, `test_lifecycle_devhygiene.py` step 8), satisfying the Global Constraints `validate_profiles` invariant. Apt assertion `["sudo","apt-get","install","-y","mosh"]` matches `pkg.Apt.install`; dnf assertion matches `pkg.Dnf.install`.
</content>
