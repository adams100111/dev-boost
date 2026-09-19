# pass multi-device P1 (Linux) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `pass` the default credential store on every Linux workstation. One shared GitHub repo, one GPG key per device, sync that runs on its own (push on commit, pull every 15 min), and one command each to enroll, approve, and revoke a device. Revocation comes with a rotation checklist that `doctor` tracks.

**Architecture:** A new library package `devboost/passstore/` holds the domain logic: paths, gpg, store layout, git, notifications, enroll/adopt, approve/revoke/rotation, and sync. Every side effect goes through the injected `Executor`. The `pass` and `pass-store` modules, which move into `base`, and a new `devboost pass` Typer sub-app are thin callers of that package. One small engine seam, `Module.after` (a dependency that orders modules but does not cascade a block), lets the modules that read `pass` run *after* `pass-store` without being blocked while this device is still waiting for approval. OS divergence is confined to two seams, `notify._native_argv` and `sync.install_scheduler`. P2 (macOS) fills those seams with `osascript` and `launchd.user_agent`.

**Tech Stack:** Python ≥ 3.12, Typer, Pydantic v2, stdlib `tomllib`/`json`/`fcntl`/`socket`, GnuPG 2.2+, `pass` 1.7+, git, systemd `--user`, `notify-send` (libnotify), optional ntfy (`curl`). pytest, mypy `--strict`, ruff, and `uv`. Every tool is free for commercial use: GPLv2/v3 CLIs invoked as external processes, plus the Apache-2.0 ntfy protocol over plain HTTP.

**Spec:** `docs/superpowers/specs/2026-09-18-pass-multi-device-design.md` (rollout row **P1**). Read it fully before starting. P2 (pinentry-mac, launchd agent, macOS notifications) is **out of scope**.

## Global Constraints

- Store repo default: `adams100111/password-store` (private), overridable by `pass_repo` in `~/.config/devboost/config.toml` and then by env `DEVBOOST_PASS_REPO` (env wins).
- Key model: **per-device GPG keys**. The age bundle never carries a GPG key.
- Device key: `ed25519` primary `cert,sign`, expiry `never`, plus a `cv25519` `encr` subkey, expiry `never`. The uid carries the comment `devboost:<device>`. The key has a passphrase, entered via pinentry. It is never written by dev-boost.
- Linux gpg-agent cache: `default-cache-ttl 28800` (8 h), `max-cache-ttl 86400` (24 h).
- Enrollment is **never automatic**. Approval needs a typed `y` on an enrolled device.
- Sync: a post-commit hook pushes immediately in the background. A background pull runs every 15 min via the systemd user timer `devboost-pass-sync.timer`.
- Servers are not enrolled by default. Scoped enrollment uses per-folder `.gpg-id` files.
- `.devboost/` in the store holds only public material and metadata. It never holds secrets.
- Not approved yet → `NeedsUser` with the exact command `devboost pass approve <name>`. Modules that read `pass` warn and skip. They never fail the run.
- gh/GitHub not authenticated → `NeedsUser` ("`gh auth login`").
- Push/pull failures are logged and notified. They never block other modules.
- Merge gates (constitution): `uv run ruff check`, `uv run mypy`, `uv run pytest` all clean. Tests are hermetic: no network, no real `$HOME`, no host GPG keyring. Real-gpg tests use an isolated `GNUPGHOME` per simulated device (short `mkdtemp` path under `/tmp`, because the gpg-agent socket path is length-limited), kill their agents on teardown, and are skipped when `gpg`/`pass`/`git` are absent.
- Every external command runs as an argv list. Shell strings are never used. The only shell text is the 3-line git hook stub, which just execs `devboost`.
- All commands below run from `engine/` unless stated otherwise.
- Tests import the shared fake as `from tests.passstore.fakes import RuleExecutor, colons`. If ruff's isort (I001) wants that line in a different block, accept `uv run ruff check --fix`. Only the import order changes.
- Commit messages: Conventional Commits, **no** `Co-Authored-By` trailer, no Claude/Anthropic attribution (constitution).

## Decisions (where the spec is silent)

