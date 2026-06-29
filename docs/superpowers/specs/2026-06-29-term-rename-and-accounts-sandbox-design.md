# Design — `term` rename + selection UX, and the `accounts` sandbox-user module

**Date:** 2026-06-29
**Status:** Design approved (brainstorm + grill complete); pending written-spec review → implementation plan.
**Builds on:** the current Python engine (`engine/`, spec 014 seams: `Ctx`, `Executor`, `core/registry`, `exec/primitives`, `OsMap`). Additive; does not block on 014 completion.

This document covers two independent deliverables that emerged from one session:

1. **Part 1 (small):** rename the `terminal` command to `term` and add a generalized app-selection UX (`--all`/`--no-all` checklist, `--app`).
2. **Part 2 (large):** a new `accounts` command that creates and manages **self-contained, resource-capped Linux users** ("sandbox users") on Fedora and Ubuntu.

They share no code except the engine seams and can be implemented and shipped separately. Part 1 is a quick early slice; Part 2 is the bulk.

---

## Part 1 — `term` command + generalized selection UX

### 1.1 Motivation

The `terminal` command reads like "open a terminal" and is a thin wrapper that installs the `terminal` *profile* (≈32 curated CLI/shell tools). We want (a) a clearer name and (b) the ability to install a subset interactively or a single tool directly — reused across the profile-installing commands.

### 1.2 Decisions

