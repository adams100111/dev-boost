# Phase 0 Research: base-profile

Spec decisions were settled in clarify (recorded in spec §Clarifications). Remaining
unknowns are plan-level; decisions below.

## D1. Module granularity — simple TOML vs escape-hatch

**Decision**: Tools that are a single idempotent package install are **pure-TOML modules**
(`verify = "command -v X"` or `rpm -q`, `[install].fedora = "sudo dnf install -y X"`,
per-OS keys for debian/macos). Only modules with real logic get an `install.sh`:
`rpmfusion` (two release rpms + appstream + refresh), `dnf-tune` (reconcile dnf.conf),
`fedora-third-party` (enable + query verify), `flatpak` (install + remote + unfilter),
`mise` (install + migration), `chezmoi` (install + init + clone), `docker` (repo +
service + group).

**Rationale**: Honors the engine principle "adding a tool is one file"; keeps the diff and
the test surface minimal; matches `tests/fixtures/modules/git.toml` shape already in the repo.

## D2. Shared escape-hatch helpers — `lib/pkg.sh`

**Decision**: Add an additive, source-only `lib/pkg.sh` with: `have`, `need_cmd`,
`dnf_install`, `rpm_q`, `flatpak_remote_add`, `write_kv_conf` (idempotent key=value into
`/etc/dnf/dnf.conf`, reconcile-not-append), `comment_block` (comment a delimited block in
`~/.bashrc` without deleting), and `mise_drift` (detect both mise and a legacy manager
active). Modules `source "$DEVBOOST_ROOT/lib/pkg.sh"`.

**Rationale**: Realizes the design §3.2 helper set (deferred in Spec 1) as a sourced lib,
not engine-injected — `run_install` stays unchanged. Avoids duplicating dnf/flatpak/
reconcile logic across seven `install.sh` scripts.

## D3. `profiles.toml` introduction + the `base` set

**Decision**: This feature creates the first real `/profiles.toml`. `base` lists (in a
`requires`-satisfiable order, though depsort handles ordering):
`secrets, ssh-setup, rpmfusion, dnf-tune, fedora-third-party, flatpak, coreutils, git,
curl, wget, unzip, jq, htop, ripgrep, fd, fzf, tmux, build-tools, mise, chezmoi, docker`.
Only `base` is defined now; other profiles are added by their own specs. `requires`
edges (not profile order) enforce real ordering (rpmfusion before nonfree consumers;
chezmoi requires secrets).

**Rationale**: base-profile is the natural home for the canonical `base` set; the engine
already reads `$DEVBOOST_PROFILES`/`profiles.toml`.

## D4. nvm/sdkman → mise migration (conditional, idempotent)

**Decision** (design §6.4): in `mise/install.sh`, after installing mise —
- if `~/.nvm` present: read `nvm` default/installed node version(s) → `mise use -g node@<v>`;
- if `~/.sdkman` present: read sdkman current java → `mise use -g java@<v>`;
- comment out (never delete) the nvm/sdkman init blocks in `~/.bashrc` via
  `comment_block`, leaving a dated `# devboost: migrated to mise …` note;
- absent ⇒ no-op. Idempotent: re-run detects already-commented blocks + already-set versions.

`mise use -g` writes the **user's** global mise config (`~/.config/mise/config.toml`) —
that is what preserves the running versions (SC-004). The **repo's committed**
`config/mise.toml` pin (reproducibility, design §8) is NOT written at install time:
mutating a tracked file during install fights §III (repo = source of truth; updates are
*proposed*, not auto-written) and would clobber an already-pinned repo on other machines.
Updating the committed pin is the later lifecycle/`update` spec's job (propose-not-commit).
So this feature does NOT write `config/mise.toml`; the empty file is removed from scope
(see data-model/tasks).

**Rationale**: Preserves exact versions in the user's mise config (no silent drift, SC-004);
reversible (legacy dirs left in place); keeps the committed repo pin under the deliberate
update flow.

## D5. `docker` group + re-login

**Decision**: `docker/install.sh` adds the docker-ce repo, installs, `systemctl enable
--now docker`, and `usermod -aG docker $USER`. Verify = `command -v docker` AND
`systemctl is-enabled docker` (or stub) AND `getent group docker` contains the user.
The module **reports** that a re-login is required for the group to take effect — it does
NOT assume the group is active in the current session.

**Rationale**: Group membership needs a new login; asserting it mid-run would be false.
`getent group` is the durable, session-independent check.

## D6. Testing strategy (no real installs / network)

**Decision**: extend the Spec-1 stub approach with a `tests/fixtures/base/` harness
providing PATH stubs for `dnf`, `rpm`, `flatpak`, `fedora-third-party`, `systemctl`,
`usermod`, `getent`, `mise`, `chezmoi`, `git`, and `sudo` (sudo just exec's the rest).
Each stub records its invocations to a log and can simulate present/absent state via env
knobs (e.g. `STUB_RPM_HAS=...`, a fake `~/.nvm`). Tests assert the commands attempted +
resulting state files (dnf.conf contents, commented bashrc, pinned config, group entry),
plus idempotent re-run (verify green ⇒ engine skip), and the unsupported-OS path.

**Rationale**: Hermetic, fast, honors §V real-behavior assertions; mirrors Spec 1.

## D7. Doctor drift warning (FR-008)

**Decision**: `cmd_doctor` sources `lib/pkg.sh` and calls `mise_drift`; if both mise and a
legacy manager are active it `log_warn`s (a drift signal, NOT a hard fail). Read-only,
generic — same shape as Spec 1's `secrets_doctor` delegation.

## Outcome

No unresolved `NEEDS CLARIFICATION`. Ready for Phase 1.