| # | Topic | Decision | Why |
|---|---|---|---|
| D1 | Blocked `pass-store` vs modules that read `pass` | New `Module.after: ClassVar[tuple[type[Module], ...]]`: ordering only, never pulls the module into the plan, never cascades `blocked`/`fail`. `claude-plugins`, `codex-config`, `pi-harness`, and `herdr-plugins` move `PassStore` from `requires` to `after`. | With `requires`, a `NeedsUser` from `pass-store` would block Claude/Codex (the spec says they must "warn + skip"). Not pulling the module in keeps servers (`brain-tools`) from getting an enrollment request. |
| D2 | Clone transport | `git clone https://github.com/<owner/repo>.git` through the credential helper `secrets` configured (gh's `setup-git` helper **or** the PAT store). A full URL (`https://…`, `git@…`) or absolute path is used verbatim. Pushes use `push --set-upstream origin HEAD`, so a freshly cloned *empty* store (genesis) gets its upstream. If the clone fails while `gh auth status` fails too → `NeedsUser("gh auth login")`. Otherwise → `ConfigError`. | Works on zero-touch boxes (PAT, no gh session) and hand-installed boxes (gh) alike. The spec's "via gh auth" is honoured. |
| D3 | `DEVBOOST_PASS_GPG_ID` | **Removed.** An empty store (no root `.gpg-id`) is initialised by its first device ("genesis"): generate the key, `pass init <fp>`, register the device, push. | One path instead of two. A new store no longer needs a hand-made key. |
| D4 | Which local key counts | Only a secret key whose uid contains `(devboost:<device>)`, **or**, for adopt, any local secret key matching a root `.gpg-id` token. A token matches when it is a case-insensitive suffix of the fingerprint (`0x` stripped), so long key ids in the existing `.gpg-id` still match. | Adopt must label the two keys the store already uses. A new enroll must not hijack an unrelated personal key. |
| D5 | Enrolled check | Enrolled = a local secret fingerprint matches a root `.gpg-id` token (workstation), or matches a token in a scope folder's `.gpg-id` (server). No decrypt attempt, so no passphrase prompt in `verify`. | `verify` must be cheap and non-interactive. |
| D6 | Unattended runs | If the device has no key and there is no TTY (`_credentials.is_interactive()` is false) → `NeedsUser("… run `devboost pass enroll` in a terminal")`. The engine never blocks on pinentry unattended. | Constitution IV (unattended by default). |
| D7 | Trust | Approve and sync import every `devices/*.asc` whose armored fingerprint equals its JSON fingerprint **and** appears in a `.gpg-id`, then set ownertrust **ultimate** (`<fp>:6:`). | `pass insert` on any device must encrypt to every device key. gpg refuses untrusted recipients in batch mode. All keys are the user's own. |
| D8 | Rotation bookkeeping | `rotation.json` is a list of `{device, fingerprint, revoked_at, after, entries}`. `after` is the SHA of the re-encryption commit. An entry counts as *rotated* when a commit in `after..HEAD` touches `<entry>.gpg` and its subject starts with neither `Reencrypt password store` nor `devboost:`. Status is computed, never mutated. An entry deleted from the store since the revoke counts as resolved. | "`pass edit`/`insert` clears it" then holds without any hook logic. Later approvals (which re-encrypt everything) don't falsely clear entries. |
| D9 | Entries needing rotation | Entries present at the first commit whose root `.gpg-id` contained the device's token, plus every entry added since. For a scoped device, only entries under its scope folders. If there is no such commit, every entry in history counts. | Matches "every entry that existed while `<name>` was enrolled". Git history is what the revoked key can still read. |
| D10 | Hook | `.git/hooks/post-commit` = a `#!/bin/sh` stub that runs `<devboost> pass sync --push-only --quiet` in the background. dev-boost's own git and `pass init` calls carry env `DEVBOOST_PASS_HOOK=off`, and `sync` returns immediately when it sees that. | All logic stays in typed Python (constitution). No double push during approve/revoke. |
| D11 | Concurrency | `sync` takes a non-blocking `fcntl.flock` on `$XDG_STATE_HOME/devboost/pass-sync.lock`. If another sync holds it, this run is a no-op. | The timer and the hook can overlap. |
| D12 | Notifications | ntfy (`DEVBOOST_NTFY_URL`, same variable as `claude-notify`) is sent **once by the enrolling device**. Every enrolled device shows a native `notify-send` on its next sync, de-duplicated per `name:fingerprint` in `$XDG_STATE_HOME/devboost/pass-notified.json`. Push failures notify once per failing HEAD SHA. | One phone ping per request, not N. No new services. ntfy is optional and free. |
| D13 | `sync --resolve` | Guidance only: it prints the conflicted files, the `.gpg-id` the device registry implies, and the exact recovery commands. It changes nothing. | The spec says "guides a manual fix". An automatic re-encrypt during a conflicted rebase is too risky. |
| D14 | Revoke guard | Refuse to revoke this device; run the revoke from another enrolled workstation. Because approve and revoke only run on an enrolled workstation, this guard also guarantees at least one workstation key remains. | Self-revocation locks you out of your own store. |
| D15 | Timer unit | `OnCalendar=*:0/15`, `Persistent=true`. `ExecStart` = absolute `devboost` path resolved at install time (`sys.executable` when frozen, else `shutil.which("devboost")`). | Same shape as the existing `aspire-gc`/`vault-sync` timers, and the absolute path survives the systemd user PATH. |
| D16 | `security-cli` profile | Kept as an alias `["pass","pass-store"]` so old invocations still resolve. The modules' `category`/`profiles` become `base`. | Backward compatible, zero cost. |
| D17 | Device name | `device_name` in `config.toml`, else the short hostname, lower-cased with characters outside `[a-z0-9-]` replaced by `-`. `devboost pass enroll --name` overrides. A name already used with a different fingerprint is refused. | Spec default. Names are also file names in the store. |
| D18 | herdr secret format | `pass show devboost/herdr-telegram` → `token: <t>` and `chat_id: <c>` lines (pass's `key: value` convention). If either is missing, fall back to `DEVBOOST_HERDR_TELEGRAM_TOKEN`/`_CHAT_ID`, else skip. | Spec: "`token`/`chat_id` lines". |
| D19 | CI | `ci.yml` installs `pass` (`apt-get install -y pass`; gpg is preinstalled on ubuntu-22.04), so the real-gpg integration test runs in CI. | Otherwise the most important test would only ever skip. |
| D20 | Commit messages | Conventional Commits with **no** `Co-Authored-By` trailer and no Claude/Anthropic attribution. | Constitution, Technology & Security Constraints. |
| D21 | Device name after `enroll --name` | Not persisted. After a request exists, `local_access` finds this device by **fingerprint** (pending or registered record), so the name only matters when a key or request is first created. | No config writes for a one-time choice. |
| D22 | `pass-store` on macOS in P1 | `PassStore.families = ("fedora", "debian", "arch")` so the plan drops it on macOS until P2 adds the launchd scheduler. `Pass` (brew `pass`) stays universal. | Keeps the P2 seam explicit instead of failing a macOS run. |

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `engine/src/devboost/model.py` (modify) | `Module.after` | 1 |
| `engine/src/devboost/core/graph.py` (modify) | `after` edges (only when both are selected) | 1 |
| `engine/src/devboost/core/registry.py` (modify) | validate `after` refs + cycles | 1 |
| `engine/src/devboost/core/userconfig.py` (create) | `~/.config/devboost/config.toml` → `UserConfig` | 2 |
| `engine/src/devboost/passstore/__init__.py` (create) | package docstring | 3 |
| `engine/src/devboost/passstore/paths.py` (create) | repo/store/state paths, device name, devboost binary | 3 |
| `engine/src/devboost/passstore/gpg.py` (create) | colon parsing, keygen, export, trusted import, token matching | 4 |
| `engine/src/devboost/passstore/layout.py` (create) | `DeviceRecord`, `RotationEntry`, `Store` (files under `.devboost/`, `.gpg-id`, entries) | 5 |
| `engine/src/devboost/passstore/git.py` (create) | git argv wrappers with the no-hook env | 6 |
| `engine/src/devboost/passstore/notify.py` (create) | ntfy + native notification (P2 seam) | 6 |
| `engine/src/devboost/passstore/enroll.py` (create) | classify / genesis / adopt / enroll / `ensure_access` | 7 |
| `engine/src/devboost/passstore/approve.py` (create) | approve, revoke, rotation list + status | 8 |
| `engine/src/devboost/passstore/sync.py` (create) | sync run, conflicts, pending notify, hook, systemd units, scheduler seam | 9 |
| `engine/src/devboost/modules/pass_store.py` (create) | `Pass` (+ gpg-agent TTLs) and `PassStore` modules (moved from `optional.py`) | 10 |
| `engine/src/devboost/modules/_pass.py` (create) | `pass_show()` shared degrade-gracefully reader | 10 |
| `engine/src/devboost/modules/optional.py` (modify) | drop `Pass`/`PassStore` | 10 |
| `engine/src/devboost/modules/claude_plugins.py`, `codex_config.py`, `pi_harness.py`, `herdr.py` (modify) | `after = (PassStore,)`, `pass_show`, herdr token from pass | 10 |
| `profiles.toml` (modify) | `base` += `pass`,`pass-store`; `full` comment | 10 |
| `engine/src/devboost/cli/pass_cmd.py` (create) | `devboost pass status/devices/approve/revoke/sync/enroll` | 11 |
| `engine/src/devboost/cli/app.py` (modify) | `app.add_typer(_pass.app, name="pass")` | 11 |
| `engine/src/devboost/cli/doctor.py` (modify) | `pass` + `pass-rotation` checks replace `pass-config` | 12 |
| `engine/tests/passstore/test_integration_gpg.py` (create) + `.github/workflows/ci.yml` (modify) | real-gpg end-to-end | 13 |
| `docs/pass.md` (create), `docs/credentials.md`, `docs/recovery-runbook.md`, `docs/agents.md`, `docs/architecture.md`, `docs/adding-a-module.md`, `README.md`, spec (modify) | docs | 14 |

Test support: `engine/tests/passstore/__init__.py` and `engine/tests/passstore/fakes.py` (the `RuleExecutor` shared by tests in `tests/passstore`, `tests/modules`, and `tests/cli`). This is created in Task 4.

---

### Task 0: Baseline

**Files:** none

- [ ] **Step 1: Sync and run the gate once**

```bash
cd engine && uv sync && uv run ruff check && uv run mypy && uv run pytest 2>&1 | tail -5
```
Expected: ruff and mypy clean, pytest all green. Record the pass count. Any red test here is pre-existing: stop and report it rather than fixing it in this plan.

- [ ] **Step 2: Check the tools used by the integration test (informational)**

```bash
command -v gpg pass git || true
```
If `gpg`/`pass` are missing locally, Task 13's tests will skip on your machine and run in CI (D19). That is expected.

---

### Task 1: `Module.after`: ordering-only dependencies

**Files:**
- Modify: `engine/src/devboost/model.py` (`Module`), `engine/src/devboost/core/graph.py` (`toposort`), `engine/src/devboost/core/registry.py` (`_validate`, `_check_cycles`)
- Test: `engine/tests/core/test_after_ordering.py` (create)

**Interfaces:**
- Produces: `Module.after: ClassVar[tuple[type[Module], ...]] = ()`. `toposort(names, modules)` orders `X` after every `after` target that is **also** in the selected closure. `after` targets are never added to the closure. The runner is unchanged: it only cascades on `requires`, so a blocked/failed `after` target never blocks the dependent. `registry.load()` raises `ManifestError` for an unknown `after` ref and `DependencyCycle` for a cycle through `after` edges.

- [ ] **Step 1: Write the failing tests**: `tests/core/test_after_ordering.py`

```python
from __future__ import annotations

from typing import ClassVar

import pytest

from devboost.core.errors import DependencyCycle, ManifestError, NeedsUser
from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.plan import PlannedModule
from devboost.core.registry import _validate
from devboost.core.runner import run_plan
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx, Module

FEDORA = OsInfo("fedora", "fedora", "x86_64")


class _Store(Module):
    name: ClassVar[str] = "t-store"

    def verify(self, ctx: Ctx) -> bool:
        return False

    def install(self, ctx: Ctx) -> None:
        raise NeedsUser("device not approved", "devboost pass approve box")


class _Reader(Module):
    name: ClassVar[str] = "t-reader"
    after = (_Store,)

    def verify(self, ctx: Ctx) -> bool:
        return True

    def install(self, ctx: Ctx) -> None:  # pragma: no cover — verify passes
        raise AssertionError


def test_after_orders_when_both_selected() -> None:
    mods = {"t-store": _Store, "t-reader": _Reader}
    assert toposort(["t-reader", "t-store"], mods) == ["t-store", "t-reader"]


def test_after_never_pulls_target_into_plan() -> None:
    mods = {"t-store": _Store, "t-reader": _Reader}
    assert toposort(["t-reader"], mods) == ["t-reader"]


def test_blocked_after_target_does_not_block_dependent() -> None:
    mods: dict[str, type[Module]] = {"t-store": _Store, "t-reader": _Reader}
    ctx = Ctx(os=FEDORA, ex=FakeExecutor())
    res = run_plan([PlannedModule("t-store"), PlannedModule("t-reader")], mods, ctx)
    assert [(r.name, r.status) for r in res] == [
        ("t-store", "blocked"), ("t-reader", "skip"),
    ]


def test_unknown_after_ref_rejected() -> None:
    class _Orphan(Module):
        name: ClassVar[str] = "t-orphan"
        after = (_Store,)

    with pytest.raises(ManifestError, match="after"):
        _validate({"t-orphan": _Orphan})


def test_after_cycle_detected() -> None:
    class _A(Module):
        name: ClassVar[str] = "t-a"

    class _B(Module):
        name: ClassVar[str] = "t-b"
        after = (_A,)

    _A.after = (_B,)
    with pytest.raises(DependencyCycle):
        _validate({"t-a": _A, "t-b": _B})
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/core/test_after_ordering.py -v`
Expected: FAIL. `_Reader` has no effect (`after` is unknown), so the first test gets the wrong order and the validation tests don't raise.

- [ ] **Step 3: Implement**

`model.py`: in `Module`, directly below `requires`:

```python
    #: Ordering-only dependencies: when a target is ALSO in the plan, this module runs
    #: after it. Unlike `requires`, a target is never pulled into the plan, and its
    #: failure or `blocked` state never blocks this module — use it for soft inputs the
    #: module degrades without (e.g. secrets read from `pass` while this device awaits
    #: approval).
    after: ClassVar[tuple[type[Module], ...]] = ()
```

`core/graph.py`: replace the `ts.add` loop:

```python
    ts: TopologicalSorter[str] = TopologicalSorter()
    for name in selected:
        soft = (d.name for d in modules[name].after if d.name in selected)
        ts.add(name, *(d.name for d in modules[name].requires), *soft)
```

and extend the docstring: `` `after` targets order the plan only when they are already selected.``

`core/registry.py`: in `_validate`, after the `requires` loop (inside the `for name, cls` loop):

```python
        for dep in cls.after:
            dep_name = getattr(dep, "name", None)
            if not dep_name or dep_name not in modules:
                raise ManifestError(f"module {name!r} has unknown 'after' module {dep!r}")
```

In `_check_cycles.walk`, change `for dep in modules[name].requires:` to:

```python
        for dep in (*modules[name].requires, *modules[name].after):
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/core -v && uv run mypy && uv run ruff check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/model.py src/devboost/core/graph.py src/devboost/core/registry.py tests/core/test_after_ordering.py
git commit -m "feat(engine): Module.after — ordering-only deps that never cascade a block"
```

---

### Task 2: `core/userconfig.py`: `~/.config/devboost/config.toml`

**Files:**
- Create: `engine/src/devboost/core/userconfig.py`
- Test: `engine/tests/core/test_userconfig.py` (create)

**Interfaces:**
- Produces: `DEFAULT_PASS_REPO = "adams100111/password-store"`; `class UserConfig(BaseModel)` with `pass_repo: str = DEFAULT_PASS_REPO`, `device_name: str | None = None` (extra keys ignored); `config_path() -> Path` (`$XDG_CONFIG_HOME/devboost/config.toml`, else `~/.config/devboost/config.toml`); `load_user_config(path: Path | None = None) -> UserConfig` (missing file → defaults; bad TOML or bad types → `ConfigError` naming the path).

- [ ] **Step 1: Write the failing tests**: `tests/core/test_userconfig.py`

```python
from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.errors import ConfigError
from devboost.core.userconfig import DEFAULT_PASS_REPO, config_path, load_user_config


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    cfg = load_user_config(tmp_path / "absent.toml")
    assert cfg.pass_repo == DEFAULT_PASS_REPO == "adams100111/password-store"
    assert cfg.device_name is None


def test_values_and_unknown_keys(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text('pass_repo = "me/store"\ndevice_name = "lap"\nother = 1\n', encoding="utf-8")
    cfg = load_user_config(p)
    assert (cfg.pass_repo, cfg.device_name) == ("me/store", "lap")


def test_invalid_toml_is_config_error(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text("pass_repo = \n", encoding="utf-8")
    with pytest.raises(ConfigError, match="config.toml"):
        load_user_config(p)


def test_wrong_type_is_config_error(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    p.write_text("pass_repo = 3\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="pass_repo"):
        load_user_config(p)


def test_config_path_honours_xdg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert config_path() == tmp_path / "xdg" / "devboost" / "config.toml"
    monkeypatch.delenv("XDG_CONFIG_HOME")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert config_path() == tmp_path / ".config" / "devboost" / "config.toml"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/core/test_userconfig.py -v`
Expected: FAIL with `ModuleNotFoundError: devboost.core.userconfig`.

- [ ] **Step 3: Implement** `core/userconfig.py`

```python
"""Per-user dev-boost preferences: ``~/.config/devboost/config.toml``.

Distinct from ``core/settings.py`` (engine env, ``DEVBOOST_*``): this file holds choices a
person makes once per account (which pass repo, what this device is called). Env vars
still win where a module documents one (e.g. ``DEVBOOST_PASS_REPO``).
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from devboost.core.errors import ConfigError

DEFAULT_PASS_REPO = "adams100111/password-store"


class UserConfig(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    pass_repo: str = DEFAULT_PASS_REPO
    device_name: str | None = None


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path(os.environ["HOME"]) / ".config"
    return root / "devboost" / "config.toml"


def load_user_config(path: Path | None = None) -> UserConfig:
    p = path if path is not None else config_path()
    if not p.exists():
        return UserConfig()
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{p}: invalid TOML ({exc})") from exc
    try:
        return UserConfig.model_validate(data)
    except ValidationError as exc:
        fields = ", ".join(str(e["loc"][0]) for e in exc.errors() if e["loc"])
        raise ConfigError(f"{p}: invalid value for {fields}") from exc
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/core/test_userconfig.py -v && uv run mypy && uv run ruff check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/core/userconfig.py tests/core/test_userconfig.py
git commit -m "feat(config): ~/.config/devboost/config.toml (pass_repo, device_name)"
```

---
### Task 3: `passstore/paths.py`: repo, store, state, device name, binary

**Files:**
- Create: `engine/src/devboost/passstore/__init__.py`, `engine/src/devboost/passstore/paths.py`
- Test: `engine/tests/passstore/__init__.py` (empty), `engine/tests/passstore/test_paths.py` (create)

**Interfaces:**
- Consumes: `UserConfig`, `load_user_config` (Task 2).
- Produces (all in `devboost.passstore.paths`):
  - `pass_repo(cfg: UserConfig | None = None) -> str`: env `DEVBOOST_PASS_REPO` › `cfg.pass_repo`.
  - `clone_url(repo: str) -> str`: `owner/repo` → `https://github.com/owner/repo.git`; a URL (`://`), scp-style `git@…` or absolute local path is returned unchanged.
  - `store_dir() -> Path`: `$PASSWORD_STORE_DIR` › `~/.password-store`.
  - `state_dir() -> Path`: `$XDG_STATE_HOME/devboost` › `~/.local/state/devboost`.
  - `sanitize_name(raw: str) -> str` (raises `ValueError` when nothing usable remains); `device_name(cfg: UserConfig | None = None, hostname: str | None = None) -> str`.
  - `devboost_bin() -> str`: `sys.executable` when frozen, else `shutil.which("devboost")`, else `"devboost"`.

- [ ] **Step 1: Write the failing tests**: `tests/passstore/test_paths.py` (also create an empty `tests/passstore/__init__.py`)

```python
from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.userconfig import UserConfig
from devboost.passstore import paths


def test_pass_repo_env_beats_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEVBOOST_PASS_REPO", raising=False)
    assert paths.pass_repo(UserConfig(pass_repo="me/cfg")) == "me/cfg"
    assert paths.pass_repo(UserConfig()) == "adams100111/password-store"
    monkeypatch.setenv("DEVBOOST_PASS_REPO", "me/env")
    assert paths.pass_repo(UserConfig(pass_repo="me/cfg")) == "me/env"


def test_clone_url_shapes() -> None:
    assert paths.clone_url("me/store") == "https://github.com/me/store.git"
    assert paths.clone_url("git@github.com:me/s.git") == "git@github.com:me/s.git"
    assert paths.clone_url("https://example.com/s.git") == "https://example.com/s.git"
    assert paths.clone_url("/srv/store.git") == "/srv/store.git"


def test_store_and_state_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("PASSWORD_STORE_DIR", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    assert paths.store_dir() == tmp_path / ".password-store"
    assert paths.state_dir() == tmp_path / ".local" / "state" / "devboost"
    monkeypatch.setenv("PASSWORD_STORE_DIR", str(tmp_path / "ps"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "st"))
    assert paths.store_dir() == tmp_path / "ps"
    assert paths.state_dir() == tmp_path / "st" / "devboost"


def test_device_name_default_and_config() -> None:
    assert paths.device_name(UserConfig(), hostname="Work-Laptop.local") == "work-laptop"
    assert paths.device_name(UserConfig(device_name="Desk 1"), hostname="x") == "desk-1"


def test_sanitize_rejects_empty() -> None:
    with pytest.raises(ValueError):
        paths.sanitize_name("...")


def test_devboost_bin_prefers_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "is_frozen", lambda: False)
    monkeypatch.setattr(paths.shutil, "which", lambda _c: "/home/u/.local/bin/devboost")
    assert paths.devboost_bin() == "/home/u/.local/bin/devboost"
    monkeypatch.setattr(paths.shutil, "which", lambda _c: None)
    assert paths.devboost_bin() == "devboost"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/passstore/test_paths.py -v`
Expected: FAIL with `ModuleNotFoundError: devboost.passstore`.

- [ ] **Step 3: Implement**

`passstore/__init__.py`:

```python
"""pass multi-device: per-device GPG keys, enroll/approve/revoke, auto-sync.

Library code only — the `pass`/`pass-store` modules and the `devboost pass` CLI call in.
Every side effect goes through the injected Executor. See docs/pass.md.
"""
```

`passstore/paths.py`:

```python
"""Where things live: the store repo, the local clone, sync state, this device's name."""

from __future__ import annotations

import os
import re
import shutil
import socket
import sys
from pathlib import Path

from devboost.core.selfupdate import is_frozen
from devboost.core.userconfig import UserConfig, load_user_config


def pass_repo(cfg: UserConfig | None = None) -> str:
    env = os.environ.get("DEVBOOST_PASS_REPO")
    if env:
        return env
    return (cfg if cfg is not None else load_user_config()).pass_repo


def clone_url(repo: str) -> str:
    """`owner/repo` → GitHub HTTPS; URLs, scp-style and local paths pass through."""
    if "://" in repo or repo.startswith(("git@", "/")):
        return repo
    return f"https://github.com/{repo.removesuffix('.git')}.git"


def store_dir() -> Path:
    override = os.environ.get("PASSWORD_STORE_DIR")
    return Path(override) if override else Path(os.environ["HOME"]) / ".password-store"


def state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME")
    root = Path(base) if base else Path(os.environ["HOME"]) / ".local" / "state"
    return root / "devboost"


def sanitize_name(raw: str) -> str:
    """Lower-case, [a-z0-9-] only — device names are file names in the store."""
    name = re.sub(r"[^a-z0-9-]+", "-", raw.strip().lower()).strip("-")
    if not name:
        raise ValueError(f"not a usable device name: {raw!r}")
    return name[:63]


def device_name(cfg: UserConfig | None = None, hostname: str | None = None) -> str:
    c = cfg if cfg is not None else load_user_config()
    if c.device_name:
        return sanitize_name(c.device_name)
    host = hostname if hostname is not None else socket.gethostname()
    return sanitize_name(host.split(".", 1)[0])


def devboost_bin() -> str:
    """Absolute path for units/hooks: the frozen binary itself, else devboost on PATH."""
    if is_frozen():
        return sys.executable
    return shutil.which("devboost") or "devboost"
```

(`core/selfupdate.py::is_frozen() -> bool` already exists.)

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/passstore/test_paths.py -v && uv run mypy && uv run ruff check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/passstore/__init__.py src/devboost/passstore/paths.py tests/passstore/__init__.py tests/passstore/test_paths.py
git commit -m "feat(passstore): repo/store/state paths and device naming"
```

---

### Task 4: `passstore/gpg.py`: keys, keygen, trusted import (+ shared test fake)

**Files:**
- Create: `engine/src/devboost/passstore/gpg.py`, `engine/tests/passstore/fakes.py`
- Test: `engine/tests/passstore/test_gpg.py` (create)

**Interfaces:**
- Produces (in `devboost.passstore.gpg`):
  - `@dataclass(frozen=True) class KeyInfo: fingerprint: str; uids: tuple[str, ...]`
  - `parse_colons(out: str, kind: Literal["sec", "pub"]) -> list[KeyInfo]`
  - `secret_keys(ctx: Ctx) -> list[KeyInfo]`; `public_fingerprints(ctx: Ctx) -> set[str]`; `show_key_file(ctx: Ctx, path: Path) -> list[KeyInfo]`
  - `device_uid(real_name: str, email: str, device: str) -> str`: `"<name> (devboost:<device>) <<email>>"`
  - `device_key(keys: Sequence[KeyInfo], device: str) -> KeyInfo | None`
  - `matches(token: str, key: KeyInfo) -> bool` (D4)
  - `generate(ctx: Ctx, uid: str, *, passphrase: str | None = None) -> str` (returns the fingerprint; `passphrase=None` → pinentry with the tty, `interactive=True`; a string → loopback, used by tests only)
  - `export_armored(ctx: Ctx, fp: str) -> str`
  - `import_trusted(ctx: Ctx, path: Path, fp: str) -> None` (D7)
  - All failures → `InstallError("pass-store", <command>, code)`.
- Produces (test support, `tests.passstore.fakes`): `RuleExecutor(FakeExecutor)` with `rules: list[tuple[tuple[str, ...], Result]]` (the first rule whose tokens are **all** in argv wins; default `Result(0)`), `on_call: list[tuple[str, tuple[tuple[str, ...], Result]]]` (trigger token → rule pushed to the front), plus `envs`, `stdins`, and `interactive` lists index-aligned with `calls`; `colons(kind: str, fp: str, *uids: str) -> str`.

- [ ] **Step 1: Write the shared fake**: `tests/passstore/fakes.py`

```python
"""Test doubles shared by passstore, module and CLI tests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from devboost.exec.executor import FakeExecutor, Result


@dataclass
class RuleExecutor(FakeExecutor):
    """FakeExecutor whose results are chosen by argv content, not just argv[0].

    ``rules`` is ordered; the first rule whose tokens all appear in argv wins.
    ``on_call`` models state changes: when a call's argv contains the trigger token, its
    rule is pushed to the FRONT of ``rules`` (e.g. after `--quick-gen-key`, the key lists).
    """

    rules: list[tuple[tuple[str, ...], Result]] = field(default_factory=list)
    on_call: list[tuple[str, tuple[tuple[str, ...], Result]]] = field(default_factory=list)
    envs: list[dict[str, str]] = field(default_factory=list)
    stdins: list[str | None] = field(default_factory=list)
    interactive: list[bool] = field(default_factory=list)

    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        interactive: bool = False,
    ) -> Result:
        super().run(argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive)
        self.envs.append(dict(env or {}))
        self.stdins.append(stdin)
        self.interactive.append(interactive)
        for trigger, rule in self.on_call:
            if trigger in argv:
                self.rules.insert(0, rule)
        for tokens, res in self.rules:
            if all(t in argv for t in tokens):
                return res
        return Result(0)


def colons(kind: str, fp: str, *uids: str) -> str:
    """Minimal `gpg --with-colons` output for one key (primary + one subkey)."""
    lines = [f"{kind}:u:255:22:{fp[-16:]}:1700000000:::u:::scESC:::+:::ed25519:::0:",
             f"fpr:::::::::{fp}:"]
    lines += [f"uid:u::::1700000000::HASH::{u}::::::::::0:" for u in uids]
    lines += ["ssb:u:255:18:SUBKEYID:1700000000::::::e:::+:::cv25519::", "fpr:::::::::SUBFPR:"]
    return "\n".join(lines) + "\n"
```

- [ ] **Step 2: Write the failing tests**: `tests/passstore/test_gpg.py`

```python
from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.errors import InstallError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.passstore import gpg
from devboost.passstore.gpg import KeyInfo
from tests.passstore.fakes import RuleExecutor, colons

FEDORA = OsInfo("fedora", "fedora", "x86_64")
FP_A = "A" * 32 + "01BD994F"
FP_B = "B" * 32 + "64F46F56"
UID = "Ada (devboost:lap) <ada@example.com>"


def _ctx(ex: RuleExecutor) -> Ctx:
    return Ctx(os=FEDORA, ex=ex)


def test_parse_colons_primary_fpr_and_uids_not_subkeys() -> None:
    out = colons("sec", FP_A, UID) + colons("sec", FP_B)
    assert gpg.parse_colons(out, "sec") == [KeyInfo(FP_A, (UID,)), KeyInfo(FP_B, ())]


def test_matches_fingerprint_keyid_0x_and_email() -> None:
    key = KeyInfo(FP_A, (UID,))
    assert gpg.matches(FP_A.lower(), key)
    assert gpg.matches("0x" + FP_A[-16:], key)
    assert gpg.matches("ada@example.com", key)
    assert not gpg.matches(FP_B, key)
    assert not gpg.matches("", key)
    assert not gpg.matches("994F", key)  # too short to be a key id


def test_device_uid_and_device_key() -> None:
    assert gpg.device_uid("Ada", "ada@example.com", "lap") == UID
    keys = [KeyInfo(FP_B, ("Other <o@x>",)), KeyInfo(FP_A, (UID,))]
    assert gpg.device_key(keys, "lap") == keys[1]
    assert gpg.device_key(keys, "desk") is None


def test_generate_runs_keygen_then_encryption_subkey_via_pinentry() -> None:
    ex = RuleExecutor(rules=[(("--list-secret-keys",), Result(0, colons("sec", FP_A, UID)))])
    assert gpg.generate(_ctx(ex), UID) == FP_A
    assert ex.calls[0] == ["gpg", "--batch", "--quick-gen-key", UID, "ed25519", "cert,sign", "never"]
    assert ex.calls[-1] == ["gpg", "--batch", "--quick-add-key", FP_A, "cv25519", "encr", "never"]
    assert ex.interactive[0] is True and ex.interactive[-1] is True


def test_generate_loopback_passphrase_for_tests() -> None:
    ex = RuleExecutor(rules=[(("--list-secret-keys",), Result(0, colons("sec", FP_A, UID)))])
    gpg.generate(_ctx(ex), UID, passphrase="")
    assert ex.calls[0][:5] == ["gpg", "--batch", "--pinentry-mode", "loopback", "--passphrase"]
    assert ex.interactive[0] is False


def test_generate_failure_raises() -> None:
    ex = RuleExecutor(rules=[(("--quick-gen-key",), Result(2))])
    with pytest.raises(InstallError, match="quick-gen-key"):
        gpg.generate(_ctx(ex), UID)


def test_export_armored_requires_output() -> None:
    armored = "-----BEGIN PGP PUBLIC KEY BLOCK-----\n"
    ex = RuleExecutor(rules=[(("--export",), Result(0, armored))])
    assert gpg.export_armored(_ctx(ex), FP_A) == armored
    with pytest.raises(InstallError):
        gpg.export_armored(_ctx(RuleExecutor()), FP_A)


def test_import_trusted_sets_ultimate_ownertrust(tmp_path: Path) -> None:
    ex = RuleExecutor()
    gpg.import_trusted(_ctx(ex), tmp_path / "k.asc", FP_A)
    assert ex.calls == [
        ["gpg", "--batch", "--import", str(tmp_path / "k.asc")],
        ["gpg", "--batch", "--import-ownertrust"],
    ]
    assert ex.stdins[1] == f"{FP_A}:6:\n"


def test_show_key_file_and_public_fingerprints(tmp_path: Path) -> None:
    ex = RuleExecutor(rules=[
        (("--show-keys",), Result(0, colons("pub", FP_B))),
        (("--list-keys",), Result(0, colons("pub", FP_A) + colons("pub", FP_B))),
    ])
    assert gpg.show_key_file(_ctx(ex), tmp_path / "b.asc") == [KeyInfo(FP_B, ())]
    assert gpg.public_fingerprints(_ctx(ex)) == {FP_A, FP_B}
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/passstore/test_gpg.py -v`
Expected: FAIL with `ImportError: cannot import name 'gpg'`.

- [ ] **Step 4: Implement** `passstore/gpg.py`

```python
"""GnuPG over the executor: list/parse keys, generate a device key, import trusted keys."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from devboost.core.errors import InstallError
from devboost.exec.executor import Result
from devboost.model import Ctx

_HEX = re.compile(r"^[0-9A-F]{16,40}$")


@dataclass(frozen=True)
class KeyInfo:
    fingerprint: str
    uids: tuple[str, ...]


def parse_colons(out: str, kind: Literal["sec", "pub"]) -> list[KeyInfo]:
    """Primary-key fingerprints + uids from `--with-colons` output (subkey fprs ignored)."""
    keys: list[KeyInfo] = []
    fp: str | None = None
    uids: list[str] = []
    want_fpr = False
    for line in out.splitlines():
        f = line.split(":")
        rec = f[0]
        if rec == kind:
            if fp is not None:
                keys.append(KeyInfo(fp, tuple(uids)))
            fp, uids, want_fpr = None, [], True
        elif rec in ("sub", "ssb"):
            want_fpr = False
        elif rec == "fpr" and want_fpr and len(f) > 9:
            fp, want_fpr = f[9].upper(), False
        elif rec == "uid" and fp is not None and len(f) > 9:
            uids.append(f[9])
    if fp is not None:
        keys.append(KeyInfo(fp, tuple(uids)))
    return keys


def _gpg(ctx: Ctx, *args: str, stdin: str | None = None, interactive: bool = False) -> Result:
    return ctx.ex.run(["gpg", "--batch", *args], stdin=stdin, interactive=interactive)


def _must(res: Result, command: str) -> Result:
    if not res.ok:
        raise InstallError("pass-store", command, res.code)
    return res


def secret_keys(ctx: Ctx) -> list[KeyInfo]:
    res = _gpg(ctx, "--with-colons", "--list-secret-keys")
    return parse_colons(res.stdout, "sec") if res.ok else []


def public_fingerprints(ctx: Ctx) -> set[str]:
    res = _gpg(ctx, "--with-colons", "--list-keys")
    return {k.fingerprint for k in parse_colons(res.stdout, "pub")} if res.ok else set()


def show_key_file(ctx: Ctx, path: Path) -> list[KeyInfo]:
    res = _gpg(ctx, "--with-colons", "--show-keys", str(path))
    return parse_colons(res.stdout, "pub") if res.ok else []


def device_uid(real_name: str, email: str, device: str) -> str:
    return f"{real_name} (devboost:{device}) <{email}>"


def device_key(keys: Sequence[KeyInfo], device: str) -> KeyInfo | None:
    tag = f"(devboost:{device})"
    return next((k for k in keys if any(tag in u for u in k.uids)), None)


def matches(token: str, key: KeyInfo) -> bool:
    """Does a `.gpg-id` token name this key? fpr / long key id (suffix, 0x ok) or email."""
    t = token.strip()
    if "@" in t:
        return any(f"<{t}>" in u or u == t for u in key.uids)
    t = t.upper().removeprefix("0X")
    return bool(_HEX.match(t)) and key.fingerprint.upper().endswith(t)


def _loopback(passphrase: str | None) -> list[str]:
    if passphrase is None:
        return []
    return ["--pinentry-mode", "loopback", "--passphrase", passphrase]


def generate(ctx: Ctx, uid: str, *, passphrase: str | None = None) -> str:
    """ed25519 cert/sign primary + cv25519 encryption subkey, no expiry. Returns the fpr.

    passphrase=None (production) → gpg-agent asks via pinentry, so the call gets the tty.
    """
    lb = _loopback(passphrase)
    tty = passphrase is None
    _must(_gpg(ctx, *lb, "--quick-gen-key", uid, "ed25519", "cert,sign", "never",
               interactive=tty), f"gpg --quick-gen-key {uid!r}")
    key = next((k for k in secret_keys(ctx) if uid in k.uids), None)
    if key is None:
        raise InstallError("pass-store", "gpg --list-secret-keys (new key not found)", 1)
    _must(_gpg(ctx, *lb, "--quick-add-key", key.fingerprint, "cv25519", "encr", "never",
               interactive=tty), f"gpg --quick-add-key {key.fingerprint}")
    return key.fingerprint


def export_armored(ctx: Ctx, fp: str) -> str:
    res = _gpg(ctx, "--armor", "--export", fp)
    if not res.ok or "BEGIN PGP PUBLIC KEY BLOCK" not in res.stdout:
        raise InstallError("pass-store", f"gpg --armor --export {fp}", res.code or 1)
    return res.stdout


def import_trusted(ctx: Ctx, path: Path, fp: str) -> None:
    """Import a device public key and trust it ultimately (all keys are the user's own)."""
    _must(_gpg(ctx, "--import", str(path)), f"gpg --import {path}")
    _must(_gpg(ctx, "--import-ownertrust", stdin=f"{fp}:6:\n"), "gpg --import-ownertrust")
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/passstore/test_gpg.py -v && uv run mypy && uv run ruff check`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/devboost/passstore/gpg.py tests/passstore/fakes.py tests/passstore/test_gpg.py
git commit -m "feat(passstore): gpg key parsing, device keygen, trusted import"
```

---

### Task 5: `passstore/layout.py`: device records, rotation, `.gpg-id`, entries

**Files:**
- Create: `engine/src/devboost/passstore/layout.py`
- Test: `engine/tests/passstore/test_layout.py` (create)

**Interfaces:**
- Produces (in `devboost.passstore.layout`):
  - `Kind = Literal["devices", "pending", "revoked"]`
  - `class DeviceRecord(BaseModel)`: `name: str`, `fingerprint: str`, `os: str`, `enrolled_at: str | None = None`, `requested_at: str | None = None`, `scope: list[str] | None = None`
  - `class RotationEntry(BaseModel)`: `device: str`, `fingerprint: str`, `revoked_at: str`, `after: str`, `entries: list[str]`
  - `now_iso() -> str` (UTC, seconds precision)
  - `class Store(root: Path)` with `root`, `meta` (`root/.devboost`), `is_clone() -> bool`, `gpg_id_path(folder: str = "") -> Path`, `gpg_ids(folder: str = "") -> list[str]`, `record_path(kind, name) -> Path`, `key_path(kind, name) -> Path`, `records(kind) -> list[DeviceRecord]`, `record(kind, name) -> DeviceRecord | None`, `write_record(kind, rec, armored: str) -> None`, `move(src: Kind, dst: Kind, name: str) -> None`, `rotation() -> list[RotationEntry]`, `write_rotation(entries: Sequence[RotationEntry]) -> None`, `entries(folder: str = "") -> list[str]` (relative names without `.gpg`, excluding `.git`/`.devboost`, sorted).

- [ ] **Step 1: Write the failing tests**: `tests/passstore/test_layout.py`

```python
from __future__ import annotations

import json
from pathlib import Path

from devboost.passstore.layout import DeviceRecord, RotationEntry, Store, now_iso

FP = "A" * 40


def _store(tmp_path: Path) -> Store:
    (tmp_path / ".git").mkdir()
    return Store(tmp_path)


def test_gpg_ids_root_and_folder(tmp_path: Path) -> None:
    s = _store(tmp_path)
    assert s.gpg_ids() == []
    (tmp_path / ".gpg-id").write_text(f"{FP}\n\n  0xBEEF0000BEEF0000 \n", encoding="utf-8")
    (tmp_path / "harness").mkdir()
    (tmp_path / "harness" / ".gpg-id").write_text("X\n", encoding="utf-8")
    assert s.gpg_ids() == [FP, "0xBEEF0000BEEF0000"]
    assert s.gpg_ids("harness") == ["X"]
    assert s.is_clone()


def test_record_roundtrip_and_move(tmp_path: Path) -> None:
    s = _store(tmp_path)
    rec = DeviceRecord(name="lap", fingerprint=FP, os="fedora", requested_at=now_iso())
    s.write_record("pending", rec, "ARMORED\n")
    assert s.record("pending", "lap") == rec
    assert s.key_path("pending", "lap").read_text(encoding="utf-8") == "ARMORED\n"
    data = json.loads(s.record_path("pending", "lap").read_text(encoding="utf-8"))
    assert data["scope"] is None and data["fingerprint"] == FP
    s.move("pending", "devices", "lap")
    assert s.record("pending", "lap") is None
    assert [r.name for r in s.records("devices")] == ["lap"]
    assert s.key_path("devices", "lap").exists()


def test_records_skip_invalid_json(tmp_path: Path) -> None:
    s = _store(tmp_path)
    d = tmp_path / ".devboost" / "devices"
    d.mkdir(parents=True)
    (d / "bad.json").write_text("{", encoding="utf-8")
    assert s.records("devices") == []


def test_rotation_roundtrip(tmp_path: Path) -> None:
    s = _store(tmp_path)
    assert s.rotation() == []
    e = RotationEntry(device="old", fingerprint=FP, revoked_at=now_iso(), after="abc",
                      entries=["web/github"])
    s.write_rotation([e])
    assert s.rotation() == [e]


def test_entries_exclude_meta_and_git(tmp_path: Path) -> None:
    s = _store(tmp_path)
    for rel in ("web/github.gpg", "clickup/api-token.gpg", ".git/x.gpg",
                ".devboost/devices/y.gpg", "harness/tg.gpg"):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
    assert s.entries() == ["clickup/api-token", "harness/tg", "web/github"]
    assert s.entries("harness") == ["harness/tg"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/passstore/test_layout.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement** `passstore/layout.py`

```python
"""The store's on-disk layout: .gpg-id files, entries, and the public `.devboost/` registry.

`.devboost/` holds only public keys and metadata — never secrets.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from devboost.core import log

Kind = Literal["devices", "pending", "revoked"]


class DeviceRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    fingerprint: str
    os: str
    enrolled_at: str | None = None
    requested_at: str | None = None
    scope: list[str] | None = None


class RotationEntry(BaseModel):
    device: str
    fingerprint: str
    revoked_at: str
    after: str
    entries: list[str]


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class Store:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.meta = root / ".devboost"

    def is_clone(self) -> bool:
        return (self.root / ".git").is_dir()

    def gpg_id_path(self, folder: str = "") -> Path:
        return (self.root / folder if folder else self.root) / ".gpg-id"

    def gpg_ids(self, folder: str = "") -> list[str]:
        p = self.gpg_id_path(folder)
        if not p.exists():
            return []
        return [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def record_path(self, kind: Kind, name: str) -> Path:
        return self.meta / kind / f"{name}.json"

    def key_path(self, kind: Kind, name: str) -> Path:
        return self.meta / kind / f"{name}.asc"

    def record(self, kind: Kind, name: str) -> DeviceRecord | None:
        p = self.record_path(kind, name)
        if not p.exists():
            return None
        try:
            return DeviceRecord.model_validate_json(p.read_text(encoding="utf-8"))
        except ValidationError:
            log.warn(f"pass: ignoring malformed {p}")
            return None

    def records(self, kind: Kind) -> list[DeviceRecord]:
        d = self.meta / kind
        if not d.is_dir():
            return []
        out = [self.record(kind, p.stem) for p in sorted(d.glob("*.json"))]
        return [r for r in out if r is not None]

    def write_record(self, kind: Kind, rec: DeviceRecord, armored: str) -> None:
        path = self.record_path(kind, rec.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rec.model_dump_json(indent=2) + "\n", encoding="utf-8")
        self.key_path(kind, rec.name).write_text(armored, encoding="utf-8")

    def move(self, src: Kind, dst: Kind, name: str) -> None:
        (self.meta / dst).mkdir(parents=True, exist_ok=True)
        for s, d in ((self.record_path(src, name), self.record_path(dst, name)),
                     (self.key_path(src, name), self.key_path(dst, name))):
            if s.exists():
                s.replace(d)

    def rotation(self) -> list[RotationEntry]:
        p = self.meta / "rotation.json"
        if not p.exists():
            return []
        raw = json.loads(p.read_text(encoding="utf-8"))
        return [RotationEntry.model_validate(x) for x in raw]

    def write_rotation(self, entries: Sequence[RotationEntry]) -> None:
        self.meta.mkdir(parents=True, exist_ok=True)
        body = json.dumps([e.model_dump() for e in entries], indent=2) + "\n"
        (self.meta / "rotation.json").write_text(body, encoding="utf-8")

    def entries(self, folder: str = "") -> list[str]:
        base = self.root / folder if folder else self.root
        out: list[str] = []
        for p in base.rglob("*.gpg"):
            rel = p.relative_to(self.root)
            if rel.parts[0] in (".git", ".devboost"):
                continue
            out.append(rel.with_suffix("").as_posix())
        return sorted(out)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/passstore/test_layout.py -v && uv run mypy && uv run ruff check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/passstore/layout.py tests/passstore/test_layout.py
git commit -m "feat(passstore): store layout — device registry, rotation, entries"
```

---

### Task 6: `passstore/git.py` + `passstore/notify.py`

**Files:**
- Create: `engine/src/devboost/passstore/git.py`, `engine/src/devboost/passstore/notify.py`
- Test: `engine/tests/passstore/test_git_notify.py` (create)

**Interfaces:**
- Produces (in `devboost.passstore.git`). Every call runs `git -C <store> …` with `env=NO_HOOK_ENV` (D10):
  - `NO_HOOK_ENV: dict[str, str] = {"DEVBOOST_PASS_HOOK": "off"}`
  - `clone(ctx, url: str, dest: Path) -> Result`; `pull(ctx, store: Path) -> Result` (`pull --rebase --autostash --quiet`); `push(ctx, store) -> Result`
  - `conflicted(ctx, store) -> list[str]`; `abort_rebase(ctx, store) -> None`
  - `commit(ctx, store, message: str) -> bool`: `add -A`; False when nothing is staged; raises `InstallError` when the commit fails.
  - `ahead(ctx, store) -> int` (0 when there is no upstream); `head(ctx, store) -> str`
  - `subjects_touching(ctx, store, since: str, path: str) -> list[str]`; `first_commit_with(ctx, store, token: str) -> str | None`; `files_at(ctx, store, rev: str) -> list[str]`; `added_since(ctx, store, rev: str) -> list[str]`; `all_history_files(ctx, store) -> list[str]`
- Produces (in `devboost.passstore.notify`):
  - `ntfy(ctx, title: str, body: str, *, priority: str = "default") -> bool` (no-op → False when `DEVBOOST_NTFY_URL` is unset)
  - `native(ctx, title: str, body: str) -> bool`
  - `_native_argv(os_info: OsInfo, title: str, body: str) -> list[str] | None`: **P2 seam**. Linux → `notify-send`. macOS → `None` for now (P2 returns an `osascript` argv).

- [ ] **Step 1: Write the failing tests**: `tests/passstore/test_git_notify.py`

```python
from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.errors import InstallError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.passstore import git, notify
from tests.passstore.fakes import RuleExecutor

FEDORA = OsInfo("fedora", "fedora", "x86_64")
MAC = OsInfo("macos", "macos", "aarch64")
S = Path("/s")


def _ctx(ex: RuleExecutor, os_: OsInfo = FEDORA) -> Ctx:
    return Ctx(os=os_, ex=ex)


def test_every_git_call_disables_the_hook() -> None:
    ex = RuleExecutor()
    git.pull(_ctx(ex), S)
    git.push(_ctx(ex), S)
    assert ex.calls == [
        ["git", "-C", "/s", "pull", "--rebase", "--autostash", "--quiet"],
        ["git", "-C", "/s", "push", "--quiet", "--set-upstream", "origin", "HEAD"],
    ]
    assert all(e == {"DEVBOOST_PASS_HOOK": "off"} for e in ex.envs)


def test_commit_only_when_staged() -> None:
    ex = RuleExecutor()  # `diff --cached --quiet` exits 0 → nothing staged
    assert git.commit(_ctx(ex), S, "m") is False
    assert ["git", "-C", "/s", "commit", "--quiet", "-m", "m"] not in ex.calls
    ex2 = RuleExecutor(rules=[(("diff", "--cached"), Result(1))])
    assert git.commit(_ctx(ex2), S, "devboost: x") is True
    assert ex2.calls[-1] == ["git", "-C", "/s", "commit", "--quiet", "-m", "devboost: x"]


def test_commit_failure_raises() -> None:
    ex = RuleExecutor(rules=[(("diff", "--cached"), Result(1)), (("commit",), Result(1))])
    with pytest.raises(InstallError):
        git.commit(_ctx(ex), S, "m")


def test_ahead_and_conflicted_parse_output() -> None:
    ex = RuleExecutor(rules=[
        (("rev-list",), Result(0, "3\n")),
        (("--diff-filter=U",), Result(0, ".gpg-id\nweb/x.gpg\n")),
    ])
    assert git.ahead(_ctx(ex), S) == 3
    assert git.conflicted(_ctx(ex), S) == [".gpg-id", "web/x.gpg"]
    assert git.ahead(_ctx(RuleExecutor(rules=[(("rev-list",), Result(128))])), S) == 0


def test_history_queries() -> None:
    ex = RuleExecutor(rules=[
        (("-SAAAA",), Result(0, "c1\nc2\n")),
        (("ls-tree",), Result(0, ".gpg-id\nweb/a.gpg\n")),
        (("--diff-filter=A",), Result(0, "\nweb/b.gpg\n\n")),
    ])
    assert git.first_commit_with(_ctx(ex), S, "AAAA") == "c1"
    assert git.files_at(_ctx(ex), S, "c1") == [".gpg-id", "web/a.gpg"]
    assert git.added_since(_ctx(ex), S, "c1") == ["web/b.gpg"]
    assert git.first_commit_with(_ctx(RuleExecutor()), S, "ZZZZ") is None


def test_ntfy_only_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEVBOOST_NTFY_URL", raising=False)
    ex = RuleExecutor()
    assert notify.ntfy(_ctx(ex), "t", "b") is False and ex.calls == []
    monkeypatch.setenv("DEVBOOST_NTFY_URL", "https://ntfy.sh/topic")
    assert notify.ntfy(_ctx(ex), "t", "b", priority="high") is True
    assert ex.calls[0][0] == "curl" and ex.calls[0][-1] == "https://ntfy.sh/topic"
    assert "Priority: high" in ex.calls[0]


def test_native_linux_uses_notify_send_when_present() -> None:
    ex = RuleExecutor(present={"notify-send"})
    assert notify.native(_ctx(ex), "t", "b") is True
    assert ex.calls == [["notify-send", "--app-name=devboost", "t", "b"]]
    assert notify.native(_ctx(RuleExecutor()), "t", "b") is False  # not installed


def test_native_macos_is_a_p2_seam() -> None:
    assert notify._native_argv(MAC, "t", "b") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/passstore/test_git_notify.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement** `passstore/git.py`

```python
"""git over the executor, scoped to the password store. Hook disabled for our own calls."""

from __future__ import annotations

from pathlib import Path

from devboost.core.errors import InstallError
from devboost.exec.executor import Result
from devboost.model import Ctx

#: Our own commits/pushes must not re-trigger the post-commit hook (D10).
NO_HOOK_ENV: dict[str, str] = {"DEVBOOST_PASS_HOOK": "off"}


def _git(ctx: Ctx, store: Path, *args: str) -> Result:
    return ctx.ex.run(["git", "-C", str(store), *args], env=NO_HOOK_ENV)


def _lines(res: Result) -> list[str]:
    return [ln.strip() for ln in res.stdout.splitlines() if ln.strip()] if res.ok else []


def clone(ctx: Ctx, url: str, dest: Path) -> Result:
    return ctx.ex.run(["git", "clone", "--quiet", url, str(dest)], env=NO_HOOK_ENV)


def pull(ctx: Ctx, store: Path) -> Result:
    return _git(ctx, store, "pull", "--rebase", "--autostash", "--quiet")


def push(ctx: Ctx, store: Path) -> Result:
    return _git(ctx, store, "push", "--quiet", "--set-upstream", "origin", "HEAD")


def conflicted(ctx: Ctx, store: Path) -> list[str]:
    return _lines(_git(ctx, store, "diff", "--name-only", "--diff-filter=U"))


def abort_rebase(ctx: Ctx, store: Path) -> None:
    _git(ctx, store, "rebase", "--abort")


def commit(ctx: Ctx, store: Path, message: str) -> bool:
    _git(ctx, store, "add", "-A")
    if _git(ctx, store, "diff", "--cached", "--quiet").ok:
        return False
    res = _git(ctx, store, "commit", "--quiet", "-m", message)
    if not res.ok:
        raise InstallError("pass-store", f"git commit -m {message!r}", res.code)
    return True


def ahead(ctx: Ctx, store: Path) -> int:
    out = _lines(_git(ctx, store, "rev-list", "--count", "@{u}..HEAD"))
    return int(out[0]) if out and out[0].isdigit() else 0


def head(ctx: Ctx, store: Path) -> str:
    out = _lines(_git(ctx, store, "rev-parse", "HEAD"))
    return out[0] if out else ""


def subjects_touching(ctx: Ctx, store: Path, since: str, path: str) -> list[str]:
    """Subjects of commits after *since* (all of history when empty) touching *path*."""
    rng = f"{since}..HEAD" if since else "HEAD"
    return _lines(_git(ctx, store, "log", "--format=%s", rng, "--", path))


def first_commit_with(ctx: Ctx, store: Path, token: str) -> str | None:
    """Oldest commit that changed the number of occurrences of *token* in root .gpg-id."""
    out = _lines(_git(ctx, store, "log", "--reverse", "--format=%H", f"-S{token}", "--",
                      ".gpg-id"))
    return out[0] if out else None


def files_at(ctx: Ctx, store: Path, rev: str) -> list[str]:
    return _lines(_git(ctx, store, "ls-tree", "-r", "--name-only", rev))


def added_since(ctx: Ctx, store: Path, rev: str) -> list[str]:
    return _lines(_git(ctx, store, "log", f"{rev}..HEAD", "--diff-filter=A", "--name-only",
                       "--format="))


def all_history_files(ctx: Ctx, store: Path) -> list[str]:
    return sorted(set(_lines(_git(ctx, store, "log", "--name-only", "--format="))))
```

`passstore/notify.py`:

```python
"""Notifications: ntfy (phone, optional) and the desktop's native notifier."""

from __future__ import annotations

import os

from devboost.core.osinfo import OsInfo
from devboost.model import Ctx


def ntfy(ctx: Ctx, title: str, body: str, *, priority: str = "default") -> bool:
    """POST to $DEVBOOST_NTFY_URL (same topic claude-notify uses). Unset → no-op."""
    url = os.environ.get("DEVBOOST_NTFY_URL")
    if not url:
        return False
    argv = ["curl", "-fsS", "--max-time", "5", "-H", f"Title: {title}",
            "-H", f"Priority: {priority}", "-H", "Tags: key", "-d", body, url]
    return ctx.ex.run(argv).ok


def _native_argv(os_info: OsInfo, title: str, body: str) -> list[str] | None:
    """P2 seam: macOS returns an osascript argv here; Linux uses libnotify."""
    if os_info.family == "macos":
        return None
    return ["notify-send", "--app-name=devboost", title, body]


def native(ctx: Ctx, title: str, body: str) -> bool:
    argv = _native_argv(ctx.os, title, body)
    if argv is None or not ctx.ex.which(argv[0]):
        return False
    return ctx.ex.run(argv).ok
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/passstore/test_git_notify.py -v && uv run mypy && uv run ruff check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/passstore/git.py src/devboost/passstore/notify.py tests/passstore/test_git_notify.py
git commit -m "feat(passstore): store git wrappers (hook-safe) and notifications"
```

---

### Task 7: `passstore/enroll.py`: clone, classify, genesis, adopt, enroll

**Files:**
- Create: `engine/src/devboost/passstore/enroll.py`
- Test: `engine/tests/passstore/test_enroll.py` (create)

**Interfaces:**
- Consumes: `paths.clone_url` (Task 3), `gpg.*` (Task 4), `Store`, `DeviceRecord`, `now_iso` (Task 5), `git.*`, `notify.ntfy` (Task 6), `_credentials.gh_is_authenticated`, `NeedsUser`.
- Produces (in `devboost.passstore.enroll`):
  - `AccessState = Literal["no-store", "genesis", "enrolled", "pending", "new"]`
  - `@dataclass(frozen=True) class Access: state: AccessState; key: KeyInfo | None; record: DeviceRecord | None`
  - `@dataclass(frozen=True) class Identity: real_name: str; email: str`; `identity(ctx) -> Identity`
  - `pass_env(store: Store) -> dict[str, str]`: `PASSWORD_STORE_DIR` + `NO_HOOK_ENV`
  - `has_access(store: Store, key: KeyInfo, scope: list[str] | None) -> bool`
  - `local_access(ctx, store: Store, device: str) -> Access`
  - `ensure_clone(ctx, store: Store, repo: str) -> None`: `NeedsUser` (no GitHub auth) / `ConfigError`
  - `publish(ctx, store: Store, message: str) -> None`: commit, then push; a push failure only warns
  - `import_device_keys(ctx, store: Store) -> list[str]` (D7; returns imported device names)
  - `ensure_access(ctx, store: Store, device: str, *, interactive: bool, scope: list[str] | None = None, passphrase: str | None = None) -> Access`: returns an `enrolled` Access, or raises `NeedsUser` whose `how_to_fix` is exactly `devboost pass approve <name>` (pending) or `run \`devboost pass enroll\` in a terminal` (no key + no TTY).

- [ ] **Step 1: Write the failing tests**: `tests/passstore/test_enroll.py`

```python
from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.errors import ConfigError, NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.passstore import enroll
from devboost.passstore.layout import DeviceRecord, Store
from tests.passstore.fakes import RuleExecutor, colons

FEDORA = OsInfo("fedora", "fedora", "x86_64")
FP_OLD = "C" * 24 + "01BD994F01BD994F"
FP_NEW = "D" * 40
ARMOR = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nx\n"
UID_NEW = "Ada (devboost:lap) <ada@example.com>"


def _store(tmp_path: Path, gpg_id: str | None = FP_OLD) -> Store:
    root = tmp_path / "store"
    (root / ".git").mkdir(parents=True)
    if gpg_id is not None:
        (root / ".gpg-id").write_text(gpg_id + "\n", encoding="utf-8")
    return Store(root)


def _ex(secret: str = "", *extra: tuple[tuple[str, ...], Result]) -> RuleExecutor:
    return RuleExecutor(rules=[
        *extra,
        (("--list-secret-keys",), Result(0, secret)),
        (("--export",), Result(0, ARMOR)),
        (("diff", "--cached"), Result(1)),  # something is staged → commit happens
        (("user.name",), Result(0, "Ada\n")),
        (("user.email",), Result(0, "ada@example.com\n")),
    ])


def _ctx(ex: RuleExecutor) -> Ctx:
    return Ctx(os=FEDORA, ex=ex)


def test_classify_genesis_when_no_root_gpg_id(tmp_path: Path) -> None:
    acc = enroll.local_access(_ctx(_ex()), _store(tmp_path, None), "lap")
    assert acc.state == "genesis"


def test_classify_enrolled_unregistered_key_by_short_id(tmp_path: Path) -> None:
    store = _store(tmp_path, gpg_id="0x01BD994F01BD994F")  # long key id, as in the real store
    acc = enroll.local_access(_ctx(_ex(colons("sec", FP_OLD, "Me <me@x>"))), store, "lap")
    assert acc.state == "enrolled" and acc.record is None and acc.key is not None


def test_classify_pending_and_new(tmp_path: Path) -> None:
    store = _store(tmp_path)
    ex = _ex(colons("sec", FP_NEW, UID_NEW))
    assert enroll.local_access(_ctx(ex), store, "lap").state == "new"
    store.write_record("pending", DeviceRecord(name="lap", fingerprint=FP_NEW, os="fedora"), ARMOR)
    assert enroll.local_access(_ctx(ex), store, "lap").state == "pending"


def test_adopt_registers_existing_key_without_approval(tmp_path: Path) -> None:
    store = _store(tmp_path)
    ex = _ex(colons("sec", FP_OLD, "Me <me@x>"))
    acc = enroll.ensure_access(_ctx(ex), store, "desk", interactive=False)
    assert acc.state == "enrolled"
    rec = store.record("devices", "desk")
    assert rec is not None and rec.fingerprint == FP_OLD and rec.enrolled_at
    assert ["git", "-C", str(store.root), "commit", "--quiet", "-m", "devboost: adopt desk"] in ex.calls
    assert ["git", "-C", str(store.root), "push", "--quiet", "--set-upstream", "origin", "HEAD"] in ex.calls


def test_new_device_interactive_generates_key_writes_pending_and_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEVBOOST_NTFY_URL", "https://ntfy.sh/t")
    store = _store(tmp_path)
    ex = _ex("")  # no key yet; after keygen the new key lists
    ex.on_call.append(
        ("--quick-gen-key", (("--list-secret-keys",), Result(0, colons("sec", FP_NEW, UID_NEW))))
    )
    with pytest.raises(NeedsUser) as err:
        enroll.ensure_access(_ctx(ex), store, "lap", interactive=True)
    assert err.value.how_to_fix == "devboost pass approve lap"
    assert ["gpg", "--batch", "--quick-gen-key", UID_NEW, "ed25519", "cert,sign", "never"] in ex.calls
    rec = store.record("pending", "lap")
    assert rec is not None and rec.fingerprint == FP_NEW and rec.requested_at
    assert store.key_path("pending", "lap").read_text(encoding="utf-8") == ARMOR
    assert any(c[0] == "curl" for c in ex.calls)  # one ntfy from the enrolling device


def test_new_device_unattended_never_prompts(tmp_path: Path) -> None:
    ex = _ex("")  # no local key at all
    with pytest.raises(NeedsUser, match="devboost pass enroll"):
        enroll.ensure_access(_ctx(ex), _store(tmp_path), "lap", interactive=False)
    assert not any("--quick-gen-key" in c for c in ex.calls)


def test_pending_device_reports_approve_command(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write_record("pending", DeviceRecord(name="lap", fingerprint=FP_NEW, os="fedora"), ARMOR)
    with pytest.raises(NeedsUser) as err:
        enroll.ensure_access(_ctx(_ex(colons("sec", FP_NEW, UID_NEW))), store, "lap",
                             interactive=True)
    assert err.value.how_to_fix == "devboost pass approve lap"


def test_name_collision_refused(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write_record("devices", DeviceRecord(name="lap", fingerprint=FP_OLD, os="fedora"), ARMOR)
    with pytest.raises(ConfigError, match="already used"):
        enroll.ensure_access(_ctx(_ex(colons("sec", FP_NEW, UID_NEW))), store, "lap",
                             interactive=True)


def test_genesis_initialises_store_to_this_device(tmp_path: Path) -> None:
    store = _store(tmp_path, None)
    ex = _ex(colons("sec", FP_NEW, UID_NEW))
    enroll.ensure_access(_ctx(ex), store, "lap", interactive=True)
    i = ex.calls.index(["pass", "init", FP_NEW])
    assert ex.envs[i]["PASSWORD_STORE_DIR"] == str(store.root)
    assert ex.envs[i]["DEVBOOST_PASS_HOOK"] == "off"
    assert store.record("devices", "lap") is not None


def test_ensure_clone_needs_gh_when_unauthenticated(tmp_path: Path) -> None:
    store = Store(tmp_path / "store")
    ex = RuleExecutor(rules=[(("clone",), Result(128))])  # gh absent → not authenticated
    with pytest.raises(NeedsUser, match="gh auth login"):
        enroll.ensure_clone(_ctx(ex), store, "me/store")
    assert ex.calls[0] == ["git", "clone", "--quiet", "https://github.com/me/store.git",
                           str(store.root)]


def test_ensure_clone_config_error_when_authenticated(tmp_path: Path) -> None:
    ex = RuleExecutor(rules=[(("clone",), Result(128))], present={"gh"})
    with pytest.raises(ConfigError, match="me/store"):
        enroll.ensure_clone(_ctx(ex), Store(tmp_path / "store"), "me/store")


def test_ensure_clone_refuses_non_git_dir(tmp_path: Path) -> None:
    root = tmp_path / "store"
    root.mkdir()
    (root / "x.gpg").write_text("x", encoding="utf-8")
    with pytest.raises(ConfigError, match="not a git clone"):
        enroll.ensure_clone(_ctx(RuleExecutor()), Store(root), "me/store")


def test_import_device_keys_only_verified_and_listed(tmp_path: Path) -> None:
    store = _store(tmp_path, gpg_id=f"{FP_OLD}\n{FP_NEW}")
    store.write_record("devices", DeviceRecord(name="a", fingerprint=FP_NEW, os="fedora"), ARMOR)
    store.write_record("devices", DeviceRecord(name="evil", fingerprint="E" * 40, os="x"), ARMOR)
    ex = RuleExecutor(rules=[
        (("--show-keys", str(store.key_path("devices", "a"))), Result(0, colons("pub", FP_NEW))),
        (("--show-keys",), Result(0, colons("pub", "F" * 40))),  # mismatching file
    ])
    assert enroll.import_device_keys(_ctx(ex), store) == ["a"]
    assert ["gpg", "--batch", "--import", str(store.key_path("devices", "a"))] in ex.calls
    assert not any(str(store.key_path("devices", "evil")) in c and "--import" in c
                   for c in ex.calls)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/passstore/test_enroll.py -v`
Expected: FAIL with `ImportError: cannot import name 'enroll'`.

- [ ] **Step 3: Implement** `passstore/enroll.py`

```python
"""Getting this device access to the store: clone → classify → genesis / adopt / request.

Never automatic: a new device only *requests* access; an enrolled device approves it.
"""

from __future__ import annotations

import getpass
import os
import socket
from dataclasses import dataclass
from typing import Literal

from devboost.core import log
from devboost.core.errors import ConfigError, InstallError, NeedsUser
from devboost.model import Ctx
from devboost.modules import _credentials as creds_src
from devboost.passstore import git, gpg, notify
from devboost.passstore.gpg import KeyInfo
from devboost.passstore.layout import DeviceRecord, Kind, Store, now_iso
from devboost.passstore.paths import clone_url

AccessState = Literal["no-store", "genesis", "enrolled", "pending", "new"]


@dataclass(frozen=True)
class Access:
    state: AccessState
    key: KeyInfo | None
    record: DeviceRecord | None


@dataclass(frozen=True)
class Identity:
    real_name: str
    email: str


def identity(ctx: Ctx) -> Identity:
    name = ctx.ex.run(["git", "config", "--global", "user.name"]).stdout.strip()
    email = ctx.ex.run(["git", "config", "--global", "user.email"]).stdout.strip()
    user = getpass.getuser()
    return Identity(name or user, email or f"{user}@{socket.gethostname()}")


def pass_env(store: Store) -> dict[str, str]:
    env = {"PASSWORD_STORE_DIR": str(store.root), **git.NO_HOOK_ENV}
    try:  # pinentry-curses needs to know the terminal when gpg asks for the passphrase
        env["GPG_TTY"] = os.ttyname(0)
    except OSError:
        pass
    return env


def has_access(store: Store, key: KeyInfo, scope: list[str] | None) -> bool:
    return any(any(gpg.matches(t, key) for t in store.gpg_ids(f)) for f in (scope or [""]))


def local_access(ctx: Ctx, store: Store, device: str) -> Access:
    if not store.is_clone():
        return Access("no-store", None, None)
    keys = gpg.secret_keys(ctx)
    if not store.gpg_ids():
        return Access("genesis", gpg.device_key(keys, device), None)
    by_fp = {k.fingerprint: k for k in keys}
    for rec in store.records("devices"):
        k = by_fp.get(rec.fingerprint)
        if k is not None and has_access(store, k, rec.scope):
            return Access("enrolled", k, rec)
    for k in keys:
        if has_access(store, k, None):
            return Access("enrolled", k, None)  # has access, not yet labelled → adopt
    for rec in store.records("pending"):
        k = by_fp.get(rec.fingerprint)
        if k is not None:
            return Access("pending", k, rec)
    return Access("new", gpg.device_key(keys, device), None)


def ensure_clone(ctx: Ctx, store: Store, repo: str) -> None:
    if store.is_clone():
        return
    if store.root.exists() and any(store.root.iterdir()):
        raise ConfigError(f"pass-store: {store.root} exists but is not a git clone — move it "
                          "aside and re-run")
    res = git.clone(ctx, clone_url(repo), store.root)
    if res.ok:
        return
    if not creds_src.gh_is_authenticated(ctx):
        raise NeedsUser("cloning the pass store needs GitHub access",
                        "gh auth login, then re-run devboost install")
    raise ConfigError(f"pass-store: cloning {repo} failed (exit {res.code}) — check pass_repo "
                      "in ~/.config/devboost/config.toml / DEVBOOST_PASS_REPO and your access")


def publish(ctx: Ctx, store: Store, message: str) -> None:
    if git.commit(ctx, store.root, message):
        res = git.push(ctx, store.root)
        if not res.ok:
            log.warn(f"pass: push failed (exit {res.code}) — the sync timer will retry")


def _name_free(store: Store, name: str, fp: str) -> None:
    kinds: tuple[Kind, ...] = ("devices", "pending")
    for kind in kinds:
        rec = store.record(kind, name)
        if rec is not None and rec.fingerprint != fp:
            raise ConfigError(f"pass: device name {name!r} is already used by key "
                              f"…{rec.fingerprint[-16:]} — choose another: "
                              "devboost pass enroll --name <name>")


def _register(ctx: Ctx, store: Store, kind: Kind, name: str, fp: str,
              scope: list[str] | None) -> DeviceRecord:
    _name_free(store, name, fp)
    pending = kind == "pending"
    rec = DeviceRecord(name=name, fingerprint=fp, os=ctx.os.distro, scope=scope,
                       enrolled_at=None if pending else now_iso(),
                       requested_at=now_iso() if pending else None)
    store.write_record(kind, rec, gpg.export_armored(ctx, fp))
    return rec


def _device_fp(ctx: Ctx, key: KeyInfo | None, device: str, passphrase: str | None) -> str:
    if key is not None:
        return key.fingerprint
    ident = identity(ctx)
    return gpg.generate(ctx, gpg.device_uid(ident.real_name, ident.email, device),
                        passphrase=passphrase)


def _no_key(interactive: bool, key: KeyInfo | None, reason: str) -> None:
    if not interactive and key is None:
        raise NeedsUser(reason, "run `devboost pass enroll` in a terminal")


def ensure_access(
    ctx: Ctx,
    store: Store,
    device: str,
    *,
    interactive: bool,
    scope: list[str] | None = None,
    passphrase: str | None = None,
) -> Access:
    acc = local_access(ctx, store, device)
    if acc.state == "no-store":
        raise ConfigError(f"pass-store: {store.root} is not cloned yet")
    if acc.state == "enrolled":
        if acc.record is None and acc.key is not None:
            _register(ctx, store, "devices", device, acc.key.fingerprint, None)
            publish(ctx, store, f"devboost: adopt {device}")
            return local_access(ctx, store, device)
        return acc
    if acc.state == "pending" and acc.record is not None:
        raise NeedsUser(f"device {acc.record.name!r} is waiting for approval",
                        f"devboost pass approve {acc.record.name}")
    if acc.state == "genesis":
        _no_key(interactive, acc.key, "the pass store is empty and this device has no key yet")
        fp = _device_fp(ctx, acc.key, device, passphrase)
        res = ctx.ex.run(["pass", "init", fp], env=pass_env(store))
        if not res.ok:
            raise InstallError("pass-store", f"pass init {fp}", res.code)
        _register(ctx, store, "devices", device, fp, None)
        publish(ctx, store, f"devboost: initialise store with {device}")
        return local_access(ctx, store, device)
    # new device: request access, then wait for an enrolled device to approve
    _no_key(interactive, acc.key, "this device has no pass key yet")
    fp = _device_fp(ctx, acc.key, device, passphrase)
    rec = _register(ctx, store, "pending", device, fp, scope)
    publish(ctx, store, f"devboost: request enrollment for {device}")
    notify.ntfy(ctx, f"pass: approve {device}?",
                f"{device} ({ctx.os.distro}) requests access, key {fp}. "
                f"On an enrolled device run: devboost pass approve {device}", priority="high")
    raise NeedsUser(f"enrollment requested for {rec.name!r}", f"devboost pass approve {rec.name}")


def import_device_keys(ctx: Ctx, store: Store) -> list[str]:
    """Import + trust every registered device key we lack, if its file and .gpg-id agree."""
    have = gpg.public_fingerprints(ctx)
    imported: list[str] = []
    for rec in store.records("devices"):
        if rec.fingerprint in have:
            continue
        path = store.key_path("devices", rec.name)
        shown = gpg.show_key_file(ctx, path)
        listed = has_access(store, KeyInfo(rec.fingerprint, ()), rec.scope)
        if len(shown) != 1 or shown[0].fingerprint != rec.fingerprint or not listed:
            log.warn(f"pass: {path} does not match its record / .gpg-id — not imported")
            continue
        gpg.import_trusted(ctx, path, rec.fingerprint)
        imported.append(rec.name)
    return imported
```

Note: in `test_classify_enrolled_unregistered_key_by_short_id`, the root token `0x01BD994F01BD994F` is a 16-hex suffix of `FP_OLD`, so `has_access` matches (D4).

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/passstore/test_enroll.py -v && uv run mypy && uv run ruff check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/passstore/enroll.py tests/passstore/test_enroll.py
git commit -m "feat(passstore): clone, adopt, genesis and enrollment requests"
```

---

### Task 8: `passstore/approve.py`: approve, revoke, rotation

**Files:**
- Create: `engine/src/devboost/passstore/approve.py`
- Test: `engine/tests/passstore/test_approve.py` (create)

**Interfaces:**
- Consumes: `enroll.local_access`, `enroll.pass_env`, `enroll.publish` (Task 7); `gpg.*`; `git.*`; `Store`, `DeviceRecord`, `RotationEntry`, `now_iso`.
- Produces (in `devboost.passstore.approve`):
  - `Confirm = Callable[[DeviceRecord], bool]`
  - `@dataclass(frozen=True) class Approved: name: str; scope: list[str] | None`
  - `approve(ctx, store: Store, device: str, name: str | None, confirm: Confirm, *, scope_override: list[str] | None = None) -> list[Approved]`: pull, then per pending request: verify its key file, confirm, import+trust, re-encrypt (root, or `-p <folder>` per scope folder), move `pending → devices` with `enrolled_at`, commit `devboost: enroll <name>`, push.
  - `revoke(ctx, store: Store, device: str, name: str, confirm: Confirm) -> RotationEntry | None` (None = cancelled)
  - `rotation_entries(ctx, store: Store, key: KeyInfo, scope: list[str] | None) -> list[str]` (D9)
  - `@dataclass(frozen=True) class Unrotated: device: str; entry: str`; `unrotated(ctx, store: Store) -> list[Unrotated]` (D8; an entry deleted from the store counts as resolved)
  - Errors: `ConfigError` (not an enrolled workstation / no such request / key-file mismatch / revoking this device / pull failed); `InstallError` from `pass init`.

- [ ] **Step 1: Write the failing tests**: `tests/passstore/test_approve.py`

```python
from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.errors import ConfigError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.passstore import approve
from devboost.passstore.layout import DeviceRecord, RotationEntry, Store
from tests.passstore.fakes import RuleExecutor, colons

FEDORA = OsInfo("fedora", "fedora", "x86_64")
FP_ME = "A" * 40
FP_NEW = "B" * 40
FP_SRV = "C" * 40
ARMOR = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nx\n"


def _store(tmp_path: Path, root_ids: list[str]) -> Store:
    root = tmp_path / "store"
    (root / ".git").mkdir(parents=True)
    (root / ".gpg-id").write_text("\n".join(root_ids) + "\n", encoding="utf-8")
    s = Store(root)
    s.write_record("devices", DeviceRecord(name="desk", fingerprint=FP_ME, os="fedora"), ARMOR)
    return s


def _ex(*extra: tuple[tuple[str, ...], Result]) -> RuleExecutor:
    return RuleExecutor(rules=[
        *extra,
        (("--list-secret-keys",), Result(0, colons("sec", FP_ME))),
        (("--show-keys",), Result(0, colons("pub", FP_NEW))),
        (("diff", "--cached"), Result(1)),
        (("rev-parse", "HEAD"), Result(0, "abc123\n")),
    ])


def _ctx(ex: RuleExecutor) -> Ctx:
    return Ctx(os=FEDORA, ex=ex)


def _pending(s: Store, scope: list[str] | None = None) -> None:
    s.write_record("pending", DeviceRecord(name="lap", fingerprint=FP_NEW, os="ubuntu",
                                           scope=scope), ARMOR)


def test_approve_workstation_reencrypts_to_n_plus_one(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME])
    _pending(s)
    ex = _ex()
    seen: list[str] = []

    def _yes(r: DeviceRecord) -> bool:
        seen.append(r.name)
        return True

    done = approve.approve(_ctx(ex), s, "desk", None, _yes)
    assert done == [approve.Approved("lap", None)] and seen == ["lap"]
    root = str(s.root)
    assert ex.calls[0] == ["git", "-C", root, "pull", "--rebase", "--autostash", "--quiet"]
    assert ["gpg", "--batch", "--import", str(s.key_path("pending", "lap"))] in ex.calls
    i = ex.calls.index(["pass", "init", FP_ME, FP_NEW])
    assert ex.interactive[i] is True and ex.envs[i]["PASSWORD_STORE_DIR"] == root
    rec = s.record("devices", "lap")
    assert rec is not None and rec.enrolled_at and s.record("pending", "lap") is None
    assert s.key_path("devices", "lap").exists()
    assert ["git", "-C", root, "commit", "--quiet", "-m", "devboost: enroll lap"] in ex.calls


def test_approve_refuses_mismatched_key_file(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME])
    _pending(s)
    ex = _ex((("--show-keys",), Result(0, colons("pub", "E" * 40))))
    with pytest.raises(ConfigError, match="does not match"):
        approve.approve(_ctx(ex), s, "desk", "lap", lambda r: True)
    assert not any(c[:2] == ["pass", "init"] for c in ex.calls)


