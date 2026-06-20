# Implementation Plan: dev-stacks

**Branch**: `007-dev-stacks` | **Date**: 2026-06-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/007-dev-stacks/spec.md`

## Summary

Deliver **seven independently-selectable stack profiles** (`python`, `web`, `laravel`, `dotnet`,
`data`, `devops`, `react-native`) as escape-hatch modules + `templates/<stack>/` starters + one
small additive helper in `lib/fresh.sh`, with **zero engine/`bin/devboost` change**. Each stack
installs its toolchain (mise package backends for runtimes/CLIs; `uv` installer for Python; rpm
SDK for .NET; ddev dnf-repo for Laravel; an Android cmdline-tools install for RN; a compose.yaml
for the container-only `data` stack) and — for the five stacks with language intelligence —
wires its `fresh` servers/formatters by reusing the editors feature's provisioning helper. All
versions are **context7-verified for 2026-06** (research.md): node 22 LTS, .NET 10 LTS + the
standalone `aspire` CLI, **OpenTofu** (not Terraform), **Valkey** (not Redis), Postgres 18, JDK
17 + Android API 35, Expo via `npx` (watchman dropped). Each module verifies on END state
(re-run no-op); Fedora-only `[install]` keys ⇒ engine reports unsupported elsewhere by data.
Built test-first with bats, stubbing all installers (`ddev`/`dotnet`/`sdkmanager`/`uv`/`npx` +
existing `mise`/`dnf`/`rpm`/`curl`/`docker`) — no real installs, network, containers, or SDK.

## Technical Context

**Language/Version**: Bash (modules + a small `lib/fresh.sh` addition); python3/jq existing.
**Primary Dependencies**: `mise` (base) as the runtime/tool manager via `aqua:`/`npm:`/`pipx:` backends; `uv` installer (Python); `dnf` (.NET 10 SDK in-distro; ddev yum repo); `dotnet tool` (aspire CLI, csharp-ls, csharpier); Android `sdkmanager`/cmdline-tools; `docker`/compose (base) for `data`; the editors feature's `fresh` + `lib/fresh.sh`. No new engine runtime dependency.
**Storage**: system packages, mise-pinned tools, `~/.dotnet/tools`, `$ANDROID_HOME`, per-stack `templates/`, and (data) named docker volumes. No database in the engine.
**Testing**: `bats`; extend `tests/fixtures/base/stubs.bash` (backward-compatible) with `ddev`, `dotnet`, `sdkmanager`/cmdline-tools, `uv`, `npx`/`expo` stubs; reuse `mise`/`dnf`/`rpm`/`curl`/`docker`. Real `jq` for fresh-config merges. No real installs/network/containers/SDK (§V).
**Target Platform**: Fedora Workstation (reference). Non-Fedora → engine-reported unsupported.
**Project Type**: Single-project Bash bootstrap engine.
**Performance Goals**: Not latency-sensitive; correctness + idempotency.
**Constraints**: Unattended (Android licenses auto-accepted; no pickers); idempotent (verify on end state); engine untouched; tool pins in-repo (per-stack `servers.tsv` / module data); no secret in git.
**Scale/Scope**: 7 stack profiles; ~16 modules (uv, web-runtimes, web-lsp, ddev, laravel-lsp, dotnet-sdk, aspire, dotnet-lsp, android-sdk, expo, devops-tools, devops-lsp, python-lsp, data); 7 `templates/<stack>` starters; per-stack `servers.tsv`; one additive `lib/fresh.sh` helper (`fresh_lsp_wire`); ~7 bats files. Reuses editors `lib/fresh.sh` + base `mise`/`docker`/`pkg.sh`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Engine + Data Separation** — PASS. No engine/`bin/devboost`/control-flow change. Stacks are modules + profile entries + templates (data). `lib/fresh.sh` gets one additive merge-only helper (`fresh_lsp_wire`) — the established profile-helper-lib pattern; `fresh_lsp_provision` is refactored to call it with identical behavior. "Adding a tool to a stack = one data edit" holds.
- **II. Idempotent & Verify-Guarded** — PASS. Each module's `verify` reflects END state (tool on PATH / mise-resolvable + lsp entry present / template file present / compose.yaml present). mise `use -g`, `dnf install -y`, `dotnet tool install` (guarded), cmdline-tools (license accept guarded), template seed-if-absent are all idempotent. Failures name the module + command.
- **III. Reproducible — Repo is Source of Truth** — PASS. Every runtime/tool version pinned in-repo (per-stack `servers.tsv` rows + module pins); `mise use -g <spec@pin>` records the resolved version to user-global `~/.config/mise/config.toml` (machine state). Templates are repo data. No secrets, no auto-commit. (Exception by design: uv project locks govern per-project Python deps.)
- **IV. Unattended by Default** — PASS. All installs non-interactive; Android licenses via `yes | sdkmanager --licenses`; no package pickers; ddev repo write scripted.
- **V. Test-First (NON-NEGOTIABLE)** — PASS. Per-stack: tool-install-attempted, fresh-servers-wired, template-present, idempotent-skip, unsupported-OS, stack-isolation — all failing-bats-first, all tooling stubbed.
- **VI. Cross-OS via Data (Fedora reference)** — PASS. Fedora-only `[install]` keys ⇒ engine reports unsupported elsewhere. Stack→server maps + pins + templates are in-repo data.

**Result: PASS** — proceed.

## Project Structure

### Documentation (this feature)
```text
specs/007-dev-stacks/
├── plan.md, research.md, data-model.md, quickstart.md
├── checklists/requirements.md
├── contracts/
│   ├── runtimes-and-tools.md   # uv, web runtimes, devops tools, dotnet sdk, ddev, android (install contracts)
│   ├── fresh-wiring.md         # per-stack servers.tsv + lib/fresh.sh fresh_lsp_wire + dotnet-tool wiring
│   ├── data-compose.md         # data stack compose.yaml + dbgate
│   └── profiles.md             # 7 stack profile entries + depsort
└── tasks.md
```

### Source Code (repository root)
```text
lib/fresh.sh                    # EDIT (additive) — extract `fresh_lsp_wire <lang> <abs-cmd> [args]` (merge-only); fresh_lsp_provision calls it
modules/                        # NEW dev-stacks modules (escape-hatch + per-stack servers.tsv + lsp wiring)
├── uv/                         # python: uv pinned installer
├── python-lsp/                 # python: basedpyright + ruff server via fresh_lsp_provision
├── web-runtimes/               # web: mise node@22 + pnpm + bun
├── web-lsp/                    # web: servers.tsv (ts/eslint/tailwind + prettier) via fresh_lsp_provision
├── ddev/                       # laravel: ddev dnf repo + install
├── laravel-lsp/                # laravel: intelephense via fresh_lsp_provision (pint is template-level)
├── dotnet-sdk/                 # dotnet: dnf dotnet-sdk-10.0
├── aspire/                     # dotnet: dotnet tool install -g Aspire.Cli
├── dotnet-lsp/                 # dotnet: csharp-ls + csharpier (dotnet tool) wired via fresh_lsp_wire
├── android-sdk/                # react-native: cmdline-tools + sdkmanager packages + license accept; mise java@17
├── expo/                       # react-native: node@22 (shared) + npx-expo flow
└── devops-tools/ + devops-lsp/ # devops: mise aqua: opentofu/kubectl/helm/k9s ; tofu-ls
   (data stack is template-only — no install module beyond a thin `data` module that seeds compose.yaml)
