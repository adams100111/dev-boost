# pass multi-device P2 (macOS) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the P1 multi-device `pass` store work on macOS workstations: pinentry-mac for the passphrase, a launchd agent for the 15-minute sync, and native macOS notifications. The plan also closes the P1 carry-overs: a recipient audit, schedulers that check their loaded state, a systemd daemon-reload, and a guard so unattended reads never open a passphrase prompt.

**Architecture:** P1 confined OS divergence to three seams. `notify._native_argv` now returns an `osascript` argv on macOS. `sync.install_scheduler` and `sync.scheduler_installed` now drive `launchd.user_agent` on macOS. `pass_store.agent_settings` now adds pinentry-mac on macOS. Filling those seams means `devboost pass` can leave `LINUX_ONLY`, and `PassStore` can join the `macos` family. A new `passstore/audit.py` reads each entry's recipients from its packets (it never decrypts) and compares them with the entry's `.gpg-id`. The audit's findings are reported by `doctor`, `devboost pass audit`/`status`, and `sync`.

**Tech Stack:** Python ≥ 3.12, Typer, Pydantic v2, stdlib `plistlib`, GnuPG 2.2+, `pass` 1.7+, git, launchd (`launchctl bootstrap/print`), `osascript`, Homebrew `pinentry-mac`, and systemd `--user`. Tooling is pytest, mypy `--strict`, ruff and `uv`.

**Spec:** `docs/superpowers/specs/2026-09-18-pass-multi-device-design.md` (rollout row **P2**, and "Carried to P2" under P1 notes). The P1 plan `docs/superpowers/plans/2026-09-19-pass-p1-linux.md` holds decisions D1–D22, which all still apply. The binding carry-over list is `.superpowers/carryover/carryover.md`, section "P2 (pass on macOS)", in the main checkout.

## Global Constraints

- macOS sync agent: `launchd.user_agent(ctx, "dev.devboost.pass-sync", [<devboost>, "pass", "sync", "--quiet"], start_interval=900)`.
- macOS passphrase entry: `pinentry-mac` from Homebrew, set as `pinentry-program` in `gpg-agent.conf`. The passphrase can then be saved in the login keychain.
- gpg-agent cache on every OS: `default-cache-ttl 28800` (8 h) and `max-cache-ttl 86400` (24 h).
- Remove `"pass"` from `cli/host.py` `LINUX_ONLY`. `PassStore.families` gains `"macos"`.
- Recipient audit uses `gpg --list-only --list-packets`. It never decrypts and never opens pinentry.
- Unattended runs never open pinentry. `pass show` in a non-interactive run fails fast when the passphrase isn't cached.
- Tests are hermetic and pass on macOS and ubuntu-22.04 CI. `tests/conftest.py` has autouse fixtures `_tmp_home` and `_linux_host`. Real-gpg tests use a short `mkdtemp` GNUPGHOME under `/tmp` and kill their agents on teardown. No test touches the real `~/.gnupg`, `~/.password-store`, `~/Library/LaunchAgents` or keychain. No test loads a real launchd job: use `FakeExecutor`/`RuleExecutor`.
- Keep `tests/core/test_macos_contract.py` green. Remove names from `KNOWN_GAPS` once they become resolvable.
- Merge gates, run from `engine/`: `uv run ruff check`, whole-engine `uv run mypy` (cold: `rm -rf .mypy_cache` first, then warm), and `uv run pytest`. Lines are ≤ 100 chars.
- Every external command runs as an argv list. Shell strings are never used.
- Commit messages: Conventional Commits, with **no** `Co-Authored-By` trailer and no Claude/Anthropic attribution (constitution).
- All commands below run from `engine/` unless stated otherwise.

## Decisions (where the spec and carry-over are silent)