def test_declined_confirmation_changes_nothing(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME])
    _pending(s)
    ex = _ex()
    assert approve.approve(_ctx(ex), s, "desk", "lap", lambda r: False) == []
    assert s.record("pending", "lap") is not None
    assert not any(c[:2] == ["pass", "init"] for c in ex.calls)


def test_scoped_approve_limits_to_folders(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME])
    _pending(s, scope=["harness"])
    ex = _ex()
    done = approve.approve(_ctx(ex), s, "desk", "lap", lambda r: True)
    assert done == [approve.Approved("lap", ["harness"])]
    assert ["pass", "init", "-p", "harness", FP_ME, FP_NEW] in ex.calls
    assert ["pass", "init", FP_ME, FP_NEW] not in ex.calls


def test_scope_override_wins(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME])
    _pending(s, scope=["harness", "web"])
    ex = _ex()
    approve.approve(_ctx(ex), s, "desk", "lap", lambda r: True, scope_override=["harness"])
    assert not any("web" in c for c in ex.calls if c[:2] == ["pass", "init"])


def test_approve_requires_enrolled_workstation(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_NEW])  # this device's key is not in .gpg-id
    _pending(s)
    with pytest.raises(ConfigError, match="enrolled"):
        approve.approve(_ctx(_ex()), s, "desk", None, lambda r: True)


