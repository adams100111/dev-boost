# Tasks: dev-stacks

**Input**: Design documents from `specs/007-dev-stacks/`
**Prerequisites**: plan.md, spec.md, research.md (context7-verified pins), data-model.md, contracts/

**Tests**: REQUIRED — constitution §V + SC-008. Every module/helper behavior is a failing bats
test before implementation.

**Organization**: by user story (US1 python P1 → US7 react-native P7). Stub-harness + `lib/fresh.sh`
helper + profile/template scaffolding are Setup/Foundational. Paths repo-root relative. Pins per
`research.md`.

## Format: `[ID] [P?] [Story?] Description`

---

## Phase 1: Setup

- [ ] T001 [P] Create module folders under `modules/` for `uv`, `python-lsp`, `web-runtimes`, `web-lsp`, `ddev`, `laravel-lsp`, `dotnet-sdk`, `aspire`, `dotnet-lsp`, `android-sdk`, `expo`, `devops-tools`, `devops-lsp`, `data` (with `.gitkeep`).
- [ ] T002 Extend `tests/fixtures/base/stubs.bash` (BACKWARD-COMPATIBLE — Specs 1–6 suite of 749 must stay green) with stubs: `ddev` (version/config/install log), `dotnet` (`--list-sdks` knob, `tool install -g`, `tool list`), `sdkmanager` (+`yes` license accept log; cmdline-tools presence knob), `uv` (installed-via curl|sh marker), `npx`/`expo` (create-expo-app log). Extend the `mise` stub `use -g` to mark multiple tools resolvable. Reuse existing `dnf`/`rpm`/`curl`/`docker`. Add knobs (`STUB_DOTNET_SDKS`, `STUB_ANDROID_SDK_PRESENT`, etc.). Run `bats tests/` → 749 still green.

**Checkpoint**: harness ready.

---

## Phase 2: Foundational (Blocking)

- [ ] T003 Add `fresh_lsp_wire <lang> <abs-cmd> [args…]` to `lib/fresh.sh` (extract the jq-merge from `fresh_lsp_provision`; refactor `fresh_lsp_provision` to call it — behavior unchanged). Run `bats tests/fresh-lsp.bats tests/vscode.bats tests/fresh.bats` → still green (editors suite unaffected). Add `tests/fresh-lsp.bats` cases for `fresh_lsp_wire` directly (merge given an absolute path; idempotent; preserves keys).
- [ ] T004 Add the 7 stack entries to `profiles.toml` per `contracts/profiles.md` (do NOT touch existing profiles); extend `tests/profiles.bats` with `profile_expand` membership/count for each of the 7 (TOML-only). Full depsort tests DEFERRED to Polish.

**Checkpoint**: helper + profiles resolve; stories can begin.

---

## Phase 3: US1 — Python stack (uv) (Priority: P1) 🎯 MVP

**Goal**: uv installed + basedpyright/ruff wired into fresh + `templates/python`; idempotent; unsupported on non-Fedora.

- [ ] T005 [P] [US1] Write `tests/python-stack.bats` (RED) per contracts: `uv` install (pinned astral installer) attempted + verify `command -v uv`; `python-lsp` provisions `pipx:basedpyright@…` + `pipx:ruff@…` (assert mise log) and wires `lsp.python`/`lsp.pythonfmt`; `templates/python/.fresh/config.json` present (tab 4); idempotent; `fresh` missing → named fail; unsupported-OS → engine failure.
- [ ] T006 [US1] Implement `modules/uv/{module.toml,install.sh}` (pinned `astral.sh/uv/<pin>/install.sh`; verify `command -v uv`).
- [ ] T007 [US1] Implement `modules/python-lsp/{module.toml,install.sh,servers.tsv,verify.sh}` (`requires=["fresh","mise","uv"]`; loop servers.tsv via `fresh_lsp_provision`) + `templates/python/` starter (`.fresh/config.json`, `pyproject.toml`, README). Reach GREEN for T005.

**Checkpoint**: US1 MVP — python buildable + intelligent.

---

## Phase 4: US2 — Web stack (node/pnpm/bun) (Priority: P2)

