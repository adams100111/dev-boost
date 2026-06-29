# `accounts` Sandbox-User Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A standalone `accounts` CLI that creates and manages self-contained, resource-capped Linux users ("sandbox users") on Fedora and Ubuntu — RAM/CPU/task caps via a systemd slice, best-effort disk quota by filesystem, privilege tiers, clean disable/delete, and optional per-user profile bootstrap.

**Architecture:** A declarative `users.toml` (at `/etc/devboost/users.toml`) is the source of truth, validated by Pydantic into frozen `ManagedUser` dataclasses (the `media/` convention). A new `exec/primitives/usermgmt.py` holds all low-level, idempotent OS operations — every side effect goes through `ctx.ex.run(..., sudo=True)`. `accounts/reconcile.py` orchestrates them to converge one user to its declared state. Profile bootstrap reuses the existing install pipeline through a new `DemotingExecutor` that runs privileged commands as root and unprivileged commands as the target user. The CLI (`cli/accounts.py`) is a Typer sub-app, never a registered `Module`, so it stays out of the declarative install plan.

**Tech Stack:** Python 3.12, Typer, questionary 2.0 (interactive form), Pydantic v2 + `tomli-w` (read/write TOML), Rich (`list` table), pytest with `FakeExecutor`. System tools: `useradd`/`usermod`/`userdel`/`gpasswd`/`chpasswd`/`getent`/`id` (shadow-utils), `systemctl`/`loginctl` (systemd), `visudo` (sudo), `findmnt`/`setquota`/`repquota`/`btrfs` (quotas).

## Global Constraints