def test_unknown_request_name(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME])
    with pytest.raises(ConfigError, match="no pending request"):
        approve.approve(_ctx(_ex()), s, "desk", "ghost", lambda r: True)


def test_revoke_workstation_reencrypts_moves_and_lists_rotation(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME, FP_NEW])
    s.write_record("devices", DeviceRecord(name="lap", fingerprint=FP_NEW, os="fedora"), ARMOR)
    ex = _ex(
        ((f"-S{FP_NEW}",), Result(0, "c1\nc9\n")),
        (("ls-tree",), Result(0, ".gpg-id\nweb/a.gpg\n.devboost/devices/desk.json\n")),
        (("--diff-filter=A",), Result(0, "web/b.gpg\n")),
    )
    entry = approve.revoke(_ctx(ex), s, "desk", "lap", lambda r: True)
    assert entry is not None
    assert (entry.device, entry.after, entry.entries) == ("lap", "abc123", ["web/a", "web/b"])
    assert ["pass", "init", FP_ME] in ex.calls
    assert s.record("devices", "lap") is None and s.record("revoked", "lap") is not None
    assert s.rotation() == [entry]
    assert ["git", "-C", str(s.root), "commit", "--quiet", "-m", "devboost: revoke lap"] in ex.calls


def test_revoke_refuses_this_device(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME, FP_NEW])
    with pytest.raises(ConfigError, match="another enrolled device"):
        approve.revoke(_ctx(_ex()), s, "desk", "desk", lambda r: True)


