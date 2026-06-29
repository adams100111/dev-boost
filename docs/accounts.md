# `accounts` — sandbox-user management

`devboost accounts` is a **standalone CLI sub-app** for creating and managing self-contained,
resource-capped Linux users on Fedora and Ubuntu. It is not part of the declarative install
pipeline (`@register`, toposort, `install`/`verify`); it is imperative admin tooling with its own
reconcile loop.

Canonical design: `docs/superpowers/specs/2026-06-29-term-rename-and-accounts-sandbox-design.md`
(Part 2).

---

## Motivation

On a box with a default admin user (e.g. `ubuntu`), `accounts` carves out an extra account — such
as `dev` — that is walled off with its own RAM/CPU/process budget, an optional disk cap, and a
controlled privilege level. The user can be **disabled reversibly** or **deleted cleanly** in one
command without leaving residue across the system.

Concrete uses: a contained account for an untrusted workload, a long-running agent under a hard
cap, or a project-specific sandbox that can be torn down when a contract ends.

---

## Registry file — `/etc/devboost/users.toml`

State lives at `/etc/devboost/users.toml` (dir `0755`, file `0644`, root-owned). Override with
`DEVBOOST_USERS_PATH` (useful in tests or multi-machine setups).

### Schema

Each user is a TOML table under `[users.<name>]`:

```toml
[users.dev]
enabled = true                       # false = account locked; config retained
shell = "/bin/bash"                  # default /bin/bash
lock_shell = false                   # true → /usr/sbin/nologin (no interactive login)
linger = false                       # loginctl enable-linger (keep slice alive after logout)
privilege = "none"                   # none | full | nopasswd | allowlist
sudo_commands = []                   # absolute paths; only used when privilege = "allowlist"
ram = "4G"                           # MemoryMax for the user's systemd slice; null = unbounded
cpu = "50%"                          # CPUQuota; >100% spans multiple cores; null = unbounded
tasks = 200                          # TasksMax (max processes); null = unbounded
disk = "20G"                         # disk quota; null = unbounded; best-effort by filesystem
ssh_authorized_keys = ["ssh-ed25519 AAAA…"]
bootstrap_profiles = ["terminal"]    # dev-boost profiles to install for this user after create
```

### Field reference

| Field | Type | Default | Meaning |
|---|---|---|---|
| `enabled` | bool | `true` | `false` locks the account with `usermod -L`; config is retained for re-enable |
| `shell` | string | `"/bin/bash"` | Login shell passed to `useradd -s` |
| `lock_shell` | bool | `false` | When `true` the shell is forced to `/usr/sbin/nologin` |
| `linger` | bool | `false` | `loginctl enable-linger` keeps the user slice alive without an active session |
| `privilege` | string | `"none"` | One of `none / full / nopasswd / allowlist` — see Privilege tiers below |
| `sudo_commands` | list | `[]` | Absolute command paths for `allowlist` privilege; each must start with `/` |
| `ram` | string \| null | `null` | RAM cap, e.g. `"4G"`, `"512M"`. `MemoryHigh` is auto-derived at ≈90%; `null` = unbounded |
| `cpu` | string \| null | `null` | CPU quota, e.g. `"50%"`, `"200%"` (multi-core). `null` = unbounded |
| `tasks` | int \| null | `null` | Max concurrent processes (`TasksMax`). Must be a positive integer; `null` = unbounded |
| `disk` | string \| null | `null` | Disk quota, e.g. `"20G"`. Best-effort by filesystem — see Disk quota below |
| `ssh_authorized_keys` | list | `[]` | Public keys written to `~/.ssh/authorized_keys` (`0600`) |
| `bootstrap_profiles` | list | `[]` | dev-boost profile names installed for the user via `--with-profile` |

**Size format:** `ram` and `disk` accept a numeric value with a unit suffix — `K`, `M`, `G`, `T`
(with optional `i`/`B`), e.g. `"4G"`, `"512M"`, `"1.5T"`. Plain integers (bytes) are also
accepted. `cpu` must be a whole-number percentage, e.g. `"50%"`.