- `mypy --strict` + ruff + pytest are merge gates (constitution v3.0.0). Fully typed; no `Any` leakage past Pydantic boundaries.
- **No `subprocess`** anywhere — all OS effects via the `Executor` seam (`ctx.ex.run`). Tests use `FakeExecutor` and assert exact sudo-prefixed argv lists.
- `from __future__ import annotations` at the top of every new module.
- Config path: **`/etc/devboost/users.toml`**, overridable via env **`DEVBOOST_USERS_PATH`** (tests redirect to `tmp_path`).
- **Registry-scoped:** only ever modify users present in `users.toml`. Never touch `root`/`ubuntu`/unmanaged accounts. `create` on an existing-but-unmanaged name refuses unless `--adopt`.
- **Owns only its artifacts:** the admin-group bit, `/etc/sudoers.d/devboost-<user>`, `/etc/systemd/system/user-<uid>.slice.d/50-devboost.conf`, the user's quota/subvolume. Never strips unrelated group membership.
- **Cross-distro branch points (only two):** admin group `wheel` (Fedora) vs `sudo` (Ubuntu), detected via `getent group`; and always pass `useradd -m -s <shell>` (Ubuntu's raw default is no-home + `/bin/sh`).
- **Sudoers safety:** stage → `visudo -cf` → `chmod 0440 root:root` → atomic `mv`; filename must be **dot-free** (sudoers skips names containing `.` or `~`).
- **Failure model:** `useradd`/privilege/slice failures are fatal (raise `AccountsError`); disk-quota and ssh-key issues are non-fatal warnings; reconcile is idempotent (re-run converges); no transactional rollback.
- New dependency: add `tomli-w>=1.0` to `engine/pyproject.toml` `dependencies` (Task 1).

---

### Task 1: Config model — `ManagedUser`, validation, load/save `users.toml`

**Files:**
- Create: `engine/src/devboost/accounts/__init__.py` (empty)
- Create: `engine/src/devboost/accounts/config.py`
- Modify: `engine/pyproject.toml` (add `tomli-w>=1.0`)
- Test: `engine/tests/accounts/test_config.py`

**Interfaces:**
- Produces:
  - `AccountsError(DevbootError)`.
  - `Privilege = Literal["none", "full", "nopasswd", "allowlist"]`.
  - `@dataclass(frozen=True) ManagedUser` with fields: `name: str, enabled: bool, shell: str, lock_shell: bool, linger: bool, privilege: Privilege, sudo_commands: tuple[str, ...], ram: str | None, cpu: str | None, tasks: int | None, disk: str | None, ssh_authorized_keys: tuple[str, ...], bootstrap_profiles: tuple[str, ...]`.
  - `users_path() -> Path` (honors `DEVBOOST_USERS_PATH`, default `/etc/devboost/users.toml`).
  - `load_users(path: Path | None = None) -> dict[str, ManagedUser]`.
  - `dump_users_toml(users: Mapping[str, ManagedUser]) -> str` (pure serializer; writing to `/etc` is Task 7's job via the executor).

- [ ] **Step 1: Write the failing test**

```python
# engine/tests/accounts/test_config.py
from __future__ import annotations

from pathlib import Path

import pytest

from devboost.accounts.config import (
    AccountsError,
    ManagedUser,
    dump_users_toml,
    load_users,
    users_path,
)


def test_users_path_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DEVBOOST_USERS_PATH", str(tmp_path / "u.toml"))
    assert users_path() == tmp_path / "u.toml"


def test_users_path_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEVBOOST_USERS_PATH", raising=False)
    assert users_path() == Path("/etc/devboost/users.toml")


def test_load_users_parses_and_defaults(tmp_path: Path) -> None:
    p = tmp_path / "u.toml"
    p.write_text(
        '[users.dev]\nram = "4G"\ncpu = "50%"\ntasks = 200\nprivilege = "nopasswd"\n',
        encoding="utf-8",
    )
    users = load_users(p)
    assert set(users) == {"dev"}
    dev = users["dev"]
    assert dev == ManagedUser(
        name="dev", enabled=True, shell="/bin/bash", lock_shell=False, linger=False,
        privilege="nopasswd", sudo_commands=(), ram="4G", cpu="50%", tasks=200,
        disk=None, ssh_authorized_keys=(), bootstrap_profiles=(),
    )


def test_load_users_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_users(tmp_path / "nope.toml") == {}


def test_load_users_rejects_bad_cpu(tmp_path: Path) -> None:
    p = tmp_path / "u.toml"
    p.write_text('[users.dev]\ncpu = "fast"\n', encoding="utf-8")
    with pytest.raises(AccountsError, match="dev"):
        load_users(p)


def test_load_users_rejects_relative_sudo_command(tmp_path: Path) -> None:
    p = tmp_path / "u.toml"
    p.write_text('[users.dev]\nprivilege = "allowlist"\nsudo_commands = ["systemctl restart x"]\n',
                 encoding="utf-8")
    with pytest.raises(AccountsError, match="absolute"):
        load_users(p)


def test_dump_then_load_roundtrips(tmp_path: Path) -> None:
    u = ManagedUser(
        name="dev", enabled=False, shell="/bin/bash", lock_shell=True, linger=True,
        privilege="allowlist", sudo_commands=("/usr/bin/systemctl restart x",),
        ram="2G", cpu="25%", tasks=100, disk="10G",
        ssh_authorized_keys=("ssh-ed25519 AAAA",), bootstrap_profiles=("terminal",),
    )
    p = tmp_path / "u.toml"
    p.write_text(dump_users_toml({"dev": u}), encoding="utf-8")
    assert load_users(p) == {"dev": u}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/accounts/test_config.py -v`
Expected: FAIL — `No module named 'devboost.accounts'`.

- [ ] **Step 3: Add the dependency**

In `engine/pyproject.toml`, add `"tomli-w>=1.0",` to the `[project] dependencies` list. Then:

Run: `cd engine && uv sync`
Expected: resolves and installs `tomli-w`.

- [ ] **Step 4: Write the implementation**

```python
# engine/src/devboost/accounts/__init__.py
```
(empty file)

```python
# engine/src/devboost/accounts/config.py
"""Typed users.toml model: Pydantic validation -> frozen ManagedUser dataclasses."""

from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import tomli_w
from pydantic import BaseModel, ValidationError, field_validator

from devboost.core.errors import DevbootError

_SIZE_RE = re.compile(r"^\d+(\.\d+)?[KMGT]i?B?$|^\d+$")
_CPU_RE = re.compile(r"^\d+%$")

Privilege = Literal["none", "full", "nopasswd", "allowlist"]


class AccountsError(DevbootError):
    """A users.toml entry is invalid, or a reconcile step failed."""


class _UserRow(BaseModel):
    enabled: bool = True
    shell: str = "/bin/bash"
    lock_shell: bool = False
    linger: bool = False
    privilege: Privilege = "none"
    sudo_commands: list[str] = []
    ram: str | None = None
    cpu: str | None = None
    tasks: int | None = None
    disk: str | None = None
    ssh_authorized_keys: list[str] = []
    bootstrap_profiles: list[str] = []

    @field_validator("ram", "disk")
    @classmethod
    def _size(cls, v: str | None) -> str | None:
        if v is not None and not _SIZE_RE.match(v):
            raise ValueError(f"invalid size {v!r} (expected e.g. '4G', '512M')")
        return v

    @field_validator("cpu")
    @classmethod
    def _cpu(cls, v: str | None) -> str | None:
        if v is not None and not _CPU_RE.match(v):
            raise ValueError(f"invalid cpu {v!r} (expected e.g. '50%', '200%')")
        return v

    @field_validator("tasks")
    @classmethod
    def _tasks(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("tasks must be a positive integer")
        return v

    @field_validator("sudo_commands")
    @classmethod
    def _abs_cmds(cls, v: list[str]) -> list[str]:
        for c in v:
            if not c.startswith("/"):
                raise ValueError(f"sudo command must be an absolute path: {c!r}")
        return v


@dataclass(frozen=True)
class ManagedUser:
    name: str
    enabled: bool
    shell: str
    lock_shell: bool
    linger: bool
    privilege: Privilege
    sudo_commands: tuple[str, ...]
    ram: str | None
    cpu: str | None
    tasks: int | None
    disk: str | None
    ssh_authorized_keys: tuple[str, ...]
    bootstrap_profiles: tuple[str, ...]


def _to_managed(name: str, row: _UserRow) -> ManagedUser:
    return ManagedUser(
        name=name, enabled=row.enabled, shell=row.shell, lock_shell=row.lock_shell,
        linger=row.linger, privilege=row.privilege, sudo_commands=tuple(row.sudo_commands),
        ram=row.ram, cpu=row.cpu, tasks=row.tasks, disk=row.disk,
        ssh_authorized_keys=tuple(row.ssh_authorized_keys),
        bootstrap_profiles=tuple(row.bootstrap_profiles),
    )


def users_path() -> Path:
    return Path(os.environ.get("DEVBOOST_USERS_PATH", "/etc/devboost/users.toml"))


def load_users(path: Path | None = None) -> dict[str, ManagedUser]:
    p = path or users_path()
    if not p.exists():
        return {}
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    rows = data.get("users", {})
    out: dict[str, ManagedUser] = {}
    for name, raw in rows.items():
        try:
            row = _UserRow.model_validate(raw)
        except ValidationError as exc:
            raise AccountsError(f"user {name!r}: {exc}") from exc
        out[str(name)] = _to_managed(str(name), row)
    return out


def dump_users_toml(users: Mapping[str, ManagedUser]) -> str:
    """Serialize managed users to a users.toml string (pure; no I/O)."""
    table: dict[str, dict[str, object]] = {}
    for name, u in users.items():
        row: dict[str, object] = {
            "enabled": u.enabled, "shell": u.shell, "lock_shell": u.lock_shell,
            "linger": u.linger, "privilege": u.privilege,
            "sudo_commands": list(u.sudo_commands),
            "ssh_authorized_keys": list(u.ssh_authorized_keys),
            "bootstrap_profiles": list(u.bootstrap_profiles),
        }
        for k, v in (("ram", u.ram), ("cpu", u.cpu), ("tasks", u.tasks), ("disk", u.disk)):
            if v is not None:
                row[k] = v
        table[name] = row
    return tomli_w.dumps({"users": table})
```

- [ ] **Step 5: Run tests + gates**

Run: `cd engine && uv run pytest tests/accounts/test_config.py -v && uv run mypy --strict src/devboost/accounts/config.py && uv run ruff check src/devboost/accounts`
Expected: PASS; clean.

- [ ] **Step 6: Commit**

```bash
git add engine/src/devboost/accounts/ engine/tests/accounts/ engine/pyproject.toml engine/uv.lock
git commit -m "feat(accounts): typed users.toml model with validation + roundtrip"
```

---

### Task 2: `usermgmt` primitive — identity & lifecycle

**Files:**
- Create: `engine/src/devboost/exec/primitives/usermgmt.py`
- Test: `engine/tests/primitives/test_usermgmt.py`

**Interfaces:**
- Consumes: `devboost.model.Ctx`; `ctx.ex.run`.
- Produces (all take `ctx: Ctx` first):
  - `exists(ctx, user) -> bool` — `getent passwd <user>` ok.
  - `uid_of(ctx, user) -> int` — parse `id -u <user>`.
  - `admin_group(ctx) -> str` — `"wheel"` if `getent group wheel` ok else `"sudo"`.
  - `ensure_user(ctx, user, *, shell, home=None) -> None` — `useradd -m -s <shell> [-d <home>] <user>` when absent.
  - `set_authorized_keys(ctx, user, home, keys) -> None`.
  - `set_password(ctx, user, password) -> None` — `chpasswd` via stdin.
  - `lock(ctx, user) -> None` / `unlock(ctx, user) -> None`.
  - `terminate_sessions(ctx, user) -> None` (best-effort; ignores failures).
  - `delete(ctx, user) -> None` — `userdel -r <user>`.
  - `enable_linger(ctx, user)` / `disable_linger(ctx, user)`.

- [ ] **Step 1: Write the failing test**

```python
# engine/tests/primitives/test_usermgmt.py
from __future__ import annotations

from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import usermgmt
from devboost.core.osinfo import OsInfo
from devboost.model import Ctx

FEDORA = OsInfo("fedora", "fedora", "x86_64")
UBUNTU = OsInfo(distro="ubuntu", family="debian", arch="x86_64")


def _ctx(os: OsInfo = FEDORA, **kw: object) -> Ctx:
    return Ctx(os=os, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_exists_true_when_getent_ok() -> None:
    ctx = _ctx(scripts={"getent": Result(0)})
    assert usermgmt.exists(ctx, "dev") is True
    assert ["getent", "passwd", "dev"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_exists_false_when_getent_fails() -> None:
    assert usermgmt.exists(_ctx(scripts={"getent": Result(2)}), "dev") is False


def test_uid_of_parses_id() -> None:
    ctx = _ctx(scripts={"id": Result(0, stdout="1005\n")})
    assert usermgmt.uid_of(ctx, "dev") == 1005


def test_admin_group_wheel_when_present() -> None:
    assert usermgmt.admin_group(_ctx(scripts={"getent": Result(0)})) == "wheel"


def test_admin_group_sudo_when_wheel_absent() -> None:
    assert usermgmt.admin_group(_ctx(scripts={"getent": Result(2)})) == "sudo"


def test_ensure_user_creates_with_home_and_shell_when_absent() -> None:
    ctx = _ctx(scripts={"getent": Result(2)})  # does not exist
    usermgmt.ensure_user(ctx, "dev", shell="/bin/bash")
    assert ["sudo", "useradd", "-m", "-s", "/bin/bash", "dev"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_ensure_user_noop_when_present() -> None:
    ctx = _ctx(scripts={"getent": Result(0)})  # exists
    usermgmt.ensure_user(ctx, "dev", shell="/bin/bash")
    assert not any("useradd" in c for c in ctx.ex.calls)  # type: ignore[attr-defined]


def test_lock_sets_password_lock_and_expiry() -> None:
    ctx = _ctx()
    usermgmt.lock(ctx, "dev")
    assert ["sudo", "usermod", "-L", "--expiredate", "1", "dev"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_delete_removes_home() -> None:
    ctx = _ctx()
    usermgmt.delete(ctx, "dev")
    assert ["sudo", "userdel", "-r", "dev"] in ctx.ex.calls  # type: ignore[attr-defined]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/primitives/test_usermgmt.py -v`
Expected: FAIL — `No module named 'devboost.exec.primitives.usermgmt'`.

- [ ] **Step 3: Write the implementation**

```python
# engine/src/devboost/exec/primitives/usermgmt.py
"""Low-level, idempotent user operations. Every effect goes through ctx.ex.run."""

from __future__ import annotations

from devboost.model import Ctx


def exists(ctx: Ctx, user: str) -> bool:
    return ctx.ex.run(["getent", "passwd", user]).ok


def uid_of(ctx: Ctx, user: str) -> int:
    return int(ctx.ex.run(["id", "-u", user]).stdout.strip())


def admin_group(ctx: Ctx) -> str:
    return "wheel" if ctx.ex.run(["getent", "group", "wheel"]).ok else "sudo"


def ensure_user(ctx: Ctx, user: str, *, shell: str, home: str | None = None) -> None:
    if exists(ctx, user):
        return
    argv = ["useradd", "-m", "-s", shell]
    if home is not None:
        argv += ["-d", home]
    argv.append(user)
    ctx.ex.run(argv, sudo=True)


def set_authorized_keys(ctx: Ctx, user: str, home: str, keys: tuple[str, ...]) -> None:
    if not keys:
        return
    ssh = f"{home}/.ssh"
    ctx.ex.run(["install", "-d", "-m", "700", "-o", user, "-g", user, ssh], sudo=True)
    ctx.ex.run(["tee", f"{ssh}/authorized_keys"], sudo=True, stdin="\n".join(keys) + "\n")
    ctx.ex.run(["chown", f"{user}:{user}", f"{ssh}/authorized_keys"], sudo=True)
    ctx.ex.run(["chmod", "600", f"{ssh}/authorized_keys"], sudo=True)


def set_password(ctx: Ctx, user: str, password: str) -> None:
    ctx.ex.run(["chpasswd"], sudo=True, stdin=f"{user}:{password}\n")


def lock(ctx: Ctx, user: str) -> None:
    ctx.ex.run(["usermod", "-L", "--expiredate", "1", user], sudo=True)


def unlock(ctx: Ctx, user: str) -> None:
    ctx.ex.run(["usermod", "-U", user], sudo=True)
    ctx.ex.run(["usermod", "-e", "", user], sudo=True)


def terminate_sessions(ctx: Ctx, user: str) -> None:
    ctx.ex.run(["loginctl", "terminate-user", user], sudo=True)
    ctx.ex.run(["pkill", "-u", user], sudo=True)


def delete(ctx: Ctx, user: str) -> None:
    ctx.ex.run(["userdel", "-r", user], sudo=True)


def enable_linger(ctx: Ctx, user: str) -> None:
    ctx.ex.run(["loginctl", "enable-linger", user], sudo=True)


def disable_linger(ctx: Ctx, user: str) -> None:
    ctx.ex.run(["loginctl", "disable-linger", user], sudo=True)
```

- [ ] **Step 4: Run tests + gates**

Run: `cd engine && uv run pytest tests/primitives/test_usermgmt.py -v && uv run mypy --strict src/devboost/exec/primitives/usermgmt.py`
Expected: PASS; clean.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/exec/primitives/usermgmt.py engine/tests/primitives/test_usermgmt.py
git commit -m "feat(usermgmt): identity + lifecycle primitives (create/lock/delete/linger)"
```

---

### Task 3: `usermgmt` — privileges (admin group + visudo-validated sudoers drop-in)

**Files:**
- Modify: `engine/src/devboost/exec/primitives/usermgmt.py`
- Modify: `engine/tests/primitives/test_usermgmt.py`

**Interfaces:**
- Consumes: `admin_group` (Task 2); `devboost.accounts.config.AccountsError`.
- Produces:
  - `in_admin_group(ctx, user) -> bool` — parse `id -nG <user>` for `wheel`/`sudo`.
  - `add_admin_group(ctx, user) -> None` / `remove_admin_group(ctx, user) -> None`.
  - `sudoers_path(user) -> str` — `/etc/sudoers.d/devboost-<user>` (dot-free).
  - `write_sudoers(ctx, user, content: str) -> None` — stage→`visudo -cf`→`chmod 0440`/`chown root:root`→atomic `mv`; raises `AccountsError` if validation fails.
  - `remove_sudoers(ctx, user) -> None`.
  - `sudoers_content(user, privilege, sudo_commands) -> str | None` — pure: `None` for `none`/`full`; the drop-in text for `nopasswd`/`allowlist`.

- [ ] **Step 1: Write the failing test**

```python
# append to engine/tests/primitives/test_usermgmt.py
import pytest

from devboost.accounts.config import AccountsError


def test_sudoers_content_none_for_basic_tiers() -> None:
    assert usermgmt.sudoers_content("dev", "none", ()) is None
    assert usermgmt.sudoers_content("dev", "full", ()) is None


def test_sudoers_content_nopasswd() -> None:
    assert usermgmt.sudoers_content("dev", "nopasswd", ()) == "dev ALL=(ALL) NOPASSWD: ALL\n"


def test_sudoers_content_allowlist() -> None:
    out = usermgmt.sudoers_content("dev", "allowlist", ("/usr/bin/systemctl restart x",))
    assert out == "dev ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart x\n"


def test_sudoers_path_is_dot_free() -> None:
    assert usermgmt.sudoers_path("dev") == "/etc/sudoers.d/devboost-dev"


def test_write_sudoers_validates_then_atomically_moves() -> None:
    ctx = _ctx(scripts={"visudo": Result(0)})
    usermgmt.write_sudoers(ctx, "dev", "dev ALL=(ALL) NOPASSWD: ALL\n")
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert any(c[:2] == ["sudo", "tee"] for c in calls)            # staged write
    assert any(c[1] == "visudo" and "-cf" in c for c in calls)     # validated
    assert any(c[1] == "chmod" and "0440" in c for c in calls)     # mode
    assert any(c[1] == "mv" and c[-1] == "/etc/sudoers.d/devboost-dev" for c in calls)


def test_write_sudoers_raises_on_invalid() -> None:
    ctx = _ctx(scripts={"visudo": Result(1, stderr="parse error")})
    with pytest.raises(AccountsError, match="sudoers"):
        usermgmt.write_sudoers(ctx, "dev", "garbage\n")
    # never moved into place:
    assert not any(c[1:2] == ["mv"] for c in ctx.ex.calls)  # type: ignore[attr-defined]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/primitives/test_usermgmt.py -k sudoers -v`
Expected: FAIL — attributes not defined.

- [ ] **Step 3: Write the implementation**

```python
# append to engine/src/devboost/exec/primitives/usermgmt.py
from devboost.accounts.config import AccountsError, Privilege

_STAGE = "/etc/sudoers.d/.devboost-stage"


def in_admin_group(ctx: Ctx, user: str) -> bool:
    groups = ctx.ex.run(["id", "-nG", user]).stdout.split()
    return "wheel" in groups or "sudo" in groups


def add_admin_group(ctx: Ctx, user: str) -> None:
    ctx.ex.run(["usermod", "-aG", admin_group(ctx), user], sudo=True)


def remove_admin_group(ctx: Ctx, user: str) -> None:
    # Best-effort: drop from whichever admin group exists; ignore "not a member".
    ctx.ex.run(["gpasswd", "-d", user, admin_group(ctx)], sudo=True)


def sudoers_path(user: str) -> str:
    return f"/etc/sudoers.d/devboost-{user}"


def sudoers_content(
    user: str, privilege: Privilege, sudo_commands: tuple[str, ...]
) -> str | None:
    if privilege in ("none", "full"):
        return None
    if privilege == "nopasswd":
        return f"{user} ALL=(ALL) NOPASSWD: ALL\n"
    # allowlist
    cmds = ", ".join(sudo_commands)
    return f"{user} ALL=(ALL) NOPASSWD: {cmds}\n"


def write_sudoers(ctx: Ctx, user: str, content: str) -> None:
    """Stage -> validate with visudo -> fix mode/owner -> atomic move. Raise on invalid."""
    ctx.ex.run(["tee", _STAGE], sudo=True, stdin=content)
    if not ctx.ex.run(["visudo", "-cf", _STAGE]).ok:
        ctx.ex.run(["rm", "-f", _STAGE], sudo=True)
        raise AccountsError(f"sudoers content for {user!r} failed visudo validation")
    ctx.ex.run(["chown", "root:root", _STAGE], sudo=True)
    ctx.ex.run(["chmod", "0440", _STAGE], sudo=True)
    ctx.ex.run(["mv", "-f", _STAGE, sudoers_path(user)], sudo=True)


def remove_sudoers(ctx: Ctx, user: str) -> None:
    ctx.ex.run(["rm", "-f", sudoers_path(user)], sudo=True)
```

Note: importing from `devboost.accounts.config` inside a primitive is acceptable here because `config.py` has no reverse dependency on primitives (no cycle). Verify with `uv run python -c "import devboost.exec.primitives.usermgmt"`.

- [ ] **Step 4: Run tests + gates**

Run: `cd engine && uv run pytest tests/primitives/test_usermgmt.py -v && uv run mypy --strict src/devboost/exec/primitives/usermgmt.py`
Expected: PASS; clean; no import cycle.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/exec/primitives/usermgmt.py engine/tests/primitives/test_usermgmt.py
git commit -m "feat(usermgmt): privilege tiers via admin group + visudo-validated sudoers drop-in"
```

---

### Task 4: `usermgmt` — systemd slice caps

**Files:**
- Modify: `engine/src/devboost/exec/primitives/usermgmt.py`
- Modify: `engine/tests/primitives/test_usermgmt.py`

**Interfaces:**
- Produces:
  - `slice_dropin_text(ram, cpu, tasks) -> str | None` — pure: the `[Slice]` body with `MemoryMax`/`MemoryHigh`(≈90% of `ram`)/`CPUQuota`/`TasksMax`; `None` if all three are `None`.
  - `set_slice(ctx, uid, *, ram, cpu, tasks) -> None` — write `/etc/systemd/system/user-<uid>.slice.d/50-devboost.conf`, `daemon-reload`, `set-property` (push live). No-op if `slice_dropin_text` is `None`.
  - `clear_slice(ctx, uid) -> None` — remove drop-in, `daemon-reload`, `set-property --runtime` reset.
  - `mem_high(ram) -> str` — `ram` parsed to bytes × 0.9, re-emitted (helper).

- [ ] **Step 1: Write the failing test**

```python
# append to engine/tests/primitives/test_usermgmt.py
def test_slice_dropin_text_none_when_all_unset() -> None:
    assert usermgmt.slice_dropin_text(None, None, None) is None


def test_slice_dropin_text_includes_only_set_knobs() -> None:
    text = usermgmt.slice_dropin_text("4G", "50%", 200)
    assert "[Slice]" in text
    assert "MemoryMax=4G" in text
    assert "MemoryHigh=" in text          # ~90% derived
    assert "CPUQuota=50%" in text
    assert "TasksMax=200" in text
    text2 = usermgmt.slice_dropin_text(None, "25%", None)
    assert "MemoryMax" not in text2 and "CPUQuota=25%" in text2


def test_set_slice_writes_dropin_reloads_and_sets_property() -> None:
    ctx = _ctx()
    usermgmt.set_slice(ctx, 1005, ram="4G", cpu="50%", tasks=200)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert any(c[1] == "install" and c[-1].endswith("user-1005.slice.d") for c in calls)
    assert any(c[1] == "tee" and c[-1].endswith("50-devboost.conf") for c in calls)
    assert ["sudo", "systemctl", "daemon-reload"] in calls
    assert any(c[1:4] == ["systemctl", "set-property", "user-1005.slice"] for c in calls)


def test_set_slice_noop_when_all_unset() -> None:
    ctx = _ctx()
    usermgmt.set_slice(ctx, 1005, ram=None, cpu=None, tasks=None)
    assert ctx.ex.calls == []  # type: ignore[attr-defined]


def test_clear_slice_removes_and_resets() -> None:
    ctx = _ctx()
    usermgmt.clear_slice(ctx, 1005)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert any(c[1] == "rm" and c[-1].endswith("50-devboost.conf") for c in calls)
    assert ["sudo", "systemctl", "daemon-reload"] in calls
    assert any(c[1:3] == ["systemctl", "set-property"] and "--runtime" in c for c in calls)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/primitives/test_usermgmt.py -k slice -v`
Expected: FAIL.

- [ ] **Step 3: Write the implementation**

```python
# append to engine/src/devboost/exec/primitives/usermgmt.py
_UNITS = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}


def _to_bytes(size: str) -> int:
    s = size.rstrip("iB")
    if s and s[-1] in _UNITS:
        return int(float(s[:-1]) * _UNITS[s[-1]])
    return int(s)


def mem_high(ram: str) -> str:
    """≈90% of *ram*, emitted in bytes (systemd accepts a bare byte count)."""
    return str(int(_to_bytes(ram) * 0.9))


def slice_dropin_text(ram: str | None, cpu: str | None, tasks: int | None) -> str | None:
    if ram is None and cpu is None and tasks is None:
        return None
    lines = ["[Slice]"]
    if ram is not None:
        lines.append(f"MemoryHigh={mem_high(ram)}")
        lines.append(f"MemoryMax={ram}")
    if cpu is not None:
        lines.append(f"CPUQuota={cpu}")
    if tasks is not None:
        lines.append(f"TasksMax={tasks}")
    return "\n".join(lines) + "\n"


def _slice_dir(uid: int) -> str:
    return f"/etc/systemd/system/user-{uid}.slice.d"


def _slice_props(ram: str | None, cpu: str | None, tasks: int | None) -> list[str]:
    props: list[str] = []
    if ram is not None:
        props += [f"MemoryHigh={mem_high(ram)}", f"MemoryMax={ram}"]
    if cpu is not None:
        props.append(f"CPUQuota={cpu}")
    if tasks is not None:
        props.append(f"TasksMax={tasks}")
    return props


def set_slice(ctx: Ctx, uid: int, *, ram: str | None, cpu: str | None, tasks: int | None) -> None:
    text = slice_dropin_text(ram, cpu, tasks)
    if text is None:
        return
    d = _slice_dir(uid)
    ctx.ex.run(["install", "-d", "-m", "755", d], sudo=True)
    ctx.ex.run(["tee", f"{d}/50-devboost.conf"], sudo=True, stdin=text)
    ctx.ex.run(["systemctl", "daemon-reload"], sudo=True)
    ctx.ex.run(["systemctl", "set-property", f"user-{uid}.slice", *_slice_props(ram, cpu, tasks)],
               sudo=True)


def clear_slice(ctx: Ctx, uid: int) -> None:
    ctx.ex.run(["rm", "-f", f"{_slice_dir(uid)}/50-devboost.conf"], sudo=True)
    ctx.ex.run(["systemctl", "daemon-reload"], sudo=True)
    ctx.ex.run(
        ["systemctl", "set-property", "--runtime", f"user-{uid}.slice",
         "MemoryHigh=", "MemoryMax=", "CPUQuota=", "TasksMax="],
        sudo=True,
    )
```

- [ ] **Step 4: Run tests + gates**

Run: `cd engine && uv run pytest tests/primitives/test_usermgmt.py -k slice -v && uv run mypy --strict src/devboost/exec/primitives/usermgmt.py`
Expected: PASS; clean.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/exec/primitives/usermgmt.py engine/tests/primitives/test_usermgmt.py
git commit -m "feat(usermgmt): per-user systemd slice caps (RAM/CPU/tasks) + clean reset"
```

---

### Task 5: `usermgmt` — tiered disk quota

**Files:**
- Modify: `engine/src/devboost/exec/primitives/usermgmt.py`
- Modify: `engine/tests/primitives/test_usermgmt.py`

**Interfaces:**
- Consumes: `devboost.exec.primitives.pkg` (auto-install `quota`).
- Produces:
  - `fstype_of(ctx, path) -> str` — `findmnt -no FSTYPE --target <path>`.
  - `ensure_subvolume(ctx, path) -> None` — `btrfs subvolume create <path>` if not already one.
  - `set_quota(ctx, user, home, size) -> str` — returns a human status: `"enforced"` or `"skipped: <reason>"`. **Never raises** (best-effort). btrfs → qgroup; ext4/xfs with quota active → `setquota` (auto-install `quota` if `setquota` missing); else → skip.
  - `clear_quota(ctx, user, home) -> None` — btrfs `qgroup limit none`; ext4/xfs `setquota 0`.

- [ ] **Step 1: Write the failing test**

```python
# append to engine/tests/primitives/test_usermgmt.py
def test_fstype_of_reads_findmnt() -> None:
    ctx = _ctx(scripts={"findmnt": Result(0, stdout="btrfs\n")})
    assert usermgmt.fstype_of(ctx, "/home/dev") == "btrfs"


def test_set_quota_btrfs_enables_and_limits() -> None:
    ctx = _ctx(scripts={"findmnt": Result(0, stdout="btrfs\n")})
    status = usermgmt.set_quota(ctx, "dev", "/home/dev", "20G")
    assert status == "enforced"
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert any(c[1:3] == ["btrfs", "quota"] and "enable" in c for c in calls)
    assert any(c[1:4] == ["btrfs", "qgroup", "limit"] and c[-1] == "/home/dev" for c in calls)


def test_set_quota_ext4_skips_when_not_active() -> None:
    # findmnt -> ext4; OPTIONS probe has no usrquota -> skipped, never fails.
    ctx = _ctx(scripts={"findmnt": Result(0, stdout="ext4\n")})
    status = usermgmt.set_quota(ctx, "dev", "/home/dev", "20G")
    assert status.startswith("skipped:")
    assert not any("setquota" in c for c in ctx.ex.calls)  # type: ignore[attr-defined]


def test_set_quota_unsupported_fs_skips() -> None:
    ctx = _ctx(scripts={"findmnt": Result(0, stdout="overlay\n")})
    assert usermgmt.set_quota(ctx, "dev", "/home/dev", "20G").startswith("skipped:")
```

Note on the ext4 path: `set_quota` must distinguish "quota active" from "not active" via a second probe. For the test above, the `findmnt` script returns the FSTYPE for the first `findmnt` call; the OPTIONS probe (a second `findmnt -no OPTIONS`) also keys on `"findmnt"` in `FakeExecutor`, returning the same `Result`. So in the ext4 test, the OPTIONS probe yields `"ext4\n"` (no `usrquota`) → treated as not-active → skipped. Keep the active-quota ext4 path covered by an integration test where `repquota`/options are scripted distinctly, or refactor the probe to a dedicated command (`quotaon -p`) so it keys separately. **Implementation choice:** probe with `quotaon -pu <mnt>` (keys on `"quotaon"`), which is cleaner to fake.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/primitives/test_usermgmt.py -k quota -v`
Expected: FAIL.

- [ ] **Step 3: Write the implementation**

```python
# append to engine/src/devboost/exec/primitives/usermgmt.py
from devboost.core import log
from devboost.exec.primitives import pkg


def fstype_of(ctx: Ctx, path: str) -> str:
    return ctx.ex.run(["findmnt", "-no", "FSTYPE", "--target", path]).stdout.strip()


def _mountpoint_of(ctx: Ctx, path: str) -> str:
    return ctx.ex.run(["findmnt", "-no", "TARGET", "--target", path]).stdout.strip() or "/"


def ensure_subvolume(ctx: Ctx, path: str) -> None:
    if not ctx.ex.run(["btrfs", "subvolume", "show", path]).ok:
        ctx.ex.run(["btrfs", "subvolume", "create", path], sudo=True)


def set_quota(ctx: Ctx, user: str, home: str, size: str) -> str:
    """Best-effort per-user disk cap. Returns 'enforced' or 'skipped: <reason>'. Never raises."""
    fs = fstype_of(ctx, home)
    if fs == "btrfs":
        ctx.ex.run(["btrfs", "quota", "enable", "/"], sudo=True)
        ctx.ex.run(["btrfs", "qgroup", "limit", size, home], sudo=True)
        return "enforced"
    if fs in ("ext4", "xfs"):
        mnt = _mountpoint_of(ctx, home)
        if not ctx.ex.run(["quotaon", "-pu", mnt]).ok:
            return f"skipped: quota not enabled on {mnt} (needs usrquota mount + reboot)"
        if not ctx.ex.which("setquota"):
            pkg.install(ctx, "quota")
        ctx.ex.run(["setquota", "-u", user, "0", size, "0", "0", mnt], sudo=True)
        return "enforced"
    return f"skipped: disk quota unsupported on {fs or 'unknown fs'}"


def clear_quota(ctx: Ctx, user: str, home: str) -> None:
    fs = fstype_of(ctx, home)
    if fs == "btrfs":
        ctx.ex.run(["btrfs", "qgroup", "limit", "none", home], sudo=True)
    elif fs in ("ext4", "xfs"):
        mnt = _mountpoint_of(ctx, home)
        ctx.ex.run(["setquota", "-u", user, "0", "0", "0", "0", mnt], sudo=True)
```

(Confirm `pkg.install(ctx, "quota")` matches the real `pkg.install` signature — check `src/devboost/exec/primitives/pkg.py`; adjust the call if it takes a different argument shape. `log` import is reserved for the reconcile-layer warning in Task 7; remove here if ruff flags it unused.)

- [ ] **Step 4: Run tests + gates**

Run: `cd engine && uv run pytest tests/primitives/test_usermgmt.py -k quota -v && uv run mypy --strict src/devboost/exec/primitives/usermgmt.py`
Expected: PASS; clean.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/exec/primitives/usermgmt.py engine/tests/primitives/test_usermgmt.py
git commit -m "feat(usermgmt): tiered best-effort disk quota (btrfs qgroup / ext4-xfs setquota / skip)"
```

---

### Task 6: `DemotingExecutor` — run privileged as root, the rest as the target user

**Files:**
- Modify: `engine/src/devboost/exec/executor.py`
- Test: `engine/tests/exec/test_demoting_executor.py`

**Interfaces:**
- Consumes: `Executor` protocol, `Result`.
- Produces: `class DemotingExecutor` implementing `Executor`. Constructor `DemotingExecutor(inner: Executor, target_user: str)`. `run(argv, *, sudo, stdin, env)`: when `sudo=True` → `inner.run(argv, sudo=False, …)` (already root); else → `inner.run(["sudo", "-u", target_user, "-H", *argv], …)`. `which` delegates to `inner.which`.

- [ ] **Step 1: Write the failing test**

```python
# engine/tests/exec/test_demoting_executor.py
from __future__ import annotations

from devboost.exec.executor import DemotingExecutor, FakeExecutor


def test_privileged_command_runs_as_root_directly() -> None:
    inner = FakeExecutor()
    DemotingExecutor(inner, "dev").run(["dnf", "install", "-y", "ripgrep"], sudo=True)
    # sudo=False passed to inner -> no 'sudo' prefix recorded
    assert inner.calls == [["dnf", "install", "-y", "ripgrep"]]


def test_unprivileged_command_demoted_to_target_user() -> None:
    inner = FakeExecutor()
    DemotingExecutor(inner, "dev").run(["chezmoi", "apply"])
    assert inner.calls == [["sudo", "-u", "dev", "-H", "chezmoi", "apply"]]


def test_which_delegates() -> None:
    inner = FakeExecutor(present={"git"})
    ex = DemotingExecutor(inner, "dev")
    assert ex.which("git") is True
    assert ex.which("nope") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/exec/test_demoting_executor.py -v`
Expected: FAIL — `cannot import name 'DemotingExecutor'`.

- [ ] **Step 3: Write the implementation**

```python
# append to engine/src/devboost/exec/executor.py
class DemotingExecutor:
    """Run as root, but demote unprivileged commands to *target_user*.

    Used by the accounts bootstrap: the engine runs as root, so sudo=True commands
    execute directly, while sudo=False commands (user-scoped writes to the user's HOME)
    are wrapped in ``sudo -u <user> -H`` so they run as — and create files owned by — the
    target user.
    """

    def __init__(self, inner: Executor, target_user: str) -> None:
        self._inner = inner
        self._user = target_user

    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> Result:
        if sudo:
            return self._inner.run(argv, sudo=False, stdin=stdin, env=env)
        wrapped = ["sudo", "-u", self._user, "-H", *argv]
        return self._inner.run(wrapped, sudo=False, stdin=stdin, env=env)

    def which(self, cmd: str) -> bool:
        return self._inner.which(cmd)
```

- [ ] **Step 4: Run tests + gates**

Run: `cd engine && uv run pytest tests/exec/test_demoting_executor.py -v && uv run mypy --strict src/devboost/exec/executor.py`
Expected: PASS; clean. Confirm `isinstance(DemotingExecutor(FakeExecutor(), "x"), Executor)` holds (runtime_checkable protocol).

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/exec/executor.py engine/tests/exec/test_demoting_executor.py
git commit -m "feat(exec): DemotingExecutor — root for privileged, target user for the rest"
```

---

### Task 7: `reconcile.py` — converge one user; disable; delete; persist `users.toml`

**Files:**
- Create: `engine/src/devboost/accounts/reconcile.py`
- Test: `engine/tests/accounts/test_reconcile.py`

**Interfaces:**
- Consumes: `usermgmt` (Tasks 2-5), `config` (Task 1), `bootstrap` (Task 8 — imported lazily to avoid an early dependency; for this task `apply_user` takes a `bootstrap` callback defaulting to a no-op).
- Produces:
  - `apply_user(ctx, user: ManagedUser, *, bootstrap=None) -> None` — full converge. Order: home/subvolume → `ensure_user` → ssh keys/password → linger → privileges → slice → quota (warn on skip) → bootstrap. If `enabled is False`, calls `disable_user` instead.
  - `disable_user(ctx, user: ManagedUser) -> None` — terminate sessions + `lock`.
  - `enable_user(ctx, user: ManagedUser) -> None` — `unlock` + `apply_user`.
  - `delete_user(ctx, user: ManagedUser, *, purge: bool = False) -> None` — terminate → remove sudoers/admin/slice/quota → `userdel -r` → (purge) orphan sweep.
  - `home_of(user: ManagedUser) -> str` — `/home/<name>`.
  - `save(ctx, users: Mapping[str, ManagedUser]) -> None` — privileged write of `users.toml` (`install -d /etc/devboost`; `tee`).

- [ ] **Step 1: Write the failing test**

```python
# engine/tests/accounts/test_reconcile.py
from __future__ import annotations

from devboost.accounts import reconcile
from devboost.accounts.config import ManagedUser
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx

FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def _user(**over: object) -> ManagedUser:
    base = dict(
        name="dev", enabled=True, shell="/bin/bash", lock_shell=False, linger=False,
        privilege="none", sudo_commands=(), ram="4G", cpu="50%", tasks=200, disk=None,
        ssh_authorized_keys=(), bootstrap_profiles=(),
    )
    base.update(over)
    return ManagedUser(**base)  # type: ignore[arg-type]


def test_apply_user_creates_and_caps() -> None:
    ctx = _ctx(scripts={"getent": Result(2), "id": Result(0, stdout="1005\n")})
    reconcile.apply_user(ctx, _user())
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "useradd", "-m", "-s", "/bin/bash", "dev"] in calls
    assert any(c[1:4] == ["systemctl", "set-property", "user-1005.slice"] for c in calls)