def test_revoke_cancelled_returns_none(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME, FP_NEW])
    s.write_record("devices", DeviceRecord(name="lap", fingerprint=FP_NEW, os="fedora"), ARMOR)
    assert approve.revoke(_ctx(_ex()), s, "desk", "lap", lambda r: False) is None
    assert s.record("devices", "lap") is not None


def test_revoke_scoped_server_restores_folder_inheritance(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME])
    (s.root / "harness").mkdir()
    (s.root / "harness" / ".gpg-id").write_text(f"{FP_ME}\n{FP_SRV}\n", encoding="utf-8")
    s.write_record("devices", DeviceRecord(name="srv", fingerprint=FP_SRV, os="ubuntu",
                                           scope=["harness"]), ARMOR)
    ex = _ex((("log", "--name-only", "--format="), Result(0, "harness/tg.gpg\nweb/a.gpg\n")))
    entry = approve.revoke(_ctx(ex), s, "desk", "srv", lambda r: True)
    assert entry is not None and entry.entries == ["harness/tg"]
    assert ["pass", "init", "-p", "harness", ""] in ex.calls
    assert not any(c == ["pass", "init", FP_ME] for c in ex.calls)


def test_unrotated_ignores_automated_reencryptions(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME])
    for e in ("web/a", "web/b"):
        (s.root / "web").mkdir(exist_ok=True)
        (s.root / f"{e}.gpg").write_text("x", encoding="utf-8")
    s.write_rotation([RotationEntry(device="lap", fingerprint=FP_NEW, revoked_at="t",
                                    after="abc", entries=["web/a", "web/b", "web/gone"])])
    ex = RuleExecutor(rules=[
        (("web/a.gpg",), Result(0, "Edit password for web/a using vim.\n"
                                   "Reencrypt password store using new GPG id A.\n")),
        (("web/b.gpg",), Result(0, "Reencrypt password store using new GPG id A.\n"
                                   "devboost: enroll x\n")),
    ])
    assert approve.unrotated(_ctx(ex), s) == [approve.Unrotated("lap", "web/b")]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/passstore/test_approve.py -v`
Expected: FAIL with `ImportError: cannot import name 'approve'`.

- [ ] **Step 3: Implement** `passstore/approve.py`

```python
"""Approve pending devices, revoke devices, and track what must be rotated after a revoke."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from devboost.core import log
from devboost.core.errors import ConfigError, InstallError
from devboost.model import Ctx
from devboost.passstore import enroll, git, gpg
from devboost.passstore.gpg import KeyInfo
from devboost.passstore.layout import DeviceRecord, RotationEntry, Store, now_iso

Confirm = Callable[[DeviceRecord], bool]

#: Commit subjects that re-encrypt without changing a secret (never count as rotation).
_AUTOMATED = ("Reencrypt password store", "devboost:")


@dataclass(frozen=True)
class Approved:
    name: str
    scope: list[str] | None


@dataclass(frozen=True)
class Unrotated:
    device: str
    entry: str


def _pull(ctx: Ctx, store: Store) -> None:
    res = git.pull(ctx, store.root)
    if not res.ok:
        raise ConfigError(f"pass: git pull failed (exit {res.code}) — run "
                          "`devboost pass sync` (or `--resolve`) and retry")


def _require_workstation(ctx: Ctx, store: Store, device: str) -> enroll.Access:
    acc = enroll.local_access(ctx, store, device)
    if acc.state != "enrolled" or (acc.record is not None and acc.record.scope):
        raise ConfigError("pass: approve/revoke must run on an enrolled workstation "
                          "(this device has no access to the whole store)")
    return acc


def _with(ids: list[str], fp: str) -> list[str]:
    key = KeyInfo(fp, ())
    return ids if any(gpg.matches(t, key) for t in ids) else [*ids, fp]


def _pass_init(ctx: Ctx, store: Store, ids: list[str], folder: str = "") -> None:
    argv = ["pass", "init", *(["-p", folder] if folder else []), *ids]
    # Re-encryption decrypts every entry: gpg-agent may ask for the passphrase (pinentry).
    res = ctx.ex.run(argv, env=enroll.pass_env(store), interactive=True)
    if not res.ok:
        raise InstallError("pass-store", " ".join(argv), res.code)


def _verify_request(ctx: Ctx, store: Store, rec: DeviceRecord) -> None:
    shown = gpg.show_key_file(ctx, store.key_path("pending", rec.name))
    if len(shown) != 1 or shown[0].fingerprint != rec.fingerprint.upper():
        raise ConfigError(f"pass: refusing {rec.name!r} — its key file does not match the "
                          "fingerprint in its request")


def approve(
    ctx: Ctx,
    store: Store,
    device: str,
    name: str | None,
    confirm: Confirm,
    *,
    scope_override: list[str] | None = None,
) -> list[Approved]:
    _pull(ctx, store)
    _require_workstation(ctx, store, device)
    pending = store.records("pending")
    if name is not None:
        pending = [r for r in pending if r.name == name]
        if not pending:
            raise ConfigError(f"pass: no pending request named {name!r}")
    done: list[Approved] = []
    for req in pending:
        _verify_request(ctx, store, req)
        scope = scope_override if scope_override is not None else req.scope
        rec = req.model_copy(update={"scope": scope})
        if not confirm(rec):
            log.skip(f"pass: {rec.name} not approved")
            continue
        gpg.import_trusted(ctx, store.key_path("pending", rec.name), rec.fingerprint)
        if scope is None:
            _pass_init(ctx, store, _with(store.gpg_ids(), rec.fingerprint))
        else:
            for folder in scope:
                base = store.gpg_ids(folder) or store.gpg_ids()
                _pass_init(ctx, store, _with(base, rec.fingerprint), folder)
        armored = store.key_path("pending", rec.name).read_text(encoding="utf-8")
        store.move("pending", "devices", rec.name)
        store.write_record("devices", rec.model_copy(update={"enrolled_at": now_iso()}), armored)
        enroll.publish(ctx, store, f"devboost: enroll {rec.name}")
        done.append(Approved(rec.name, scope))
    return done


def rotation_entries(ctx: Ctx, store: Store, key: KeyInfo,
                     scope: list[str] | None) -> list[str]:
    """Entries the key could decrypt at any point (D9) — git history keeps them readable."""
    token = next((t for t in store.gpg_ids() if gpg.matches(t, key)), None)
    start = git.first_commit_with(ctx, store.root, token) if token and not scope else None
    if start:
        files = set(git.files_at(ctx, store.root, start)) | set(
            git.added_since(ctx, store.root, start))
    else:
        files = set(git.all_history_files(ctx, store.root))
    names = sorted(f.removesuffix(".gpg") for f in files
                   if f.endswith(".gpg") and not f.startswith(".devboost/"))
    if scope:
        names = [n for n in names if any(n.startswith(f.rstrip("/") + "/") for f in scope)]
    return names


def _subfolders_listing(store: Store, key: KeyInfo) -> list[str]:
    out: list[str] = []
    for p in sorted(store.root.rglob(".gpg-id")):
        rel = p.parent.relative_to(store.root)
        if rel.parts and rel.parts[0] not in (".git", ".devboost"):
            folder = rel.as_posix()
            if any(gpg.matches(t, key) for t in store.gpg_ids(folder)):
                out.append(folder)
    return out


def revoke(ctx: Ctx, store: Store, device: str, name: str,
           confirm: Confirm) -> RotationEntry | None:
    _pull(ctx, store)
    me = _require_workstation(ctx, store, device)
    rec = store.record("devices", name)
    if rec is None:
        raise ConfigError(f"pass: no enrolled device named {name!r}")
    if me.key is not None and me.key.fingerprint == rec.fingerprint:
        raise ConfigError("pass: refusing to revoke this device — run the revoke from "
                          "another enrolled device")
    if not confirm(rec):
        return None
    key = KeyInfo(rec.fingerprint, ())
    entries = rotation_entries(ctx, store, key, rec.scope)
    root = store.gpg_ids()
    remaining = [t for t in root if not gpg.matches(t, key)]
    if len(remaining) != len(root):
        _pass_init(ctx, store, remaining)
    for folder in _subfolders_listing(store, key):
        left = [t for t in store.gpg_ids(folder) if not gpg.matches(t, key)]
        # Nothing folder-specific left → drop its .gpg-id so it inherits the root set again.
        _pass_init(ctx, store, left if left and left != remaining else [""], folder)
    entry = RotationEntry(device=name, fingerprint=rec.fingerprint, revoked_at=now_iso(),
                          after=git.head(ctx, store.root), entries=entries)
    store.move("devices", "revoked", name)
    store.write_rotation([*store.rotation(), entry])
    enroll.publish(ctx, store, f"devboost: revoke {name}")
    return entry


def unrotated(ctx: Ctx, store: Store) -> list[Unrotated]:
    out: list[Unrotated] = []
    for r in store.rotation():
        for e in r.entries:
            if not (store.root / f"{e}.gpg").exists():
                continue  # deleted from the store since — nothing left to rotate here
            subjects = git.subjects_touching(ctx, store.root, r.after, f"{e}.gpg")
            if not any(not s.startswith(_AUTOMATED) for s in subjects):
                out.append(Unrotated(r.device, e))
    return out
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/passstore/test_approve.py -v && uv run mypy && uv run ruff check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/passstore/approve.py tests/passstore/test_approve.py
git commit -m "feat(passstore): approve/revoke with re-encryption and rotation tracking"
```

---

### Task 9: `passstore/sync.py`: sync run, hook, systemd timer

**Files:**
- Create: `engine/src/devboost/passstore/sync.py`
- Test: `engine/tests/passstore/test_sync.py` (create)

**Interfaces:**
- Consumes: `git.*`, `notify.native`, `enroll.local_access`, `enroll.import_device_keys`, `paths.state_dir`, `systemd.write_user_unit`/`enable_user_unit`/`_user_unit_dir`.
- Produces (in `devboost.passstore.sync`):
  - `SERVICE = "devboost-pass-sync.service"`, `TIMER = "devboost-pass-sync.timer"`, `HOOK_MARK = "# managed by devboost (pass-store)"`
  - `hook_script(bin_: str) -> str`; `service_unit(bin_: str) -> str`; `timer_unit() -> str`
  - `install_hook(store: Store, bin_: str) -> bool`; `hook_installed(store: Store) -> bool`
  - `install_scheduler(ctx, bin_: str) -> None` (**P2 seam**: macOS → `UnsupportedOS` until P2 adds `launchd.user_agent`); `scheduler_installed(ctx) -> bool`
  - `SyncStatus = Literal["ok", "skipped", "busy", "no-store", "conflict", "pull-failed", "push-failed"]`; `@dataclass(frozen=True) class SyncResult: status: SyncStatus; detail: str = ""`
  - `run(ctx, store: Store, device: str, *, push_only: bool = False) -> SyncResult`
  - `last_sync() -> str` (ISO time or `""`)
  - `resolve_guidance(ctx, store: Store) -> str` (D13)

- [ ] **Step 1: Write the failing tests**: `tests/passstore/test_sync.py`

```python
from __future__ import annotations

import fcntl
from pathlib import Path

import pytest

from devboost.core.errors import UnsupportedOS
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.passstore import sync
from devboost.passstore.layout import DeviceRecord, Store
from tests.passstore.fakes import RuleExecutor, colons

FEDORA = OsInfo("fedora", "fedora", "x86_64")
MAC = OsInfo("macos", "macos", "aarch64")
FP_ME = "A" * 40
FP_NEW = "B" * 40


@pytest.fixture(autouse=True)
def _dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.delenv("DEVBOOST_PASS_HOOK", raising=False)


def _store(tmp_path: Path) -> Store:
    root = tmp_path / "store"
    (root / ".git" / "hooks").mkdir(parents=True)
    (root / ".gpg-id").write_text(FP_ME + "\n", encoding="utf-8")
    return Store(root)


def _ex(*extra: tuple[tuple[str, ...], Result]) -> RuleExecutor:
    return RuleExecutor(present={"notify-send"}, rules=[
        *extra,
        (("--list-secret-keys",), Result(0, colons("sec", FP_ME))),
    ])


def _ctx(ex: RuleExecutor, os_: OsInfo = FEDORA) -> Ctx:
    return Ctx(os=os_, ex=ex)


def _notifications(ex: RuleExecutor) -> list[list[str]]:
    return [c for c in ex.calls if c[0] == "notify-send"]


def test_hook_is_a_logic_free_stub_and_idempotent(tmp_path: Path) -> None:
    s = _store(tmp_path)
    assert sync.install_hook(s, "/bin/devboost") is True
    hook = s.root / ".git" / "hooks" / "post-commit"
    text = hook.read_text(encoding="utf-8")
    assert text.startswith("#!/bin/sh\n") and sync.HOOK_MARK in text
    assert '"/bin/devboost" pass sync --push-only --quiet' in text and text.rstrip().endswith("&")
    assert hook.stat().st_mode & 0o111
    assert sync.install_hook(s, "/bin/devboost") is False
    assert sync.hook_installed(s)


def test_foreign_hook_is_backed_up(tmp_path: Path) -> None:
    s = _store(tmp_path)
    hook = s.root / ".git" / "hooks" / "post-commit"
    hook.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
    sync.install_hook(s, "/bin/devboost")
    assert (hook.parent / "post-commit.devboost-backup").read_text(encoding="utf-8").endswith(
        "echo mine\n")


def test_units_content() -> None:
    assert "ExecStart=/bin/devboost pass sync --quiet" in sync.service_unit("/bin/devboost")
    t = sync.timer_unit()
    assert "OnCalendar=*:0/15" in t and "Persistent=true" in t and "WantedBy=timers.target" in t


def test_install_scheduler_linux_enables_timer(tmp_path: Path) -> None:
    ex = _ex()
    sync.install_scheduler(_ctx(ex), "/bin/devboost")
    units = tmp_path / "home" / ".config" / "systemd" / "user"
    assert (units / sync.SERVICE).exists() and (units / sync.TIMER).exists()
    assert ["systemctl", "--user", "enable", "--now", sync.TIMER] in ex.calls
    assert sync.scheduler_installed(_ctx(ex))


def test_install_scheduler_macos_is_p2(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedOS, match="P2"):
        sync.install_scheduler(_ctx(_ex(), MAC), "/bin/devboost")


def test_hook_env_short_circuits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVBOOST_PASS_HOOK", "off")
    ex = _ex()
    assert sync.run(_ctx(ex), _store(tmp_path), "desk").status == "skipped"
    assert ex.calls == []


def test_pull_push_and_record_last_sync(tmp_path: Path) -> None:
    s = _store(tmp_path)
    ex = _ex((("rev-list",), Result(0, "2\n")))
    assert sync.run(_ctx(ex), s, "desk").status == "ok"
    root = str(s.root)
    assert ex.calls[0] == ["git", "-C", root, "pull", "--rebase", "--autostash", "--quiet"]
    assert ["git", "-C", root, "push", "--quiet", "--set-upstream", "origin", "HEAD"] in ex.calls
    assert sync.last_sync()


def test_push_only_never_pulls(tmp_path: Path) -> None:
    ex = _ex()
    sync.run(_ctx(ex), _store(tmp_path), "desk", push_only=True)
    assert not any("pull" in c for c in ex.calls)


def test_gpg_id_conflict_aborts_and_notifies(tmp_path: Path) -> None:
    ex = _ex((("pull",), Result(1)), (("--diff-filter=U",), Result(0, ".gpg-id\n")))
    res = sync.run(_ctx(ex), _store(tmp_path), "desk")
    assert (res.status, res.detail) == ("conflict", ".gpg-id")
    assert any(c[-2:] == ["rebase", "--abort"] for c in ex.calls)
    assert "devboost pass sync --resolve" in _notifications(ex)[0][-1]


def test_push_failure_notifies_once_per_head(tmp_path: Path) -> None:
    s = _store(tmp_path)
    ex = _ex((("rev-list",), Result(0, "1\n")), (("push",), Result(1)),
             (("rev-parse",), Result(0, "h1\n")))
    assert sync.run(_ctx(ex), s, "desk").status == "push-failed"
    assert sync.run(_ctx(ex), s, "desk").status == "push-failed"
    assert len(_notifications(ex)) == 1


def test_pending_request_notified_once(tmp_path: Path) -> None:
    s = _store(tmp_path)
    s.write_record("pending", DeviceRecord(name="lap", fingerprint=FP_NEW, os="ubuntu"), "K")
    ex = _ex()
    sync.run(_ctx(ex), s, "desk")
    sync.run(_ctx(ex), s, "desk")
    notes = _notifications(ex)
    assert len(notes) == 1 and "devboost pass approve lap" in notes[0][-1]


def test_unenrolled_device_does_not_notify_pending(tmp_path: Path) -> None:
    s = _store(tmp_path)
    s.write_record("pending", DeviceRecord(name="lap", fingerprint=FP_NEW, os="ubuntu"), "K")
    ex = _ex((("--list-secret-keys",), Result(0, colons("sec", FP_NEW))))
    sync.run(_ctx(ex), s, "lap")
    assert _notifications(ex) == []


def test_concurrent_sync_is_a_noop(tmp_path: Path) -> None:
    lock = tmp_path / "state" / "devboost" / "pass-sync.lock"
    lock.parent.mkdir(parents=True)
    with lock.open("w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ex = _ex()
        assert sync.run(_ctx(ex), _store(tmp_path), "desk").status == "busy"
        assert ex.calls == []


def test_resolve_guidance_lists_registry_fingerprints(tmp_path: Path) -> None:
    s = _store(tmp_path)
    s.write_record("devices", DeviceRecord(name="desk", fingerprint=FP_ME, os="fedora"), "K")
    text = sync.resolve_guidance(_ctx(_ex()), s)
    assert FP_ME in text and f"pass init {FP_ME}" in text and "git rebase --continue" in text
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/passstore/test_sync.py -v`
Expected: FAIL with `ImportError: cannot import name 'sync'`.

- [ ] **Step 3: Implement** `passstore/sync.py`

```python
"""Keep every device's clone current: push on commit (hook), pull every 15 min (timer).

