# Remote Fleet — M2 (part 1): Brain Tooling & Profiles — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the brain-overlay *tooling and profiles* — the `caddy` and `crossarch-build` modules, the `brain-host` and `brain-tools` leaf profiles — and remove `agent-sudo` from the default `server` profile.

**Architecture:** Two new one-file modules following the existing `docker.py` per-OS pattern (Fedora reference + **Debian/Ubuntu primary**, since the fleet's brain runs on Ubuntu servers). `caddy` installs via the official COPR (Fedora) / Cloudsmith apt repo (Debian). `crossarch-build` installs `podman` + `qemu-user-static` (both families' default repos) for capped rootless multi-arch builds. New leaf profiles `brain-host = ["mosh","caddy","crossarch-build"]` and `brain-tools = ["herdr","herdr-plugins"]`. This is the tooling layer of spec §5.2/§5.3/§3; the `devbrain` managed account + `devboost brain` wrapper (spec §4/§6) are the immediately-following M2 part 2 plan.

**Tech Stack:** Python ≥3.12, `pkg` OS-dispatch primitive (`install(ctx, *pkgs, source=OsMap(...))`, `add_repo`), `AptRepo`/`OsMap`, injected `Executor`/`FakeExecutor`, chezmoi dotfiles, `uv`.

**Source spec:** `docs/superpowers/specs/2026-07-22-remote-fleet-workflow-design.md` (§3 profiles, §5.2 caddy, §5.3 crossarch-build, §5.4 herdr→brain-tools).

## Global Constraints

- Merge gates, all from `engine/`: `uv run ruff check`, `uv run mypy` (`--strict`), `uv run pytest`.
- Each module: one typed file, `@register`, mypy --strict clean, `from __future__ import annotations`.
- **Two OS families are supported: Fedora (dnf) and Debian/Ubuntu (apt) — both must be implemented and tested.** Debian/Ubuntu is the primary target (the brain runs on Ubuntu servers). For any other `ctx.os.family`, `raise UnsupportedOS` (do not silently no-op).
- `validate_profiles` invariant: every module's declared `profiles` must name a key present in the live `profiles.toml` AND the synthetic fixtures `engine/tests/conftest.py` and `engine/tests/cli/test_lifecycle_devhygiene.py`.
- Green-at-commit: a module declaring `profiles=("X",)` requires key `X` to already exist in all three sources at that commit; never reference a not-yet-created module from a profile that any test expands (`full`, or an explicitly-expanded profile). `brain-host`/`brain-tools` are expanded by no test, but keep their member lists to modules that exist as of that commit.
- Profile names differ from module names (`brain-host`, `brain-tools` are profiles; `caddy`, `crossarch-build` are modules — OK).
- Commit messages: no Claude/Anthropic attribution.
- Ruff set: `E, F, I, UP, B`, line length 100.

---

## File Structure

- **Create** `engine/src/devboost/modules/caddy.py` — the `Caddy` module (per-OS install).
- **Create** `engine/tests/modules/test_caddy.py` — `Caddy` tests (both OS paths).
- **Create** `engine/src/devboost/modules/crossarch_build.py` — the `CrossArchBuild` module.
- **Create** `engine/tests/modules/test_crossarch_build.py` — its tests.
- **Create** `dotfiles/dot_config/caddy/Caddyfile` — starter Caddyfile (chezmoi source).
- **Modify** `profiles.toml` — add `brain-host`, `brain-tools` leaves.
- **Modify** `engine/src/devboost/modules/mosh.py` — `Mosh.profiles` gains `brain-host`.
- **Modify** `engine/src/devboost/modules/herdr.py` — `Herdr`/`HerdrPlugins` gain `brain-tools`.
- **Modify** `engine/src/devboost/modules/server.py` — `AgentSudo.profiles = ()`.
- **Modify** `profiles.toml` — remove `agent-sudo` from `server`.
- **Modify** `engine/tests/conftest.py`, `engine/tests/cli/test_lifecycle_devhygiene.py` — add `brain-host`/`brain-tools` keys.
- **Modify** `engine/tests/modules/test_server.py`, `engine/tests/modules/test_herdr.py` — assertion updates.
- **Modify** `README.md`, `docs/roadmap.md` — M2 doc slice.

