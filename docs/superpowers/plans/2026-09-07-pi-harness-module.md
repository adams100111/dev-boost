# Pi harness module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single `pi-harness` dev-boost module that bootstraps the operator's Pi
coding-agent harness (`harness-cli` in the private `adams100111/agent-harness` repo) and delegates
all `~/.pi` configuration to it — shipped in `full` plus a `pi` profile.

**Architecture:** Bootstrap-and-delegate (see `docs/superpowers/specs/2026-09-07-pi-harness-module-design.md`).
The module ensures node (Mise), clones+builds `agent-harness` → `harness` on PATH (HARD-fails via
`ConfigError`), then runs `harness secrets init --backend pass` + `provision` (SOFT — only if a pass
store exists) and `harness install` (SOFT — best-effort, never reds the build). No dotfiles, no
`pi-config`: `harness-cli` is the sole writer of `~/.pi`. Auth for the private clone is the GitHub
PAT the existing `secrets` module already wrote into `~/.git-credentials`.

**Tech Stack:** typed-Python dev-boost engine (`engine/src/devboost/`), `@register` `Module`
subclasses, `Ctx`/`Executor` seam, `FakeExecutor` tests, `mypy --strict` + ruff + pytest gates.

## Global Constraints

- Merge gates: `uv run ruff check`, `uv run mypy`, `uv run pytest` all green; 80-column lines.
- Module name `pi-harness`; profile `pi`. They must differ (profile/module name-collision rule).
- `requires = (Mise, Secrets)` ONLY — never `PassStore` (it raises `ConfigError` when pass is
  unconfigured; requiring it would break `full` on pass-less boxes).
- **HARD failure** (bootstrap) = raise `devboost.core.errors.ConfigError` with an actionable message.
  **SOFT failure** (provision, `harness install`) = `devboost.core.log.warn(...)` and continue;
  never raise, never abort the `full` build.
- `DEFAULT_HARNESS_REPO = "adams100111/agent-harness"`, `DEFAULT_HARNESS_REF = "main"`; both
  overridable via `DEVBOOST_HARNESS_REPO` / `DEVBOOST_HARNESS_REF` env vars.
- Bootstrap clones the DEFAULT branch shallowly just to obtain `install.sh`, then runs it with
  `HARNESS_REF=<ref>` (install.sh does the ref-pinned clone — so SHA/tag/branch all work).
- No commit trailer or body may reference Claude/Anthropic.

## Grill-confirmed runtime behaviors (facts — do not re-litigate)

- **Failure isolation:** `core/runner.py` wraps `mod.install(ctx)` in `except Exception` → a raising
  module becomes an isolated `fail` result; the run CONTINUES to other modules. Nothing `requires`
  `pi-harness`, so no cascade. So a HARD bootstrap failure fails only Pi in `full` (the overall run
  exits non-zero and reports `pi-harness: fail`), never the whole workstation.
- **No exec timeout:** `RealExecutor.run` calls `subprocess.run` with no timeout — a multi-minute
  `harness install` runs to completion.
- **PATH:** `RealExecutor` prepends `~/.local/bin` for both `run` and `which`, so `which("harness")`
  and `run(["harness"/"pass", …])` resolve. (Do NOT add `pi-harness` to accounts-firstboot bootstrap
  choices — that path demotes via root and would probe `/root/.local/bin`.)
- **`requires` are auto-installed transitively** (`toposort`), so `devboost install pi` pulls Mise +
  Secrets and orders them first.
- **`install.sh` env:** `HARNESS_REPO` (full URL, default the agent-harness https URL), `HARNESS_REF`
  (branch/tag/SHA, default `main`); it re-clones `HARNESS_REPO@HARNESS_REF` into
  `~/.local/share/harness` itself. It does NOT modify PATH.
- **`harness secrets init --backend pass --yes`** exits 0 with a partial auto-map: `CONTEXT7_API_KEY`,
  `GOOGLE_CLIENT_ID`→`google-docs/dits_client_id`, `GOOGLE_CLIENT_SECRET` all map; `HERDR_*` stay
  unmapped. Writes `~/.config/harness/config.toml`.
- **`harness provision`** writes whatever the backend returns; it **throws** if a *mapped* pass entry
  can't be decrypted (GPG passphrase not cached unattended) — hence SOFT/guarded. Expect a **partial**
  provision (context7 + google), never herdr secrets.