templates/                      # POPULATE existing dirs + add data/, nextjs
├── python/{.fresh/config.json, starter}
├── nextjs/{.fresh/config.json, starter}
├── laravel/{.fresh/config.json, README ddev flow}
├── dotnet/{.fresh/config.json, AppHost Persistent+WithDataVolume starter}
├── react-native/{.fresh/config.json, npx-expo README}
└── data/compose.yaml
profiles.toml                   # EDIT — add 7 stack profiles
tests/
├── python-stack.bats, web-stack.bats, laravel-stack.bats, dotnet-stack.bats,
│   data-stack.bats, devops-stack.bats, react-native-stack.bats   # NEW
├── profiles.bats               # EXTEND — 7 stack profiles membership + depsort
└── fixtures/base/stubs.bash    # EXTEND — ddev/dotnet/sdkmanager/uv/npx stubs
```

**Structure Decision**: Single-project Bash engine; fully additive. Stacks split into a
*runtime/tool* module + a *-lsp* wiring module where both exist, so fresh-LSP wiring (requires
`fresh`+`mise`) is cleanly separable from toolchain install and the profile composes them. The
one shared code change is the additive `fresh_lsp_wire` helper in `lib/fresh.sh` (merge-only),
enabling the dotnet stack (dotnet-tool servers, not mise) to reuse the same idempotent jq-merge.

## Complexity Tracking

> No constitution violations. The `lib/fresh.sh` addition is a refactor-extract (merge-only
> helper) preserving existing behavior — re-verified by the editors suite. The runtime/LSP module
> split is organizational (data), not engine control flow. Seven stacks ⇒ many modules, but each
> is one-file-per-tool data per Principle I. The roadmap's backend/web-mobile split remains
> available (stacks are independent) if delivery needs to land incrementally.