---

## Task 1: `caddy` module + `brain-host` profile intro

Introduces the `brain-host` leaf with its first two members (`mosh`, `caddy`), the `Caddy` module (both OS paths), and the starter Caddyfile. Green at commit.

**Files:**
- Create: `engine/src/devboost/modules/caddy.py`
- Create: `engine/tests/modules/test_caddy.py`
- Create: `dotfiles/dot_config/caddy/Caddyfile`
- Modify: `profiles.toml` (add `brain-host` leaf; near the other leaves)
- Modify: `engine/src/devboost/modules/mosh.py` (`profiles` gains `brain-host`)
- Modify: `engine/tests/conftest.py`, `engine/tests/cli/test_lifecycle_devhygiene.py`

**Interfaces:**
- Consumes: `pkg.install(ctx, *pkgs, source=...)`, `pkg` `AptRepo` add path; `OsMap` (`devboost.core.osinfo`), `AptRepo` (`devboost.model`), `UnsupportedOS` (`devboost.core.errors`).
- Produces: `Caddy` module — `name="caddy"`, `category="brain-host"`, `profiles=("brain-host",)`, `verify` via `which("caddy")`, `install` per-OS. New key `brain-host = ["mosh","caddy"]`. `Mosh.profiles == ("remote","brain-host")`.

- [ ] **Step 1: Write the failing test**

Create `engine/tests/modules/test_caddy.py`:

```python
from __future__ import annotations

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules.caddy import Caddy


def _ubuntu() -> Ctx:
    return Ctx(os=OsInfo("ubuntu", "debian", "x86_64"), ex=FakeExecutor())


def _fedora() -> Ctx:
    return Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor())


def test_caddy_installs_on_debian_via_cloudsmith_apt() -> None:
    ctx = _ubuntu()
    Caddy().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    # apt repo written, then caddy installed
    assert ["sudo", "tee", "/etc/apt/sources.list.d/dl-cloudsmith-io.list"] in calls
    assert ["sudo", "apt-get", "install", "-y", "caddy"] in calls


def test_caddy_installs_on_fedora_via_copr() -> None:
    ctx = _fedora()
    Caddy().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert any(
        c[:2] == ["sudo", "sh"] and "copr enable" in c[2] and "caddy" in c[2] for c in calls
    )


def test_caddy_unsupported_os_raises() -> None:
    from devboost.core.errors import UnsupportedOS

    ctx = Ctx(os=OsInfo("arch", "arch", "x86_64"), ex=FakeExecutor())
    import pytest

    with pytest.raises(UnsupportedOS):
        Caddy().install(ctx)


def test_caddy_verify_uses_which() -> None:
    ex = FakeExecutor(present={"caddy"})
    assert Caddy().verify(Ctx(os=OsInfo("ubuntu", "debian", "x86_64"), ex=ex)) is True
    assert Caddy().verify(_ubuntu()) is False


def test_caddy_profiles() -> None:
    assert Caddy.profiles == ("brain-host",)
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `engine/`): `uv run pytest tests/modules/test_caddy.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'devboost.modules.caddy'`.

- [ ] **Step 3: Create the module**

Create `engine/src/devboost/modules/caddy.py`:

```python
"""caddy — locally-trusted reverse proxy (`tls internal`) for the brain's dev-server UIs.

Fedora (reference) via the official COPR; Debian/Ubuntu (primary, where the brain runs)
via Caddy's Cloudsmith apt repo. Mirrors docker.py's per-OS install shape.
"""

from __future__ import annotations

from devboost.core.errors import UnsupportedOS
from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import AptRepo, Ctx, Module

# Caddy ships on Fedora only via the official COPR (no plain baseurl repo), so enable it with a
# shell script the way docker.py enables docker-ce. `dnf-command(copr)` provides `copr` on
# dnf4 and dnf5.
_CADDY_COPR_FEDORA = (
    "set -e\n"
    "dnf install -y 'dnf-command(copr)'\n"
    "dnf copr enable -y @caddy/caddy\n"
    "dnf install -y caddy\n"
)