---

## Privilege tiers

| Tier | Effect |
|---|---|
| `none` | Not in admin group; no sudoers drop-in |
| `full` | Added to admin group (`wheel` on Fedora, `sudo` on Ubuntu — auto-detected); stock group rule grants sudo with password |
| `nopasswd` | Admin group **plus** a drop-in: `<user> ALL=(ALL) NOPASSWD: ALL` |
| `allowlist` | No admin group; drop-in: `<user> ALL=(ALL) NOPASSWD: <cmd1>, <cmd2>, …` (absolute paths from `sudo_commands`) |

The admin group is detected at runtime via `getent group wheel` (Fedora) or falls back to `sudo`
(Ubuntu). Any sudoers drop-in is written via a stage→`visudo -cf`→atomic-mv sequence; a malformed
drop-in aborts the reconcile rather than breaking `sudo` system-wide. Drop-in files are named
`/etc/sudoers.d/devboost-<user>` (dot-free, so sudoers does not silently skip them).

---

## Resource caps

### RAM, CPU, tasks — systemd slice (reliable)

Caps are written to `/etc/systemd/system/user-<uid>.slice.d/50-devboost.conf` and pushed onto
the live slice immediately via `systemctl set-property` — no re-login required:

```ini
[Slice]
MemoryHigh=<≈90% of ram>   # soft limit — throttles before hitting the hard cap
MemoryMax=<ram>            # hard cap
CPUQuota=<cpu>             # e.g. 50% or 200% for multi-core
TasksMax=<tasks>           # max concurrent processes
```

Only the knobs that are set in `users.toml` appear in the file. These caps apply whenever the
user has processes; `linger` only controls whether the slice stays alive between sessions.

**These caps are reliable on both Fedora and Ubuntu (cgroup v2).**

### Disk quota — best-effort by filesystem

Disk containment depends on the filesystem hosting the user's home directory:

| Filesystem | Behaviour |
|---|---|
| **btrfs** (Fedora default) | Home is a dedicated subvolume; `btrfs quota enable` + `btrfs qgroup limit <size> <home>`. **Reboot-free.** |
| **ext4 / xfs** | Enforced only if quota is already active on the mount (detected via `quotaon -pu`). If active, `setquota` is used (the `quota` package is auto-installed if missing). If **not** active, the cap is **skipped** with a message: add `usrquota` to the mount options in `/etc/fstab` and reboot to enable. |
| Other (overlay, tmpfs, zfs, nfs, …) | **Skipped** with a message: `"disk quota unsupported on <fstype>"`. |

A missing or skipped disk cap is **non-fatal** — the create/apply succeeds with a warning. The
compute caps (RAM/CPU/tasks) are the reliable containment boundary; storage is best-effort.

---

## Commands

### `accounts create [NAME]`

Create a managed user. With `NAME` omitted (or with `--interactive`) an interactive
`questionary` form is shown. With a name, all limits are set via flags (unset = unbounded).

```
devboost accounts create dev \
  --ram 4G \
  --cpu 50% \
  --disk 20G \
  --tasks 200 \
  --privilege nopasswd \
  --ssh-key 'ssh-ed25519 AAAA…' \
  --with-profile terminal
```

Key flags:

| Flag | Default | Meaning |
|---|---|---|
| `--ram TEXT` | (none) | RAM cap, e.g. `4G` |
| `--cpu TEXT` | (none) | CPU quota, e.g. `50%` |
| `--disk TEXT` | (none) | Disk quota, e.g. `20G` |
| `--tasks INT` | (none) | Max processes |
| `--privilege TEXT` | `none` | One of `none / full / nopasswd / allowlist` |
| `--sudo-cmd TEXT` | (none) | Repeatable; absolute command path for `allowlist` tier |
| `--shell TEXT` | `/bin/bash` | Login shell |
| `--lock-shell` | off | Force shell to `/usr/sbin/nologin` |
| `--linger` | off | Enable loginctl linger |
| `--ssh-key TEXT` | (none) | Repeatable; public key added to `authorized_keys` |
| `--with-profile TEXT` | (none) | Repeatable; bootstrap profile(s) installed after create |
| `--no-apply` | off | Write config only; skip reconcile |
| `--adopt` | off | Accept an existing unmanaged account into the registry |
| `--interactive` | off | Force the interactive form even when NAME is given |

