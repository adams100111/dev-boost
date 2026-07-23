# Remote Fleet — M2 (part 2): devbrain account + `devboost brain` wrapper — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the one-command sandboxed-brain provisioning — the `devbrain` managed-account recipe and the thin `devboost brain` CLI wrapper that installs `brain-host` then reconciles that account.

**Architecture:** Pure helpers in a new `cli/brain.py` (the `devbrain` recipe = a capped, `privilege="none"` `ManagedUser` whose `bootstrap_profiles=["brain-tools"]`, built via the existing `accounts.form.merge_flags`; plus a best-effort `~/.ssh/*.pub` reader). A thin `@app.command() def brain(...)` orchestrates the two existing operations: `_run(["brain-host"], …)` then `reconcile.save` + `reconcile.apply_user` (with the demoted `bootstrap_user`). Builds on M2 pt1's `brain-host`/`brain-tools` profiles (already on main).

**Tech Stack:** Python ≥3.12, Typer CLI (`CliRunner` tests), the `accounts` subsystem (`ManagedUser`, `merge_flags`, `reconcile.apply_user`/`save`, `bootstrap_user`), `uv`.

**Source spec:** `docs/superpowers/specs/2026-07-22-remote-fleet-workflow-design.md` (§4 devbrain account, §6 `devboost brain` wrapper).

## Global Constraints

- Merge gates from `engine/`: `uv run ruff check`, `uv run mypy` (`--strict`), `uv run pytest`.
- Hermetic tests only: no real system mutation. Isolate via `DEVBOOST_USERS_PATH` env + `--dry-run`/`--no-apply` (mirrors `tests/cli/test_accounts_cli.py`).
- `devbrain` recipe values (spec §4/§6): `privilege="none"`, `linger=True`, `bootstrap_profiles=("brain-tools",)`, default caps `ram="8G"`, `cpu="200%"`, `disk="50G"`, `tasks=4096` (overridable via flags).
- New code typed, mypy --strict clean, `from __future__ import annotations`. Ruff `E,F,I,UP,B` (line 100). Typer list-defaults get a `# noqa: B006` like existing commands.
- Commit messages: no Claude/Anthropic attribution.

---

## File Structure

- **Create** `engine/src/devboost/cli/brain.py` — pure `devbrain` recipe helpers (`DEVBRAIN_DEFAULTS`, `default_ssh_keys`, `devbrain_user`).
- **Create** `engine/tests/cli/test_brain_helpers.py` — unit tests for the helpers.
- **Modify** `engine/src/devboost/cli/app.py` — add the `@app.command() def brain(...)`.
- **Create** `engine/tests/cli/test_brain_cli.py` — CLI test for the command.
- **Modify** `README.md`, `docs/roadmap.md` — M2 pt2 doc note.

---

## Task 1: `cli/brain.py` — the `devbrain` recipe helpers

**Files:**
- Create: `engine/src/devboost/cli/brain.py`
- Create: `engine/tests/cli/test_brain_helpers.py`

**Interfaces:**
- Consumes: `merge_flags` (`devboost.accounts.form`), `ManagedUser` (`devboost.accounts.config`).
- Produces: `DEVBRAIN_DEFAULTS: dict`; `default_ssh_keys() -> tuple[str,...]`; `devbrain_user(*, ssh_keys, ram, cpu, disk, tasks) -> ManagedUser`.

- [ ] **Step 1: Write the failing test**