def _caddy_apt_source() -> pkg.Source:
    # Debian/Ubuntu: Caddy's official Cloudsmith apt repo. `signed-by` must match the keyring
    # path Apt.add_repo derives from the URL host (dl.cloudsmith.io -> dl-cloudsmith-io).
    return OsMap(
        debian=AptRepo(
            list_line=(
                "deb [signed-by=/etc/apt/keyrings/dl-cloudsmith-io.gpg]"
                " https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main"
            ),
            key_url="https://dl.cloudsmith.io/public/caddy/stable/gpg.key",
        )
    )


@register
class Caddy(Module):
    name = "caddy"
    category = "brain-host"
    description = "Caddy — locally-trusted reverse proxy (tls internal) for brain dev UIs."
    profiles = ("brain-host",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("caddy")

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "debian":
            pkg.install(ctx, "caddy", source=_caddy_apt_source())
        elif ctx.os.family == "fedora":
            ctx.ex.run(["sh", "-c", _CADDY_COPR_FEDORA], sudo=True)
        else:
            raise UnsupportedOS(f"caddy install not implemented for {ctx.os.distro!r}")
```

- [ ] **Step 4: Run the module test to verify it passes**

Run (from `engine/`): `uv run pytest tests/modules/test_caddy.py -q`
Expected: PASS (5 passed).

> Do NOT run the full suite yet — `brain-host` must exist first (next steps).

- [ ] **Step 5: Create the starter Caddyfile dotfile**

Create `dotfiles/dot_config/caddy/Caddyfile`:

```caddy
# dev-boost starter Caddyfile for the brain box.
# *.localhost resolves to 127.0.0.1 (RFC 6761); `tls internal` mints a locally-trusted cert.
# Front these with `tailscale serve` to reach them from a laptop over the tailnet.

app.localhost {
	tls internal
	reverse_proxy localhost:3000
}

aspire.localhost {
	tls internal
	reverse_proxy localhost:18888
}
```

- [ ] **Step 6: Introduce the `brain-host` profile and wire `mosh` into it**

In `profiles.toml`, add the leaf (near the `remote` leaf) — members are only the modules that exist as of this commit:

```toml
brain-host = ["mosh","caddy"]
```

In `engine/src/devboost/modules/mosh.py`, change:

```python
    profiles = ("remote", "brain-host")
```

- [ ] **Step 7: Add `brain-host` to the test fixtures**

In `engine/tests/conftest.py` `profiles_file` (after the `remote` line added in M1):

```python
        'brain-host = ["mosh","caddy"]\n'
```

In `engine/tests/cli/test_lifecycle_devhygiene.py` synthetic profiles block (after the `remote` line):

```python
        'brain-host = ["mosh","caddy"]\n'
```

- [ ] **Step 8: Run the full gates**

Run (from `engine/`): `uv run pytest -q`, then `uv run mypy`, then `uv run ruff check`.
Expected: all green (test_caddy, test_mosh, test_base, test_system, test_lifecycle_devhygiene included).

- [ ] **Step 9: Commit**

```bash
git add engine/src/devboost/modules/caddy.py engine/tests/modules/test_caddy.py \
        dotfiles/dot_config/caddy/Caddyfile profiles.toml \
        engine/src/devboost/modules/mosh.py \
        engine/tests/conftest.py engine/tests/cli/test_lifecycle_devhygiene.py
git commit -m "feat(brain): add caddy module + brain-host profile (mosh, caddy)"
```

---

## Task 2: `crossarch-build` module + add to `brain-host`

**Files:**
- Create: `engine/src/devboost/modules/crossarch_build.py`
- Create: `engine/tests/modules/test_crossarch_build.py`
- Modify: `profiles.toml` (`brain-host` gains `crossarch-build`)
- Modify: `engine/tests/conftest.py`, `engine/tests/cli/test_lifecycle_devhygiene.py`

**Interfaces:**
- Consumes: `pkg.install(ctx, *pkgs)`.
- Produces: `CrossArchBuild` — `name="crossarch-build"`, `category="brain-host"`, `profiles=("brain-host",)`, `verify` via `which("podman")`, `install` = podman + qemu-user-static (+ binfmt-support on debian).

- [ ] **Step 1: Write the failing test**

Create `engine/tests/modules/test_crossarch_build.py`:

```python
from __future__ import annotations

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules.crossarch_build import CrossArchBuild


def _ctx(distro: str, family: str) -> Ctx:
    return Ctx(os=OsInfo(distro, family, "x86_64"), ex=FakeExecutor())


def test_crossarch_installs_podman_and_qemu_on_debian() -> None:
    ctx = _ctx("ubuntu", "debian")
    CrossArchBuild().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "apt-get", "install", "-y", "podman", "qemu-user-static"] in calls
    assert ["sudo", "apt-get", "install", "-y", "binfmt-support"] in calls