The entry is written to `users.toml` first, then reconciled (unless `--no-apply`). The account
must not already be in the registry; if the OS account exists but is unmanaged, `--adopt` is
required.

### `accounts list`

Print a Rich table of all managed users and their declared caps:

```
devboost accounts list
```

Columns: `user`, `enabled`, `ram`, `cpu`, `tasks`, `disk`, `privilege`.

### `accounts edit NAME`

Open a prefilled interactive form for an existing managed user, then re-apply:

```
devboost accounts edit dev
```

### `accounts disable NAME`

**Reversible lock.** Runs `usermod -L --expiredate 1` to prevent login, terminates active
sessions, and flips `enabled: false` in `users.toml`. All limits and privilege config are
retained so `enable` can restore the account exactly.

```
devboost accounts disable dev
```

### `accounts enable NAME`

Unlock and re-apply a previously disabled account:

```
devboost accounts enable dev
```

### `accounts delete NAME [--purge]`

Full teardown: terminate sessions, `userdel -r`, remove the slice drop-in, sudoers drop-in,
admin-group membership, and disk quota; drop the entry from `users.toml`.

```
devboost accounts delete dev          # warns if UID-owned files remain outside home
devboost accounts delete dev --purge  # sweeps orphaned UID-owned files on the root filesystem
```

`--purge` runs `find / -xdev -uid <uid>` (does not cross filesystem boundaries; skips
pseudo-filesystems) and removes what it finds, guarding against UID-reuse leaks after deletion.

### `accounts apply [NAME]`

Reconcile all managed users, or a single named user, against the current `users.toml`. Idempotent:
safe to re-run at any time to converge drift.

```
devboost accounts apply        # all users
devboost accounts apply dev    # one user
```

---

## Bootstrap (`--with-profile`)

When `bootstrap_profiles` is set (or `--with-profile` is passed to `create`), dev-boost installs
the named profiles **as the new user** immediately after the account is created. This uses a
`DemotingExecutor` that wraps the real executor: privileged commands (`sudo=True`) run directly
(the process is already root), while unprivileged commands are demoted via `sudo -u <user> -H`.
The entire existing module catalog installs correctly for the new user with no per-module changes.

Example: `--with-profile terminal` provisions the account and installs ~32 terminal/shell tools
into the user's home in one step.

---

## Idempotence and safety guarantees

- **Registry-scoped:** only users listed in `users.toml` are touched. Accounts not in the
  registry (`root`, `ubuntu`, etc.) are never modified.
- **Owns only its artifacts:** the admin-group membership bit, the `devboost-<user>` sudoers
  drop-in, the `50-devboost.conf` slice drop-in, and the quota/subvolume. Unrelated group
  memberships (e.g. `docker`) are not touched.
- **No transactional rollback:** a partially-applied user stays partially applied. Re-running
  `apply` converges the remainder. This matches the engine's best-effort install semantics.
- **Fatal on structural failures** (user creation, privilege application, slice write): the
  reconcile aborts and reports the failing command. Disk quota failures are non-fatal (warn and
  continue).

---

## Cross-distro notes

| Aspect | Fedora | Ubuntu |
|---|---|---|
| Admin group | `wheel` | `sudo` |
| `useradd` | `-m -s <shell>` always passed | Same (`-m -s` required; Ubuntu defaults to no home and `/bin/sh`) |
| Disk quota (default fs) | btrfs — reboot-free subvolume qgroup | ext4 on root — usually needs `usrquota` mount + reboot |

Everything else (systemd slice, sudoers.d, shadow-utils lock/unlock) is identical between distros.