def test_apply_user_nopasswd_writes_sudoers() -> None:
    ctx = _ctx(scripts={"getent": Result(2), "id": Result(0, stdout="1005\n"), "visudo": Result(0)})
    reconcile.apply_user(ctx, _user(privilege="nopasswd"))
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert any(c[1] == "mv" and c[-1] == "/etc/sudoers.d/devboost-dev" for c in calls)


def test_apply_user_disabled_locks_instead_of_creating() -> None:
    ctx = _ctx(scripts={"getent": Result(0), "id": Result(0, stdout="1005\n")})
    reconcile.apply_user(ctx, _user(enabled=False))
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "usermod", "-L", "--expiredate", "1", "dev"] in calls


def test_delete_user_tears_down_and_removes() -> None:
    ctx = _ctx(scripts={"id": Result(0, stdout="1005\n"), "findmnt": Result(0, stdout="ext4\n")})
    reconcile.delete_user(ctx, _user())
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "userdel", "-r", "dev"] in calls
    assert any(c[1] == "rm" and "sudoers.d/devboost-dev" in c[-1] for c in calls)
    assert any(c[1] == "rm" and "50-devboost.conf" in c[-1] for c in calls)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/accounts/test_reconcile.py -v`
Expected: FAIL — `No module named 'devboost.accounts.reconcile'`.

- [ ] **Step 3: Write the implementation**

```python
# engine/src/devboost/accounts/reconcile.py
"""Converge one managed user to its declared state, idempotently."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from devboost.accounts.config import ManagedUser, dump_users_toml, users_path
from devboost.core import log
from devboost.exec.primitives import usermgmt as um
from devboost.model import Ctx

Bootstrap = Callable[[Ctx, ManagedUser], None]


def home_of(user: ManagedUser) -> str:
    return f"/home/{user.name}"


def _apply_privilege(ctx: Ctx, user: ManagedUser) -> None:
    if user.privilege in ("full", "nopasswd"):
        um.add_admin_group(ctx, user.name)
    else:
        um.remove_admin_group(ctx, user.name)
    content = um.sudoers_content(user.name, user.privilege, user.sudo_commands)
    if content is None:
        um.remove_sudoers(ctx, user.name)
    else:
        um.write_sudoers(ctx, user.name, content)


def apply_user(ctx: Ctx, user: ManagedUser, *, bootstrap: Bootstrap | None = None) -> None:
    if not user.enabled:
        disable_user(ctx, user)
        return
    home = home_of(user)
    shell = "/usr/sbin/nologin" if user.lock_shell else user.shell
    if user.disk is not None and um.fstype_of(ctx, "/home") == "btrfs":
        um.ensure_subvolume(ctx, home)
        um.ensure_user(ctx, user.name, shell=shell, home=home)
    else:
        um.ensure_user(ctx, user.name, shell=shell)
    um.set_authorized_keys(ctx, user.name, home, user.ssh_authorized_keys)
    (um.enable_linger if user.linger else um.disable_linger)(ctx, user.name)
    _apply_privilege(ctx, user)
    uid = um.uid_of(ctx, user.name)
    um.set_slice(ctx, uid, ram=user.ram, cpu=user.cpu, tasks=user.tasks)
    if user.disk is not None:
        status = um.set_quota(ctx, user.name, home, user.disk)
        (log.ok if status == "enforced" else log.warn)(f"{user.name}: disk quota {status}")
    if bootstrap is not None and user.bootstrap_profiles:
        bootstrap(ctx, user)


def disable_user(ctx: Ctx, user: ManagedUser) -> None:
    um.terminate_sessions(ctx, user.name)
    um.lock(ctx, user.name)


def enable_user(ctx: Ctx, user: ManagedUser) -> None:
    um.unlock(ctx, user.name)
    apply_user(ctx, user)


def delete_user(ctx: Ctx, user: ManagedUser, *, purge: bool = False) -> None:
    um.terminate_sessions(ctx, user.name)
    um.remove_sudoers(ctx, user.name)
    um.remove_admin_group(ctx, user.name)
    if um.exists(ctx, user.name):
        uid = um.uid_of(ctx, user.name)
        um.clear_slice(ctx, uid)
        if user.disk is not None:
            um.clear_quota(ctx, user.name, home_of(user))
        um.delete(ctx, user.name)
        if purge:
            ctx.ex.run(["find", "/", "-xdev", "-uid", str(uid), "-delete"], sudo=True)


def save(ctx: Ctx, users: Mapping[str, ManagedUser]) -> None:
    path = users_path()
    ctx.ex.run(["install", "-d", "-m", "755", str(path.parent)], sudo=True)
    ctx.ex.run(["tee", str(path)], sudo=True, stdin=dump_users_toml(users))
```

- [ ] **Step 4: Run tests + gates**

Run: `cd engine && uv run pytest tests/accounts/test_reconcile.py -v && uv run mypy --strict src/devboost/accounts/reconcile.py`
Expected: PASS; clean.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/accounts/reconcile.py engine/tests/accounts/test_reconcile.py
git commit -m "feat(accounts): reconcile — converge/disable/enable/delete + users.toml persistence"
```

---

### Task 8: Bootstrap — install profiles for the new user via `DemotingExecutor`

**Files:**
- Create: `engine/src/devboost/accounts/bootstrap.py`
- Test: `engine/tests/accounts/test_bootstrap.py`

**Interfaces:**
- Consumes: `DemotingExecutor` (Task 6); the existing pipeline pieces (`load`, `load_profiles`, `expand`, `toposort`, `build_plan`, `run_plan`); `ManagedUser`; `reconcile.home_of`.
- Produces: `bootstrap_user(ctx, user: ManagedUser, *, root: Path) -> None` — builds a `Ctx` whose executor is `DemotingExecutor(ctx.ex, user.name)` and whose process env sets `HOME=/home/<user>`, then runs `user.bootstrap_profiles` through the standard plan/runner. Designed to be passed as the `bootstrap` callback to `apply_user`.

- [ ] **Step 1: Write the failing test**

```python
# engine/tests/accounts/test_bootstrap.py
from __future__ import annotations

from pathlib import Path

from devboost.accounts import bootstrap
from devboost.accounts.config import ManagedUser
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx


def _user(**over: object) -> ManagedUser:
    base = dict(
        name="dev", enabled=True, shell="/bin/bash", lock_shell=False, linger=False,
        privilege="none", sudo_commands=(), ram=None, cpu=None, tasks=None, disk=None,
        ssh_authorized_keys=(), bootstrap_profiles=("terminal",),
    )
    base.update(over)
    return ManagedUser(**base)  # type: ignore[arg-type]


def test_bootstrap_demotes_unprivileged_commands_to_user(monkeypatch, tmp_path: Path) -> None:
    # Stub the heavy pipeline so the test asserts only the executor wiring.
    seen: dict[str, object] = {}

    def fake_run_profiles(c: Ctx, tokens: list[str], root: Path) -> None:
        seen["executor"] = type(c.ex).__name__
        seen["tokens"] = tokens
        c.ex.run(["chezmoi", "apply"])  # an unprivileged user-scoped command

    monkeypatch.setattr(bootstrap, "_run_profiles", fake_run_profiles)
    inner = FakeExecutor()
    ctx = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=inner)
    bootstrap.bootstrap_user(ctx, _user(), root=tmp_path)
    assert seen["executor"] == "DemotingExecutor"
    assert seen["tokens"] == ["terminal"]
    assert ["sudo", "-u", "dev", "-H", "chezmoi", "apply"] in inner.calls
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/accounts/test_bootstrap.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write the implementation**

```python
# engine/src/devboost/accounts/bootstrap.py
"""Install a managed user's bootstrap_profiles as that user, via DemotingExecutor."""