- **`harness install --yes`** needs no prior `setup`, installs pi itself, and **exits non-zero today**
  on the herdr `REPLACE_WITH_VERIFIED_SHA256` pin — hence SOFT/guarded; pi core installs first.
- **`verify()=which harness` ⇒ bootstrap-once:** a re-run skips the module (so provision/install do
  not retry) unless `--force`. Ongoing reconcile is `harness-cli`'s job (`harness upgrade`, etc.).

---

### Task 1: `pi-harness` module + profile wiring + unit tests

**Files:**
- Create: `engine/src/devboost/modules/pi_harness.py`
- Modify: `profiles.toml` (add `pi` profile; add `"pi"` to `full`)
- Modify: `engine/tests/conftest.py` (add `pi = ["pi-harness"]` to the profiles.toml fixture)
- Modify: `engine/tests/cli/test_lifecycle_devhygiene.py` (add `pi = ["pi-harness"]` to its inline table)
- Create: `engine/tests/modules/test_pi_harness.py`

**Interfaces:**
- Consumes: `Mise`, `Secrets` (modules); `mise.use_global(ctx, spec)`; `log.warn/info`;
  `ConfigError`; `FakeExecutor(present=..., scripts=..., calls=...)` where `scripts` maps the
  FIRST argv token → a canned `Result`, and `env` passed to `run` is NOT recorded (assert on argv).
- Produces: module `pi-harness` (registered), profile `pi`.

**Why the profile wiring is in THIS task:** `pi-harness` declares `profiles = ("pi",)`, and
`validate_profiles` fails load-wide unless every profiles.toml the suite loads (real + both
fixtures) has a `pi` key. So the `pi` key must land in the same change that introduces the module.

- [ ] **Step 1: Add the `pi` profile wiring first (keeps the suite loadable)**

In `profiles.toml`, add after the `codex` line (line ~21):
```toml
# pi — bootstrap the operator's Pi coding-agent harness (harness-cli) and delegate config.
pi = ["pi-harness"]
```
And add `"pi"` to the `full` list (end of its array, after `"codex"`):
```toml
full = ["base","cli","shell","gnome","multimedia","editors","python","web","laravel",
        "dotnet","data","devops","react-native","apps","system","dev-hygiene","remote","claude","codex","pi"]
```
In `engine/tests/conftest.py`, add after the `'codex = ["codex-code"]\n'` line:
```python
        'pi = ["pi-harness"]\n'
```
In `engine/tests/cli/test_lifecycle_devhygiene.py`, change the final table line from
`'laravel = ["ddev"]\nclaude = ["claude-code"]\ncodex = ["codex-code"]\n',` to:
```python
        'laravel = ["ddev"]\nclaude = ["claude-code"]\ncodex = ["codex-code"]\n'
        'pi = ["pi-harness"]\n',
```
(If a repo-wide grep `grep -rn 'codex = \["codex-code"\]' engine/tests` finds any OTHER inline
profiles.toml fixture, add the same `pi = ["pi-harness"]` line there too.)

- [ ] **Step 2: Write the failing unit tests**