- [ ] T008 [P] [US2] Write `tests/web-stack.bats` (RED): `web-runtimes` does `mise use -g node@22 pnpm@… bun@…` (assert log) + verify mise-resolvable; `web-lsp` provisions ts/eslint/tailwind servers + prettier and wires them; `templates/nextjs/.fresh/config.json` (tab 2, prettier) present; idempotent; unsupported-OS.
- [ ] T009 [US2] Implement `modules/web-runtimes/{module.toml,install.sh,verify.sh}` (`requires=["mise"]`; `mise use -g node@22 pnpm@11.8.0 bun@1.3.14`).
- [ ] T010 [US2] Implement `modules/web-lsp/{module.toml,install.sh,servers.tsv,verify.sh}` (`requires=["fresh","mise","web-runtimes"]`; provision ts/eslint(`vscode-langservers-extracted`)/tailwind(`@tailwindcss/language-server`) + `npm:prettier`) + `templates/nextjs/` starter. GREEN for T008.

**Checkpoint**: US2 — web buildable + intelligent.

---

## Phase 5: US3 — Laravel stack (ddev-only) (Priority: P3)

- [ ] T011 [P] [US3] Write `tests/laravel-stack.bats` (RED): `ddev` writes `/etc/yum.repos.d/ddev.repo` (idempotent, honor `DEVBOOST_YUM_REPOS_DIR`) + `dnf install --refresh ddev` + verify `command -v ddev`; NO host php/composer install; `laravel-lsp` wires intelephense; `templates/laravel/.fresh/config.json` sets php formatter `vendor/bin/pint`; idempotent; unsupported-OS.
- [ ] T012 [US3] Implement `modules/ddev/{module.toml,install.sh}` (`requires=["docker"]`; ddev repo + install + mkcert; honor `DEVBOOST_YUM_REPOS_DIR`).
- [ ] T013 [US3] Implement `modules/laravel-lsp/{module.toml,install.sh,servers.tsv,verify.sh}` (`requires=["fresh","mise","ddev"]`; intelephense via `fresh_lsp_provision`) + `templates/laravel/` (ddev `laravel new` README + `.fresh/config.json` pint formatter). GREEN for T011.

**Checkpoint**: US3 — laravel via ddev + intelligent.

---

## Phase 6: US4 — .NET stack (SDK 10 + Aspire) (Priority: P4)

- [ ] T014 [P] [US4] Write `tests/dotnet-stack.bats` (RED): `dotnet-sdk` does `dnf install -y dotnet-sdk-10.0` + verify SDK 10 (`STUB_DOTNET_SDKS`); `aspire` does `dotnet tool install -g Aspire.Cli` + verify `command -v aspire`; `dotnet-lsp` installs csharp-ls + csharpier (dotnet tool) and `fresh_lsp_wire`s csharp to `~/.dotnet/tools/csharp-ls`; `templates/dotnet` AppHost has `WithDataVolume()`+`WithLifetime(ContainerLifetime.Persistent)` + `.fresh/config.json` csharpier; idempotent; unsupported-OS.
- [ ] T015 [US4] Implement `modules/dotnet-sdk/{module.toml,install.sh,verify.sh}` (`dnf install -y dotnet-sdk-10.0`; verify dotnet + 10.* SDK).
- [ ] T016 [US4] Implement `modules/aspire/{module.toml,install.sh}` (`requires=["dotnet-sdk"]`; `dotnet tool install -g Aspire.Cli` guarded; verify `command -v aspire`).
- [ ] T017 [US4] Implement `modules/dotnet-lsp/{module.toml,install.sh,verify.sh}` (`requires=["fresh","dotnet-sdk"]`; dotnet tool install csharp-ls+csharpier guarded; `fresh_lsp_wire csharp ~/.dotnet/tools/csharp-ls`) + `templates/dotnet/` Persistent-infra AppHost starter. GREEN for T014.

**Checkpoint**: US4 — .NET 10 + Aspire + intelligent.

---

## Phase 7: US5 — Data stack (containers + dbgate) (Priority: P5)

- [ ] T018 [P] [US5] Write `tests/data-stack.bats` (RED): `data` seeds `templates/data/compose.yaml` (postgres:18 + valkey/valkey:8.1 + dbgate/dbgate:7.2.0, named volumes); NO host postgres/redis dnf install; idempotent (seed-if-absent); unsupported-OS.
- [ ] T019 [US5] Implement `modules/data/{module.toml,install.sh,verify.sh}` (`requires=["docker"]`; ensure `templates/data/compose.yaml` present; no host db) + author `templates/data/compose.yaml` per contract. GREEN for T018.