Never raises into the caller for network/git trouble — it logs, notifies (de-duplicated)
and returns a status, because a sync problem must never block anything else.
"""

from __future__ import annotations

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from devboost.core import log
from devboost.core.errors import DevbootError, UnsupportedOS
from devboost.exec.primitives import systemd
from devboost.model import Ctx
from devboost.passstore import enroll, git, notify
from devboost.passstore.layout import Store, now_iso
from devboost.passstore.paths import state_dir

SERVICE = "devboost-pass-sync.service"
TIMER = "devboost-pass-sync.timer"
HOOK_MARK = "# managed by devboost (pass-store)"

SyncStatus = Literal["ok", "skipped", "busy", "no-store", "conflict", "pull-failed",
                     "push-failed"]


@dataclass(frozen=True)
class SyncResult:
    status: SyncStatus
    detail: str = ""


class _State(BaseModel):
    notified: list[str] = []
    push_failed_head: str = ""
    pull_failing: bool = False
    last_sync: str = ""


# --- hook + scheduler -----------------------------------------------------------------


def hook_script(bin_: str) -> str:
    return (f"#!/bin/sh\n{HOOK_MARK} — push each commit in the background; all logic lives "
            f"in devboost.\n\"{bin_}\" pass sync --push-only --quiet </dev/null >/dev/null 2>&1 &\n")


def _hook_path(store: Store) -> Path:
    return store.root / ".git" / "hooks" / "post-commit"


def hook_installed(store: Store) -> bool:
    p = _hook_path(store)
    return p.exists() and HOOK_MARK in p.read_text(encoding="utf-8")


def install_hook(store: Store, bin_: str) -> bool:
    p = _hook_path(store)
    body = hook_script(bin_)
    if p.exists():
        current = p.read_text(encoding="utf-8")
        if current == body:
            return False
        if HOOK_MARK not in current:
            p.with_name("post-commit.devboost-backup").write_text(current, encoding="utf-8")
            log.warn(f"pass: existing {p} saved as post-commit.devboost-backup")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    p.chmod(0o755)
    return True


def service_unit(bin_: str) -> str:
    return ("[Unit]\nDescription=devboost pass store sync\n\n[Service]\nType=oneshot\n"
            f"ExecStart={bin_} pass sync --quiet\n")


def timer_unit() -> str:
    return ("[Unit]\nDescription=devboost pass store sync every 15 min\n\n[Timer]\n"
            "OnCalendar=*:0/15\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n")


def install_scheduler(ctx: Ctx, bin_: str) -> None:
    if ctx.os.family == "macos":
        # P2: launchd.user_agent(ctx, launchd.label("pass-sync"), [bin_, "pass", "sync",
        #     "--quiet"], start_interval=900)
        raise UnsupportedOS("pass sync scheduling on macOS arrives in P2 (launchd agent)")
    systemd.write_user_unit(ctx, SERVICE, service_unit(bin_))
    systemd.write_user_unit(ctx, TIMER, timer_unit())
    systemd.enable_user_unit(ctx, TIMER, now=True)


def scheduler_installed(ctx: Ctx) -> bool:
    if ctx.os.family == "macos":
        return False
    return (systemd._user_unit_dir() / TIMER).exists()


# --- state, log, lock -----------------------------------------------------------------


def _state_file() -> Path:
    return state_dir() / "pass-sync.json"


def _load() -> _State:
    p = _state_file()
    if not p.exists():
        return _State()
    try:
        return _State.model_validate_json(p.read_text(encoding="utf-8"))
    except ValidationError:
        return _State()


def _save(state: _State) -> None:
    p = _state_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")


def _log(msg: str) -> None:
    log.info(f"pass sync: {msg}")
    p = state_dir() / "pass-sync.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(f"{now_iso()} {msg}\n")


@contextmanager
def _lock() -> Iterator[bool]:
    p = state_dir() / "pass-sync.lock"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True


def last_sync() -> str:
    return _load().last_sync


# --- the sync itself ------------------------------------------------------------------


def _notify_pending(ctx: Ctx, store: Store, device: str, state: _State) -> None:
    acc = enroll.local_access(ctx, store, device)
    if acc.state != "enrolled" or (acc.record is not None and acc.record.scope):
        return  # only workstations can approve, so only they are asked
    for rec in store.records("pending"):
        key = f"{rec.name}:{rec.fingerprint}"
        if key in state.notified:
            continue
        notify.native(ctx, f"pass: {rec.name} wants access",
                      f"{rec.name} ({rec.os}) requested access. Approve with: "
                      f"devboost pass approve {rec.name}")
        state.notified.append(key)


def run(ctx: Ctx, store: Store, device: str, *, push_only: bool = False) -> SyncResult:
    if os.environ.get("DEVBOOST_PASS_HOOK") == "off":
        return SyncResult("skipped", "devboost's own commit")
    if not store.is_clone():
        return SyncResult("no-store")
    with _lock() as got:
        if not got:
            return SyncResult("busy")
        state = _load()
        if not push_only:
            res = git.pull(ctx, store.root)
            if not res.ok:
                files = git.conflicted(ctx, store.root)
                if files:
                    git.abort_rebase(ctx, store.root)
                    _log(f"conflict in {', '.join(files)} — rebase aborted")
                    notify.native(ctx, "pass sync: conflict",
                                  f"Conflict in {', '.join(files)}. Run: "
                                  "devboost pass sync --resolve")
                    return SyncResult("conflict", ", ".join(files))
                _log(f"pull failed (exit {res.code})")
                if not state.pull_failing:
                    notify.native(ctx, "pass sync: pull failed",
                                  f"git pull failed (exit {res.code}); will retry")
                    state.pull_failing = True
                    _save(state)
                return SyncResult("pull-failed", f"exit {res.code}")
            state.pull_failing = False
        if git.ahead(ctx, store.root) > 0:
            res = git.push(ctx, store.root)
            if not res.ok:
                head = git.head(ctx, store.root)
                _log(f"push failed (exit {res.code}) at {head}")
                if state.push_failed_head != head:
                    notify.native(ctx, "pass sync: push failed",
                                  f"git push failed (exit {res.code}); will retry")
                    state.push_failed_head = head
                    _save(state)
                return SyncResult("push-failed", f"exit {res.code}")
        state.push_failed_head = ""
        if not push_only:
            try:
                enroll.import_device_keys(ctx, store)
            except DevbootError as exc:
                _log(f"importing device keys failed: {exc}")
            _notify_pending(ctx, store, device, state)
        state.last_sync = now_iso()
        _save(state)
        return SyncResult("ok")


def resolve_guidance(ctx: Ctx, store: Store) -> str:
    files = git.conflicted(ctx, store.root)
    fps = [r.fingerprint for r in store.records("devices") if r.scope is None]
    return "\n".join([
        "devboost pass sync --resolve — nothing is changed automatically.",
        f"store: {store.root}",
        f"conflicted files now: {', '.join(files) or 'none (the last sync aborted its rebase)'}",
        "The device registry (.devboost/devices) says the root .gpg-id must list exactly:",
        *[f"  {fp}" for fp in fps],
        "Fix:",
        f"  cd {store.root}",
        "  git pull --rebase                  # reproduces the conflict",
        "  # write exactly the fingerprints above into .gpg-id, then:",
        "  git add .gpg-id && git rebase --continue",
        f"  pass init {' '.join(fps)}   # re-encrypt every entry to that set",
        "  git push && devboost pass sync",
    ])
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/passstore/test_sync.py -v && uv run mypy && uv run ruff check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/passstore/sync.py tests/passstore/test_sync.py
git commit -m "feat(passstore): sync — hook, 15-min systemd timer, conflicts, de-duplicated notices"
```

---

### Task 10: modules: `pass` + `pass-store` into `base`, readers switch to `after`

**Files:**
- Create: `engine/src/devboost/modules/pass_store.py`, `engine/src/devboost/modules/_pass.py`
- Modify: `engine/src/devboost/modules/optional.py` (delete `Pass`, `PassStore`, and now-unused imports), `engine/src/devboost/modules/claude_plugins.py`, `engine/src/devboost/modules/codex_config.py`, `engine/src/devboost/modules/pi_harness.py`, `engine/src/devboost/modules/herdr.py` (`HerdrPlugins`), `profiles.toml`
- Modify tests: `engine/tests/modules/test_optional_ubuntu.py` (drop the Pass/PassStore sections)
- Test: `engine/tests/modules/test_pass_store.py` (create), `engine/tests/modules/test_herdr.py` (append)

**Interfaces:**
- Consumes: everything in `devboost.passstore` (Tasks 3–9), `Module.after` (Task 1), `load_user_config` (Task 2).
- Produces:
  - `devboost.modules.pass_store`: `AGENT_TTLS: dict[str, str]`; `gnupg_home() -> Path`; `agent_settings(os_info: OsInfo) -> dict[str, str]` (**P2 seam**: macOS adds `pinentry-program`); `ensure_agent_conf(path: Path, settings: Mapping[str, str]) -> bool`; `agent_conf_ok(path: Path, settings: Mapping[str, str]) -> bool`; `@register class Pass(Module)` (`name="pass"`, `profiles=("base",)`); `@register class PassStore(Module)` (`name="pass-store"`, `requires=(Pass, Secrets, Git)`, `families=("fedora","debian","arch")`, `profiles=("base",)`).
  - `devboost.modules._pass`: `pass_show(ctx: Ctx, entry: str, *, who: str) -> str | None`; `pass_fields(text: str) -> dict[str, str]`.
  - `claude-plugins`, `codex-config`, `pi-harness`, `herdr-plugins`: `after = (PassStore,)`; `PassStore` no longer in any `requires`.

- [ ] **Step 1: Write the failing tests**: `tests/modules/test_pass_store.py`

```python
from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.errors import NeedsUser
from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.profiles import load_profiles
from devboost.core.registry import load
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.modules._pass import pass_fields, pass_show
from devboost.modules.pass_store import Pass, PassStore
from devboost.passstore.layout import DeviceRecord, Store
from tests.passstore.fakes import RuleExecutor, colons

REPO_ROOT = Path(__file__).resolve().parents[3]
FEDORA = OsInfo("fedora", "fedora", "x86_64")
UBUNTU = OsInfo("ubuntu", "debian", "x86_64")
FP_ME = "A" * 40
ARMOR = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nx\n"


@pytest.fixture(autouse=True)
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("PASSWORD_STORE_DIR", str(tmp_path / "store"))
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")
    monkeypatch.delenv("GNUPGHOME", raising=False)
    monkeypatch.delenv("DEVBOOST_PASS_REPO", raising=False)
    cfg = tmp_path / "cfg" / "devboost" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('device_name = "desk"\n', encoding="utf-8")


def _seed(tmp_path: Path, gpg_id: str = FP_ME) -> Store:
    root = tmp_path / "store"
    (root / ".git" / "hooks").mkdir(parents=True)
    (root / ".gpg-id").write_text(gpg_id + "\n", encoding="utf-8")
    return Store(root)


def _ex(secret: str = colons("sec", FP_ME)) -> RuleExecutor:
    return RuleExecutor(present={"pass"}, rules=[
        (("--list-secret-keys",), Result(0, secret)),
        (("--export",), Result(0, ARMOR)),
        (("diff", "--cached"), Result(1)),
    ])


# --- Pass -----------------------------------------------------------------------------


def test_pass_is_base() -> None:
    assert (Pass.category, Pass.profiles) == ("base", ("base",))


def test_pass_sets_agent_cache_ttls_and_reloads(tmp_path: Path) -> None:
    conf = tmp_path / "home" / ".gnupg" / "gpg-agent.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text("pinentry-program /usr/bin/pinentry-gnome3\ndefault-cache-ttl 600\n",
                    encoding="utf-8")
    ex = RuleExecutor(present={"pass"})
    Pass().install(Ctx(os=FEDORA, ex=ex))
    assert conf.read_text(encoding="utf-8") == (
        "pinentry-program /usr/bin/pinentry-gnome3\n"
        "default-cache-ttl 28800\nmax-cache-ttl 86400\n"
    )
    assert ex.calls == [["gpgconf", "--reload", "gpg-agent"]]
    assert Pass().verify(Ctx(os=FEDORA, ex=RuleExecutor(present={"pass"})))
    again = RuleExecutor(present={"pass"})
    Pass().install(Ctx(os=FEDORA, ex=again))
    assert again.calls == []  # unchanged conf → no reload


def test_pass_installs_package_via_apt_on_ubuntu() -> None:
    ex = RuleExecutor()
    Pass().install(Ctx(os=UBUNTU, ex=ex))
    assert ["sudo", "apt-get", "install", "-y", "pass"] in ex.calls


# --- PassStore ------------------------------------------------------------------------


def test_pass_store_metadata() -> None:
    assert (PassStore.category, PassStore.profiles) == ("base", ("base",))
    assert PassStore.families == ("fedora", "debian", "arch")
    assert {m.name for m in PassStore.requires} == {"pass", "secrets", "git"}


def test_install_enrolled_device_adopts_and_wires_sync(tmp_path: Path) -> None:
    store = _seed(tmp_path)
    ctx = Ctx(os=FEDORA, ex=_ex())
    PassStore().install(ctx)
    assert store.record("devices", "desk") is not None
    assert (store.root / ".git" / "hooks" / "post-commit").exists()
    units = tmp_path / "home" / ".config" / "systemd" / "user"
    assert (units / "devboost-pass-sync.timer").exists()
    assert PassStore().verify(Ctx(os=FEDORA, ex=_ex()))


def test_verify_false_until_device_is_registered(tmp_path: Path) -> None:
    _seed(tmp_path)
    ctx = Ctx(os=FEDORA, ex=_ex())
    PassStore().install(ctx)
    (tmp_path / "store" / ".devboost" / "devices" / "desk.json").unlink()
    assert PassStore().verify(ctx) is False


def test_install_new_device_unattended_blocks_but_still_syncs(tmp_path: Path) -> None:
    store = _seed(tmp_path, gpg_id="B" * 40)
    with pytest.raises(NeedsUser, match="devboost pass enroll"):
        PassStore().install(Ctx(os=FEDORA, ex=_ex(secret="")))
    # the timer must be in place so the approval arrives by itself
    assert (store.root / ".git" / "hooks" / "post-commit").exists()


def test_pending_device_blocks_with_approve_command(tmp_path: Path) -> None:
    store = _seed(tmp_path, gpg_id="B" * 40)
    store.write_record("pending", DeviceRecord(name="desk", fingerprint=FP_ME, os="fedora"), ARMOR)
    with pytest.raises(NeedsUser) as err:
        PassStore().install(Ctx(os=FEDORA, ex=_ex()))
    assert err.value.how_to_fix == "devboost pass approve desk"


def test_missing_store_clones_default_repo_or_asks_for_gh(tmp_path: Path) -> None:
    ex = RuleExecutor(rules=[(("clone",), Result(128))])
    with pytest.raises(NeedsUser, match="gh auth login"):
        PassStore().install(Ctx(os=FEDORA, ex=ex))
    assert ex.calls[0] == ["git", "clone", "--quiet",
                           "https://github.com/adams100111/password-store.git",
                           str(tmp_path / "store")]


# --- profiles + ordering ----------------------------------------------------------------


def test_base_profile_carries_pass_and_security_cli_is_an_alias() -> None:
    profiles = load_profiles(REPO_ROOT / "profiles.toml")
    assert {"pass", "pass-store"} <= set(profiles["base"])
    assert profiles["security-cli"] == ["pass", "pass-store"]


def test_readers_order_after_pass_store_without_requiring_it() -> None:
    modules = load()
    for name in ("claude-plugins", "codex-config", "pi-harness", "herdr-plugins"):
        cls = modules[name]
        assert PassStore in cls.after and PassStore not in cls.requires, name
    order = toposort(["claude-plugins", "pass-store"], modules)
    assert order.index("pass-store") < order.index("claude-plugins")
    assert "pass-store" not in toposort(["herdr-plugins"], modules)


# --- _pass helpers ----------------------------------------------------------------------


def test_pass_show_degrades_and_reads() -> None:
    assert pass_show(Ctx(os=FEDORA, ex=RuleExecutor()), "x/y", who="t") is None  # no pass
    failing = RuleExecutor(present={"pass"}, rules=[(("show",), Result(2))])
    assert pass_show(Ctx(os=FEDORA, ex=failing), "x/y", who="t") is None
    ok = RuleExecutor(present={"pass"}, rules=[(("show",), Result(0, "s3cret\nuser: me\n"))])
    assert pass_show(Ctx(os=FEDORA, ex=ok), "x/y", who="t") == "s3cret\nuser: me\n"
    assert ok.calls == [["pass", "show", "x/y"]]


def test_pass_fields_parses_key_value_lines() -> None:
    assert pass_fields("tok\ntoken: T1\nChat_ID:  C1 \nnoise\n") == {"token": "T1", "chat_id": "C1"}
```

Append to `tests/modules/test_herdr.py`:

```python
def test_herdr_plugins_reads_telegram_from_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DEVBOOST_HERDR_TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("DEVBOOST_HERDR_TELEGRAM_CHAT_ID", raising=False)
    cfg_dir = tmp_path / "cfg"
    ctx = _ctx(present={"pass"}, scripts={
        "herdr": Result(0, stdout=str(cfg_dir)),
        "pass": Result(0, stdout="telegram\ntoken: P-TOKEN\nchat_id: P-CHAT\n"),
    })
    HerdrPlugins()._configure_notify(ctx)
    text = (cfg_dir / ".env").read_text(encoding="utf-8")
    assert "TELEGRAM_BOT_TOKEN=P-TOKEN" in text and "TELEGRAM_CHAT_ID=P-CHAT" in text
    assert ["pass", "show", "devboost/herdr-telegram"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_herdr_plugins_orders_after_pass_store() -> None:
    from devboost.modules.pass_store import PassStore

    assert HerdrPlugins.after == (PassStore,)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_pass_store.py tests/modules/test_herdr.py -v`
Expected: FAIL with `ModuleNotFoundError: devboost.modules.pass_store`.

- [ ] **Step 3: Implement**

`modules/_pass.py`:

```python
"""Reading secrets from `pass` without ever failing the run.

Until this device is approved (or when pass is absent), a read simply returns None and the
caller skips that one secret — the spec's "warn + skip, never fail".
"""

from __future__ import annotations

from devboost.core import log
from devboost.model import Ctx


def pass_show(ctx: Ctx, entry: str, *, who: str) -> str | None:
    if not ctx.ex.which("pass"):
        log.warn(f"{who}: pass not installed — skipping {entry}")
        return None
    res = ctx.ex.run(["pass", "show", entry])
    if not res.ok or not res.stdout.strip():
        log.warn(f"{who}: `pass show {entry}` unavailable (missing, or this device is not "
                 "approved yet — see `devboost pass status`) — skipping")
        return None
    return res.stdout


def pass_fields(text: str) -> dict[str, str]:
    """`key: value` lines of a pass entry (the first line, the password, is not a field)."""
    out: dict[str, str] = {}
    for line in text.splitlines()[1:]:
        key, sep, value = line.partition(":")
        if sep and key.strip():
            out[key.strip().lower()] = value.strip()
    return out
```

`modules/pass_store.py`:

```python
"""pass + pass-store — the credential store on every workstation (see docs/pass.md)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar

from devboost.core.osinfo import OsInfo
from devboost.core.registry import register
from devboost.core.userconfig import load_user_config
from devboost.exec.primitives import pkg
from devboost.model import Ctx, Module
from devboost.modules import _credentials as creds_src
from devboost.modules.cli_tools import Git
from devboost.modules.secrets import Secrets
from devboost.passstore import enroll, paths, sync
from devboost.passstore.layout import Store

#: Passphrase cached 8 h since last use, 24 h at most (spec: Linux gpg-agent cache).
AGENT_TTLS: dict[str, str] = {"default-cache-ttl": "28800", "max-cache-ttl": "86400"}


def gnupg_home() -> Path:
    override = os.environ.get("GNUPGHOME")
    return Path(override) if override else Path(os.environ["HOME"]) / ".gnupg"


def agent_settings(os_info: OsInfo) -> dict[str, str]:
    """P2 seam: macOS adds `pinentry-program /opt/homebrew/bin/pinentry-mac` here."""
    return dict(AGENT_TTLS)


def _key(line: str) -> str | None:
    s = line.strip()
    return None if not s or s.startswith("#") else s.split(maxsplit=1)[0]