| # | Topic | Decision | Why |
|---|---|---|---|
| R1 | macOS notification | `osascript -e 'on run argv' -e 'display notification (item 2 of argv) with title (item 1 of argv)' -e 'end run' <title> <body>`. Title and body are **argv**, never AppleScript text. Markup escaping (`&<>`) moves from `notify.clean()` to the `notify-send` body only. | This makes AppleScript injection impossible. macOS would show `&amp;` literally. `clean()` stays the sanitiser of remote strings. |
| R2 | launchd agent shape | Label `dev.devboost.pass-sync`, `StartInterval` 900, **no** `RunAtLoad`, no `EnvironmentVariables`. | Loading happens mid-install, and a `RunAtLoad` sync would race the installer's own git calls. launchd runs a missed interval once on wake, like systemd's `Persistent=`. `RealExecutor` already prepends `/opt/homebrew/bin`, so `gpg` resolves. |
| R3 | `scheduler_installed(ctx, bin_)` | macOS: the plist on disk is byte-identical to the expected one **and** `launchctl print gui/<uid>/<label>` succeeds. Linux: both unit files are identical to the expected ones **and** `systemctl --user is-enabled` **and** `is-active` succeed for the timer. | Carry-over: existence alone missed an unloaded or stale agent. A moved `devboost` binary rewrites the scheduler. |
| R4 | systemd daemon-reload | `systemd.write_user_unit` skips identical content and returns `bool` (changed). On change it runs `systemctl --user daemon-reload`. This applies to every caller. New helpers: `unit_current(name, content)` and `is_active(ctx, name, user=)`. | A rewritten unit takes effect without a re-login. The primitive fix covers every timer. |
| R5 | pinentry-mac path | `/opt/homebrew/bin/pinentry-mac` on `aarch64`, `/usr/local/bin/pinentry-mac` on `x86_64` (Homebrew's default prefixes). `pinentry-program` is a **managed** key, so a custom value is replaced. | `verify` stays pure (no `brew --prefix` call). One key and one owner, the same as the TTLs. |
| R6 | macOS `pass` install | `pkg.install` (brew) installs only the missing formulae among `pass`, `gnupg` and `pinentry-mac`, keyed by command `pass`/`gpg`/`pinentry-mac`. `verify` requires all three commands plus the agent conf. Linux is unchanged (`pass` only). Keychain caching needs no gpg-agent option: pinentry-mac's "Save in Keychain" works while `no-allow-external-cache` is unset, which is the default. | Spec module row: "macOS brew `pass`, `gnupg`, `pinentry-mac`". |
| R7 | Catalog contract | `Pass.portable = True`. `PassStore.portable = True` and `families = ("fedora", "debian", "arch", "macos")`. `"pass"` leaves `KNOWN_GAPS`. | Both install paths are now OS-aware. |
| R8 | macOS default profile | `macos = ["terminal", "pass", "pass-store"]`. | The spec puts pass on every workstation. The `macos` profile is the Mac default (`base` holds Linux-only modules). If M2 edits the same line, the conflict is one line. |
| R9 | Audit semantics | For each entry: its recipient long key ids come from `gpg --list-only --list-packets`. Each id maps to a primary fingerprint through the keyring, **plus** the store's own `devices/` `revoked/` `pending/` `.asc` files. A file only vouches for its record's fingerprint. An id that doesn't resolve stays a bare key id. The expected keys are the nearest `.gpg-id` (pass semantics). `extra` = recipients no token names. `missing` = tokens no recipient matches. A folder whose `.gpg-id` names any key by email is reported as `unauditable`, not flagged. | This answers the carry-over "flags entries whose recipients differ from their `.gpg-id`" in both directions. Revoked keys are named even after the sync deleted them from the keyring. |
| R10 | Where the audit shows up | `doctor` has a **failing** check `pass-recipients`, like `pass-rotation`. `devboost pass audit` lists each mismatch plus the fix and exits 1 when anything is flagged. `devboost pass status` shows a count. `sync` audits after a successful pull when HEAD moved since the last audit. It notifies when the flagged set gains an entry (state `audit_flagged`, `audited_head`). | The audit runs one gpg per entry, so it only runs when the store changed. A standing mismatch is announced once, not every 15 minutes. |
| R11 | Fix guidance | `pass init [-p <folder>] $(cat <folder>/.gpg-id)` re-encrypts exactly the entries whose recipients differ (pass compares them itself). When a revoked device is among the recipients, also change the secret (`pass edit <entry>`). | Both steps are exact and minimal. Git history keeps the old ciphertext. |
| R12 | Unattended pinentry guard | When `_credentials.is_interactive()` is false, `pass_show` runs `pass show` with `PASSWORD_STORE_GPG_OPTS="<existing> --pinentry-mode error"`. A cached passphrase still works. An uncached one fails at once, and the read is skipped with a hint. Applies on every OS. | Verified with gpg 2.5: the cache is used, and without it gpg returns "No pinentry" immediately. A pinentry-mac dialog nobody answers would otherwise stall a timer or unattended run. |
| R13 | `devboost pass` on macOS | Allowed. `LINUX_ONLY = {"installer", "accounts", "brain"}`. | The flows are OS-agnostic now that the seams are filled. |
| R14 | Commit messages | Conventional Commits with **no** `Co-Authored-By` trailer and no Claude/Anthropic attribution. | Constitution. |

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `engine/src/devboost/passstore/notify.py` (modify) | osascript argv; markup only for notify-send | 1 |
| `engine/src/devboost/exec/primitives/systemd.py` (modify) | idempotent write + daemon-reload, `unit_current`, `is_active` | 2 |
| `engine/src/devboost/exec/primitives/launchd.py` (modify) | `agent_current` (plist identical + loaded) | 2 |
| `engine/src/devboost/passstore/sync.py` (modify) | launchd branch, `scheduler_installed(ctx, bin_)` | 3 |
| `engine/src/devboost/modules/pass_store.py` (modify) | verify passes `bin_`; macOS `Pass`; `PassStore` macOS | 3, 6 |
| `engine/src/devboost/passstore/gpg.py` (modify) | `parse_key_ids`, `key_ids`, `key_ids_in_file`, `recipients`, `is_key_token` | 4 |
| `engine/src/devboost/passstore/layout.py` (modify) | `Store.governing_folder` | 4 |
| `engine/src/devboost/passstore/audit.py` (create) | `Mismatch`, `Report`, `audit()`, `fix_hint()` | 4 |
| `engine/src/devboost/passstore/sync.py`, `cli/doctor.py`, `cli/pass_cmd.py` (modify) | audit in sync / doctor / `pass audit` + status | 5 |
| `engine/src/devboost/cli/host.py`, `profiles.toml`, `tests/core/test_macos_contract.py` (modify) | `pass` on macOS | 6 |
| `engine/src/devboost/modules/_pass.py` (modify) | unattended pinentry guard | 7 |
| `engine/tests/passstore/test_integration_gpg.py` (modify) | real gpg: offline insert after revoke is flagged; the guard | 8 |
| `docs/pass.md`, `CHANGELOG.md`, spec (modify) | docs | 9 |

---

### Task 0: Baseline

**Files:** none

- [ ] **Step 1: Sync and run the gate once**

```bash
cd engine && uv sync && uv run ruff check && rm -rf .mypy_cache && uv run mypy && uv run mypy \
  && uv run pytest -q 2>&1 | tail -3
```
Expected: ruff and mypy are clean and pytest is all green. Record the pass count. Any red test here already existed: stop and report it rather than fixing it.

---

### Task 1: native macOS notifications (`notify._native_argv`)

**Files:**
- Modify: `engine/src/devboost/passstore/notify.py`
- Test: `engine/tests/passstore/test_git_notify.py`

**Interfaces:**
- Produces: `notify.clean(text, limit=64) -> str` (no markup escaping any more). `notify._native_argv(os_info, title, body) -> list[str]`, which never returns `None` now. `notify.native(ctx, title, body) -> bool` is unchanged.

- [ ] **Step 1: Write the failing tests.** In `tests/passstore/test_git_notify.py`, replace `test_native_macos_is_a_p2_seam` and `test_clean_escapes_markup_and_strip_zero_width_and_bidi` with:

```python
def test_native_macos_uses_osascript_with_argv_not_script_text() -> None:
    title, body = 'pass: "x" wants access', 'a" & do shell script "rm -rf ~'
    argv = notify._native_argv(MAC, title, body)
    assert argv == [
        "osascript",
        "-e", "on run argv",
        "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
        "-e", "end run",
        title, body,
    ]
    ex = RuleExecutor(present={"osascript"})
    assert notify.native(Ctx(os=MAC, ex=ex), title, body) is True
    assert ex.calls == [argv]


def test_notify_send_body_is_markup_escaped_title_is_not() -> None:
    argv = notify._native_argv(FEDORA, "a<b", "<b>x&y</b>")
    assert argv == ["notify-send", "--app-name=devboost", "a<b", "&lt;b&gt;x&amp;y&lt;/b&gt;"]


def test_clean_strips_zero_width_and_bidi_but_no_longer_escapes() -> None:
    assert notify.clean("<b>a&b</b>") == "<b>a&b</b>"
    hidden = "d​e‏s؜k﻿‪⁦"
    assert notify.clean(hidden) == "desk"
```
(`FEDORA`, `MAC`, `Ctx` and `RuleExecutor` are already imported or defined at the top of this file. Add any that are missing: `MAC = OsInfo("macos", "macos", "aarch64")`.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/passstore/test_git_notify.py -v`
Expected: FAIL. `_native_argv(MAC, …)` is `None`, and `clean` escapes.

- [ ] **Step 3: Implement.** In `notify.py`:

```python
def clean(text: str, limit: int = 64) -> str:
    """A remote-sourced string (a record's name / os) made safe to show in a notification:
    no control / invisible characters, no leading `-` (never read as an option), at most
    *limit* chars. Markup escaping is the notifier's business (see `_native_argv`)."""
    return _UNSAFE.sub("", text).strip().lstrip("-").strip()[:limit]


def _markup(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


#: AppleScript that takes the title and body as run-handler arguments: they are never
#: parsed as script text, so no quoting can break out of them (R1).
_OSASCRIPT = (
    "on run argv",
    "display notification (item 2 of argv) with title (item 1 of argv)",
    "end run",
)


def _native_argv(os_info: OsInfo, title: str, body: str) -> list[str]:
    """macOS: osascript (title/body as argv); Linux: libnotify (the body is markup)."""
    if os_info.family == "macos":
        script = [arg for line in _OSASCRIPT for arg in ("-e", line)]
        return ["osascript", *script, title, body]
    return ["notify-send", "--app-name=devboost", title, _markup(body)]


def native(ctx: Ctx, title: str, body: str) -> bool:
    argv = _native_argv(ctx.os, title, body)
    if not ctx.ex.which(argv[0]):
        return False
    return ctx.ex.run(argv).ok
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/passstore -q && uv run ruff check && uv run mypy`
Expected: PASS. If a sync test asserted an escaped name inside a notify-send body, its expectation still holds, because the body is now escaped in `_native_argv`.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/passstore/notify.py engine/tests/passstore/test_git_notify.py
git commit -m "feat(pass): native macOS notifications via osascript run-handler argv"
```

---

### Task 2: primitives: systemd daemon-reload + launchd `agent_current`

**Files:**
- Modify: `engine/src/devboost/exec/primitives/systemd.py`, `engine/src/devboost/exec/primitives/launchd.py`
- Test: `engine/tests/primitives/test_base_primitives.py` (systemd; add to it, or create `engine/tests/primitives/test_systemd.py` if the systemd tests live nowhere), `engine/tests/primitives/test_launchd.py`

**Interfaces:**
- Produces: `systemd.write_user_unit(ctx, name, content) -> bool` (True = written and daemon-reloaded). `systemd.unit_current(name: str, content: str) -> bool`. `systemd.is_active(ctx, name, *, user=False) -> bool`. `launchd.agent_current(ctx, lbl, program_args, *, start_interval=None, start_calendar=None, run_at_load=False, env=None) -> bool`.

- [ ] **Step 1: Write the failing tests**

systemd (new file `tests/primitives/test_systemd.py`):

```python
from __future__ import annotations

from pathlib import Path

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import systemd
from devboost.model import Ctx

FEDORA = OsInfo("fedora", "fedora", "x86_64")
RELOAD = ["systemctl", "--user", "daemon-reload"]


def test_write_user_unit_reloads_only_on_change(tmp_path: Path) -> None:
    ex = FakeExecutor()
    ctx = Ctx(os=FEDORA, ex=ex)
    assert systemd.write_user_unit(ctx, "x.service", "A\n") is True
    assert ex.calls == [RELOAD]
    assert systemd.unit_current("x.service", "A\n")
    assert systemd.write_user_unit(ctx, "x.service", "A\n") is False
    assert ex.calls == [RELOAD]  # unchanged → no write, no reload
    assert systemd.write_user_unit(ctx, "x.service", "B\n") is True
    assert ex.calls == [RELOAD, RELOAD]
    assert not systemd.unit_current("x.service", "A\n")
    assert not systemd.unit_current("missing.timer", "A\n")


def test_is_active() -> None:
    ok = Ctx(os=FEDORA, ex=FakeExecutor())
    assert systemd.is_active(ok, "t.timer", user=True)
    assert ok.ex.calls == [["systemctl", "--user", "is-active", "t.timer"]]  # type: ignore[attr-defined]
    bad = Ctx(os=FEDORA, ex=FakeExecutor(scripts={"systemctl": Result(3)}))
    assert not systemd.is_active(bad, "t.timer", user=True)
```
(If mypy rejects `ok.ex.calls`, bind `ex = FakeExecutor()` first and assert on `ex.calls`. The autouse `_tmp_home` makes `HOME` equal `tmp_path`.)

launchd (append to `tests/primitives/test_launchd.py`):

```python
def test_agent_current_needs_identical_plist_and_loaded(home: Path) -> None:
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    args = ["/bin/devboost", "pass", "sync", "--quiet"]
    assert not launchd.agent_current(ctx, "dev.devboost.x", args, start_interval=900)
    launchd.user_agent(ctx, "dev.devboost.x", args, start_interval=900)
    assert launchd.agent_current(ctx, "dev.devboost.x", args, start_interval=900)
    assert not launchd.agent_current(ctx, "dev.devboost.x", args, start_interval=60)
    unloaded = Ctx(os=MAC, ex=FakeExecutor(scripts={"launchctl": Result(113)}))
    assert not launchd.agent_current(unloaded, "dev.devboost.x", args, start_interval=900)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/primitives/test_systemd.py tests/primitives/test_launchd.py -v`
Expected: FAIL (`unit_current` / `is_active` / `agent_current` missing; no reload).

- [ ] **Step 3: Implement**

`systemd.py`:

```python
def unit_current(name: str, content: str) -> bool:
    """The user unit on disk is exactly *content*."""
    p = _user_unit_dir() / name
    return p.exists() and p.read_text(encoding="utf-8") == content


def write_user_unit(ctx: Ctx, name: str, content: str) -> bool:
    """Write a user unit; True when it changed. A change is followed by `daemon-reload`, so
    systemd uses the new unit without a re-login (identical content: nothing runs)."""
    if unit_current(name, content):
        return False
    d = _user_unit_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(content, encoding="utf-8")
    ctx.ex.run(["systemctl", "--user", "daemon-reload"])
    return True


def is_active(ctx: Ctx, name: str, *, user: bool = False) -> bool:
    scope = ["--user"] if user else []
    return ctx.ex.run(["systemctl", *scope, "is-active", name]).ok
```

`launchd.py`: add `agent_current`, and make `user_agent` use it:

```python
def agent_current(
    ctx: Ctx,
    lbl: str,
    program_args: Sequence[str],
    *,
    start_interval: int | None = None,
    start_calendar: Mapping[str, int] | None = None,
    run_at_load: bool = False,
    env: Mapping[str, str] | None = None,
) -> bool:
    """The agent's plist on disk is exactly this one AND launchd has it loaded."""
    path = _agents_dir() / f"{lbl}.plist"
    body = _plist(lbl, program_args, start_interval=start_interval,
                  start_calendar=start_calendar, run_at_load=run_at_load, env=env)
    return path.exists() and path.read_bytes() == body and agent_loaded(ctx, lbl)
```

In `user_agent`, replace `if path.exists() and path.read_bytes() == body and agent_loaded(ctx, lbl):` with `if agent_current(ctx, lbl, program_args, start_interval=start_interval, start_calendar=start_calendar, run_at_load=run_at_load, env=env):`, wrapped to 100 columns.

- [ ] **Step 4: Run the whole suite.** Other timer modules (`dev_hygiene`, `apps`, `server`, `system`, `orca`) call `write_user_unit`. A test that asserts an **exact** call list for them now also sees `["systemctl", "--user", "daemon-reload"]` once per changed unit. Update those expectations to include the reload. Do not change the modules.

Run: `uv run pytest -q && uv run ruff check && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/exec/primitives/ engine/tests/
git commit -m "fix(systemd): daemon-reload after rewriting a user unit; add launchd agent_current"
```

---

### Task 3: macOS sync scheduler (launchd) + loaded-state `scheduler_installed`

**Files:**
- Modify: `engine/src/devboost/passstore/sync.py`, `engine/src/devboost/modules/pass_store.py` (`PassStore.verify`)
- Test: `engine/tests/passstore/test_sync.py`, `engine/tests/modules/test_pass_store.py`

**Interfaces:**
- Consumes: `launchd.user_agent`, `launchd.agent_current`, `launchd.label`, `systemd.write_user_unit -> bool`, `systemd.unit_current`, `systemd.is_enabled`, `systemd.is_active` (Task 2).
- Produces: `sync.AGENT: str = "dev.devboost.pass-sync"`, `sync.INTERVAL: int = 900`, `sync.agent_args(bin_: str) -> list[str]`, `sync.install_scheduler(ctx, bin_) -> None` (both OSes), `sync.scheduler_installed(ctx: Ctx, bin_: str) -> bool` (**signature change**: `bin_` added).

- [ ] **Step 1: Write the failing tests.** In `tests/passstore/test_sync.py`, drop the `UnsupportedOS` import if it's unused, and replace `test_install_scheduler_linux_enables_timer` and `test_install_scheduler_macos_is_p2` with:

```python
def test_install_scheduler_linux_enables_timer_and_checks_state(tmp_path: Path) -> None:
    ex = _ex()
    sync.install_scheduler(_ctx(ex), "/bin/devboost")
    units = tmp_path / "home" / ".config" / "systemd" / "user"
    assert (units / sync.SERVICE).exists() and (units / sync.TIMER).exists()
    assert ["systemctl", "--user", "daemon-reload"] in ex.calls
    assert ["systemctl", "--user", "enable", "--now", sync.TIMER] in ex.calls
    assert sync.scheduler_installed(_ctx(ex), "/bin/devboost")
    assert not sync.scheduler_installed(_ctx(ex), "/other/devboost")  # stale ExecStart
    disabled = _ex((("is-enabled",), Result(1)))
    assert not sync.scheduler_installed(_ctx(disabled), "/bin/devboost")
    stopped = _ex((("is-active",), Result(3)))
    assert not sync.scheduler_installed(_ctx(stopped), "/bin/devboost")


def test_install_scheduler_linux_rewrite_is_idempotent(tmp_path: Path) -> None:
    sync.install_scheduler(_ctx(_ex()), "/bin/devboost")
    again = _ex()
    sync.install_scheduler(_ctx(again), "/bin/devboost")
    assert ["systemctl", "--user", "daemon-reload"] not in again.calls


def test_install_scheduler_macos_is_a_launchd_agent(tmp_path: Path) -> None:
    import os
    import plistlib

    ex = _ex()
    sync.install_scheduler(_ctx(ex, MAC), "/bin/devboost")
    plist = tmp_path / "home" / "Library" / "LaunchAgents" / "dev.devboost.pass-sync.plist"
    assert plistlib.loads(plist.read_bytes()) == {
        "Label": "dev.devboost.pass-sync",
        "ProgramArguments": ["/bin/devboost", "pass", "sync", "--quiet"],
        "StartInterval": 900,
    }
    assert ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist)] in ex.calls
    assert not any(c[0] == "systemctl" for c in ex.calls)
    assert sync.scheduler_installed(_ctx(ex, MAC), "/bin/devboost")
    assert not sync.scheduler_installed(_ctx(ex, MAC), "/other/devboost")
    unloaded = _ex((("launchctl", "print"), Result(113)))
    assert not sync.scheduler_installed(_ctx(unloaded, MAC), "/bin/devboost")
```
(Move the `os`/`plistlib` imports to the top of the file.) In `tests/modules/test_pass_store.py`, update any direct call of `sync.scheduler_installed(ctx)` to pass a `bin_`. A test that monkeypatches `sync.scheduler_installed` with a one-argument lambda must now accept `(ctx, bin_)`.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/passstore/test_sync.py -v`
Expected: FAIL (the macOS branch raises `UnsupportedOS`; `scheduler_installed` takes one argument).

- [ ] **Step 3: Implement.** In `sync.py`: import `launchd` next to `systemd` (`from devboost.exec.primitives import launchd, systemd`), and drop `UnsupportedOS` from the errors import if it's unused. Then:

```python
AGENT = launchd.label("pass-sync")
INTERVAL = 900  # seconds — the same 15 minutes as the systemd timer


def agent_args(bin_: str) -> list[str]:
    return [bin_, "pass", "sync", "--quiet"]


def install_scheduler(ctx: Ctx, bin_: str) -> None:
    """The OS seam in sync: a systemd user timer on Linux, a launchd agent on macOS.

    macOS: no RunAtLoad (R2): the agent is loaded mid-install, and an immediate sync would
    race the installer's own git calls. launchd runs a missed interval once on wake.
    """
    if ctx.os.family == "macos":
        launchd.user_agent(ctx, AGENT, agent_args(bin_), start_interval=INTERVAL)
        return
    systemd.write_user_unit(ctx, SERVICE, service_unit(bin_))
    systemd.write_user_unit(ctx, TIMER, timer_unit())
    systemd.enable_user_unit(ctx, TIMER, now=True)


def scheduler_installed(ctx: Ctx, bin_: str) -> bool:
    """Installed = what is on disk is exactly what `install_scheduler(bin_)` writes AND the
    scheduler has it live (R3) — a stale path or an unloaded agent means reinstall."""
    if ctx.os.family == "macos":
        return launchd.agent_current(ctx, AGENT, agent_args(bin_), start_interval=INTERVAL)
    return (systemd.unit_current(SERVICE, service_unit(bin_))
            and systemd.unit_current(TIMER, timer_unit())
            and systemd.is_enabled(ctx, TIMER, user=True)
            and systemd.is_active(ctx, TIMER, user=True))
```

In `modules/pass_store.py` `PassStore.verify`, replace `sync.scheduler_installed(ctx)` with `sync.scheduler_installed(ctx, paths.devboost_bin())`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/passstore tests/modules/test_pass_store.py -q && uv run ruff check && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/passstore/sync.py engine/src/devboost/modules/pass_store.py \
  engine/tests/passstore/test_sync.py engine/tests/modules/test_pass_store.py
git commit -m "feat(pass): launchd sync agent on macOS; scheduler check requires it loaded"
```

---

### Task 4: recipient audit (`gpg --list-only --list-packets`)

**Files:**
- Modify: `engine/src/devboost/passstore/gpg.py`, `engine/src/devboost/passstore/layout.py`
- Create: `engine/src/devboost/passstore/audit.py`
- Test: `engine/tests/passstore/test_gpg.py`, `engine/tests/passstore/test_layout.py`, `engine/tests/passstore/test_audit.py` (create)

**Interfaces:**
- Produces:
  - `gpg.parse_key_ids(out: str) -> dict[str, str]`: long key id (16 upper-hex) of every primary key and subkey, mapped to its primary fingerprint.
  - `gpg.key_ids(ctx) -> dict[str, str]`: the keyring (`--list-keys`). Raises `InstallError` on failure.
  - `gpg.key_ids_in_file(ctx, path: Path) -> dict[str, str]` (`--show-keys`). Raises `InstallError`.
  - `gpg.recipients(ctx, path: Path) -> set[str]`: upper-case long key ids from `:pubkey enc packet:` lines. Raises `InstallError`.
  - `gpg.is_key_token(token: str) -> bool`: a fingerprint or long key id, never an email.
  - `Store.governing_folder(entry: str) -> str`: the folder of the nearest `.gpg-id` at or above the entry, `""` for the root.
  - `audit.Mismatch(entry: str, extra: tuple[str, ...], missing: tuple[str, ...])` (frozen dataclass).
  - `audit.Report(mismatches: list[Mismatch], unauditable: list[str])` (frozen dataclass).
  - `audit.audit(ctx: Ctx, store: Store) -> Report`.
  - `audit.fix_hint(store: Store, m: Mismatch) -> str`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/passstore/test_gpg.py`:

```python
LIST = (
    "pub:u:255:22:9CF30C2EF3DCADF8:1:::u:::scESC:::::ed25519:::0:\n"
    "fpr:::::::::7BC3DEDB389ABAEF6DA28D8D9CF30C2EF3DCADF8:\n"
    "uid:u::::1::H::A (devboost:a) <a@x>::::::::::0:\n"
    "sub:u:255:18:EB0162C1D881CB89:1::::::e:::::cv25519::\n"
    "fpr:::::::::5B11BEBBCA4F4F82E4BA376BEB0162C1D881CB89:\n"
)
PACKETS = (
    "# off=0 ctb=84 tag=1 hlen=2 plen=94\n"
    ":pubkey enc packet: version 3, algo 18, keyid EB0162C1D881CB89\n"
    "\tdata: [263 bits]\n"
    ":pubkey enc packet: version 3, algo 18, keyid 00112233aabbccdd\n"
    ":aead encrypted packet: cipher=9 aead=2 cb=16\n"
)


def test_parse_key_ids_maps_primary_and_subkeys_to_the_primary_fpr() -> None:
    fp = "7BC3DEDB389ABAEF6DA28D8D9CF30C2EF3DCADF8"
    assert gpg.parse_key_ids(LIST) == {"9CF30C2EF3DCADF8": fp, "EB0162C1D881CB89": fp}


def test_recipients_reads_packets_without_decrypting(tmp_path: Path) -> None:
    ex = RuleExecutor(rules=[(("--list-packets",), Result(0, PACKETS))])
    got = gpg.recipients(Ctx(os=FEDORA, ex=ex), tmp_path / "e.gpg")
    assert got == {"EB0162C1D881CB89", "00112233AABBCCDD"}
    assert ex.calls == [["gpg", "--batch", "--list-only", "--list-packets",
                         str(tmp_path / "e.gpg")]]
    assert not any("--decrypt" in c or "-d" in c for c in ex.calls)


def test_recipients_failure_raises(tmp_path: Path) -> None:
    ex = RuleExecutor(rules=[(("--list-packets",), Result(2))])
    with pytest.raises(InstallError):
        gpg.recipients(Ctx(os=FEDORA, ex=ex), tmp_path / "e.gpg")


def test_is_key_token() -> None:
    assert gpg.is_key_token("0x" + "a" * 16) and gpg.is_key_token("B" * 40)
    assert not gpg.is_key_token("me@example.com") and not gpg.is_key_token("ABC")
```
(Add the missing imports, such as `InstallError`, `Path`, `pytest`, `Result` and `FEDORA`, as the file needs.)

Add to `tests/passstore/test_layout.py`:

```python
def test_governing_folder_is_the_nearest_gpg_id(tmp_path: Path) -> None:
    s = Store(tmp_path)
    (tmp_path / ".gpg-id").write_text("A" * 40 + "\n", encoding="utf-8")
    (tmp_path / "harness" / "deep").mkdir(parents=True)
    (tmp_path / "harness" / ".gpg-id").write_text("B" * 40 + "\n", encoding="utf-8")
    assert s.governing_folder("web/github") == ""
    assert s.governing_folder("top") == ""
    assert s.governing_folder("harness/tg") == "harness"
    assert s.governing_folder("harness/deep/x") == "harness"
```

Create `tests/passstore/test_audit.py`:

```python
from __future__ import annotations

from pathlib import Path

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.passstore import audit
from devboost.passstore.layout import DeviceRecord, Store
from tests.passstore.fakes import RuleExecutor

FEDORA = OsInfo("fedora", "fedora", "x86_64")
FP_A = "A" * 24 + "1111111111111111"
FP_B = "B" * 24 + "2222222222222222"
SUB_A, SUB_B = "AAAA0000AAAA0000", "BBBB0000BBBB0000"
ARMOR = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nx\n"


def _keys(*pairs: tuple[str, str]) -> str:
    out = ""
    for fp, sub in pairs:
        out += (f"pub:u:255:22:{fp[-16:]}:1:::u:::scESC:::::ed25519:::0:\nfpr:::::::::{fp}:\n"
                f"sub:u:255:18:{sub}:1::::::e:::::cv25519::\nfpr:::::::::{'F' * 24}{sub}:\n")
    return out


def _packets(*subs: str) -> Result:
    return Result(0, "".join(f":pubkey enc packet: version 3, algo 18, keyid {s}\n"
                             for s in subs))


def _store(tmp_path: Path) -> Store:
    root = tmp_path / "store"
    (root / ".git").mkdir(parents=True)
    (root / "web").mkdir()
    (root / ".gpg-id").write_text(FP_A + "\n", encoding="utf-8")
    for e in ("web/ok", "web/offline"):
        (root / f"{e}.gpg").write_bytes(b"x")
    s = Store(root)
    s.write_record("devices", DeviceRecord(name="alpha", fingerprint=FP_A, os="fedora"), ARMOR)
    s.write_record("revoked", DeviceRecord(name="bravo", fingerprint=FP_B, os="macos"), ARMOR)
    return s


def _ex(store: Store) -> RuleExecutor:
    return RuleExecutor(rules=[
        (("--list-packets", str(store.root / "web/offline.gpg")), _packets(SUB_A, SUB_B)),
        (("--list-packets",), _packets(SUB_A)),
        # bravo's key is gone from the keyring (sync deleted it) — only its store file names it
        (("--show-keys", str(store.key_path("revoked", "bravo"))), Result(0, _keys((FP_B, SUB_B)))),
        (("--show-keys",), Result(0, _keys((FP_A, SUB_A)))),
        (("--list-keys",), Result(0, _keys((FP_A, SUB_A)))),
    ])


def test_offline_entry_still_encrypted_to_a_revoked_key_is_flagged(tmp_path: Path) -> None:
    s = _store(tmp_path)
    report = audit.audit(Ctx(os=FEDORA, ex=_ex(s)), s)
    assert report.mismatches == [audit.Mismatch("web/offline", ("bravo (revoked)",), ())]
    assert report.unauditable == []
    hint = audit.fix_hint(s, report.mismatches[0])
    assert "pass init " + FP_A in hint and "pass edit web/offline" in hint


def test_missing_recipient_is_flagged(tmp_path: Path) -> None:
    s = _store(tmp_path)
    (s.root / ".gpg-id").write_text(f"{FP_A}\n{FP_B}\n", encoding="utf-8")
    ex = _ex(s)
    ex.rules.insert(0, (("--list-packets",), _packets(SUB_A)))
    report = audit.audit(Ctx(os=FEDORA, ex=ex), s)
    assert {m.entry for m in report.mismatches} == {"web/ok", "web/offline"}
    # labels name registered keys, even when the name is a revoked record's
    assert all(m.missing == ("bravo (revoked)",) and m.extra == () for m in report.mismatches)


def test_unknown_recipient_stays_a_key_id(tmp_path: Path) -> None:
    s = _store(tmp_path)
    ex = _ex(s)
    ex.rules.insert(0, (("--list-packets",), _packets(SUB_A, "0123456789ABCDEF")))
    report = audit.audit(Ctx(os=FEDORA, ex=ex), s)
    assert report.mismatches[0].extra == ("0123456789ABCDEF",)


def test_forged_key_file_cannot_rename_a_recipient(tmp_path: Path) -> None:
    """A pushed .asc only vouches for its own record's fingerprint (R9)."""
    s = _store(tmp_path)
    ex = _ex(s)
    ex.rules.insert(0, (("--show-keys", str(s.key_path("revoked", "bravo"))),
                        Result(0, _keys((FP_A, SUB_B)))))
    report = audit.audit(Ctx(os=FEDORA, ex=ex), s)
    assert report.mismatches == [audit.Mismatch("web/offline", (SUB_B,), ())]


def test_email_gpg_id_folder_is_unauditable_not_flagged(tmp_path: Path) -> None:
    s = _store(tmp_path)
    (s.root / "web" / ".gpg-id").write_text("me@example.com\n", encoding="utf-8")
    report = audit.audit(Ctx(os=FEDORA, ex=_ex(s)), s)
    assert report.mismatches == [] and report.unauditable == ["web"]


def test_unreadable_entry_is_reported(tmp_path: Path) -> None:
    s = _store(tmp_path)
    ex = _ex(s)
    ex.rules.insert(0, (("--list-packets", str(s.root / "web/ok.gpg")), Result(2)))
    report = audit.audit(Ctx(os=FEDORA, ex=ex), s)
    assert audit.Mismatch("web/ok", ("<unreadable>",), ()) in report.mismatches
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/passstore/test_gpg.py tests/passstore/test_layout.py tests/passstore/test_audit.py -v`
Expected: FAIL (missing functions / module).

- [ ] **Step 3: Implement**

`gpg.py`: add these under `show_key_file`:

```python
_RECIPIENT = re.compile(r"^:pubkey enc packet:.*\bkeyid ([0-9A-Fa-f]{16})\b", re.MULTILINE)


def parse_key_ids(out: str) -> dict[str, str]:
    """Long key id of every primary key AND subkey → its primary fingerprint (`--with-colons`).

    Entries are encrypted to a subkey, so the audit needs subkey ids, not just primaries."""
    ids: dict[str, str] = {}
    primary: str | None = None
    first: str | None = None  # the primary's key id, until its fpr line names the primary
    for line in out.splitlines():
        f = line.split(":")
        if f[0] in ("pub", "sec") and len(f) > 4:
            primary, first = None, f[4].upper()
        elif f[0] == "fpr" and primary is None and first is not None and len(f) > 9:
            primary = f[9].upper()
            ids[first] = primary
            first = None
        elif f[0] in ("sub", "ssb") and primary is not None and len(f) > 4:
            ids[f[4].upper()] = primary
    return ids


def key_ids(ctx: Ctx) -> dict[str, str]:
    res = _must(_gpg(ctx, "--with-colons", "--list-keys"), "gpg --list-keys")
    return parse_key_ids(res.stdout)


def key_ids_in_file(ctx: Ctx, path: Path) -> dict[str, str]:
    res = _must(_gpg(ctx, "--with-colons", "--show-keys", str(path)),
                f"gpg --show-keys {path}")
    return parse_key_ids(res.stdout)


def recipients(ctx: Ctx, path: Path) -> set[str]:
    """Long key ids an entry is encrypted to, read from its packets: `--list-only` skips the
    decryption, so this never needs a secret key or a passphrase (no pinentry)."""
    res = _must(_gpg(ctx, "--list-only", "--list-packets", str(path)),
                f"gpg --list-packets {path}")
    return {m.upper() for m in _RECIPIENT.findall(res.stdout)}


def is_key_token(token: str) -> bool:
    """A `.gpg-id` token naming a key by fingerprint / long key id (never an email)."""
    return bool(_HEX.match(token.strip().upper().removeprefix("0X")))
```

`layout.py`: add `from pathlib import PurePosixPath` next to `Path`, and this `Store` method:

```python
    def governing_folder(self, entry: str) -> str:
        """The folder whose `.gpg-id` pass encrypts *entry* to — the nearest one at or above
        the entry's folder (`""` = the root)."""
        parts = PurePosixPath(entry).parts[:-1]
        for i in range(len(parts), 0, -1):
            folder = "/".join(parts[:i])
            if self.gpg_id_path(folder).exists():
                return folder
        return ""
```

`audit.py` (create):

```python
"""Recipient audit: is every entry encrypted to exactly the keys its `.gpg-id` names?

An entry written on a device with a stale `.gpg-id` — for instance inserted offline after a
revoke — stays encrypted to the old key set, and no re-encryption ever touched it. The audit
reads each entry's recipients from its packets (`gpg --list-only --list-packets`): nothing
is decrypted, so it never needs a passphrase and never opens pinentry.
"""

from __future__ import annotations

from dataclasses import dataclass

from devboost.core.errors import InstallError
from devboost.model import Ctx
from devboost.passstore import gpg
from devboost.passstore.layout import Kind, Store

_KINDS: tuple[Kind, ...] = ("devices", "revoked", "pending")
UNREADABLE = "<unreadable>"


@dataclass(frozen=True)
class Mismatch:
    entry: str
    extra: tuple[str, ...]    # recipients the entry's .gpg-id does not name (labels)
    missing: tuple[str, ...]  # .gpg-id keys the entry is not encrypted to (labels)


@dataclass(frozen=True)
class Report:
    mismatches: list[Mismatch]
    unauditable: list[str]  # folders whose .gpg-id names a key by email: cannot be checked


def _owners(ctx: Ctx, store: Store) -> dict[str, str]:
    """Key id → primary fingerprint: the keyring, plus the store's own key files — so a
    revoked key (deleted from the keyring by sync) is still recognised. A key file only
    vouches for the fingerprint its record names: a pushed `.asc` cannot rename a key."""
    ids = gpg.key_ids(ctx)
    for kind in _KINDS:
        for rec in store.records(kind):
            try:
                found = gpg.key_ids_in_file(ctx, store.key_path(kind, rec.name))
            except InstallError:
                continue
            for kid, fp in found.items():
                if fp == rec.fingerprint.upper():
                    ids.setdefault(kid, fp)
    return ids


def _labels(store: Store) -> dict[str, str]:
    out: dict[str, str] = {}
    for kind in _KINDS:
        suffix = "" if kind == "devices" else f" ({'revoked' if kind == 'revoked' else 'pending'})"
        for rec in store.records(kind):
            out.setdefault(rec.fingerprint.upper(), f"{rec.name}{suffix}")
    return out


def audit(ctx: Ctx, store: Store) -> Report:
    owners = _owners(ctx, store)
    labels = _labels(store)
    mismatches: list[Mismatch] = []
    unauditable: set[str] = set()
    for entry in store.entries():
        folder = store.governing_folder(entry)
        tokens = store.gpg_ids(folder)
        if not tokens or not all(gpg.is_key_token(t) for t in tokens):
            unauditable.add(folder or ".")
            continue
        try:
            got = gpg.recipients(ctx, store.root / f"{entry}.gpg")
        except InstallError:
            mismatches.append(Mismatch(entry, (UNREADABLE,), ()))
            continue
        fps = {owners.get(kid, kid) for kid in got}  # an unknown key stays a bare key id
        extra = sorted(labels.get(fp, fp) for fp in fps
                       if not any(gpg.matches_fingerprint(t, fp) for t in tokens))
        missing = sorted(labels.get(t.upper(), t) for t in tokens
                         if not any(gpg.matches_fingerprint(t, fp) for fp in fps))
        if extra or missing:
            mismatches.append(Mismatch(entry, tuple(extra), tuple(missing)))
    return Report(mismatches, sorted(unauditable))


def fix_hint(store: Store, m: Mismatch) -> str:
    """R11: `pass init` with the same ids re-encrypts exactly the entries that differ; a
    revoked recipient could read this entry's old ciphertext, so its secret must change."""
    folder = store.governing_folder(m.entry)
    ids = " ".join(store.gpg_ids(folder))
    init = f"pass init {'-p ' + folder + ' ' if folder else ''}{ids}"
    if any(x.endswith("(revoked)") for x in m.extra):
        return f"{init}, then change the secret: pass edit {m.entry}"
    return init
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/passstore -q && uv run ruff check && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/passstore/ engine/tests/passstore/
git commit -m "feat(pass): recipient audit from packet lists (no decrypt, no pinentry)"
```

---

### Task 5: audit wiring: sync notices, `doctor`, `devboost pass audit` + status

**Files:**
- Modify: `engine/src/devboost/passstore/sync.py`, `engine/src/devboost/cli/doctor.py`, `engine/src/devboost/cli/pass_cmd.py`
- Test: `engine/tests/passstore/test_sync.py`, `engine/tests/cli/test_doctor_resources.py`, `engine/tests/cli/test_pass_cli.py`

**Interfaces:**
- Consumes: `audit.audit`, `audit.Report`, `audit.Mismatch`, `audit.fix_hint` (Task 4).
- Produces: `_State.audited_head: str | None = None`, `_State.audit_flagged: list[str] = []`. Doctor check `pass-recipients`. CLI command `devboost pass audit`. A `recipients:` line in `devboost pass status`.

- [ ] **Step 1: Write the failing tests**

`tests/passstore/test_sync.py`: import `audit` from `devboost.passstore`, then add:

```python
def _audited(monkeypatch: pytest.MonkeyPatch, *reports: audit.Report) -> list[int]:
    calls: list[int] = []
    it = iter(reports)

    def fake(ctx: Ctx, store: Store) -> audit.Report:
        calls.append(1)
        return next(it)

    monkeypatch.setattr(audit, "audit", fake)
    return calls


def test_sync_audits_when_head_moves_and_notifies_new_mismatches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = _store(tmp_path)
    bad = audit.Report([audit.Mismatch("web/x", ("bravo (revoked)",), ())], [])
    calls = _audited(monkeypatch, bad, bad)
    ex = _ex((("rev-parse", "HEAD"), Result(0, "h1\n")))
    assert sync.run(_ctx(ex), s, "desk").status == "ok"
    notes = [c for c in _notifications(ex) if "recipients" in c[2]]
    assert len(notes) == 1 and "web/x" in notes[0][3]
    assert "devboost pass audit" in notes[0][3]
    sync.run(_ctx(ex), s, "desk")  # same HEAD → no second audit
    assert len(calls) == 1
    ex2 = _ex((("rev-parse", "HEAD"), Result(0, "h2\n")))
    sync.run(_ctx(ex2), s, "desk")  # HEAD moved, same findings → audited, not re-announced
    assert len(calls) == 2
    assert not [c for c in _notifications(ex2) if "recipients" in c[2]]


def test_sync_audit_failure_is_logged_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = _store(tmp_path)

    def boom(ctx: Ctx, store: Store) -> audit.Report:
        raise InstallError("pass-store", "gpg --list-keys", 2)

    monkeypatch.setattr(audit, "audit", boom)
    ex = _ex((("rev-parse", "HEAD"), Result(0, "h1\n")))
    assert sync.run(_ctx(ex), s, "desk").status == "ok"


def test_push_only_sync_never_audits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    s = _store(tmp_path)
    calls = _audited(monkeypatch)
    sync.run(_ctx(_ex((("rev-parse", "HEAD"), Result(0, "h1\n")))), s, "desk", push_only=True)
    assert calls == []
```
(Import `InstallError` from `devboost.core.errors`. The `_notifications` helper already exists. If the exact title index in the notify-send argv differs, index by `c[2]` for the title and `c[3]` for the body: `["notify-send", "--app-name=devboost", title, body]`.)

`tests/cli/test_doctor_resources.py`:

```python
def test_doctor_flags_entries_with_wrong_recipients(tmp_path: Path) -> None:
    _pass_store(tmp_path)
    packets = Result(0, ":pubkey enc packet: version 3, algo 18, keyid 0123456789ABCDEF\n")
    ex = FakeExecutor(present={"curl", "age"}, scripts={"gpg": packets})
    out = _checks(tmp_path, ex)
    assert out["pass-recipients"][0] is False
    assert "web/github" in out["pass-recipients"][1]
    assert "pass init" in out["pass-recipients"][1]


def test_doctor_recipients_ok_when_entries_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from devboost.passstore import audit

    _pass_store(tmp_path)
    monkeypatch.setattr(audit, "audit", lambda ctx, store: audit.Report([], []))
    out = _checks(tmp_path, FakeExecutor(present={"curl", "age"}))
    assert out["pass-recipients"][0] is True
```
(Check how `_pass_store` makes doctor find the store: `pass_paths.store_dir()` honours `PASSWORD_STORE_DIR`. If the existing rotation tests rely on a monkeypatched env, follow the same pattern.)

`tests/cli/test_pass_cli.py`:

```python
def test_audit_lists_mismatches_and_exits_1(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    from devboost.passstore import audit

    _use(monkeypatch)
    m = audit.Mismatch("web/x", ("bravo (revoked)",), ())
    monkeypatch.setattr(audit, "audit", lambda ctx, s: audit.Report([m], ["legacy"]))
    res = runner.invoke(app, ["pass", "audit"])
    assert res.exit_code == 1
    assert "web/x" in res.output and "bravo (revoked)" in res.output
    assert "pass edit web/x" in res.output and "legacy" in res.output


def test_audit_clean_exits_0(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    from devboost.passstore import audit

    _use(monkeypatch)
    monkeypatch.setattr(audit, "audit", lambda ctx, s: audit.Report([], []))
    res = runner.invoke(app, ["pass", "audit"])
    assert res.exit_code == 0 and "every entry matches" in res.output


def test_status_shows_recipient_count(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    from devboost.passstore import audit

    _use(monkeypatch)
    m = audit.Mismatch("web/x", ("Z" * 16,), ())
    monkeypatch.setattr(audit, "audit", lambda ctx, s: audit.Report([m], []))
    res = runner.invoke(app, ["pass", "status"])
    assert "recipients: 1 entries differ from their .gpg-id" in res.output
```
Also add `"audit"` to the verb tuple in `test_pass_subapp_is_registered`.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/passstore/test_sync.py tests/cli/test_doctor_resources.py tests/cli/test_pass_cli.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

`sync.py`: import `audit` (`from devboost.passstore import audit, enroll, git, gpg, notify`). In `_State` add:

```python
    # Recipient audit (R10): HEAD last audited, and entries already announced.
    audited_head: str | None = None
    audit_flagged: list[str] = []
```

Add:

```python
def _audit(ctx: Ctx, store: Store, state: _State) -> None:
    """R10: after a pull that moved HEAD, check entries against their .gpg-id; announce only
    entries not flagged before. Never raises (a sync problem must not block anything)."""
    head = git.head(ctx, store.root)
    if not head or head == state.audited_head:
        return
    try:
        report = audit.audit(ctx, store)
    except DevbootError as exc:
        _log(f"recipient audit failed: {exc}")
        return
    state.audited_head = head
    flagged = sorted(m.entry for m in report.mismatches)
    new = [e for e in flagged if e not in state.audit_flagged]
    state.audit_flagged = flagged
    if not new:
        return
    _log(f"recipient audit: {len(flagged)} entries differ from their .gpg-id: "
         f"{', '.join(flagged)}")
    notify.native(ctx, "pass: entries with the wrong recipients",
                  f"{notify.clean(', '.join(new), 200)} — encrypted to other keys than their "
                  ".gpg-id. Run: devboost pass audit")
```

In `_sync`, inside the final `if not push_only:` block, after `_tripwire(ctx, store, acc, state)`, call `_audit(ctx, store, state)`.

`doctor.py`: `from devboost.passstore import audit as pass_audit`. At the end of `_pass_state`, build:

```python
    report = pass_audit.audit(ctx, store)
    if report.mismatches:
        rec = (f"{len(report.mismatches)} entries are not encrypted to exactly their .gpg-id "
               "keys — " + "; ".join(f"{m.entry}: {pass_audit.fix_hint(store, m)}"
                                     for m in report.mismatches))
    else:
        rec = "every entry is encrypted to exactly its .gpg-id keys"
    if report.unauditable:
        rec += (f" (not checked — .gpg-id names keys by email: "
                f"{', '.join(report.unauditable)})")
    return [Check("pass", True, state), Check("pass-rotation", not todo, rot),
            Check("pass-recipients", not report.mismatches, rec)]
```

`pass_cmd.py`: `from devboost.passstore import audit as audit_flow`. In `status`, inside the `try`, add `report = audit_flow.audit(ctx, store)`, and after the rotation line print:

```python
    typer.echo(f"recipients: {len(report.mismatches)} entries differ from their .gpg-id")
```

New command:

```python
@app.command(name="audit")
def audit_cmd() -> None:
    """Entries not encrypted to exactly their .gpg-id keys (read from packets; no decrypt)."""
    ctx, store = _ctx(), _store()
    _need_store(store)
    try:
        report = audit_flow.audit(ctx, store)
    except DevbootError as exc:
        _fail(exc)
    for folder in report.unauditable:
        typer.echo(f"not checked: {folder}/.gpg-id names keys by email")
    if not report.mismatches:
        typer.echo("every entry matches its .gpg-id")
        return
    for m in report.mismatches:
        typer.echo(f"{m.entry}\n  extra:   {', '.join(m.extra) or '-'}\n"
                   f"  missing: {', '.join(m.missing) or '-'}\n"
                   f"  fix:     {audit_flow.fix_hint(store, m)}")
    raise typer.Exit(1)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -q && uv run ruff check && uv run mypy`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/passstore/sync.py engine/src/devboost/cli/ engine/tests/
git commit -m "feat(pass): recipient audit in sync, doctor and devboost pass audit/status"
```

---

### Task 6: `pass` + `pass-store` on macOS (pinentry-mac, family, host, profile, contract)

**Files:**
- Modify: `engine/src/devboost/modules/pass_store.py`, `engine/src/devboost/cli/host.py`, `profiles.toml` (repo root), `engine/tests/core/test_macos_contract.py`
- Test: `engine/tests/modules/test_pass_store.py`, `engine/tests/cli/test_host.py`

**Interfaces:**
- Produces: `pass_store.pinentry_mac(os_info: OsInfo) -> str`, `pass_store.MAC_FORMULAE: dict[str, str]` (command → formula), `agent_settings(os_info)` (macOS adds `pinentry-program`), `Pass.portable = True`, `PassStore.families` including `"macos"`, `PassStore.portable = True`. `host.LINUX_ONLY` without `"pass"`.

- [ ] **Step 1: Write the failing tests**

`tests/modules/test_pass_store.py` (add `MAC = OsInfo("macos", "macos", "aarch64")` and `MAC_INTEL = OsInfo("macos", "macos", "x86_64")`):

```python
def test_agent_settings_per_os() -> None:
    from devboost.modules.pass_store import agent_settings

    ttls = {"default-cache-ttl": "28800", "max-cache-ttl": "86400"}
    assert agent_settings(FEDORA) == ttls
    assert agent_settings(MAC) == {**ttls, "pinentry-program": "/opt/homebrew/bin/pinentry-mac"}
    assert agent_settings(MAC_INTEL)["pinentry-program"] == "/usr/local/bin/pinentry-mac"


def test_pass_on_macos_brews_missing_formulae_and_sets_pinentry(tmp_path: Path) -> None:
    conf = tmp_path / "home" / ".gnupg" / "gpg-agent.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text("pinentry-program /usr/local/bin/pinentry-tty\n", encoding="utf-8")
    ex = RuleExecutor(present={"gpg"})  # pass + pinentry-mac missing
    Pass().install(Ctx(os=MAC, ex=ex))
    brew = [c for c in ex.calls if c[0] == "brew" and "install" in c]
    assert brew and brew[0][-2:] == ["pass", "pinentry-mac"]
    assert "gnupg" not in brew[0]
    assert conf.read_text(encoding="utf-8") == (
        "pinentry-program /opt/homebrew/bin/pinentry-mac\n"
        "default-cache-ttl 28800\nmax-cache-ttl 86400\n"
    )
    assert ["gpgconf", "--reload", "gpg-agent"] in ex.calls
    ready = RuleExecutor(present={"pass", "gpg", "pinentry-mac"})
    assert Pass().verify(Ctx(os=MAC, ex=ready))
    assert not Pass().verify(Ctx(os=MAC, ex=RuleExecutor(present={"pass", "gpg"})))


def test_pass_on_linux_still_installs_only_pass(tmp_path: Path) -> None:
    ex = RuleExecutor(present=set())
    Pass().install(Ctx(os=FEDORA, ex=ex))
    installs = [c for c in ex.calls if "install" in c]
    assert installs and installs[0][-1] == "pass" and "pinentry-mac" not in installs[0]


def test_pass_store_runs_on_macos() -> None:
    assert "macos" in PassStore.families and PassStore.portable and Pass.portable
```
(The brew argv shape is `["brew", "install", "--formula", "-y", *pkgs]`; `pkg.install` may also run `brew update` first. Assert on the install call as shown. The Linux path may be `sudo dnf install -y pass`, and `installs[0][-1] == "pass"` holds either way.)

`tests/cli/test_host.py`: change `test_linux_only_commands_refused_on_macos` to loop over `("installer", "accounts", "brain")`, and add:

```python
def test_pass_is_allowed_on_macos() -> None:
    assert plat.invocation_error(MAC, "pass", euid=501) is None
```

`tests/core/test_macos_contract.py`: delete `"pass",` from `KNOWN_GAPS`.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_pass_store.py tests/cli/test_host.py tests/core/test_macos_contract.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

`pass_store.py`:

```python
#: Homebrew's default prefix per arch — Apple Silicon /opt/homebrew, Intel /usr/local (R5).
_BREW_PREFIX: dict[str, str] = {"aarch64": "/opt/homebrew", "x86_64": "/usr/local"}
#: macOS: command → Homebrew formula (R6). pinentry-mac asks for the passphrase in a dialog
#: that can keep it in the login keychain.
MAC_FORMULAE: dict[str, str] = {"pass": "pass", "gpg": "gnupg", "pinentry-mac": "pinentry-mac"}


def pinentry_mac(os_info: OsInfo) -> str:
    return f"{_BREW_PREFIX.get(os_info.arch, '/opt/homebrew')}/bin/pinentry-mac"


def agent_settings(os_info: OsInfo) -> dict[str, str]:
    """The gpg-agent.conf keys dev-boost manages: cache TTLs everywhere; on macOS also the
    pinentry-mac program (a managed key — a different pinentry-program is replaced)."""
    out = dict(AGENT_TTLS)
    if os_info.family == "macos":
        out["pinentry-program"] = pinentry_mac(os_info)
    return out
```

`Pass`: update the `description` to "pass password-store CLI + gpg-agent passphrase cache (8 h idle / 24 h max; pinentry-mac on macOS).", then add:

```python
    portable = True  # install is OS-aware: brew formulae + pinentry-mac on macOS

    @staticmethod
    def _needed(ctx: Ctx) -> dict[str, str]:
        return MAC_FORMULAE if ctx.os.family == "macos" else {"pass": "pass"}

    def verify(self, ctx: Ctx) -> bool:
        return (all(ctx.ex.which(c) for c in self._needed(ctx))
                and agent_conf_ok(self._conf(), agent_settings(ctx.os)))

    def install(self, ctx: Ctx) -> None:
        missing = [f for c, f in self._needed(ctx).items() if not ctx.ex.which(c)]
        if missing:
            pkg.install(ctx, *missing)
        # … the ensure_agent_conf + gpgconf --reload block stays as it is
```

`PassStore`: `families: ClassVar[tuple[str, ...]] = ("fedora", "debian", "arch", "macos")`, `portable = True`. Remove the "macOS scheduling (launchd) lands in P2" comment.

`cli/host.py`: `LINUX_ONLY: frozenset[str] = frozenset({"installer", "accounts", "brain"})`.

`profiles.toml` line `macos = ["terminal"]` becomes `macos = ["terminal", "pass", "pass-store"]`. Keep any comment on that line.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -q && uv run ruff check && uv run mypy`
Expected: PASS, including `test_macos_contract.py` (both tests).

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/modules/pass_store.py engine/src/devboost/cli/host.py profiles.toml \
  engine/tests/
git commit -m "feat(pass): pass and pass-store on macOS with pinentry-mac and gpg-agent TTLs"
```

---

### Task 7: unattended pinentry guard for `pass` readers

**Files:**
- Modify: `engine/src/devboost/modules/_pass.py`
- Test: `engine/tests/modules/test_pass_store.py`

**Interfaces:**
- Produces: `_pass.NO_PINENTRY = "--pinentry-mode error"`. `pass_show(ctx, entry, *, who)` keeps its signature. When `_credentials.is_interactive()` is false, the `pass show` call carries env `PASSWORD_STORE_GPG_OPTS` ending in `--pinentry-mode error`. When interactive, it carries no env override.

- [ ] **Step 1: Write the failing tests**

```python
def test_unattended_pass_show_never_opens_pinentry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")
    monkeypatch.setenv("PASSWORD_STORE_GPG_OPTS", "--armor")
    ex = RuleExecutor(present={"pass"}, rules=[(("show",), Result(0, "s3cret\n"))])
    assert pass_show(Ctx(os=FEDORA, ex=ex), "web/x", who="t") == "s3cret\n"
    assert ex.envs[-1] == {"PASSWORD_STORE_GPG_OPTS": "--armor --pinentry-mode error"}


def test_interactive_pass_show_may_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    from devboost.modules import _credentials

    monkeypatch.delenv("DEVBOOST_NONINTERACTIVE", raising=False)
    monkeypatch.setattr(_credentials, "is_interactive", lambda: True)
    ex = RuleExecutor(present={"pass"}, rules=[(("show",), Result(0, "s\n"))])
    pass_show(Ctx(os=FEDORA, ex=ex), "web/x", who="t")
    assert ex.envs[-1] == {}


def test_unattended_uncached_read_is_skipped_with_a_hint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")
    ex = RuleExecutor(present={"pass"}, rules=[(("show",), Result(2))])
    assert pass_show(Ctx(os=FEDORA, ex=ex), "web/x", who="t") is None
    out = capsys.readouterr()
    assert "passphrase is not cached" in out.out + out.err
```
(If `log.warn` writes through a rich console that `capsys` can't see, assert the message with the logging capture this test module already uses for other `log.warn` checks. Search the file for `log.` monkeypatching.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_pass_store.py -k pass_show -v`
Expected: FAIL.

- [ ] **Step 3: Implement.** In `_pass.py`:

```python
import os

from devboost.core import log
from devboost.model import Ctx
from devboost.modules import _credentials as creds_src

#: Unattended reads never open a passphrase prompt nobody answers (pinentry-mac is a GUI
#: dialog; R12): gpg still uses a cached passphrase, and without one it fails at once.
NO_PINENTRY = "--pinentry-mode error"


def _env(interactive: bool) -> dict[str, str] | None:
    if interactive:
        return None
    opts = os.environ.get("PASSWORD_STORE_GPG_OPTS", "").strip()
    return {"PASSWORD_STORE_GPG_OPTS": f"{opts} {NO_PINENTRY}".strip()}


def pass_show(ctx: Ctx, entry: str, *, who: str) -> str | None:
    if not ctx.ex.which("pass"):
        log.skip(f"{who}: pass not installed — skipping {entry}")
        return None
    interactive = creds_src.is_interactive()
    res = ctx.ex.run(["pass", "show", entry], env=_env(interactive))
    if not res.ok or not res.stdout.strip():
        hint = "" if interactive else (
            ", or its passphrase is not cached — unlock once in a terminal: "
            f"`pass show {entry}`")
        log.warn(f"{who}: `pass show {entry}` unavailable (missing, or this device is not "
                 f"approved yet — see `devboost pass status`{hint}) — skipping")
        return None
    return res.stdout
```
(Check for an import cycle: `_credentials` must not import `_pass`. It doesn't today.)

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -q && uv run ruff check && uv run mypy`
Expected: PASS. Reader-module tests (claude/codex/pi/herdr) record argv only, so they are unaffected.

- [ ] **Step 5: Commit**

```bash
git add engine/src/devboost/modules/_pass.py engine/tests/modules/test_pass_store.py
git commit -m "fix(pass): unattended pass reads never open pinentry (--pinentry-mode error)"
```

---

### Task 8: real-gpg end-to-end: offline insert after a revoke, and the guard

**Files:**
- Modify: `engine/tests/passstore/test_integration_gpg.py`

**Interfaces:**
- Consumes: `audit.audit`, `audit.Mismatch` (Task 4), `sync.run` (Task 5 audit), `_pass.pass_show` (Task 7), and the existing `make_device`, `origin`, `_genesis` and `_request` fixtures/helpers.

- [ ] **Step 1: Write the tests** (append; import `audit` from `devboost.passstore` and `pass_show` from `devboost.modules._pass`):

```python
def test_offline_insert_after_revoke_is_flagged_and_fixed(
    origin: str, make_device: MakeDevice
) -> None:
    """Carry-over I5: bravo, offline, still encrypts to its stale .gpg-id after the revoke."""
    a = _genesis(origin, make_device)
    b = make_device("bravo")
    _request(b, origin)
    approve.approve(a.ctx, a.store, "alpha", "bravo", lambda r: True)
    assert sync.run(b.ctx, b.store, "bravo").status == "ok"  # imports alpha's key
    assert audit.audit(a.ctx, a.store).mismatches == []

    assert approve.revoke(a.ctx, a.store, "alpha", "bravo", lambda r: True) is not None
    # bravo has not pulled the revoke: its .gpg-id still lists both keys
    assert b.pass_("insert", "-m", "web/offline", stdin="late\n").ok
    assert sync.run(b.ctx, b.store, "bravo").status == "ok"  # rebased onto the revoke, pushed
    assert sync.run(a.ctx, a.store, "alpha").status == "ok"  # also deletes bravo's pubkey

    report = audit.audit(a.ctx, a.store)
    assert report.mismatches == [audit.Mismatch("web/offline", ("bravo (revoked)",), ())]
    # R11: `pass init` with the same ids re-encrypts exactly the differing entry
    assert a.pass_("init", *a.store.gpg_ids()).ok
    assert audit.audit(a.ctx, a.store).mismatches == []


def test_unattended_read_uses_the_cache_and_never_prompts(
    origin: str, make_device: MakeDevice, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R12 with real gpg: a passphrase-protected key, read unattended."""
    a = make_device("alpha")
    enroll.ensure_clone(a.ctx, a.store, origin)
    enroll.ensure_access(a.ctx, a.store, "alpha", interactive=True, passphrase="pw")
    assert a.pass_("insert", "-m", "web/k", stdin="guarded\n").ok
    dev_ex = a.ctx.ex
    assert isinstance(dev_ex, _DeviceEx)
    gnupg = str(dev_ex.gnupg)
    subprocess.run(["gpgconf", "--homedir", gnupg, "--reload", "gpg-agent"], check=True)
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")
    monkeypatch.setenv("PASSWORD_STORE_DIR", str(a.store.root))
    assert pass_show(a.ctx, "web/k", who="t") is None  # uncached: fails fast, skipped

    entry = str(a.store.root / "web" / "k.gpg")
    unlock = a.ctx.ex.run(["gpg", "--batch", "--pinentry-mode", "loopback",
                           "--passphrase", "pw", "--decrypt", entry])
    assert unlock.ok  # caches the passphrase in the agent
    assert pass_show(a.ctx, "web/k", who="t") == "guarded\n"
```

- [ ] **Step 2: Run**

Run: `uv run pytest tests/passstore/test_integration_gpg.py -v`
Expected: PASS on this Mac (brew gpg + pass) and on CI (ubuntu, `apt-get install pass`). If `ensure_access(..., passphrase="pw")` needs loopback allowed, note that gpg ≥ 2.1.12 allows it by default. Don't write any agent conf. If a step fails, debug it with superpowers:systematic-debugging. Don't weaken an assertion.

- [ ] **Step 3: Full gate, then commit**

```bash
uv run pytest -q && uv run ruff check && uv run mypy
git add engine/tests/passstore/test_integration_gpg.py
git commit -m "test(pass): real-gpg audit of an offline insert after revoke; pinentry guard"
```

---

### Task 9: documentation

**Files:**
- Modify: `docs/pass.md`, `CHANGELOG.md`, `docs/superpowers/specs/2026-09-18-pass-multi-device-design.md`, plus any doc that still calls `devboost pass` Linux-only (`grep -rn "Linux-only until P2\|until P2" docs README.md`)

- [ ] **Step 1: `docs/pass.md`**
  - Replace the "`devboost pass` itself is **Linux-only until P2** …" paragraph. It now says the store works on Linux and macOS, and on a Mac the `macos` profile installs `pass` + `pass-store`.
  - Under **Model → Passphrase**, add macOS: Homebrew `pass`, `gnupg`, `pinentry-mac`. `gpg-agent.conf` gets `pinentry-program /opt/homebrew/bin/pinentry-mac` (`/usr/local` on Intel). pinentry-mac's "Save in Keychain" keeps the passphrase in the login keychain. `pinentry-program` is managed: a custom value is replaced on the next install.
  - Under **Sync**: macOS uses the launchd agent `dev.devboost.pass-sync` (`~/Library/LaunchAgents/dev.devboost.pass-sync.plist`, every 900 s, no run-at-load; a missed interval runs on wake). Notifications use `osascript` (Notification Center). `pass-store` counts the scheduler installed only when the agent is loaded (Linux: the timer is enabled and active) and points at the current `devboost`. Rewriting a unit runs `systemctl --user daemon-reload`.
  - New section **Recipient audit** (before "Revoke a device"): what it catches (an entry inserted offline after a revoke, or before an approval reached that device). It reads packets only (`gpg --list-only --list-packets`, no passphrase). It is reported by `devboost pass audit`, `devboost doctor` (`pass-recipients`), `devboost pass status`, and a sync notification when new entries are flagged. The fix is `pass init [-p <folder>] <the .gpg-id keys>` (it re-encrypts only the entries that differ), and when a revoked device was a recipient, also `pass edit <entry>`. Folders whose `.gpg-id` names keys by email are not checked.
  - New subsection **Unattended runs** (under Sync or Model): outside a terminal, modules reading `pass` use `--pinentry-mode error`. A cached passphrase works. Otherwise the secret is skipped with a hint to run `pass show <entry>` once in a terminal.
  - Commands table: add `devboost pass audit`.
- [ ] **Step 2: `CHANGELOG.md` under `[Unreleased]`**, merged into the existing headings (no new duplicate headings):
  - `### Added`: **`pass` multi-device on macOS (P2)**: pinentry-mac + gpg-agent TTLs, launchd sync agent `dev.devboost.pass-sync`, Notification Center notices, `devboost pass` allowed on macOS, `pass`/`pass-store` in the `macos` profile; **recipient audit** (`devboost pass audit`, doctor `pass-recipients`, sync notice). Also edit the P1 bullet so it no longer says "Linux-only until P2".
  - `### Fixed` (create it once if absent): systemd user units are daemon-reloaded after a rewrite. `pass-store` verify checks that the scheduler is loaded/enabled, not just that the file exists. Unattended `pass` reads never open pinentry.
  - `### Docs`: docs/pass.md macOS + audit.
- [ ] **Step 3: Spec.** In the rollout table, the P2 row notes gain `plan: [2026-09-19-pass-p2-macos](../plans/2026-09-19-pass-p2-macos.md)`. Under "P1 notes → Carried to P2", add "(done in P2: `devboost pass audit`)".
- [ ] **Step 4: Check and commit**

```bash
grep -rn "Linux-only until P2\|until P2" docs README.md CHANGELOG.md || true   # expect nothing
awk 'length > 100 && FILENAME ~ /pass.md/ {print FILENAME": "FNR}' docs/pass.md
git add docs CHANGELOG.md
git commit -m "docs(pass): macOS (pinentry-mac, launchd, notifications) and the recipient audit"
```

---

## Spec coverage

| Requirement | Task |
|---|---|
| P2: pinentry-mac (+ keychain), gpg-agent TTLs on macOS | 6 |
| P2: launchd sync agent `dev.devboost.pass-sync`, 15 min | 3 |
| P2: native notifications (osascript) | 1 |
| Carry-over: remove `pass` from `LINUX_ONLY`; `PassStore.families += macos` | 6 |
| Carry-over: recipient audit via `gpg --list-only --list-packets` | 4, 5, 8 |
| Carry-over: scheduler checks loaded/enabled state | 3 |
| Carry-over: systemd daemon-reload after rewriting units | 2 |
| Carry-over: P-R16 unattended pinentry guard | 7, 8 |
| Contract test green; `pass` removed from `KNOWN_GAPS` | 6 |
| Docs: `docs/pass.md` macOS, CHANGELOG `[Unreleased]` | 9 |