from __future__ import annotations

import os
from pathlib import Path

from devboost.accounts.config import ManagedUser
from devboost.accounts.reconcile import home_of
from devboost.core.graph import toposort
from devboost.core.plan import build_plan
from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load, validate_profiles
from devboost.core.runner import run_plan
from devboost.exec.executor import DemotingExecutor
from devboost.model import Ctx


def _run_profiles(ctx: Ctx, tokens: list[str], root: Path) -> None:
    modules = load()
    profiles = load_profiles(root / "profiles.toml")
    validate_profiles(modules, set(profiles))
    order = toposort(expand(tokens, profiles, modules), modules)
    plan = build_plan(order, modules, ctx.os)
    run_plan(plan, modules, ctx)


def bootstrap_user(ctx: Ctx, user: ManagedUser, *, root: Path) -> None:
    """Install user.bootstrap_profiles for *user*: root for privileged, user for the rest."""
    os.environ["HOME"] = home_of(user)  # modules compute ~paths from $HOME
    demoted = Ctx(
        os=ctx.os,
        ex=DemotingExecutor(ctx.ex, user.name),
        force=ctx.force,
        dry_run=ctx.dry_run,
    )
    _run_profiles(demoted, list(user.bootstrap_profiles), root)
```

(Note: setting `os.environ["HOME"]` is process-global; acceptable because `bootstrap_user` is the last reconcile step of a one-shot CLI invocation. If `accounts apply` ever loops over many users with bootstrap in one process, snapshot/restore `HOME` around each call — out of scope for v1, single-user create.)

- [ ] **Step 4: Run tests + gates**

Run: `cd engine && uv run pytest tests/accounts/test_bootstrap.py -v && uv run mypy --strict src/devboost/accounts/bootstrap.py`
Expected: PASS; clean.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/accounts/bootstrap.py engine/tests/accounts/test_bootstrap.py
git commit -m "feat(accounts): bootstrap profiles for a managed user via DemotingExecutor"
```

