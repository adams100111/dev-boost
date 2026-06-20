# Implementation Plan: base-profile

**Branch**: `002-base-profile` | **Date**: 2026-06-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/002-base-profile/spec.md`

## Summary

Deliver the `base` profile as **data + escape-hatch modules over the existing engine**,
introducing the first real `profiles.toml` (the `base` set) and one additive sourced
helper lib (`lib/pkg.sh`). Most tools are **pure-TOML modules** (`verify = command -v X`,
`[install].fedora = dnf install -y X`) — no escape hatch. The handful with real logic
(`rpmfusion`, `dnf-tune`, `fedora-third-party`, `flatpak`, `mise`, `chezmoi`, `docker`)
are folder modules with an `install.sh` that sources `lib/log.sh`/`lib/pkg.sh`/(and for
chezmoi) `lib/secrets.sh`. Engine control flow (`run_install`/`depsort`/`module`/
`profile`) is untouched; the only engine edit is a sanctioned `doctor` addition for the
runtime-manager drift warning (FR-008), mirroring Spec 1's `secrets_doctor`. Built
test-first with bats, extending the Spec-1 stub-harness approach to fake
`dnf`/`flatpak`/`rpm`/`fedora-third-party`/`systemctl`/`usermod`/`mise`/`chezmoi`/`sudo`
so no real installs or network occur.

## Technical Context

**Language/Version**: Bash (engine + modules); system `python3` (TOML) + `jq` (JSON), already required.
**Primary Dependencies**: leaf tools invoked by modules — `dnf`, `rpm`, `flatpak`, `fedora-third-party`, `systemctl`, `usermod`/`getent`, `mise`, `chezmoi`, `git`, plus the installed packages themselves. No new engine runtime dependency.
**Storage**: system + user config only — `/etc/dnf/dnf.conf`, RPM Fusion release packages, flatpak remotes, `~/.config/mise/config.toml` (or repo `config/mise.toml`), `~/.bashrc` (commented legacy blocks), `~/.local/share/chezmoi`, docker service unit + `docker` group. No database.
**Testing**: `bats` (existing harness), PATH stub bins for all external commands + `DEVBOOST_*`/`HOME`/`OS_*` overrides. No real installs/network (constitution §V).
**Target Platform**: Fedora 44 reference (full); `debian`/`macos` thinner via per-OS `[install]` keys where a tool/repo differs.
**Project Type**: Single-project Bash bootstrap engine. Source at repo root.
**Performance Goals**: Not latency-sensitive; correctness + idempotency matter.
**Constraints**: Unattended (no prompts); idempotent/verify-guarded; engine control flow unchanged; no secret in git; cross-OS via data.
**Scale/Scope**: ~11 simple tool modules + 7 logic modules + `build-tools` bundle + `profiles.toml` + `lib/pkg.sh` + a doctor drift check + ~6 bats files. Reuses Spec-1 patterns (`lib/secrets.sh`, escape-hatch, stub harness).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Engine + Data Separation** — PASS (one justified touch). New capability is modules (data + `install.sh`) + `profiles.toml` (data) + the additive `lib/pkg.sh`. `run_install`/`depsort`/`module.sh`/`profile.sh` unchanged. Only engine edit: `cmd_doctor` gains a runtime-manager drift warning that delegates to a lib helper (FR-008) — generic preflight, not per-module branching. Recorded in Complexity Tracking.
- **II. Idempotent & Verify-Guarded** — PASS. Every module declares a top-level `verify` detecting end-state; simple modules use `command -v`/`rpm -q`; logic modules reconcile-not-duplicate (dnf.conf, bashrc blocks, flatpak remotes, docker group).
- **III. Reproducible — Repo is Source of Truth** — PASS. Pinned mise versions land in `config/mise.toml`; no secret committed; migration preserves existing versions (no silent drift).
- **IV. Unattended by Default** — PASS. All installs non-interactive (`-y`); the docker group re-login requirement is reported, not waited on; chezmoi clone failure is non-blocking by default.
- **V. Test-First (NON-NEGOTIABLE)** — PASS. Each module + the migration branches + unsupported-OS path are specified by failing bats tests first; all external commands stubbed.
- **VI. Cross-OS via Data** — PASS. Package names / repo setup live in per-OS `[install]` keys; Fedora reference; unmatched OS reported unsupported by the existing engine.

**Result: PASS** — proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/002-base-profile/
├── plan.md, research.md, data-model.md, quickstart.md
├── contracts/
│   ├── profiles.md            # profiles.toml — the `base` set
│   ├── lib-pkg.md             # shared escape-hatch helpers
│   ├── repos-and-pkgmgr.md    # rpmfusion, dnf-tune, fedora-third-party, flatpak (US1)
│   ├── cli-and-build-tools.md # simple tool modules + build-tools bundle (US2)
│   ├── managers.md            # mise(+migration), chezmoi, docker (US3)
│   └── doctor-mise-drift.md   # FR-008 doctor addition
└── tasks.md                   # (/speckit-tasks)
```