def ensure_agent_conf(path: Path, settings: Mapping[str, str]) -> bool:
    """Set `key value` lines in gpg-agent.conf, keeping every other line. True if changed."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    out: list[str] = []
    seen: set[str] = set()
    for ln in lines:
        k = _key(ln)
        if k in settings:
            if k not in seen:
                out.append(f"{k} {settings[k]}")
                seen.add(k)
            continue
        out.append(ln)
    out += [f"{k} {v}" for k, v in settings.items() if k not in seen]
    body = "\n".join(out) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == body:
        return False
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return True


def agent_conf_ok(path: Path, settings: Mapping[str, str]) -> bool:
    if not path.exists():
        return False
    have = {_key(ln): ln.split(maxsplit=1)[1].strip()
            for ln in path.read_text(encoding="utf-8").splitlines()
            if _key(ln) and len(ln.split(maxsplit=1)) == 2}
    return all(have.get(k) == v for k, v in settings.items())


@register
class Pass(Module):
    name = "pass"
    category = "base"
    description = "pass password-store CLI + gpg-agent passphrase cache (8 h idle / 24 h max)."
    profiles = ("base",)

    def _conf(self) -> Path:
        return gnupg_home() / "gpg-agent.conf"

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("pass") and agent_conf_ok(self._conf(), agent_settings(ctx.os))

    def install(self, ctx: Ctx) -> None:
        if not ctx.ex.which("pass"):
            pkg.install(ctx, "pass")
        if ensure_agent_conf(self._conf(), agent_settings(ctx.os)):
            ctx.ex.run(["gpgconf", "--reload", "gpg-agent"])


@register
class PassStore(Module):
    name = "pass-store"
    category = "base"
    description = (
        "Shared pass store: clone, enroll/adopt this device's GPG key, push-on-commit + "
        "15-min sync (devboost pass …)."
    )
    requires = (Pass, Secrets, Git)
    profiles = ("base",)
    # macOS scheduling (launchd) lands in P2 — until then the plan drops this module there.
    families: ClassVar[tuple[str, ...]] = ("fedora", "debian", "arch")

    def _store(self) -> Store:
        return Store(paths.store_dir())

    def verify(self, ctx: Ctx) -> bool:
        store = self._store()
        if not store.is_clone():
            return False
        if not (sync.hook_installed(store) and sync.scheduler_installed(ctx)):
            return False
        acc = enroll.local_access(ctx, store, paths.device_name())
        return acc.state == "enrolled" and acc.record is not None

    def install(self, ctx: Ctx) -> None:
        cfg = load_user_config()
        store = self._store()
        enroll.ensure_clone(ctx, store, paths.pass_repo(cfg))
        bin_ = paths.devboost_bin()
        # Sync is wired BEFORE enrollment: a pending device learns of its approval by itself.
        sync.install_hook(store, bin_)
        sync.install_scheduler(ctx, bin_)
        enroll.import_device_keys(ctx, store)
        enroll.ensure_access(ctx, store, paths.device_name(cfg),
                             interactive=creds_src.is_interactive())
```

Note on `test_missing_store_clones_default_repo_or_asks_for_gh`: the fake clone creates nothing, and `gh` is absent from `present`, so `ensure_clone` raises `NeedsUser` before the hook step. That is the intended order.

`modules/optional.py`: delete the `Pass` and `PassStore` classes, then delete the imports that are now unused (`ConfigError`, `Secrets`; keep `os`/`Path`, which `JetbrainsToolbox` uses). Update the module docstring to `"""optional-editors profile (opt-in, off the production path)."""`.

`modules/claude_plugins.py`:
- replace `from devboost.modules.optional import PassStore` with `from devboost.modules.pass_store import PassStore` and add `from devboost.modules._pass import pass_show`;
- change `requires = (ClaudeCode, Dotfiles, Secrets, PassStore)` to `requires = (ClaudeCode, Dotfiles, Secrets)` plus a new line `after = (PassStore,)`. Update the comment above it: `# PassStore is soft (after): the CLICKUP token is skipped until this device is approved.`;
- replace the first eight lines of `_resolve_clickup_token` (from `if not ctx.ex.which("pass"):` through the second `return`) with:

```python
        out = pass_show(ctx, "clickup/api-token", who="claude-plugins")
        token = out.splitlines()[0].strip() if out else ""
        if not token:
            return
```

`modules/codex_config.py`: same import change; `requires = (CodexCode, Dotfiles)` + `after = (PassStore,)`; `_clickup` body becomes:

```python
    def _clickup(self, ctx: Ctx) -> str | None:
        out = pass_show(ctx, "clickup/api-token", who="codex-config")
        token = out.splitlines()[0].strip() if out else ""
        return token or None
```

`modules/pi_harness.py`: `from devboost.modules.pass_store import PassStore`; add `after = (PassStore,)` below `requires`.

`modules/herdr.py` (`HerdrPlugins`): add `from devboost.modules._pass import pass_fields, pass_show` and `from devboost.modules.pass_store import PassStore`; add `after = (PassStore,)` below `requires`; replace the two `os.environ.get(...)` lines at the top of `_configure_notify` with:

```python
        stored = pass_show(ctx, "devboost/herdr-telegram", who="herdr-plugins")
        fields = pass_fields(stored) if stored else {}
        token = fields.get("token") or os.environ.get("DEVBOOST_HERDR_TELEGRAM_TOKEN")
        chat = fields.get("chat_id") or os.environ.get("DEVBOOST_HERDR_TELEGRAM_CHAT_ID")
```

and update its docstring's first line to `Provision the Telegram notify plugin from pass (devboost/herdr-telegram), else env, else skip.`

`profiles.toml`:
- `base = [...]`: append `,"pass","pass-store"` after `"docker-build-gc"`;
- change the `security-cli` line to `security-cli     = ["pass","pass-store"]   # alias — both now ship in base`;
- in the header comment of `full`, delete `security-cli` from the excluded list (`(gnome-aesthetics, gnome-theme, hardware-nvidia, optional-editors, optional-agents)`).

`tests/modules/test_optional_ubuntu.py`: delete everything from the `# Pass` section banner through `test_pass_store_raises_when_pass_init_fails` (these behaviours now live in `test_pass_store.py`; the `DEVBOOST_PASS_GPG_ID` path is removed by D3). Change the import to `from devboost.modules.optional import JetbrainsToolbox, Neovim`, and remove imports ruff reports as unused (F401).

- [ ] **Step 4: Run to verify pass (and no regression)**

Run: `uv run pytest tests/modules tests/core tests/cli -v && uv run mypy && uv run ruff check`
Expected: PASS. `test_claude_plugins.py` and `test_codex_config.py` pass unchanged: `pass_show` keeps their contract (the `which("pass")` gate, then `pass show clickup/api-token`, first line = token).

- [ ] **Step 5: Commit**

```bash
git add ../profiles.toml src/devboost/modules/pass_store.py src/devboost/modules/_pass.py src/devboost/modules/optional.py src/devboost/modules/claude_plugins.py src/devboost/modules/codex_config.py src/devboost/modules/pi_harness.py src/devboost/modules/herdr.py tests/modules/test_pass_store.py tests/modules/test_herdr.py tests/modules/test_optional_ubuntu.py
git commit -m "feat(pass): pass + pass-store in base; readers order after it and degrade gracefully"
```

---

### Task 11: `devboost pass` CLI sub-app

**Files:**
- Create: `engine/src/devboost/cli/pass_cmd.py`
- Modify: `engine/src/devboost/cli/app.py` (register the sub-app next to `accounts`)
- Test: `engine/tests/cli/test_pass_cli.py` (create)

**Interfaces:**
- Consumes: `enroll`, `approve`, `sync`, `paths`, `Store` (Tasks 3–9).
- Produces: `devboost pass status | devices | approve [NAME] [--scope F]… | revoke NAME | sync [--resolve] [--quiet] | enroll [--name N] [--scope F]…`. There is also a hidden `sync --push-only`, which the git hook uses. `pass_cmd._ctx() -> Ctx` is the test seam. Exit code 1 on a `DevbootError`, or when sync ends in `conflict`/`pull-failed`/`push-failed`/`no-store`. `enroll` exits 0 with the next step when it ends in `NeedsUser`.

- [ ] **Step 1: Write the failing tests**: `tests/cli/test_pass_cli.py`

```python
from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from devboost.cli import pass_cmd
from devboost.cli.app import app
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.passstore.layout import DeviceRecord, Store
from tests.passstore.fakes import RuleExecutor, colons

FEDORA = OsInfo("fedora", "fedora", "x86_64")
FP_ME = "A" * 40
FP_NEW = "B" * 40
ARMOR = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nx\n"
runner = CliRunner()


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Store:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("PASSWORD_STORE_DIR", str(tmp_path / "store"))
    cfg = tmp_path / "cfg" / "devboost" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('device_name = "desk"\n', encoding="utf-8")
    root = tmp_path / "store"
    (root / ".git").mkdir(parents=True)
    (root / ".gpg-id").write_text(FP_ME + "\n", encoding="utf-8")
    s = Store(root)
    s.write_record("devices", DeviceRecord(name="desk", fingerprint=FP_ME, os="fedora"), ARMOR)
    return s


def _use(monkeypatch: pytest.MonkeyPatch, *extra: tuple[tuple[str, ...], Result]) -> RuleExecutor:
    ex = RuleExecutor(rules=[
        *extra,
        (("--list-secret-keys",), Result(0, colons("sec", FP_ME))),
        (("--show-keys",), Result(0, colons("pub", FP_NEW))),
        (("diff", "--cached"), Result(1)),
        (("rev-parse", "HEAD"), Result(0, "abc\n")),
    ])
    monkeypatch.setattr(pass_cmd, "_ctx", lambda: Ctx(os=FEDORA, ex=ex))
    return ex


def test_pass_subapp_is_registered() -> None:
    out = runner.invoke(app, ["pass", "--help"]).output
    for verb in ("status", "devices", "approve", "revoke", "sync", "enroll"):
        assert verb in out


def test_status_reports_enrollment(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch)
    res = runner.invoke(app, ["pass", "status"])
    assert res.exit_code == 0, res.output
    assert "desk (enrolled)" in res.output and FP_ME in res.output


def test_devices_lists_enrolled_and_pending(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    store.write_record("pending", DeviceRecord(name="lap", fingerprint=FP_NEW, os="ubuntu"), ARMOR)
    _use(monkeypatch)
    res = runner.invoke(app, ["pass", "devices"])
    assert "desk" in res.output and "lap" in res.output and "pending" in res.output


def test_approve_requires_typed_y(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    store.write_record("pending", DeviceRecord(name="lap", fingerprint=FP_NEW, os="ubuntu"), ARMOR)
    ex = _use(monkeypatch)
    res = runner.invoke(app, ["pass", "approve", "lap"], input="n\n")
    assert "nothing approved" in res.output and store.record("pending", "lap") is not None
    res = runner.invoke(app, ["pass", "approve", "lap"], input="y\n")
    assert res.exit_code == 0, res.output
    assert FP_NEW in res.output and "approved lap" in res.output
    assert ["pass", "init", FP_ME, FP_NEW] in ex.calls


def test_approve_error_exits_1(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch)
    res = runner.invoke(app, ["pass", "approve", "ghost"], input="y\n")
    assert res.exit_code == 1


def test_revoke_prints_rotation_checklist(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    (store.root / ".gpg-id").write_text(f"{FP_ME}\n{FP_NEW}\n", encoding="utf-8")
    store.write_record("devices", DeviceRecord(name="lap", fingerprint=FP_NEW, os="fedora"), ARMOR)
    _use(monkeypatch, ((f"-S{FP_NEW}",), Result(0, "c1\n")),
         (("ls-tree",), Result(0, "web/a.gpg\n")))
    res = runner.invoke(app, ["pass", "revoke", "lap"], input="y\n")
    assert res.exit_code == 0, res.output
    assert "[ ] web/a" in res.output and "devboost doctor" in res.output


def test_sync_resolve_prints_guidance(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch)
    res = runner.invoke(app, ["pass", "sync", "--resolve"])
    assert res.exit_code == 0 and "git rebase --continue" in res.output


def test_sync_conflict_exits_1(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, (("pull",), Result(1)), (("--diff-filter=U",), Result(0, ".gpg-id\n")))
    res = runner.invoke(app, ["pass", "sync", "--quiet"])
    assert res.exit_code == 1 and "conflict" in res.output


def test_enroll_pending_prints_next_step(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    (store.root / ".gpg-id").write_text("C" * 40 + "\n", encoding="utf-8")  # not us
    store.write_record("pending", DeviceRecord(name="desk", fingerprint=FP_ME, os="fedora"), ARMOR)
    (store.root / ".devboost" / "devices" / "desk.json").unlink()
    _use(monkeypatch)
    res = runner.invoke(app, ["pass", "enroll"])
    assert res.exit_code == 0 and "devboost pass approve desk" in res.output
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cli/test_pass_cli.py -v`
Expected: FAIL with `ImportError: cannot import name 'pass_cmd'`.

- [ ] **Step 3: Implement** `cli/pass_cmd.py`

```python
"""The `pass` sub-app: the shared store across devices (status, approve, revoke, sync…)."""

from __future__ import annotations

from typing import Annotated, NoReturn

import typer
from rich.console import Console
from rich.table import Table

from devboost.core import log, osinfo
from devboost.core.errors import DevbootError, NeedsUser
from devboost.exec.executor import RealExecutor
from devboost.model import Ctx
from devboost.passstore import approve as approve_flow
from devboost.passstore import enroll as enroll_flow
from devboost.passstore import paths
from devboost.passstore import sync as sync_flow
from devboost.passstore.layout import DeviceRecord, Kind, Store

app = typer.Typer(
    help="The shared pass store: devices, enrollment, approval, revocation, sync.",
    no_args_is_help=True,
)

ScopeOpt = Annotated[
    list[str],
    typer.Option("--scope", help="limit access to this store folder (repeatable; servers)"),
]


def _ctx() -> Ctx:
    return Ctx(os=osinfo.detect(), ex=RealExecutor())


def _store() -> Store:
    return Store(paths.store_dir())


def _fail(exc: Exception) -> NoReturn:
    log.error(str(exc))
    raise typer.Exit(1) from exc


def _need_store(store: Store) -> None:
    if not store.is_clone():
        log.error(f"no pass store at {store.root} — run: devboost install pass-store")
        raise typer.Exit(1)


def _describe(rec: DeviceRecord) -> str:
    scope = ", ".join(rec.scope) if rec.scope else "whole store (workstation)"
    return (f"  name:        {rec.name}\n  os:          {rec.os}\n"
            f"  fingerprint: {rec.fingerprint}\n"
            f"  requested:   {rec.requested_at or rec.enrolled_at or '-'}\n  scope:       {scope}")


def _ask(verb: str) -> approve_flow.Confirm:
    def confirm(rec: DeviceRecord) -> bool:
        typer.echo(f"{verb} this device?\n{_describe(rec)}")
        answer = str(typer.prompt("Type y to confirm", default="n", show_default=False))
        return answer.strip().lower() == "y"

    return confirm


@app.command()
def status() -> None:
    """This device's enrollment, pending requests, rotation backlog and last sync."""
    ctx, store = _ctx(), _store()
    _need_store(store)
    device = paths.device_name()
    acc = enroll_flow.local_access(ctx, store, device)
    name = acc.record.name if acc.record else device
    typer.echo(f"repo:      {paths.pass_repo()}")
    typer.echo(f"store:     {store.root}")
    typer.echo(f"device:    {name} ({acc.state})")
    typer.echo(f"key:       {acc.key.fingerprint if acc.key else '-'}")
    typer.echo(f"pending:   {len(store.records('pending'))}")
    typer.echo(f"rotation:  {len(approve_flow.unrotated(ctx, store))} entries to rotate")
    typer.echo(f"last sync: {sync_flow.last_sync() or 'never'}")


@app.command()
def devices() -> None:
    """Enrolled devices and pending requests."""
    store = _store()
    _need_store(store)
    table = Table("name", "state", "os", "fingerprint", "scope", "since")
    rows: tuple[tuple[Kind, str], ...] = (("devices", "enrolled"), ("pending", "pending"))
    for kind, label in rows:
        for r in store.records(kind):
            table.add_row(r.name, label, r.os, r.fingerprint,
                          ", ".join(r.scope) if r.scope else "-",
                          r.enrolled_at or r.requested_at or "-")
    Console(width=200).print(table)


@app.command(name="approve")
def approve_cmd(
    name: Annotated[str | None, typer.Argument(help="pending device (default: each)")] = None,
    scope: ScopeOpt = [],  # noqa: B006
) -> None:
    """Grant a pending device access (typed confirmation; re-encrypts the store)."""
    ctx, store = _ctx(), _store()
    _need_store(store)
    try:
        done = approve_flow.approve(ctx, store, paths.device_name(), name, _ask("Approve"),
                                    scope_override=scope or None)
    except DevbootError as exc:
        _fail(exc)
    if not done:
        typer.echo("nothing approved")
        return
    for a in done:
        typer.echo(f"approved {a.name} — it gets access on its next sync")


@app.command(name="revoke")
def revoke_cmd(name: Annotated[str, typer.Argument(help="enrolled device to revoke")]) -> None:
    """Remove a device's access and print what must now be rotated."""
    ctx, store = _ctx(), _store()
    _need_store(store)
    try:
        entry = approve_flow.revoke(ctx, store, paths.device_name(), name, _ask("REVOKE"))
    except DevbootError as exc:
        _fail(exc)
    if entry is None:
        typer.echo("revoke cancelled")
        return
    typer.echo(f"revoked {name}. Git history still holds ciphertexts its key can read — "
               f"rotate these {len(entry.entries)} entries (pass edit <entry>):")
    for e in entry.entries:
        typer.echo(f"  [ ] {e}")
    typer.echo("`devboost doctor` tracks what is left.")


@app.command(name="sync")
def sync_cmd(
    resolve: Annotated[bool, typer.Option("--resolve", help="explain how to fix a conflict")] = False,
    push_only: Annotated[bool, typer.Option("--push-only", hidden=True)] = False,
    quiet: Annotated[bool, typer.Option("--quiet", help="print only problems")] = False,
) -> None:
    """Pull + push the store now (the timer does this every 15 min)."""
    ctx, store = _ctx(), _store()
    if resolve:
        _need_store(store)
        typer.echo(sync_flow.resolve_guidance(ctx, store))
        return
    res = sync_flow.run(ctx, store, paths.device_name(), push_only=push_only)
    problem = res.status in ("conflict", "pull-failed", "push-failed", "no-store")
    if problem or not quiet:
        typer.echo(f"pass sync: {res.status}" + (f" — {res.detail}" if res.detail else ""))
    if problem:
        raise typer.Exit(1)


@app.command(name="enroll")
def enroll_cmd(
    name: Annotated[str | None, typer.Option("--name", help="device name (default: host)")] = None,
    scope: ScopeOpt = [],  # noqa: B006
) -> None:
    """Request access for this device (generates its key; passphrase via pinentry)."""
    ctx, store = _ctx(), _store()
    try:
        device = paths.sanitize_name(name) if name else paths.device_name()
        enroll_flow.ensure_clone(ctx, store, paths.pass_repo())
        acc = enroll_flow.ensure_access(ctx, store, device, interactive=True,
                                        scope=scope or None)
    except NeedsUser as exc:
        typer.echo(f"{exc.reason}\nnext: {exc.how_to_fix}")
        return
    except (DevbootError, ValueError) as exc:
        _fail(exc)
    typer.echo(f"this device is enrolled as {acc.record.name if acc.record else device}")
```

`cli/app.py`: next to `from devboost.cli import accounts as _accounts` add `from devboost.cli import pass_cmd as _pass`, and below `app.add_typer(_accounts.app, name="accounts")` add:

```python
app.add_typer(_pass.app, name="pass")
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/cli -v && uv run mypy && uv run ruff check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/cli/pass_cmd.py src/devboost/cli/app.py tests/cli/test_pass_cli.py
git commit -m "feat(cli): devboost pass — status, devices, approve, revoke, sync, enroll"
```

---

### Task 12: `doctor`: enrollment status and rotation backlog

**Files:**
- Modify: `engine/src/devboost/cli/doctor.py` (replace the `pass-config` block)
- Modify: `engine/tests/cli/test_doctor_resources.py` (replace the two `pass-config` tests; add a hermetic autouse fixture)

**Interfaces:**
- Consumes: `enroll.local_access`, `approve.unrotated`, `paths`, `Store`.
- Produces: `doctor._pass_checks(ctx: Ctx) -> list[Check]`. It returns `Check("pass", True, <state>)`, which is always informational, and, when a store exists, `Check("pass-rotation", <no unrotated entries>, <list>)`. That check **fails** `doctor` while any entry still needs rotation.

- [ ] **Step 1: Write the failing tests**: in `tests/cli/test_doctor_resources.py`, delete `test_doctor_pass_config_check_warns_when_unset` and `test_doctor_pass_config_reports_repo_when_set`, then add:

```python
from devboost.passstore.layout import RotationEntry, Store