---

### Task 9: Interactive create/edit form (questionary seam)

**Files:**
- Create: `engine/src/devboost/accounts/form.py`
- Test: `engine/tests/accounts/test_form.py`

**Interfaces:**
- Produces:
  - `merge_flags(name, *, ram, cpu, disk, tasks, privilege, sudo_commands, shell, lock_shell, linger, ssh_keys, bootstrap_profiles, enabled=True) -> ManagedUser` — pure builder from CLI flags (used by non-interactive `create`).
  - `run_form(default: ManagedUser | None = None) -> ManagedUser` — the questionary form (not unit-tested; needs a TTY). For `edit`, prefilled from `default`.

- [ ] **Step 1: Write the failing test**

```python
# engine/tests/accounts/test_form.py
from __future__ import annotations

from devboost.accounts.config import ManagedUser
from devboost.accounts.form import merge_flags


def test_merge_flags_builds_managed_user() -> None:
    u = merge_flags(
        "dev", ram="4G", cpu="50%", disk="20G", tasks=200, privilege="nopasswd",
        sudo_commands=(), shell="/bin/bash", lock_shell=False, linger=True,
        ssh_keys=("ssh-ed25519 AAAA",), bootstrap_profiles=("terminal",),
    )
    assert u == ManagedUser(
        name="dev", enabled=True, shell="/bin/bash", lock_shell=False, linger=True,
        privilege="nopasswd", sudo_commands=(), ram="4G", cpu="50%", tasks=200, disk="20G",
        ssh_authorized_keys=("ssh-ed25519 AAAA",), bootstrap_profiles=("terminal",),
    )


def test_merge_flags_defaults_privilege_none() -> None:
    u = merge_flags("dev", ram=None, cpu=None, disk=None, tasks=None, privilege="none",
                    sudo_commands=(), shell="/bin/bash", lock_shell=False, linger=False,
                    ssh_keys=(), bootstrap_profiles=())
    assert u.privilege == "none" and u.ram is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/accounts/test_form.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write the implementation**

```python
# engine/src/devboost/accounts/form.py
"""Interactive create/edit form + a pure flag->ManagedUser builder."""