Create `engine/tests/cli/test_brain_helpers.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from devboost.cli.brain import DEVBRAIN_DEFAULTS, default_ssh_keys, devbrain_user


def test_devbrain_user_is_capped_sudoless_and_bootstraps_brain_tools() -> None:
    u = devbrain_user(
        ssh_keys=("ssh-ed25519 AAAA me",), ram="8G", cpu="200%", disk="50G", tasks=4096
    )
    assert u.name == "devbrain"
    assert u.privilege == "none"
    assert u.sudo_commands == ()
    assert u.linger is True
    assert (u.ram, u.cpu, u.disk, u.tasks) == ("8G", "200%", "50G", 4096)
    assert u.bootstrap_profiles == ("brain-tools",)
    assert u.ssh_authorized_keys == ("ssh-ed25519 AAAA me",)


def test_default_ssh_keys_reads_pub_files_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ssh = tmp_path / ".ssh"
    ssh.mkdir()
    (ssh / "id_ed25519.pub").write_text("ssh-ed25519 KEY1 a\n", encoding="utf-8")
    (ssh / "id_rsa.pub").write_text("ssh-rsa KEY2 b\n", encoding="utf-8")
    (ssh / "id_ed25519").write_text("PRIVATE", encoding="utf-8")  # not a .pub -> ignored
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_ssh_keys() == ("ssh-ed25519 KEY1 a", "ssh-rsa KEY2 b")


def test_default_ssh_keys_empty_when_no_ssh_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_ssh_keys() == ()


def test_devbrain_defaults() -> None:
    assert DEVBRAIN_DEFAULTS == {"ram": "8G", "cpu": "200%", "disk": "50G", "tasks": 4096}
```

- [ ] **Step 2: Run to verify it fails**

Run (from `engine/`): `uv run pytest tests/cli/test_brain_helpers.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'devboost.cli.brain'`.

- [ ] **Step 3: Create the helpers**

Create `engine/src/devboost/cli/brain.py`:

```python
"""The sandboxed-brain recipe: the `devbrain` managed-account definition + key discovery.

`devboost brain` (in app.py) installs the brain-host tools then reconciles this account —
a capped, sudo-less user whose bootstrap_profiles install herdr et al. into its home.
"""

from __future__ import annotations

import os
from pathlib import Path

from devboost.accounts.config import ManagedUser
from devboost.accounts.form import merge_flags

#: Conservative default resource caps for the devbrain slice. Overridable via `devboost brain`
#: flags — the right values depend on how much headroom the (often production) host needs.
DEVBRAIN_DEFAULTS: dict[str, object] = {
    "ram": "8G",
    "cpu": "200%",
    "disk": "50G",
    "tasks": 4096,
}


def default_ssh_keys() -> tuple[str, ...]:
    """Best-effort: the invoking user's public keys, so `mosh devbrain@brain` works.

    Reads ~/.ssh/*.pub. Returns () when none are found — the operator can pass --ssh-key
    explicitly instead.
    """
    home = os.environ.get("HOME")
    if not home:
        return ()
    ssh = Path(home) / ".ssh"
    if not ssh.is_dir():
        return ()
    keys: list[str] = []
    for pub in sorted(ssh.glob("*.pub")):
        try:
            text = pub.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            keys.append(text)
    return tuple(keys)


def devbrain_user(
    *, ssh_keys: tuple[str, ...], ram: str, cpu: str, disk: str, tasks: int
) -> ManagedUser:
    """The devbrain recipe: a capped, sudo-less user that bootstraps the brain-tools profile."""
    return merge_flags(
        "devbrain",
        ram=ram,
        cpu=cpu,
        disk=disk,
        tasks=tasks,
        privilege="none",  # the safety core: cannot sudo
        sudo_commands=(),
        shell="/bin/bash",
        lock_shell=False,
        linger=True,  # herdr / mosh-server persist without an active login
        ssh_keys=ssh_keys,
        bootstrap_profiles=("brain-tools",),
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run (from `engine/`): `uv run pytest tests/cli/test_brain_helpers.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Run the full gates**