def test_crossarch_installs_podman_and_qemu_on_fedora() -> None:
    ctx = _ctx("fedora", "fedora")
    CrossArchBuild().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "dnf", "install", "-y", "podman", "qemu-user-static"] in calls


def test_crossarch_verify_uses_which_podman() -> None:
    ex = FakeExecutor(present={"podman"})
    assert CrossArchBuild().verify(Ctx(os=OsInfo("ubuntu", "debian", "x86_64"), ex=ex)) is True
    assert CrossArchBuild().verify(_ctx("ubuntu", "debian")) is False


def test_crossarch_profiles() -> None:
    assert CrossArchBuild.profiles == ("brain-host",)
```

- [ ] **Step 2: Run to verify it fails**

Run (from `engine/`): `uv run pytest tests/modules/test_crossarch_build.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Create the module**

Create `engine/src/devboost/modules/crossarch_build.py`:

```python
"""crossarch-build — capped rootless multi-arch builds for the brain (podman + qemu binfmt).

Installs podman (daemonless, first-class rootless — coexists with docker-ce; only the
podman-docker CLI shim conflicts, which docker.py already removes) and qemu-user-static so
`podman build --platform linux/amd64,linux/arm64 --manifest ... --push` runs as the capped
`devbrain` user without root or the docker group. binfmt handlers register via the
qemu-user-static package (Debian also gets binfmt-support).
"""

from __future__ import annotations

from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import Ctx, Module


@register
class CrossArchBuild(Module):
    name = "crossarch-build"
    category = "brain-host"
    description = "Rootless podman + qemu binfmt for capped multi-arch (amd64+arm64) builds."
    profiles = ("brain-host",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("podman")

    def install(self, ctx: Ctx) -> None:
        pkg.install(ctx, "podman", "qemu-user-static")
        # Debian's qemu-user-static needs binfmt-support to register the arm64 handler.
        if ctx.os.family == "debian":
            pkg.install(ctx, "binfmt-support")
```

- [ ] **Step 4: Run the module test to verify it passes**

Run (from `engine/`): `uv run pytest tests/modules/test_crossarch_build.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Add `crossarch-build` to `brain-host`**

In `profiles.toml`, change the `brain-host` leaf to:

```toml
brain-host = ["mosh","caddy","crossarch-build"]
```

In `engine/tests/conftest.py` and `engine/tests/cli/test_lifecycle_devhygiene.py`, update the `brain-host` line to:

```python
        'brain-host = ["mosh","caddy","crossarch-build"]\n'
```

- [ ] **Step 6: Run the full gates**

Run (from `engine/`): `uv run pytest -q`, `uv run mypy`, `uv run ruff check`. Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add engine/src/devboost/modules/crossarch_build.py \
        engine/tests/modules/test_crossarch_build.py profiles.toml \
        engine/tests/conftest.py engine/tests/cli/test_lifecycle_devhygiene.py
git commit -m "feat(brain): add crossarch-build module (rootless podman + qemu) to brain-host"
```

---

## Task 3: `brain-tools` profile + herdr into it

**Files:**
- Modify: `profiles.toml` (add `brain-tools` leaf)
- Modify: `engine/src/devboost/modules/herdr.py` (`Herdr` and `HerdrPlugins` `profiles`)
- Modify: `engine/tests/conftest.py`, `engine/tests/cli/test_lifecycle_devhygiene.py`
- Modify: `engine/tests/modules/test_herdr.py` (profile assertions)

