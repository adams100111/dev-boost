# Contract: `lib/pkg.sh` (NEW, sourced)

Source-only helper library for escape-hatch modules. Depends on `lib/log.sh`. No side
effects on source. All external commands are PATH-stubbable in tests.

## Functions
- `have <cmd>` → 0 if on PATH (mirrors `lib/secrets.sh::have`; single canonical copy — if
  both libs define it, keep one and source it).
- `need_cmd <cmd> <pkg>` → ensure a command exists, installing `<pkg>` via the OS package
  manager only if absent.
- `dnf_install <pkg...>` → `sudo dnf install -y <pkg...>` (fedora family); no-op args safe.
- `rpm_q <pkg...>` → 0 iff all installed (`rpm -q`).
- `flatpak_remote_add <name> <url>` → add remote if absent (`flatpak remotes` check);
  idempotent.
- `write_kv_conf <file> <key> <value>` → ensure `key=value` present in an ini-style file,
  **reconciling** an existing `key=` line (replace) rather than appending a duplicate;
  creates the file/section if missing. Used for `/etc/dnf/dnf.conf`.
- `comment_block <file> <begin-marker> <end-marker>` → prefix `# ` to each line of a
  delimited block (idempotent: already-commented lines untouched); used to disable
  nvm/sdkman init in `~/.bashrc` without deleting.
- `mise_drift` → prints/returns whether BOTH `mise` and a legacy manager (`~/.nvm` active
  in shell, `~/.sdkman`) are active; consumed by `cmd_doctor` (FR-008). Read-only.

## Guarantees
- Every install/reconcile helper is idempotent.
- No helper prints secrets. Failures name the operation (FR-014).
- `write_kv_conf` and `comment_block` never corrupt unrelated lines (tests assert
  surrounding content preserved).

## Tests
Covered across `repos.bats`/`mise.bats`/`doctor-mise.bats` via the stub harness:
`write_kv_conf` reconcile-not-duplicate; `comment_block` idempotency + preserves other
lines; `flatpak_remote_add` skip-when-present; `rpm_q`/`need_cmd` present/absent.