Run (from `engine/`): `uv run pytest -q`, `uv run mypy`, `uv run ruff check`. Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add engine/src/devboost/cli/brain.py engine/tests/cli/test_brain_helpers.py
git commit -m "feat(brain): devbrain managed-account recipe helpers"
```

---

## Task 2: `devboost brain` command

**Files:**
- Modify: `engine/src/devboost/cli/app.py` (add the `brain` command; place it after the `install` command, before `list`)
- Create: `engine/tests/cli/test_brain_cli.py`

**Interfaces:**
- Consumes: `_run` (app.py), `Ctx`/`osinfo`/`RealExecutor`/`log`/`settings`/`RootOpt`/`DryOpt`/`ForceOpt` (already imported in app.py); `devbrain_user`/`default_ssh_keys` (Task 1); `reconcile.save`/`reconcile.apply_user`, `bootstrap.bootstrap_user`, `load_users` (accounts).
- Produces: `devboost brain` command that installs `brain-host` then persists + (optionally) applies the `devbrain` account.

- [ ] **Step 1: Write the failing test**

Create `engine/tests/cli/test_brain_cli.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from devboost.cli.app import app

runner = CliRunner()


def test_brain_dry_run_no_apply_persists_devbrain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    users = tmp_path / "users.toml"
    monkeypatch.setenv("DEVBOOST_USERS_PATH", str(users))
    # --dry-run makes the brain-host install a no-op; --no-apply skips the real reconcile.
    result = runner.invoke(
        app, ["brain", "--dry-run", "--no-apply", "--ssh-key", "ssh-ed25519 K me"]
    )
    assert result.exit_code == 0, result.stdout

    from devboost.accounts.config import load_users

    u = load_users()["devbrain"]
    assert u.privilege == "none"
    assert u.bootstrap_profiles == ("brain-tools",)
    assert u.linger is True
    assert u.ssh_authorized_keys == ("ssh-ed25519 K me",)


def test_brain_help_lists_it() -> None:
    result = runner.invoke(app, ["brain", "--help"])
    assert result.exit_code == 0
    assert "devbrain" in result.stdout.lower() or "brain" in result.stdout.lower()