- **Rename `terminal` → `term`.** Clean rename, **no back-compat alias**: the tool is pre-1.0, `install terminal` still works (the *profile* token is unchanged, so `get.sh`'s `install terminal devtools` form is unaffected), and the only references to the *command* are `cli/app.py` and `docs/architecture.md` (updated here). The `terminal` *profile* name stays. No `terminal` module exists, so no profile/module name collision.
- **Generalized selection helper** applied to `term`, `devtools`, and `install` (all funnel through `_run` / `_order`):

  ```
  select_modules(expanded: list[str], *, all_: bool, apps: list[str]) -> list[str]
  ```

  sits between `_order` (expand+toposort) and `_run` (build plan).

- **`-a / --all`** boolean, **default `True`** (Typer auto-provides `--no-all`).
- **`--no-all`** → `questionary.checkbox` over the expanded module set, **grouped by `module.category`** using `questionary.Separator` section headers (Terminal / GUI apps / Editors / Hardware / System / …). Modules with an empty `category` fall into an **"Other"** bucket. Every item is **preselected** (`Choice(value=name, checked=True)`).
- **Dependency closure (correctness):** after the user's selection, compute the transitive `requires`-closure and **auto-include** any missing dependencies, logging `"+N required dependencies added"`. The toposort requires deps to be present; the selection must never produce an invalid plan.
- **`--app NAME`** installs a single module; **repeatable** (`--app git --app fzf`). Selection is drawn from the expanded set of the named profile(s). Unknown name → `difflib.get_close_matches` against the expanded set → `"unknown app 'gti' — did you mean: git?"` and exit non-zero. `--app` **overrides** `--all`.
- **No live in-checklist search.** `questionary.checkbox` has no built-in search filter (only the single-select `autocomplete` prompt does); a searchable multi-select needs a custom `prompt_toolkit` widget, which is not worth it for a ~32-item, category-grouped list.

### 1.3 Composition / interaction

- `install` already accepts a profiles list; `install <profiles> --no-all` shows the grouped checklist over the union of those profiles' expanded modules. `--all` (default) installs the full expansion. `--app` selects specific modules from that expansion.
- Behaviour is identical across `term`, `devtools`, `install` because the mechanism is one shared helper.

### 1.4 Testing

- Unit tests for `select_modules`: all/none/subset selection, `--app` single & repeated, typo suggestion, dependency-closure auto-inclusion, "Other" bucket for empty category.
- The interactive `questionary.checkbox` call is wrapped behind a thin seam so tests inject the selection without a TTY (mirroring how `media/wizard.py` is structured).

---

## Part 2 — `accounts`: self-contained, resource-capped sandbox users

### 2.1 Motivation & use case

Concretely: on a VPS that already has `root` and a default user (e.g. `ubuntu`), create an extra account such as `dev` that is **walled off** — its own RAM/CPU/disk/process budget — so it cannot starve the box or other users, and so it can be **disabled or wiped cleanly in one move** without leaving residue across the system. Isolation and clean blast-radius, not multi-tenant fairness. A secondary use is a contained account to run untrusted code or a long-running agent under a hard cap.

### 2.2 Architecture (mirrors the `media/` subpackage + `exec/primitives/` conventions)

| Piece | Path | Role |
|---|---|---|
| Typed config | `accounts/config.py` | Pydantic `ManagedUser` model ↔ `users.toml`; validated → frozen public dataclass (the `media/` convention) |
| Reconciler | `accounts/reconcile.py` | idempotent desired-state apply for one user; the only orchestrator |
| Interactive form | `accounts/form.py` | `questionary` create/edit form (seam-wrapped for tests) |
| Low-level ops | `exec/primitives/usermgmt.py` | new primitive (peer of `pkg`/`systemd`/`config`): `ensure_user`, `lock`/`unlock`, `delete`, `set_slice`/`clear_slice`, `set_quota`/`clear_quota`, `set_sudoers`/`clear_sudoers`, `add_admin_group`/`remove_admin_group`, `enable_linger`/`disable_linger`. **All side effects via `ctx.ex.run(..., sudo=True)`** — never `subprocess`. |
| Demoting executor | `exec/executor.py` (new class) | `DemotingExecutor(target_user)` for `--with-profile` bootstrap (see 2.7) |
| CLI | `cli/accounts.py` | Typer sub-app, registered via `app.add_typer(accounts.app, name="accounts")` |

**Integration boundary (deliberate):**
1. **Standalone CLI, never a registered `Module`.** Not `@register`-ed → never appears in `install full` / `verify` / `diff` / the plan toposort. Account management is imperative admin, outside the declarative install pipeline. `accounts apply` is its own reconcile entrypoint.
2. **Registry-scoped:** only ever touches users listed in `users.toml`. Never modifies `root`, `ubuntu`, or any pre-existing account. `accounts create dev` when `dev` already exists but is not in the registry **refuses** unless `--adopt` is passed.
3. **Owns only its own artifacts:** the admin-group membership bit, the `devboost-<user>` sudoers drop-in, the `50-devboost.conf` slice drop-in, and the user's quota/subvolume — all namespaced. It does **not** strip the user from unrelated groups (e.g. `docker`) or touch state it didn't create.

### 2.3 Config: `/etc/devboost/users.toml`

`settings.root` is the repo root in source mode but `_MEIPASS` (read-only) in the frozen binary, so a **writable** registry cannot live there. It lives at **`/etc/devboost/users.toml`** (dir `0755`, file `0644`, root-owned), overridable via **`DEVBOOST_USERS_PATH`** (mirrors the `system` module's `DEVBOOST_*` override pattern; tests redirect to `tmp_path`). It is system-wide machine state, so `/etc` — not XDG/`~/.config`.

```toml
[users.dev]
enabled = true
shell = "/bin/bash"          # or "/usr/sbin/nologin" when lock_shell
lock_shell = false
linger = false               # loginctl enable-linger for contained 24/7 background work
privilege = "none"           # none | full | nopasswd | allowlist  (default none)
sudo_commands = []           # absolute paths only; used when privilege = "allowlist"
ram = "4G"                   # MemoryMax; MemoryHigh auto-derived ≈ 90%; null = unset
cpu = "50%"                  # CPUQuota; >100% spans multiple cores; null = unset
tasks = 200                  # TasksMax; null = unset
disk = "20G"                 # quota; null = unset; best-effort by filesystem
ssh_authorized_keys = ["ssh-ed25519 AAAA…"]
bootstrap_profiles = ["terminal"]   # profiles to install for this user after create
```

**Pydantic validators:** `ram`/`disk` size pattern (e.g. `^\d+(\.\d+)?[KMGT]i?B?$|^\d+[KMGT]?$`), `cpu` `^\d+%$`, `tasks` positive int, every `sudo_commands` entry must start with `/` (absolute). Validation failures re-raised as a domain `AccountsError` (the `media/` convention). The validated model is converted to a frozen `ManagedUser` dataclass for downstream use.

### 2.4 Cross-distro reality (only two branch points)

Verified against man pages / context7. Fedora and Ubuntu differ in exactly two places; everything else (systemd, sudoers.d, shadow-utils) is byte-identical:

1. **Admin group:** Fedora `wheel`, Ubuntu `sudo` — detected at runtime via `getent group wheel || getent group sudo` (both pre-wired in `/etc/sudoers`).
2. **`useradd` defaults:** Ubuntu's raw `useradd` defaults to **no home** and `/bin/sh`. So we **always** pass `-m -s <shell>` explicitly.

### 2.5 Reconcile — desired state applied idempotently

Order (per user). The TOML entry is written **first** (declared intent); reconcile then applies and reports. Idempotent re-run converges; **no auto-rollback** (matches the engine's best-effort install semantics).

1. **User existence/identity.** `getent passwd <u>` → else `useradd -m -s <shell> <u>` (`/usr/sbin/nologin` when `lock_shell`). Password left locked `!` (key-only). If `ssh_authorized_keys` set: write `~/.ssh/authorized_keys` (`0600`, dir `0700`, owned by the user). Optional `--password` → prompted (never on argv) → `chpasswd`. **Fatal on failure** (raise, like other modules). UID auto-allocated; re-resolved via `getent`/`id -u`, never stored.
2. **Linger.** `loginctl enable-linger`/`disable-linger` to match `linger`.
3. **Privileges (converge the admin bit + our drop-in only).**
   - `none` → ensure NOT in admin group (`gpasswd -d` if present) and no `devboost-<u>` drop-in.
   - `full` → `usermod -aG <admin> <u>` (stock `%wheel`/`%sudo` rule grants it; no drop-in).
   - `nopasswd` → admin group **plus** drop-in `<u> ALL=(ALL) NOPASSWD: ALL`.
   - `allowlist` → drop-in `<u> ALL=(ALL) [NOPASSWD:] <abs cmds>` (absolute paths only).
   - **Safe install** for any drop-in: write to a dot-prefixed temp in `/etc/sudoers.d/`, `visudo -cf <tmp>` (abort on non-zero — a malformed file can lock out sudo), `chown root:root`, `chmod 0440`, atomic `mv` to `/etc/sudoers.d/devboost-<u>` (**dot-free** filename — sudoers silently skips names containing `.` or `~`), then a final whole-tree `visudo -c`. **Fatal on failure.**
4. **Compute limits (RAM/CPU/tasks).** Write `/etc/systemd/system/user-<uid>.slice.d/50-devboost.conf`:
   ```ini
   [Slice]
   MemoryHigh=<≈90% of ram>
   MemoryMax=<ram>
   CPUQuota=<cpu>
   TasksMax=<tasks>
   ```
   then `systemctl daemon-reload` and `systemctl set-property user-<uid>.slice …` (pushes the cap onto a live slice without waiting for re-login). Omitted knobs are simply absent from the file. cgroup v2 on both distros; capping the slice auto-enables the needed controllers (no delegation required). The cap applies whenever the user has processes; `linger` only governs whether the slice stays alive across logouts. **Fatal on failure.**
5. **Disk quota (tiered, best-effort, warn-and-proceed).** `findmnt -no FSTYPE --target /home/<u>`:
   - **btrfs** (Fedora default): home is its **own subvolume** (created at provision time — see 2.6), `btrfs quota enable` (once) + `btrfs qgroup limit <disk> <home>`. Reboot-free.
   - **ext4/xfs**: probe whether quota is active for the mount (`findmnt -no OPTIONS` + `repquota`/`quotaon -p`). If active → `setquota -u <u> 0 <disk> 0 0 <mnt>` (auto-install the `quota` package via `pkg.install` if `setquota` is missing). If **not** active → **skip with a clear message** (`"disk quota requires usrquota on this mount; not active — skipped; add to /etc/fstab + reboot to enable"`); optional `--enable-quota-fstab` edits fstab (effective next reboot). Per-user quota on a typical Ubuntu VPS root fs usually lands here.
   - other fs (overlay/tmpfs/zfs/nfs) → `"unsupported on <fstype>; skipped"`.
   - **Non-fatal:** a missing/unsupported disk cap warns loudly but does not fail the create — the compute caps are the real sandbox.
6. **Bootstrap (`--with-profile` / `bootstrap_profiles`).** Run last; see 2.7.

### 2.6 btrfs home-as-subvolume ordering

On btrfs with a disk limit, the home must be its own subvolume (a directory cannot be converted in place). Order: `btrfs subvolume create /home/<u>` → `useradd -M -d /home/<u> -s <shell> <u>` (no auto-home) → copy `/etc/skel` into it → `chown -R <u>:<u> /home/<u>` → `btrfs quota enable /` (idempotent) → `btrfs qgroup limit <disk> /home/<u>`. On non-btrfs (or no disk limit), the simple `useradd -m` path is used.

### 2.7 Bootstrap via a demoting executor

The engine's model is **run as the target user; escalate privileged commands via `sudo=True`**. `accounts` runs as **root**, while the default sandbox user has **no sudo** — so neither "run as dev" nor "run as root" works naively. Since `sudo=True` already classifies every command, we add:

```
DemotingExecutor(inner: Executor, target_user: str)
  run(argv, *, sudo, …):
    if sudo:  inner.run(argv, sudo=False, …)      # we are already root → run directly
    else:     inner.run(["sudo","-u",target,"-H", *argv], …)  # demote unprivileged cmds to the user
```

The bootstrap builds the existing pipeline's `Ctx` with `ex=DemotingExecutor(RealExecutor(), "dev")` and `HOME=/home/dev` in the process env (so modules' `os.environ["HOME"]` path computations resolve to the user's home). Result: **the entire existing catalog installs correctly for the new user with zero per-module changes** — privileged ops as root, user-owned files as the user — with no temporary privilege grant. `--with-profile term` (or any profile) provisions the sandbox *and* installs its toolchain in one command. Reusable beyond `accounts`. This is the one piece that touches the core `Executor` seam, so it carries the most test burden (2.10).

### 2.8 CLI verbs (`accounts` sub-app)

- **`create [NAME] [--ram --cpu --disk --tasks --privilege --sudo-cmd --shell --lock-shell --linger --ssh-key --password --with-profile --no-apply --adopt --interactive]`** — `create` with no name → full interactive `questionary` form; with a name → non-interactive (unset flags = unbounded); `--interactive` forces the form even with a name. Writes the `users.toml` entry, then reconciles unless `--no-apply`.
- **`list`** — Rich table: user, enabled, uid, RAM/CPU/tasks, disk (usage/limit or n/a), privilege, and a **status** column (ok / drift / missing / disabled) computed from live state (`getent`, `id -nG`, `passwd -S`, `btrfs qgroup show`/`repquota`, `sudo -l -U`).
- **`edit NAME …`** — load entry → prefilled form (or apply flags) → write → re-reconcile.
- **`disable NAME` / `enable NAME`** — reversible. Disable = `usermod -L --expiredate 1` + `loginctl terminate-user` + flip `enabled:false`; limit/privilege config is **retained** so re-enable restores it. Enable = `usermod -U && usermod -e ''` + reconcile.
- **`delete NAME [--purge]`** — terminate sessions (`loginctl terminate-user` + `pkill -u`) → `userdel -r` → tear down slice drop-in (`rm` + `daemon-reload` + `set-property --runtime …=` reset), sudoers drop-in (`rm`), admin group (`gpasswd -d`), quota (`btrfs subvolume delete` + `qgroup clear-stale`, or `setquota 0`), drop the `users.toml` entry. Default delete **warns** if UID-owned files remain outside home; **`--purge`** sweeps them (`find / -xdev -uid <uid>` — does not cross filesystems; pseudo-fs skipped; prints what it removes) to prevent UID-reuse leaks.
- **`apply [NAME]`** — reconcile all/one; idempotent; the verify-style entrypoint.

### 2.9 Failure model & honest limitations

- **Fatal** (raise, abort that user's reconcile): `useradd`, privilege application, slice application.
- **Non-fatal** (warn, continue): disk quota unsupported/unavailable, `ssh` key write issues, bootstrap module failures (logged like normal install failures).
- **Compute containment (RAM/CPU/tasks via the slice) is reliable on both distros. Storage containment is best-effort and filesystem-dependent** — fully reboot-free only on btrfs; on ext4/xfs root it usually requires enabling quota at mount time (a reboot), so it is detected and skipped with a clear message rather than silently failing or pretending to enforce.
- Idempotent re-run converges; there is no transactional rollback of a partially-applied user.

### 2.10 Testing (mirrors `tests/modules/test_system.py`)

- `FakeExecutor`-driven unit tests asserting exact sudo-prefixed argv sequences for create/disable/enable/delete, and the slice/sudoers/quota teardown sequences.
- Per-filesystem branching driven by `scripts={"findmnt": Result(...)}` (btrfs vs ext4 vs xfs vs unsupported).
- Fedora vs Ubuntu via the two `OsInfo` ctx factories (admin group `wheel` vs `sudo`; `useradd -m -s` always passed).
- The sudoers **stage→`visudo -cf`→chmod→atomic-mv** path, including the abort-on-invalid branch.
- `DemotingExecutor`: `sudo=True` → direct root argv; `sudo=False` → `sudo -u <user> -H` wrapping; plus an integration-style test that a sample module's writes are correctly demoted.
- Pydantic config load/validation tests (valid + each rejection: bad cpu%, relative sudo path, bad size).
- `mypy --strict` + ruff + pytest are merge gates (constitution v3.0.0).

### 2.11 Out of scope (v1)

- Multi-tenant fairness/scheduling beyond hard caps.
- Reserved UID bands / guaranteed non-recycled UIDs (mitigated by the `--purge` orphan sweep + warning).
- Centralised auth (LDAP/SSSD), PAM `limits.conf` tuning beyond what the slice provides, network/bandwidth caps.
- GUI/desktop provisioning for managed users (headless VPS focus).

---

## Implementation sequencing

1. **Part 1 (`term` + selection)** — small, independent, ships first.
2. **Part 2 (`accounts`)** — `usermgmt` primitive + config model → reconcile (user/priv/slice/quota) → CLI verbs → `DemotingExecutor` + `--with-profile`. The demoting executor and the btrfs-subvolume path are the highest-risk slices and get the most tests.

Both are additive to the current engine and gated by `mypy --strict` + ruff + pytest.