from __future__ import annotations

from devboost.accounts.config import ManagedUser, Privilege


def merge_flags(
    name: str,
    *,
    ram: str | None,
    cpu: str | None,
    disk: str | None,
    tasks: int | None,
    privilege: Privilege,
    sudo_commands: tuple[str, ...],
    shell: str,
    lock_shell: bool,
    linger: bool,
    ssh_keys: tuple[str, ...],
    bootstrap_profiles: tuple[str, ...],
    enabled: bool = True,
) -> ManagedUser:
    return ManagedUser(
        name=name, enabled=enabled, shell=shell, lock_shell=lock_shell, linger=linger,
        privilege=privilege, sudo_commands=sudo_commands, ram=ram, cpu=cpu, tasks=tasks,
        disk=disk, ssh_authorized_keys=ssh_keys, bootstrap_profiles=bootstrap_profiles,
    )


def run_form(default: ManagedUser | None = None) -> ManagedUser:  # pragma: no cover (TTY)
    """questionary-driven create/edit form. Prefilled from *default* when editing."""
    import questionary

    d = default
    name = questionary.text("Username:", default=(d.name if d else "")).ask()
    ram = questionary.text("RAM cap (e.g. 4G, blank = none):", default=(d.ram or "" if d else "")).ask()
    cpu = questionary.text("CPU cap (e.g. 50%, blank = none):", default=(d.cpu or "" if d else "")).ask()
    disk = questionary.text("Disk cap (e.g. 20G, blank = none):", default=(d.disk or "" if d else "")).ask()
    tasks_s = questionary.text("Max processes (blank = none):",
                               default=(str(d.tasks) if d and d.tasks else "")).ask()
    privilege = questionary.select(
        "Privileges:", choices=["none", "full", "nopasswd", "allowlist"],
        default=(d.privilege if d else "none"),
    ).ask()
    return merge_flags(
        name, ram=ram or None, cpu=cpu or None, disk=disk or None,
        tasks=int(tasks_s) if tasks_s else None, privilege=privilege, sudo_commands=(),
        shell=(d.shell if d else "/bin/bash"), lock_shell=(d.lock_shell if d else False),
        linger=(d.linger if d else False),
        ssh_keys=(d.ssh_authorized_keys if d else ()),
        bootstrap_profiles=(d.bootstrap_profiles if d else ()),
    )