### Source Code (repository root)

```text
profiles.toml                  # NEW — first real profiles file; `base` = [secrets, ssh-setup, rpmfusion, dnf-tune, fedora-third-party, flatpak, <tools…>, build-tools, mise, chezmoi, docker]
lib/
└── pkg.sh                     # NEW — sourced helpers: have, need_cmd, dnf_install, rpm_q, flatpak_remote, write_kv (idempotent /etc/dnf/dnf.conf), comment_block (bashrc), mise_drift
modules/                       # NEW base modules
├── rpmfusion/{module.toml,install.sh}
├── dnf-tune/{module.toml,install.sh}
├── fedora-third-party/{module.toml,install.sh}
├── flatpak/{module.toml,install.sh}
├── build-tools/module.toml            # bundle (simple)
├── git.toml, curl.toml, wget.toml, unzip.toml, jq.toml, htop.toml,
│   ripgrep.toml, fd.toml, fzf.toml, tmux.toml, coreutils.toml   # simple per-tool
├── mise/{module.toml,install.sh}      # install + nvm/sdkman migration
├── chezmoi/{module.toml,install.sh}   # requires secrets; clone non-blocking
└── docker/{module.toml,install.sh}    # repo + service + group
bin/devboost                   # EDIT — cmd_doctor: runtime-manager drift warning (delegates to lib/pkg.sh::mise_drift)
# (no config/mise.toml here — migration writes the USER global mise config; the repo pin is the later update spec's job, F2/§III)
tests/
├── repos.bats, tools.bats, build-tools.bats, mise.bats, chezmoi.bats, docker.bats, profiles.bats, doctor-mise.bats
└── fixtures/base/             # NEW — stub bins (dnf/flatpak/rpm/fedora-third-party/systemctl/usermod/getent/mise/chezmoi/sudo) + harness
```

**Structure Decision**: Single-project Bash engine; additive. Engine control-flow files
untouched; only `bin/devboost` (doctor drift warning) changes, within its existing
preflight responsibility. Simple tools are pure TOML (the cheapest possible change per
the engine principle); only genuinely stateful modules get an `install.sh`.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Engine touch: `cmd_doctor` runtime-manager drift warning | FR-008 / design §6.4 require `doctor` to warn when mise and a legacy manager are both active | A module can't own a cross-cutting environment warning; doctor is the defined place for drift signals. Generic (delegates to `lib/pkg.sh::mise_drift`), not per-module branching — Engine+Data separation holds (same precedent as Spec 1 `secrets_doctor`). |
| New `lib/pkg.sh` sourced helper | Many escape-hatch modules share dnf/flatpak/reconcile logic | Re-implementing dnf/flatpak/idempotent-write in each `install.sh` would duplicate logic and drift; a sourced lib (not engine control-flow) keeps modules thin and is the §3.2 helper pattern, deferred from Spec 1. |