**Checkpoint**: US5 — databases as persistent containers.

---

## Phase 8: US6 — DevOps stack (OpenTofu/kubectl/helm/k9s) (Priority: P6)

- [ ] T020 [P] [US6] Write `tests/devops-stack.bats` (RED): `devops-tools` does `mise use -g aqua:opentofu/opentofu@… aqua:kubernetes/kubectl@… aqua:helm/helm@… aqua:derailed/k9s@…` (assert log) + verify mise-resolvable; `devops-lsp` wires tofu-ls; idempotent; unsupported-OS.
- [ ] T021 [US6] Implement `modules/devops-tools/{module.toml,install.sh,verify.sh}` (`requires=["mise"]`; the four `mise use -g aqua:` pins).
- [ ] T022 [US6] Implement `modules/devops-lsp/{module.toml,install.sh,servers.tsv,verify.sh}` (`requires=["fresh","mise","devops-tools"]`; tofu-ls via `fresh_lsp_provision`). GREEN for T020.

**Checkpoint**: US6 — IaC tooling + intelligent.

---

## Phase 9: US7 — React Native stack (Android/Expo) (Priority: P7)

- [ ] T023 [P] [US7] Write `tests/react-native-stack.bats` (RED): `android-sdk` does `mise use -g java@temurin-17`, installs cmdline-tools, `sdkmanager "platform-tools" "platforms;android-35" "build-tools;36.0.0" "cmdline-tools;latest"`, `yes | sdkmanager --licenses` (assert), verify SDK marker + java; `expo` seeds `templates/react-native` (npx create-expo-app README) — NO global expo-cli; shares `web-runtimes` (node@22); idempotent (licenses not re-accepted); unsupported-OS.
- [ ] T024 [US7] Implement `modules/android-sdk/{module.toml,install.sh,verify.sh}` (`requires=["mise"]`; java@temurin-17 + cmdline-tools + sdkmanager packages + license accept; idempotent marker; honor `ANDROID_HOME` override for tests).
- [ ] T025 [US7] Implement `modules/expo/{module.toml,install.sh,verify.sh}` (`requires=["web-runtimes"]`; seed `templates/react-native/` with the `npx create-expo-app`/`npx expo prebuild` README + `.fresh/config.json`; no global cli). GREEN for T023.

**Checkpoint**: US7 — React Native + Expo Android buildable.

---

## Phase 10: Polish & Cross-Cutting

- [ ] T026 Add full-resolution depsort tests to `tests/profiles.bats` for all 7 stacks (`devboost list --profile <stack>` resolves without cycle; `*-lsp` after toolchain + `mise`/`fresh`; `react-native` includes `web-runtimes`). Then run the FULL suite `bats tests/` — all green, NO regression to Specs 1–6 (749) or engine.
- [ ] T027 [P] Reconcile `quickstart.md` + `research.md` pins against the delivered modules/servers.tsv; fix any drift.
- [ ] T028 [P] Update `docs/roadmap.md` Spec 7 row status (done at branch completion).

---

## Dependencies & Execution Order
- Setup (T001–T002) → Foundational (T003–T004) → US1…US7 (each: RED test → toolchain → lsp/template) → Polish (T026–T028).
- Stacks are independent (different modules); `react-native` reuses `web-runtimes` (US2's module — so US2 before US7, or US7 implements/￼shares web-runtimes). All `*-lsp` depend on editors' `fresh`/`lib/fresh.sh` (base/editors on main).
- TDD inside each story: RED → implement → GREEN.

## Parallel Opportunities
- Test files (T005/T008/T011/T014/T018/T020/T023) are independent of each other (different files).
- T027 ∥ T028. Same-file tasks (`profiles.bats` T004+T026; `stubs.bash` T002; `lib/fresh.sh` T003) are NOT parallel.

## Implementation Strategy
- **MVP = US1 python** (Phases 1–3): smallest end-to-end proof of the per-stack pattern.
- Then US2…US7, each an independently-shippable green increment. The roadmap's backend/web-mobile
  split remains available (stacks independent). Whole-branch review + finishing after Polish.

**Total: 28 tasks** — Setup 2, Foundational 2, US1 3, US2 3, US3 3, US4 4, US5 2, US6 3, US7 3, Polish 3.