Create `engine/tests/modules/test_pi_harness.py`:
```python
from __future__ import annotations

import pytest

from devboost.core.errors import ConfigError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.pi_harness import PiHarness

FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def _joined(ctx: Ctx) -> list[str]:
    return [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]


def test_verify_uses_harness_binary() -> None:
    assert PiHarness().verify(_ctx(present={"harness"})) is True
    assert PiHarness().verify(_ctx()) is False


def test_bootstrap_clones_repo_and_runs_installer() -> None:
    ctx = _ctx(present={"node", "harness"})
    PiHarness().install(ctx)
    j = _joined(ctx)
    assert any("github.com/adams100111/agent-harness" in c for c in j)
    assert any("install.sh" in c for c in j)
    assert any("HARNESS_REF=main" in c for c in j)
    # install.sh must receive HARNESS_REPO as a full URL (it re-clones the repo itself).
    assert any("HARNESS_REPO=https://github.com/adams100111/agent-harness" in c for c in j)


def test_provisions_node_when_absent() -> None:
    ctx = _ctx(present={"harness"})  # node absent
    PiHarness().install(ctx)
    assert any("node@lts" in c for c in _joined(ctx))


def test_bootstrap_failure_raises_configerror() -> None:
    ctx = _ctx(present={"node"}, scripts={"sh": Result(1)})
    with pytest.raises(ConfigError):
        PiHarness().install(ctx)


def test_env_overrides_repo_and_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVBOOST_HARNESS_REPO", "me/fork")
    monkeypatch.setenv("DEVBOOST_HARNESS_REF", "v1.2.3")
    ctx = _ctx(present={"node", "harness"})
    PiHarness().install(ctx)
    j = _joined(ctx)
    assert any("github.com/me/fork" in c for c in j)
    assert any("HARNESS_REF=v1.2.3" in c for c in j)
    assert any("HARNESS_REPO=https://github.com/me/fork" in c for c in j)


def test_provisions_from_pass_when_store_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    monkeypatch.setenv("PASSWORD_STORE_DIR", str(tmp_path))  # tmp_path exists
    ctx = _ctx(present={"node", "harness", "pass"})
    PiHarness().install(ctx)
    j = _joined(ctx)
    assert any("harness secrets init --backend pass" in c for c in j)
    assert any(c == "harness provision" for c in j)


def test_skips_provision_without_pass_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PASSWORD_STORE_DIR", raising=False)
    ctx = _ctx(present={"node", "harness"})  # no pass
    PiHarness().install(ctx)
    assert not any("secrets init" in c for c in _joined(ctx))


def test_guarded_install_never_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    # bootstrap (`sh`) succeeds by default; every `harness ...` call fails.
    monkeypatch.setenv("PASSWORD_STORE_DIR", str(tmp_path))
    ctx = _ctx(present={"node", "harness", "pass"}, scripts={"harness": Result(1)})
    PiHarness().install(ctx)  # must NOT raise
    assert any("harness install --yes" in c for c in _joined(ctx))
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd engine && uv run pytest tests/modules/test_pi_harness.py -q`
Expected: FAIL — `ModuleNotFoundError: devboost.modules.pi_harness`.

- [ ] **Step 4: Write the module**

Create `engine/src/devboost/modules/pi_harness.py`:
```python
"""pi-harness — bootstrap the operator's Pi agent-harness (harness-cli) and delegate config."""

from __future__ import annotations

import os
from pathlib import Path

from devboost.core import log
from devboost.core.errors import ConfigError
from devboost.core.registry import register
from devboost.exec.primitives import mise
from devboost.model import Ctx, Module
from devboost.modules.mise import Mise
from devboost.modules.secrets import Secrets

DEFAULT_HARNESS_REPO = "adams100111/agent-harness"
DEFAULT_HARNESS_REF = "main"


@register
class PiHarness(Module):
    name = "pi-harness"
    category = "cli"
    description = "Bootstrap the Pi coding-agent harness (clone+build harness-cli; delegate config)."
    requires = (Mise, Secrets)
    profiles = ("pi",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("harness")

    def _repo(self) -> str:
        return os.environ.get("DEVBOOST_HARNESS_REPO", DEFAULT_HARNESS_REPO)

    def _ref(self) -> str:
        return os.environ.get("DEVBOOST_HARNESS_REF", DEFAULT_HARNESS_REF)

    def _pass_ready(self, ctx: Ctx) -> bool:
        store = os.environ.get("PASSWORD_STORE_DIR") or str(
            Path(os.environ["HOME"]) / ".password-store"
        )
        return ctx.ex.which("pass") and Path(store).is_dir()

    def install(self, ctx: Ctx) -> None:
        if not ctx.ex.which("node"):
            mise.use_global(ctx, "node@lts")

        # Bootstrap (HARD). Auth = the PAT the `secrets` module wrote into ~/.git-credentials
        # (credential.helper store), so the private clone inside install.sh authenticates with no
        # token juggling. Shallow-clone the default branch just to obtain install.sh; it then does
        # the HARNESS_REF-pinned clone itself (so SHA/tag/branch all work).
        repo, ref = self._repo(), self._ref()
        url = f"https://github.com/{repo}"
        # install.sh re-clones $HARNESS_REPO@$HARNESS_REF into ~/.local/share/harness itself
        # (our temp checkout is only the source of install.sh's bytes), so BOTH env vars must be
        # passed — and install.sh's HARNESS_REPO is a full URL, not owner/repo.
        script = (
            f"set -e; d=$(mktemp -d); "
            f'git clone --depth 1 {url} "$d/h"; '
            f'HARNESS_REPO={url} HARNESS_REF={ref} bash "$d/h/install.sh"'
        )
        res = ctx.ex.run(["sh", "-c", script])
        if not res.ok:
            raise ConfigError(
                f"pi-harness: bootstrapping agent-harness ({repo}@{ref}) failed "
                f"(exit {res.code}) — check the GitHub PAT from the secrets bundle has "
                "read scope on the private repo"
            )

        # Provision secrets from pass (SOFT) — only when a pass store is present.
        if self._pass_ready(ctx):
            init = ctx.ex.run(["harness", "secrets", "init", "--backend", "pass", "--yes"])
            if not init.ok:
                log.warn("pi-harness: `harness secrets init` failed — provision manually later")
            elif not ctx.ex.run(["harness", "provision"]).ok:
                log.warn("pi-harness: `harness provision` failed — run `harness provision` later")
        else:
            log.warn(
                "pi-harness: no pass store — skipping secret provisioning "
                "(run `harness secrets init` + `harness provision` later)"
            )

        # Reconcile the manifest (SOFT) — never red the full build if the manifest is pre-release
        # or secrets are missing. First Pi session still needs a one-time `pi /login`.
        if not ctx.ex.run(["harness", "install", "--yes"]).ok:
            log.warn(
                "pi-harness: `harness install` incomplete — run `harness doctor` then "
                "`harness install`; first Pi session needs a one-time `pi /login`"
            )
        else:
            log.info("pi-harness: installed; first Pi session needs a one-time `pi /login`")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd engine && uv run pytest tests/modules/test_pi_harness.py -q`