```

- [ ] **Step 4: Run tests + gates**

Run: `cd engine && uv run pytest tests/accounts/test_form.py -v && uv run mypy --strict src/devboost/accounts/form.py`
Expected: PASS; clean (the `run_form` body is `# pragma: no cover`).

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/accounts/form.py engine/tests/accounts/test_form.py
git commit -m "feat(accounts): create/edit form + pure flag->ManagedUser builder"
```

---

### Task 10: `accounts` CLI sub-app — verbs + registration

**Files:**
- Create: `engine/src/devboost/cli/accounts.py`
- Modify: `engine/src/devboost/cli/app.py` (register the sub-app)
- Test: `engine/tests/cli/test_accounts_cli.py`

**Interfaces:**
- Consumes: `config` (load/save model), `reconcile`, `bootstrap`, `form`.
- Produces: a `typer.Typer` named `accounts` with commands `create`, `list`, `edit`, `disable`, `enable`, `delete`, `apply`; registered via `app.add_typer(accounts_app, name="accounts")`.

- [ ] **Step 1: Write the failing test**

```python
# engine/tests/cli/test_accounts_cli.py
from __future__ import annotations

from typer.testing import CliRunner

from devboost.cli.app import app

runner = CliRunner()


def test_accounts_subapp_registered() -> None:
    result = runner.invoke(app, ["accounts", "--help"])
    assert result.exit_code == 0
    for verb in ("create", "list", "edit", "disable", "enable", "delete", "apply"):
        assert verb in result.output


def test_accounts_create_writes_entry_with_no_apply(tmp_path, monkeypatch) -> None:
    users = tmp_path / "users.toml"
    monkeypatch.setenv("DEVBOOST_USERS_PATH", str(users))
    # --no-apply must not touch the system; it only persists the entry locally.
    monkeypatch.setattr("devboost.cli.accounts._save_local", lambda u: users.write_text(
        __import__("devboost.accounts.config", fromlist=["dump_users_toml"]).dump_users_toml(u),
        encoding="utf-8"))
    result = runner.invoke(app, ["accounts", "create", "dev", "--ram", "4G", "--no-apply"])
    assert result.exit_code == 0
    from devboost.accounts.config import load_users
    assert load_users(users)["dev"].ram == "4G"
```

(The `_save_local` seam exists so `--no-apply` can persist `users.toml` without the privileged `tee` path in a unit test. In production `create` without `--no-apply` persists via `reconcile.save(ctx, …)`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/cli/test_accounts_cli.py -v`
Expected: FAIL — `No such command 'accounts'`.

- [ ] **Step 3: Write the implementation**