**Interfaces:**
- Produces: `brain-tools = ["herdr","herdr-plugins"]`; `Herdr.profiles == ("optional-agents","brain-tools")`, `HerdrPlugins.profiles == ("optional-agents","brain-tools")`.

- [ ] **Step 1: Update the herdr profile assertions (failing test first)**

In `engine/tests/modules/test_herdr.py`, update the two profile assertions (currently `== ("optional-agents",)`):

```python
    assert Herdr.profiles == ("optional-agents", "brain-tools")
```
and
```python
    assert HerdrPlugins.profiles == ("optional-agents", "brain-tools")
```

- [ ] **Step 2: Run to verify it fails**

Run (from `engine/`): `uv run pytest tests/modules/test_herdr.py -q`
Expected: FAIL — assertion mismatch (still `("optional-agents",)`).

- [ ] **Step 3: Add `brain-tools` and wire herdr**

In `profiles.toml`, add the leaf (near `brain-host`):

```toml
brain-tools = ["herdr","herdr-plugins"]
```

In `engine/src/devboost/modules/herdr.py`, change both classes' `profiles`:

```python
    profiles = ("optional-agents", "brain-tools")
```
(the `Herdr` class ~line 20 and the `HerdrPlugins` class ~line 84 — both to the same value.)

In `engine/tests/conftest.py` and `engine/tests/cli/test_lifecycle_devhygiene.py`, add:

```python
        'brain-tools = ["herdr","herdr-plugins"]\n'
```

- [ ] **Step 4: Run the full gates**

Run (from `engine/`): `uv run pytest -q`, `uv run mypy`, `uv run ruff check`. Expected: all green (test_herdr assertions now match; validate_profiles green).

- [ ] **Step 5: Commit**

```bash
git add profiles.toml engine/src/devboost/modules/herdr.py \
        engine/tests/conftest.py engine/tests/cli/test_lifecycle_devhygiene.py \
        engine/tests/modules/test_herdr.py
git commit -m "feat(brain): add brain-tools profile (herdr, herdr-plugins)"
```

---

## Task 4: Remove `agent-sudo` from the `server` profile

Passwordless sudo must not default onto a production server (spec §3). The `AgentSudo` module stays (still correct/tested), but becomes explicit opt-in (`profiles = ()`).

**Files:**
- Modify: `profiles.toml` (`server` list drops `agent-sudo`)
- Modify: `engine/src/devboost/modules/server.py` (`AgentSudo.profiles = ()`)
- Modify: `engine/tests/modules/test_server.py` (add a profile-membership assertion)

**Interfaces:**
- Produces: `AgentSudo.profiles == ()`; `expand("server")` no longer includes `agent-sudo`.

- [ ] **Step 1: Write the failing assertion**

In `engine/tests/modules/test_server.py`, add near the agent-sudo tests (around line 189):

```python
def test_agent_sudo_not_in_default_server_profile() -> None:
    from devboost.modules.server import AgentSudo

    assert AgentSudo.profiles == ()
```

- [ ] **Step 2: Run to verify it fails**

Run (from `engine/`): `uv run pytest tests/modules/test_server.py::test_agent_sudo_not_in_default_server_profile -q`
Expected: FAIL — `AgentSudo.profiles` is still `("server",)`.

- [ ] **Step 3: Make the change**

In `engine/src/devboost/modules/server.py`, change `AgentSudo`:

```python
    profiles = ()
```

In `profiles.toml`, remove `agent-sudo` from the `server` leaf. The `server` line becomes:

```toml
server = ["tailscale","server-firewall","zram","restic-b2","tmux-persist",
          "docker","docker-build-gc"]
```

- [ ] **Step 4: Run the full gates**

Run (from `engine/`): `uv run pytest -q`, `uv run mypy`, `uv run ruff check`.
Expected: all green. (Existing `AgentSudo` verify/install tests still pass — the module is unchanged; only its `profiles` and the `server` list changed. `validate_profiles` stays green: `()` names no profile.)

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/modules/server.py profiles.toml \
        engine/tests/modules/test_server.py