Expected: PASS (8 tests).

- [ ] **Step 6: Run the gates**

Run: `cd engine && uv run ruff check && uv run mypy && uv run pytest -q`
Expected: all green (the new module registers; `pi` profile validates; no regressions).

- [ ] **Step 7: Commit**

```bash
git add engine/src/devboost/modules/pi_harness.py engine/tests/modules/test_pi_harness.py \
        profiles.toml engine/tests/conftest.py engine/tests/cli/test_lifecycle_devhygiene.py
git commit -m "feat(pi): pi-harness bootstraps agent-harness (harness-cli) + delegates; in full & pi profile"
```

---

### Task 2: Profile-expansion integration test + roadmap note

**Files:**
- Create: `engine/tests/cli/test_pi_profile.py`
- Modify: `docs/roadmap.md` (one line noting the shipped Pi module, if a modules/agents section exists)

**Interfaces:**
- Consumes: `devboost.core.profiles.load_profiles`, `expand`; `devboost.core.registry` module load
  (the same helpers other profile tests use — check `engine/tests/cli/` for the exact import path
  used by an existing profile test, e.g. how `full` is expanded there, and mirror it).

- [ ] **Step 1: Write the failing integration test**

Create `engine/tests/cli/test_pi_profile.py`. Mirror an existing profile-expansion test's imports
(find one with `grep -rln "def expand\|load_profiles\|load()" engine/tests`); the assertions:
```python
from __future__ import annotations

from pathlib import Path

from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_pi_profile_expands_to_pi_harness() -> None:
    profiles = load_profiles(REPO_ROOT / "profiles.toml")
    modules = load()
    assert expand(["pi"], profiles, modules) == ["pi-harness"]


def test_full_includes_pi_harness() -> None:
    profiles = load_profiles(REPO_ROOT / "profiles.toml")
    modules = load()
    assert "pi-harness" in expand(["full"], profiles, modules)
```
(If `load()`'s real name/signature differs, adjust to whatever the existing profile tests call to
get `dict[name, Module]` — do NOT invent an API; copy the working one.)

- [ ] **Step 2: Run to verify it fails, then passes**