```python
# engine/src/devboost/cli/accounts.py
"""The `accounts` sub-app: create/list/edit/disable/enable/delete/apply managed users."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from devboost.accounts import bootstrap as bs
from devboost.accounts import reconcile
from devboost.accounts.config import ManagedUser, Privilege, load_users, users_path
from devboost.accounts.form import merge_flags, run_form
from devboost.core import log, osinfo
from devboost.core.settings import settings
from devboost.exec.executor import RealExecutor
from devboost.model import Ctx

app = typer.Typer(help="Manage self-contained, resource-capped sandbox users.")


def _ctx() -> Ctx:
    return Ctx(os=osinfo.detect(), ex=RealExecutor())


def _save_local(users: Mapping[str, ManagedUser]) -> None:
    """Persist users.toml. Overridden in tests; production uses reconcile.save."""
    reconcile.save(_ctx(), users)


@app.command()
def create(
    name: Annotated[str, typer.Argument(help="username")] = "",
    ram: Annotated[str, typer.Option("--ram", help="RAM cap, e.g. 4G")] = "",
    cpu: Annotated[str, typer.Option("--cpu", help="CPU cap, e.g. 50%")] = "",
    disk: Annotated[str, typer.Option("--disk", help="disk quota, e.g. 20G")] = "",
    tasks: Annotated[int, typer.Option("--tasks", help="max processes")] = 0,
    privilege: Annotated[str, typer.Option("--privilege")] = "none",
    sudo_cmd: Annotated[list[str], typer.Option("--sudo-cmd", help="allowlist cmd (repeatable)")] = [],
    shell: Annotated[str, typer.Option("--shell")] = "/bin/bash",
    lock_shell: Annotated[bool, typer.Option("--lock-shell")] = False,
    linger: Annotated[bool, typer.Option("--linger")] = False,
    ssh_key: Annotated[list[str], typer.Option("--ssh-key", help="authorized key (repeatable)")] = [],
    with_profile: Annotated[list[str], typer.Option("--with-profile", help="bootstrap profile")] = [],
    interactive: Annotated[bool, typer.Option("--interactive")] = False,
    apply_: Annotated[bool, typer.Option("--apply/--no-apply")] = True,
    adopt: Annotated[bool, typer.Option("--adopt", help="manage an existing unmanaged account")] = False,
) -> None:
    """Create a managed user (interactive form when NAME omitted)."""
    if not name or interactive:
        user = run_form()
    else:
        user = merge_flags(
            name, ram=ram or None, cpu=cpu or None, disk=disk or None,
            tasks=tasks or None, privilege=_privilege(privilege), sudo_commands=tuple(sudo_cmd),
            shell=shell, lock_shell=lock_shell, linger=linger, ssh_keys=tuple(ssh_key),
            bootstrap_profiles=tuple(with_profile),
        )
    users = load_users()
    ctx = _ctx()
    from devboost.exec.primitives import usermgmt as um
    if user.name in users:
        log.error(f"{user.name}: already managed (use 'accounts edit')")
        raise typer.Exit(2)
    if um.exists(ctx, user.name) and not adopt:
        log.error(f"{user.name}: account already exists; pass --adopt to manage it")
        raise typer.Exit(2)
    users[user.name] = user
    _save_local(users)
    if apply_:
        reconcile.apply_user(
            ctx, user,
            bootstrap=(lambda c, u: bs.bootstrap_user(c, u, root=settings.root))
            if user.bootstrap_profiles else None,
        )
    log.ok(f"{user.name}: created")


@app.command(name="list")
def list_() -> None:
    """List managed users and their declared caps."""
    users = load_users()
    table = Table("user", "enabled", "ram", "cpu", "tasks", "disk", "privilege")
    for u in users.values():
        table.add_row(u.name, str(u.enabled), u.ram or "-", u.cpu or "-",
                      str(u.tasks or "-"), u.disk or "-", u.privilege)
    Console().print(table)


@app.command()
def edit(name: str) -> None:
    """Edit a managed user via a prefilled form, then re-apply."""
    users = load_users()
    if name not in users:
        log.error(f"{name}: not managed")
        raise typer.Exit(2)
    updated = run_form(default=users[name])
    users[name] = updated
    _save_local(users)
    reconcile.apply_user(_ctx(), updated)
    log.ok(f"{name}: updated")


@app.command()
def disable(name: str) -> None:
    """Lock a managed user (reversible)."""
    user = _require(name)
    disabled = _with_enabled(user, False)
    users = load_users()
    users[name] = disabled
    _save_local(users)
    reconcile.disable_user(_ctx(), disabled)
    log.ok(f"{name}: disabled")


@app.command()
def enable(name: str) -> None:
    """Unlock + re-apply a managed user."""
    user = _with_enabled(_require(name), True)
    users = load_users()
    users[name] = user
    _save_local(users)
    reconcile.enable_user(_ctx(), user)
    log.ok(f"{name}: enabled")


@app.command()
def delete(
    name: str,
    purge: Annotated[bool, typer.Option("--purge", help="also sweep orphaned UID-owned files")] = False,
) -> None:
    """Delete a managed user and tear down all its artifacts."""
    user = _require(name)
    reconcile.delete_user(_ctx(), user, purge=purge)
    users = load_users()
    users.pop(name, None)
    _save_local(users)
    log.ok(f"{name}: deleted")


@app.command()
def apply(name: Annotated[str, typer.Argument(help="user (blank = all)")] = "") -> None:
    """Reconcile all managed users, or one."""
    users = load_users()
    ctx = _ctx()
    targets = [users[name]] if name else list(users.values())
    for u in targets:
        reconcile.apply_user(ctx, u)
    log.ok(f"applied {len(targets)} user(s)")


def _privilege(value: str) -> Privilege:
    if value not in ("none", "full", "nopasswd", "allowlist"):
        log.error(f"invalid privilege {value!r}")
        raise typer.Exit(2)
    return value  # type: ignore[return-value]


def _require(name: str) -> ManagedUser:
    users = load_users()
    if name not in users:
        log.error(f"{name}: not managed")
        raise typer.Exit(2)
    return users[name]


def _with_enabled(u: ManagedUser, enabled: bool) -> ManagedUser:
    from dataclasses import replace
    return replace(u, enabled=enabled)
```

Then register it in `engine/src/devboost/cli/app.py` (after the other imports and near the `installer` registration at the bottom):

```python
from devboost.cli import accounts as _accounts  # add to imports
app.add_typer(_accounts.app, name="accounts")    # add near app.command(name="installer")(_installer)
```

- [ ] **Step 4: Run tests + gates**

Run: `cd engine && uv run pytest tests/cli/test_accounts_cli.py -v && uv run mypy --strict src/devboost/cli/accounts.py && uv run ruff check src/devboost`
Expected: PASS; clean.

- [ ] **Step 5: Full suite**

Run: `cd engine && uv run pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add engine/src/devboost/cli/accounts.py engine/src/devboost/cli/app.py engine/tests/cli/test_accounts_cli.py
git commit -m "feat(cli): accounts sub-app (create/list/edit/disable/enable/delete/apply)"
```

---

### Task 11: Docs — architecture + quickstart for `accounts`

**Files:**
- Modify: `docs/architecture.md` (add `accounts` to the command list + a short subsystem note)
- Create: `docs/accounts.md` (usage: create/disable/delete, the `/etc/devboost/users.toml` schema, the "disk quota is best-effort" caveat, the cross-distro notes)

**Interfaces:** none (docs).

- [ ] **Step 1: Write the docs**

Add `accounts` to the `cli/` command enumeration in `docs/architecture.md`, and create `docs/accounts.md` documenting: the `users.toml` schema (copy the table from the design spec §2.3), the four privilege tiers, the limit knobs, the best-effort disk-quota matrix (btrfs reboot-free / ext4-xfs needs mount-time quota), `--with-profile` bootstrap, and clean disable/delete. Reference the design spec at `docs/superpowers/specs/2026-06-29-term-rename-and-accounts-sandbox-design.md`.

- [ ] **Step 2: Commit**

```bash
git add docs/architecture.md docs/accounts.md
git commit -m "docs: accounts sandbox-user usage + schema + disk-quota caveats"
```

---

## Self-Review

- **Spec coverage:** `/etc/devboost/users.toml` + env override (Task 1) ✓; Pydantic validation + frozen dataclass (Task 1) ✓; identity/lifecycle (Task 2) ✓; privilege tiers + visudo-validated dot-free sudoers (Task 3) ✓; slice caps RAM/CPU/tasks + MemoryHigh derivation + clean reset (Task 4) ✓; tiered best-effort disk quota incl. btrfs subvolume + auto-install `quota` + skip-with-reason (Tasks 5, 7) ✓; DemotingExecutor (Task 6) ✓; reconcile converge/disable/enable/delete + `--purge` orphan sweep (Task 7) ✓; `--with-profile` bootstrap (Task 8) ✓; interactive form + flag builder (Task 9) ✓; standalone sub-app never `@register`-ed, registry-scoped, `--adopt` (Task 10) ✓; cross-distro `wheel`/`sudo` + always `-m -s` (Tasks 2, 3) ✓; docs incl. best-effort caveat (Task 11) ✓.
- **Placeholder scan:** no TBD/TODO; every code step has real code; the only `# pragma: no cover` is the TTY form body, which is intentional and has a pure tested builder beside it.
- **Type consistency:** `ManagedUser` field names/order are identical across Tasks 1, 7, 8, 9; `usermgmt` function names (`ensure_user`, `set_slice`/`clear_slice`, `set_quota`/`clear_quota`, `write_sudoers`/`sudoers_content`/`sudoers_path`, `admin_group`, `uid_of`, `exists`) are used consistently in reconcile (Task 7); `Privilege` literal is shared from `config`.
- **Known seams to verify during execution (called out inline, not placeholders):** exact `pkg.install` signature (Task 5 note); `CliRunner` stderr mixing (Task 10); test directory layout (`tests/exec/primitives/`, `tests/accounts/`) should match the repo's existing layout — adjust paths if the repo nests differently.