@pytest.fixture(autouse=True)
def _hermetic_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let doctor look at the developer's real ~/.password-store."""
    monkeypatch.setenv("PASSWORD_STORE_DIR", str(tmp_path / "pass-store"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


def _pass_store(tmp_path: Path) -> Store:
    root = tmp_path / "pass-store"
    (root / ".git").mkdir(parents=True)
    (root / ".gpg-id").write_text("A" * 40 + "\n", encoding="utf-8")
    (root / "web").mkdir()
    (root / "web" / "github.gpg").write_text("x", encoding="utf-8")
    return Store(root)


def _checks(tmp_path: Path, ex: FakeExecutor) -> dict[str, tuple[bool, str]]:
    (tmp_path / "profiles.toml").write_text("[profiles]\n", encoding="utf-8")
    ctx = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=ex)
    return {c.name: (c.ok, c.detail) for c in run_checks(ctx, tmp_path)}


def test_doctor_pass_without_store_is_informational(tmp_path: Path) -> None:
    out = _checks(tmp_path, FakeExecutor(present={"curl", "age"}))
    assert out["pass"][0] is True and "no store" in out["pass"][1]
    assert "pass-rotation" not in out


def test_doctor_fails_while_entries_await_rotation(tmp_path: Path) -> None:
    s = _pass_store(tmp_path)
    s.write_rotation([RotationEntry(device="lap", fingerprint="B" * 40, revoked_at="t",
                                    after="abc", entries=["web/github"])])
    out = _checks(tmp_path, FakeExecutor(present={"curl", "age"}))  # git log → no commits
    assert out["pass-rotation"][0] is False and "web/github (lap)" in out["pass-rotation"][1]
    assert "not enrolled" in out["pass"][1]


def test_doctor_rotation_clears_after_edit(tmp_path: Path) -> None:
    s = _pass_store(tmp_path)
    s.write_rotation([RotationEntry(device="lap", fingerprint="B" * 40, revoked_at="t",
                                    after="abc", entries=["web/github"])])
    ex = FakeExecutor(present={"curl", "age"},
                      scripts={"git": Result(0, "Edit password for web/github using vim.\n")})
    assert _checks(tmp_path, ex)["pass-rotation"][0] is True
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cli/test_doctor_resources.py -v`
Expected: FAIL with `KeyError: 'pass'`.

- [ ] **Step 3: Implement**: in `cli/doctor.py`, remove the whole `# pass-config: …` block (the comment, the `if/elif/else`, and the `checks.append(Check("pass-config", …))`), and in its place add:

```python
    checks.extend(_pass_checks(ctx))
```

Add the imports:

```python
from devboost.passstore import approve as pass_approve
from devboost.passstore import enroll as pass_enroll
from devboost.passstore import paths as pass_paths
from devboost.passstore.layout import Store
```

and the helper below `run_checks`:

```python
def _pass_checks(ctx: Ctx) -> list[Check]:
    """pass: enrollment state (informational) + rotation backlog after a revoke (blocking)."""
    store = Store(pass_paths.store_dir())
    if not store.is_clone():
        return [Check("pass", True, f"no store at {store.root} yet — `devboost install` "
                                    f"clones {pass_paths.pass_repo()}")]
    device = pass_paths.device_name()
    acc = pass_enroll.local_access(ctx, store, device)
    name = acc.record.name if acc.record else device
    state = {
        "enrolled": f"{name} is enrolled",
        "pending": f"{name} is waiting for approval — on an enrolled device: "
                   f"devboost pass approve {name}",
        "new": "this device is not enrolled — run `devboost pass enroll`",
        "genesis": "the store is empty — run `devboost pass enroll` to initialise it",
        "no-store": "no store",
    }[acc.state]
    todo = pass_approve.unrotated(ctx, store)
    rot = ("nothing awaiting rotation" if not todo else
           f"{len(todo)} entries are still readable by a revoked device's key (git history) "
           "— rotate each with `pass edit <entry>`: "
           + ", ".join(f"{u.entry} ({u.device})" for u in todo))
    return [Check("pass", True, state), Check("pass-rotation", not todo, rot)]
```

Also delete the now-unused `os` import if ruff reports it (it is still used by `pi-login`, so it most likely stays).

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/cli -v && uv run mypy && uv run ruff check`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/cli/doctor.py tests/cli/test_doctor_resources.py
git commit -m "feat(doctor): pass enrollment state and post-revoke rotation backlog"
```

---

### Task 13: real-gpg end-to-end test + CI

**Files:**
- Create: `engine/tests/passstore/test_integration_gpg.py`
- Modify: `.github/workflows/ci.yml` (install `pass` in the `engine` job)

**Interfaces:**
- Consumes: `enroll.ensure_clone`, `enroll.ensure_access(…, passphrase="")`, `enroll.local_access`, `approve.approve`, `approve.revoke`, `approve.unrotated`, `git.pull`, `git.push`.
- Produces: nothing new. This task proves the spec's test list with real `gpg`, `pass` and `git`: approve re-encrypts to N+1 keys and the new key decrypts; scoped approve limits folders; revoke removes access to new entries and builds the rotation list from history; rotation clears on edit.

- [ ] **Step 1: Write the test**: `tests/passstore/test_integration_gpg.py`

```python
"""End to end with real gpg + pass + git: genesis → enroll → approve → decrypt → revoke.

Each simulated device has its own HOME (git identity) and GNUPGHOME. GNUPGHOMEs are short
/tmp paths (the gpg-agent socket path is length-limited) and their agents are killed on
teardown. Keys are passphrase-less via loopback — tests only.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from devboost.core.errors import NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import RealExecutor, Result
from devboost.model import Ctx
from devboost.passstore import approve, enroll, git
from devboost.passstore.layout import Store

pytestmark = pytest.mark.skipif(
    not all(shutil.which(t) for t in ("gpg", "pass", "git")), reason="needs gpg, pass and git"
)
FEDORA = OsInfo("fedora", "fedora", "x86_64")


class _DeviceEx(RealExecutor):
    """One simulated device: its own HOME + GNUPGHOME; never hands over the tty."""

    def __init__(self, home: Path, gnupg: Path) -> None:
        self.home = home
        self.gnupg = gnupg

    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        interactive: bool = False,
    ) -> Result:
        merged = {"HOME": str(self.home), "GNUPGHOME": str(self.gnupg), **(env or {})}
        return super().run(argv, sudo=sudo, stdin=stdin, env=merged, cwd=cwd, interactive=False)


@dataclass
class Device:
    name: str
    ctx: Ctx
    store: Store

    def pass_(self, *args: str, stdin: str | None = None) -> Result:
        return self.ctx.ex.run(["pass", *args], stdin=stdin,
                               env={"PASSWORD_STORE_DIR": str(self.store.root)})


MakeDevice = Callable[[str], Device]


@pytest.fixture
def make_device(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[MakeDevice]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.delenv("DEVBOOST_NTFY_URL", raising=False)
    gnupg_dirs: list[Path] = []

    def make(name: str) -> Device:
        home = tmp_path / f"home-{name}"
        home.mkdir()
        (home / ".gitconfig").write_text(
            f"[user]\n\tname = {name}\n\temail = {name}@example.com\n"
            "[init]\n\tdefaultBranch = main\n",
            encoding="utf-8",
        )
        gnupg = Path(tempfile.mkdtemp(prefix="dbg", dir="/tmp"))
        gnupg.chmod(0o700)
        gnupg_dirs.append(gnupg)
        return Device(name, Ctx(os=FEDORA, ex=_DeviceEx(home, gnupg)),
                      Store(tmp_path / f"store-{name}"))

    yield make
    for g in gnupg_dirs:
        subprocess.run(["gpgconf", "--homedir", str(g), "--kill", "gpg-agent"], check=False)
        shutil.rmtree(g, ignore_errors=True)


@pytest.fixture
def origin(tmp_path: Path) -> str:
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--quiet", "--bare", "-b", "main", str(bare)], check=True)
    return str(bare)


def _genesis(origin: str, make_device: MakeDevice) -> Device:
    a = make_device("alpha")
    enroll.ensure_clone(a.ctx, a.store, origin)
    acc = enroll.ensure_access(a.ctx, a.store, "alpha", interactive=True, passphrase="")
    assert acc.state == "enrolled" and acc.record is not None
    for entry, secret in (("web/github", "gh-secret"), ("harness/tg", "t\ntoken: T\nchat_id: C")):
        assert a.pass_("insert", "-m", entry, stdin=secret + "\n").ok
    assert git.push(a.ctx, a.store.root).ok
    return a


def _request(dev: Device, origin: str, scope: list[str] | None = None) -> None:
    enroll.ensure_clone(dev.ctx, dev.store, origin)
    with pytest.raises(NeedsUser) as err:
        enroll.ensure_access(dev.ctx, dev.store, dev.name, interactive=True, scope=scope,
                             passphrase="")
    assert err.value.how_to_fix == f"devboost pass approve {dev.name}"


def test_enroll_approve_decrypt_revoke_rotate(origin: str, make_device: MakeDevice) -> None:
    a = _genesis(origin, make_device)
    b = make_device("bravo")
    _request(b, origin)
    assert enroll.local_access(b.ctx, b.store, "bravo").state == "pending"
    assert not b.pass_("show", "web/github").ok  # no access before approval

    done = approve.approve(a.ctx, a.store, "alpha", "bravo", lambda r: True)
    assert done == [approve.Approved("bravo", None)]
    assert len(a.store.gpg_ids()) == 2  # N+1

    assert git.pull(b.ctx, b.store.root).ok
    assert enroll.local_access(b.ctx, b.store, "bravo").state == "enrolled"
    assert b.pass_("show", "web/github").stdout.strip() == "gh-secret"

    entry = approve.revoke(a.ctx, a.store, "alpha", "bravo", lambda r: True)
    assert entry is not None and {"web/github", "harness/tg"} <= set(entry.entries)
    assert a.store.record("revoked", "bravo") is not None

    assert a.pass_("insert", "-m", "web/new", stdin="fresh\n").ok
    assert git.push(a.ctx, a.store.root).ok
    assert git.pull(b.ctx, b.store.root).ok
    assert not b.pass_("show", "web/new").ok  # revoked key cannot read new entries

    assert "web/github" in {u.entry for u in approve.unrotated(a.ctx, a.store)}
    assert a.pass_("insert", "-f", "-m", "web/github", stdin="rotated\n").ok
    assert "web/github" not in {u.entry for u in approve.unrotated(a.ctx, a.store)}


def test_scoped_server_reads_only_its_folder(origin: str, make_device: MakeDevice) -> None:
    a = _genesis(origin, make_device)
    srv = make_device("srv")
    _request(srv, origin, scope=["harness"])

    done = approve.approve(a.ctx, a.store, "alpha", "srv", lambda r: True)
    assert done == [approve.Approved("srv", ["harness"])]
    assert len(a.store.gpg_ids()) == 1 and len(a.store.gpg_ids("harness")) == 2

    assert git.pull(srv.ctx, srv.store.root).ok
    assert enroll.local_access(srv.ctx, srv.store, "srv").state == "enrolled"
    assert "chat_id: C" in srv.pass_("show", "harness/tg").stdout
    assert not srv.pass_("show", "web/github").ok
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/passstore/test_integration_gpg.py -v`
Expected: PASS where `gpg`, `pass` and `git` exist, or `2 skipped` otherwise (e.g. a Mac without `brew install gnupg pass`). This test exercises code from Tasks 3–9 that is already written, so it is a verification step rather than red→green. If it fails, fix the library code in the task that owns it. Do not weaken the test.

- [ ] **Step 3: Run it in CI**: `.github/workflows/ci.yml`, `engine` job, insert before `- run: uv sync`:

```yaml
      - name: pass + gpg for the pass integration test
        run: sudo apt-get update && sudo apt-get install -y pass
```

- [ ] **Step 4: Full gate**

Run: `uv run ruff check && uv run mypy && uv run pytest`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add tests/passstore/test_integration_gpg.py ../.github/workflows/ci.yml
git commit -m "test(passstore): real gpg/pass end-to-end — approve, scoped access, revoke, rotation"
```

---

### Task 14: documentation

**Files:**
- Create: `docs/pass.md`
- Modify: `docs/credentials.md`, `docs/recovery-runbook.md`, `docs/agents.md`, `docs/architecture.md`, `docs/adding-a-module.md`, `README.md`, `docs/superpowers/specs/2026-09-18-pass-multi-device-design.md`

**Interfaces:** none (docs only). All commands in this task run from the repo root.

- [ ] **Step 1: Write `docs/pass.md`**

````markdown
# pass across devices

`pass` is the credential store on every workstation (it ships in `base`). One private GitHub
repo — `adams100111/password-store` by default — is shared by all devices. Each device has
**its own GPG key**, credentials added anywhere reach every other device automatically, and
adding or removing a device is one explicit command.

## Model

- **Per-device keys.** Each device generates an ed25519 key (`cv25519` encryption subkey,
  no expiry) whose uid is tagged `(devboost:<device>)`. The private key never leaves it.
- **Root `.gpg-id`** lists every workstation key, so every entry is encrypted to all of them.
- **`.devboost/`** in the store holds only public keys and metadata:
  `devices/`, `pending/`, `revoked/` (`<name>.json` + `<name>.asc`) and `rotation.json`.
- **Passphrase:** asked by pinentry, then cached by gpg-agent for 8 h idle / 24 h max
  (`~/.gnupg/gpg-agent.conf`, set by the `pass` module).

Choose the repo in `~/.config/devboost/config.toml` (`DEVBOOST_PASS_REPO` overrides):

```toml
pass_repo = "you/password-store"   # owner/repo on GitHub, or any git URL
device_name = "work-laptop"        # optional; default is the short hostname
```

The clone uses the GitHub access `secrets` set up (gh or the provisioned token). With
neither, `pass-store` reports `blocked` and asks for `gh auth login`.

## Add a device: enroll → approve → sync

1. On the new device: `devboost install` (or `devboost pass enroll` in a terminal).
   It clones the store, generates the key (you choose the passphrase), and pushes a
   request under `.devboost/pending/`. `pass-store` shows `blocked` with the next step;
   modules that read secrets from pass skip them for now — nothing fails.
   Unattended runs never generate a key: they tell you to run `devboost pass enroll`.
2. On any enrolled workstation: `devboost pass approve <name>`. Check the **full
   fingerprint** against the new device's `devboost pass status`, then type `y`. The store
   is re-encrypted to the new key and pushed. (With `DEVBOOST_NTFY_URL` set, the request
   pings your phone; enrolled desktops also show a notification on their next sync.)
3. The new device's sync timer pulls within 15 minutes (or run `devboost pass sync`);
   the next `devboost install` finds access and finishes the secret-reading modules.

Devices that already hold a key listed in `.gpg-id` are **adopted** on their first run —
registered under `.devboost/devices/` with no approval, because they already have access.
An empty store is initialised by its first device.

## Sync

- A `post-commit` hook in the store pushes every commit (`pass insert`, `edit`, …)
  in the background.
- `devboost-pass-sync.timer` (systemd user timer) pulls with `--rebase --autostash`
  every 15 minutes, pushes anything unpushed, imports newly enrolled device keys, and
  notifies once per pending request.
- Failures are logged to `~/.local/state/devboost/pass-sync.log` and notified; they never
  block anything else. A conflict in `.gpg-id` aborts the rebase — run
  `devboost pass sync --resolve` for the exact recovery steps.

## Revoke a device + rotate

`devboost pass revoke <name>` (from another enrolled workstation) removes the key from
every `.gpg-id`, re-encrypts, moves the device to `.devboost/revoked/`, and writes
`rotation.json`. **Git history still holds old ciphertexts the revoked key can decrypt**,
so every entry it could ever read must be changed at its source and updated with
`pass edit <entry>` (or `pass insert -f`). `devboost doctor` fails its `pass-rotation`
check until each one is done.

## Servers (scoped access)

Servers are not enrolled by default. To give one access to a single folder:
`devboost pass enroll --scope harness` on the server, then
`devboost pass approve <server>` on a workstation (`--scope` there overrides). Only that
folder gets its own `.gpg-id` (workstations + the server); everything else stays
unreadable to it.

## Commands

| Command | Does |
|---|---|
| `devboost pass status` | this device's state, key, pending requests, rotation backlog, last sync |
| `devboost pass devices` | enrolled devices and pending requests |
| `devboost pass enroll [--name N] [--scope F]…` | request access for this device |
| `devboost pass approve [NAME] [--scope F]…` | approve pending requests (typed `y`) |
| `devboost pass revoke NAME` | revoke a device and print the rotation checklist |
| `devboost pass sync [--resolve]` | sync now / explain a conflict |

## If every device is lost

The store is only as recoverable as one private key. Keep an **offline backup of one
device key** (`gpg --export-secret-keys --armor <fingerprint>` to an encrypted USB or
paper). Restore it on a new machine with `gpg --import`, run `devboost install` — it is
adopted — then revoke the lost devices.
````

- [ ] **Step 2: Update the other docs**

`docs/credentials.md`: append this section at the end:

```markdown
## Which tool holds what

| Secret | Lives in | Why |
|---|---|---|
| GitHub access (git over HTTPS, API) | `gh` (or the provisioned PAT) | first thing a box needs; `gh auth login` is the fallback |
| Every other credential (API tokens, bot tokens, …) | `pass` — see [pass.md](pass.md) | per-device keys, auto-sync, revocable |
| Bootstrap-only values (`GIT_USER`, `GIT_EMAIL`, `GITHUB_PAT`) | the `age` bundle | zero-touch installs before anything else exists |

The age bundle never carries a GPG key: each device makes its own and is approved from
another device.
```

`docs/recovery-runbook.md`: append:

```markdown
## Lost (or stolen) a laptop
1. On any other enrolled workstation: `devboost pass revoke <laptop>` — removes its key
   and re-encrypts the store.
2. Rotate every entry it printed (change the secret at its source, then `pass edit
   <entry>`); `devboost doctor` lists what is left until all are done.
3. Revoke its GitHub access too (`gh auth` token / SSH key in GitHub settings).
Lost **every** device? Restore your offline key backup — see [pass.md](pass.md#if-every-device-is-lost).
```

`docs/agents.md`:
- in the Claude / Codex paragraph, replace `set \`DEVBOOST_PASS_REPO\` (see the security-cli profile)` with `every workstation has it (\`base\`); see [pass.md](pass.md)`;
- in the env table, change the `DEVBOOST_PASS_REPO` row to `| \`DEVBOOST_PASS_REPO\` | \`pass-store\` | \`adams100111/password-store\` | overrides \`pass_repo\` in \`~/.config/devboost/config.toml\` |`;
- delete the `DEVBOOST_PASS_GPG_ID` row;
- extend the `DEVBOOST_NTFY_URL` row's module column to `claude-notify\`, \`pass-store\``.

`docs/architecture.md`:
- under Layout, add the bullet `- **\`passstore/\`** — the pass multi-device domain (paths, gpg, store layout, git, notify, enroll/approve/revoke, sync). Library code only; the \`pass\`/\`pass-store\` modules and \`cli/pass_cmd.py\` (\`devboost pass\`) call into it.`;
- in the `cli/` bullet, add `pass` to the command list.

`docs/adding-a-module.md`: below the `requires = ()` line of the example, add `    after = ()                    # ordering only: run after these IF they are in the plan; never pulls them in, never blocked by them`. Below the paragraph about `requires = (Docker,)`, add: `Use \`after\` for a soft input the module can do without — e.g. \`claude-plugins\` reads a token from \`pass\` and runs \`after = (PassStore,)\`, so a device awaiting approval still installs Claude and just skips the token.`

`README.md`:
- profile table: append `, \`pass\`, \`pass-store\`` to the `base` row; change the `security-cli` row to `| \`security-cli\` | \`pass\`, \`pass-store\` (alias — both are in \`base\`) |`;
- module table: `| \`pass\` | base | pass password-store CLI + gpg-agent passphrase cache (8 h idle / 24 h max). |` and `| \`pass-store\` | base | Shared pass store: clone, enroll/adopt this device's GPG key, push-on-commit + 15-min sync (devboost pass …). |`;
- in the command list near `devboost accounts`, add `- \`devboost pass\` — the shared pass store: \`status\`, \`devices\`, \`enroll\`, \`approve\`, \`revoke\`, \`sync\` ([docs/pass.md](docs/pass.md)).`

Spec (`docs/superpowers/specs/2026-09-18-pass-multi-device-design.md`): in the Rollout table's P1 row, append to Notes: `— plan: [2026-09-19-pass-p1-linux](../plans/2026-09-19-pass-p1-linux.md)`.

- [ ] **Step 3: Check that links resolve and that nothing still references removed behaviour**

Run (repo root): `grep -rn "DEVBOOST_PASS_GPG_ID\|pass-config" docs README.md engine/src engine/tests | grep -v superpowers`
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add docs/pass.md docs/credentials.md docs/recovery-runbook.md docs/agents.md docs/architecture.md docs/adding-a-module.md README.md docs/superpowers/specs/2026-09-18-pass-multi-device-design.md
git commit -m "docs(pass): multi-device model, enroll/approve/sync, revoke + rotation, recovery"
```

---

## Spec coverage

| Spec item | Task |
|---|---|
| `pass` + `pass-store` → `base` | 10 |
| Default `pass_repo` in `config.toml`, env override | 2, 3 |
| Clone over HTTPS with GitHub auth; gh missing → `NeedsUser` | 7 (D2) |
| Per-device ed25519 key + cv25519 subkey, pinentry passphrase | 4 |
| gpg-agent 8 h / 24 h cache (Linux) | 10 |
| Enroll: pending files, commit, push, notify, `blocked (NeedsUser)` with approve command | 7 |
| Name = short hostname, `--name`, collisions refused | 3, 7, 11 |
| Approve: pull, full fingerprint, typed `y`, import + ownertrust, `pass init` N+1, scoped `-p` per folder, move to `devices/`, commit, push; key-file mismatch refused | 8, 11 |
| New device verifies it can decrypt and clears blocked | 7 (`local_access`), 10 (`verify`), 13 |
| Revoke: remove from every `.gpg-id`, re-encrypt, move to `revoked/`, `rotation.json` from history, checklist | 8, 11 |
| `doctor` lists unrotated entries; edit/insert clears | 8 (D8), 12 |
| Adopt existing devices without approval | 7 |
| Post-commit hook push; 15-min systemd user timer pull + push | 9, 10 |
| Pending → notify once per request | 9 |
| `.gpg-id` conflict aborts + notifies; `sync --resolve` guides | 9, 11 |
| Dependent modules warn + skip until approved | 1, 10 |
| `devboost pass status/devices/approve/revoke/sync/enroll` | 11 |
| `herdr-plugins` Telegram from `pass show devboost/herdr-telegram`, env fallback, else skip | 10 |
| Push/pull failures logged + notified, never blocking | 9 |
| Tests: fake + real-gpg fixture (enroll, approve N+1 decrypt, scoped, revoke + rotation, adopt, hook/timer, dedup) | 4–13 |
| Docs: `pass.md`, `credentials.md`, `recovery-runbook.md`, README | 14 |
| P2 seams (macOS): `notify._native_argv`, `sync.install_scheduler`, `pass_store.agent_settings`, `PassStore.families` | 6, 9, 10 |