Run: `cd engine && uv run pytest tests/cli/test_pi_profile.py -q`
If it fails only because `load()`/import names differ, fix the imports to match the existing profile
test and re-run. Expected once correct: PASS. (These assertions already hold after Task 1 — this
task LOCKS them so a future edit to `full`/`pi` can't silently drop Pi.)

- [ ] **Step 3: Roadmap note (only if a relevant section exists)**

If `docs/roadmap.md` tracks shipped modules/agents, add one line under the agent-config entry:
`- pi-harness — bootstraps the operator's Pi harness (harness-cli); in \`full\` + \`pi\` profile.`
If there's no natural home, skip this step (do not invent a section).

- [ ] **Step 4: Run the gates + commit**

```bash
cd engine && uv run ruff check && uv run mypy && uv run pytest -q
git add engine/tests/cli/test_pi_profile.py docs/roadmap.md
git commit -m "test(pi): lock pi profile expansion + full membership"
```

---

### Task 3: `pi-login` doctor check (informational, never-blocking)

**Files:**
- Modify: `engine/src/devboost/cli/doctor.py` (append a `pi-login` `Check`, mirroring `pass-config`)
- Modify/Create: the doctor test (find it: `grep -rln "run_checks\|pass-config" engine/tests`; add a
  case there, or create `engine/tests/cli/test_doctor_pi_login.py`)

**Interfaces:**
- Consumes: `Check`, `run_checks(ctx, root)` in `doctor.py`; `Ctx`/`FakeExecutor`; `Path`.
- The check is **always `ok=True`** (informational only) — like `pass-config` it must never fail
  `all_ok()` (doctor doesn't know the selected profile, and Pi auth is a manual one-time step).

- [ ] **Step 1: Write the failing test**

Add a test asserting `run_checks` includes a `pi-login` check that is always `ok=True`, and whose
`detail` differs by auth state. Mirror how the existing doctor test builds a `Ctx` +
`FakeExecutor` and calls `run_checks(ctx, root)`:
```python
def test_pi_login_check_is_informational(tmp_path: object) -> None:
    ctx = Ctx(os=FEDORA, ex=FakeExecutor(present={"harness"}))  # type: ignore[arg-type]
    checks = run_checks(ctx, tmp_path)  # type: ignore[arg-type]
    pi = next(c for c in checks if c.name == "pi-login")
    assert pi.ok is True
    assert "pi /login" in pi.detail  # reminds when auth.json absent
```
(Match the existing doctor test's imports/fixtures for `FEDORA`, `Ctx`, `run_checks`.)

- [ ] **Step 2: Run it to see it fail**

Run: `cd engine && uv run pytest -k pi_login -q` → FAIL (no `pi-login` check yet).

- [ ] **Step 3: Add the check to `doctor.py`**

After the `pass-config` block (before `return checks`), append:
```python
    # pi-login: informational only (ok=True) — Pi auth is a manual one-time `pi /login` per box
    # (like pass-config, doctor never blocks on it). Surfaces the reminder until auth.json exists.
    auth_json = Path(os.environ["HOME"]) / ".pi" / "agent" / "auth.json"
    if auth_json.exists():
        pi_detail = "Pi authenticated (~/.pi/agent/auth.json present)"
    elif ctx.ex.which("harness") or ctx.ex.which("pi"):
        pi_detail = "Pi installed but not authenticated — run `pi /login` once per box"
    else:
        pi_detail = "Pi not installed (install the `pi` profile)"
    checks.append(Check("pi-login", True, pi_detail))
```

- [ ] **Step 4: Run tests + gates**

Run: `cd engine && uv run ruff check && uv run mypy && uv run pytest -q` → all green.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/cli/doctor.py engine/tests/cli/test_doctor_pi_login.py
git commit -m "feat(pi): informational pi-login doctor check (reminds to run pi /login)"
```

---

## Self-review notes

- **Spec coverage:** design's single `pi-harness` module (bootstrap HARD + guarded provision/install,
  `requires=(Mise,Secrets)`, `pi` profile + `full`, no dotfiles) → Task 1. Profile membership
  guarantee → Task 2. Informational `pi-login` doctor check → Task 3. No spec requirement unmapped.
- **Placeholder scan:** none. `DEFAULT_HARNESS_REF="main"` is an intentional env-overridable default.
- **Type consistency:** `verify→bool`, `install→None`, `_repo/_ref→str`, `_pass_ready→bool`; module
  name `pi-harness`, profile `pi` used identically in module, profiles.toml, and both test fixtures.
- **FakeExecutor caveat baked into tests:** `env=` is not recorded, so `HARNESS_REF`/repo are
  asserted via the `sh -c` script argv (they appear literally in it), and guarded behavior is driven
  by `scripts={token: Result(1)}` on the `sh` (bootstrap) vs `harness` (soft) tokens.