git commit -m "refactor(server): remove agent-sudo from default server profile (opt-in only)"
```

---

## Task 5: M2 documentation slice

**Files:**
- Modify: `README.md` (regenerated profiles table)
- Modify: `docs/roadmap.md`

**Interfaces:**
- Consumes: the new profiles/modules from Tasks 1-4.

- [ ] **Step 1: Regenerate the README profiles table**

Run (from repo root): `uv run --project engine python scripts/gen_profiles_table.py`
Note: this script prints the table to **stdout**; splice its output between the `BEGIN`/`END` markers in `README.md` (same as the prior M1 / `0c511a7` commits — the generator has no in-place `--write` mode).

- [ ] **Step 2: Verify the table diff**

Run: `git diff README.md`
Expected: new `brain-host` row (mosh, caddy, crossarch-build), new `brain-tools` row (herdr, herdr-plugins), new `caddy` + `crossarch-build` module rows, `mosh` now also under `brain-host`, `herdr`/`herdr-plugins` now also under `brain-tools`, and `agent-sudo` no longer under `server`. If anything beyond these appears, STOP and report — do not commit surprising drift.

- [ ] **Step 3: Add the roadmap note**

In `docs/roadmap.md`, under the existing "Shipped, opt-in:" list, add:

```markdown
- **Remote fleet — M2 pt1 (brain tooling):** `caddy` + `crossarch-build` modules and the
  `brain-host`/`brain-tools` opt-in profiles; `agent-sudo` removed from the default `server`
  profile (now explicit opt-in). (M2 pt2: `devbrain` account + `devboost brain` wrapper.)
```

- [ ] **Step 4: Verify tests unaffected**

Run (from `engine/`): `uv run pytest -q`. Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/roadmap.md
git commit -m "docs(brain): regenerate profiles table + roadmap note for M2 brain tooling"
```

---

## Self-Review (completed during authoring)

**Spec coverage (this plan's scope):** §5.2 caddy (COPR + Cloudsmith apt, both OS) → Task 1. §5.3 crossarch-build (podman + qemu, both OS) → Task 2. §3 `brain-host` → Tasks 1-2; `brain-tools` + §5.4 herdr wiring → Task 3; `agent-sudo` off `server` → Task 4. §10 M2 doc slice → Task 5. Explicitly OUT of this plan (spec §4/§6, next plan): the `devbrain` managed account and the `devboost brain` CLI wrapper. The starter Caddyfile (§5.2) → Task 1 step 5.

**Placeholder scan:** none — exact paths, complete code, exact commands/expected output throughout.

**Type consistency:** `Caddy.profiles`/`CrossArchBuild.profiles == ("brain-host",)`; `Mosh.profiles == ("remote","brain-host")` (Task 1 step 6); `Herdr`/`HerdrPlugins.profiles == ("optional-agents","brain-tools")` (Task 3); `AgentSudo.profiles == ()` (Task 4). `brain-host` member list grows caddy(T1)→crossarch-build(T2) so `profiles.toml` never names a not-yet-created module; the same value is mirrored into both fixtures at each step. Apt assertions (`["sudo","tee","/etc/apt/sources.list.d/dl-cloudsmith-io.list"]`, `["sudo","apt-get","install","-y","caddy"]`) match `pkg.Apt.add_repo`/`Apt.install`; the Cloudsmith `signed-by` path matches the slug `_apt_slug` derives (`dl-cloudsmith-io`). dnf assertions match `pkg.Dnf.install`.

## Note on part 2

The immediately-following plan ("M2 part 2: devbrain account + `devboost brain` wrapper") builds spec §4/§6 on top of the `brain-host`/`brain-tools` profiles this plan creates: a `devbrain` `users.toml` recipe (privilege=none, caps, `bootstrap_profiles=["brain-tools"]`, seeded `ssh_authorized_keys`) and a thin `devboost brain` subcommand that installs `brain-host` (sudo) then reconciles the `devbrain` account.
</content>