```

- [ ] **Step 2: Run to verify it fails**

Run (from `engine/`): `uv run pytest tests/cli/test_brain_cli.py -q`
Expected: FAIL — no such command `brain` (exit code != 0 / "No such command").

- [ ] **Step 3: Add the command**

In `engine/src/devboost/cli/app.py`, add after the `install` command (uses symbols already imported there — `_run`, `Ctx`, `osinfo`, `RealExecutor`, `log`, `settings`, `RootOpt`, `DryOpt`, `ForceOpt`, `Annotated`, `typer`):

```python
@app.command()
def brain(
    root: RootOpt = settings.root,
    ram: Annotated[str, typer.Option("--ram", help="devbrain RAM cap")] = "8G",
    cpu: Annotated[str, typer.Option("--cpu", help="devbrain CPU cap")] = "200%",
    disk: Annotated[str, typer.Option("--disk", help="devbrain disk quota")] = "50G",
    tasks: Annotated[int, typer.Option("--tasks", help="devbrain max processes")] = 4096,
    ssh_key: Annotated[
        list[str], typer.Option("--ssh-key", help="authorized key for devbrain (repeatable)")
    ] = [],  # noqa: B006
    dry_run: DryOpt = False,
    force: ForceOpt = False,
    apply_: Annotated[bool, typer.Option("--apply/--no-apply")] = True,
) -> None:
    """Provision the sandboxed brain: install brain-host tools + the capped devbrain account."""
    from devboost.accounts import bootstrap as bs
    from devboost.accounts import reconcile
    from devboost.accounts.config import load_users
    from devboost.cli.brain import default_ssh_keys, devbrain_user

    # 1) host-level brain tools (sudo): mosh, caddy, crossarch-build.
    _run(["brain-host"], root, dry_run, force)

    # 2) the capped, sudo-less devbrain account (bootstraps brain-tools into its home).
    keys = tuple(ssh_key) or default_ssh_keys()
    if not keys:
        log.warn(
            "brain: no --ssh-key given and no ~/.ssh/*.pub found — add an authorized key "
            "before you can `mosh devbrain@this-host`"
        )
    user = devbrain_user(ssh_keys=keys, ram=ram, cpu=cpu, disk=disk, tasks=tasks)
    ctx = Ctx(os=osinfo.detect(), ex=RealExecutor(), force=force, dry_run=dry_run)
    users = load_users()
    users["devbrain"] = user
    reconcile.save(ctx, users)
    if apply_ and not dry_run:
        reconcile.apply_user(
            ctx, user, bootstrap=lambda c, u: bs.bootstrap_user(c, u, root=root)
        )
    log.info(
        "review devbrain caps for this box (ram/cpu/disk/tasks) — production headroom "
        "matters: devboost accounts edit devbrain"
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run (from `engine/`): `uv run pytest tests/cli/test_brain_cli.py -q`
Expected: PASS (2 passed). If `reconcile.save` needs the users dir to exist, it is created by `DEVBOOST_USERS_PATH` pointing at a tmp file — confirm the test's `load_users()` reads the same path (it does, via the env var).

- [ ] **Step 5: Run the full gates**

Run (from `engine/`): `uv run pytest -q`, `uv run mypy`, `uv run ruff check`. Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add engine/src/devboost/cli/app.py engine/tests/cli/test_brain_cli.py
git commit -m "feat(brain): add 'devboost brain' wrapper (install brain-host + devbrain account)"
```

---

## Task 3: M2 pt2 documentation note

**Files:**
- Modify: `docs/roadmap.md`
- Modify: `README.md`

- [ ] **Step 1: Add the roadmap note**

In `docs/roadmap.md`, under "Shipped, opt-in:", add:

```markdown
- **Remote fleet — M2 pt2 (sandboxed brain):** `devboost brain` provisions the capped,
  sudo-less `devbrain` account (privilege=none + cgroup caps, bootstraps `brain-tools`) and
  installs the `brain-host` tools in one command. (M3: `fleet` DX verbs + operator guide.)
```

- [ ] **Step 2: Add a README mention**

In `README.md`, find the "Remote fleet" prose (added in M1/M2, near the profiles table) — or if none exists, add a one-line note under the profiles table — stating:

```markdown
`devboost brain` provisions a sandboxed **devbrain** brain on a chosen server (installs the
`brain-host` tools + a capped, sudo-less account that runs herdr and cross-arch builds).
```

If a "Remote fleet" section already exists, append this line there; do not duplicate a heading.

- [ ] **Step 3: Verify tests unaffected**

Run (from `engine/`): `uv run pytest -q`. Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/roadmap.md
git commit -m "docs(brain): roadmap + README note for devboost brain (M2 pt2)"
```

---

## Self-Review (completed during authoring)

**Spec coverage:** §4 devbrain recipe (privilege=none, caps, linger, `bootstrap_profiles=["brain-tools"]`, ssh keys) → Task 1 `devbrain_user` + `default_ssh_keys`. §6 `devboost brain` wrapper (install brain-host → reconcile devbrain, default overridable caps, idempotent via `load_users`+`save`+`apply_user`, "review caps" note, key seeding) → Task 2. Doc note → Task 3.

**Placeholder scan:** none — exact paths, complete code, exact commands/expected output. Task 3 Step 2 is conditional (append vs add) but both branches are specified.

**Type consistency:** `devbrain_user(*, ssh_keys, ram, cpu, disk, tasks)` signature identical in Task 1 test, Task 1 impl, and Task 2's call. `merge_flags` call passes every required kw arg (verified against `accounts/form.py:25-45`). The command reuses `_run`/`Ctx`/`osinfo`/`RealExecutor`/`log`/`settings`/`RootOpt`/`DryOpt`/`ForceOpt` — all already imported in `app.py`. Hermetic isolation via `DEVBOOST_USERS_PATH` + `--dry-run`/`--no-apply` matches `tests/cli/test_accounts_cli.py`.

**Idempotency:** re-running `devboost brain` re-`load_users()`, overwrites the `devbrain` entry, and `reconcile.apply_user` converges (existing accounts subsystem behavior) — no error on re-run.
</content>
