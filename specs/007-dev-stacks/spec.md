# Feature Specification: dev-stacks

**Feature Branch**: `007-dev-stacks`

**Created**: 2026-06-20

**Status**: Draft

**Input**: User description: "dev-stacks profiles: per-stack developer environments (laravel ddev-only, dotnet rpm SDK + aspire, python uv, web node/pnpm/bun, react-native, devops, data as containers) + per-stack templates/ + per-stack fresh LSP via lib/fresh.sh. Depends on base + editors."

## Clarifications

### Session 2026-06-20 (self-answered from the design doc + constitution + the editors feature's implemented patterns — source of truth — and current package docs via context7; user "take over and complete properly, don't ask")

- Q: Is each stack independently selectable, or is dev-stacks one monolithic profile? → A: **one profile per stack** (`laravel`, `dotnet`, `python`, `web`, `react-native`, `devops`, `data`), each independently selectable and independently testable; `full` composes them. A developer who only builds Python selects `python` and gets none of the others.
- Q: Which stacks get `fresh` language intelligence, and how is it wired? → A: `laravel` (intelephense + pint), `dotnet` (csharp-ls + csharpier), `python` (basedpyright + ruff), `web` (typescript + eslint + tailwind language servers + prettier), `devops` (terraform-ls) each ship a per-stack `servers.tsv` and call the **editors feature's `lib/fresh.sh::fresh_lsp_provision`** to install each server/formatter as a mise-managed pinned tool and jq-merge it into `~/.config/fresh/config.json`. `react-native` and `data` are build/infra stacks with **no** fresh LSP rows. This is the per-stack consumption of the mechanism the editors feature deferred to here.
- Q: How are language runtimes provisioned and pinned? → A: via **mise** (`mise use -g <backend>:<tool>@<pin>` / `mise use -g <runtime>@<pin>`), version-pinned in each module's in-repo data, **except** (per design): **Python uses `uv`** (mise defers to it) and **.NET uses the rpm SDK** (not mise). Node/pnpm/bun, JDK, terraform/kubectl/helm/k9s come from mise.
- Q: Laravel — host PHP/Composer or containerized? → A: **ddev-only**. The `laravel` stack installs Docker (already base) + ddev + a templates starter whose `laravel new` runs *through ddev*. Host `php`/`composer` are explicitly **out of scope** (opt-in, a later/other feature). So the laravel stack's "PHP" intelligence (intelephense) is a fresh LSP tool, but the PHP *runtime* lives in ddev containers, not on the host.
- Q: Databases — host installs or containers? → A: **persistent containers**, never host installs. The `data` stack ships a `templates/data/compose.yaml` (postgres + redis with named data volumes for persistence) + thin wrapper(s) to bring them up/down, plus **dbgate** as the DB GUI (DBeaver is demoted/optional). Verify is about the compose assets + dbgate being present, not a running host service.
- Q: .NET Aspire infra defaults? → A: the `templates/dotnet` AppHost ships shared infra (postgres, redis, object-storage) set to **Persistent + data volumes** by default, so local runs keep their data across restarts.
- Q: react-native Android licenses (unattended)? → A: the `android-sdk`/cmdline-tools install must **auto-accept SDK licenses** non-interactively (`yes | sdkmanager --licenses`), consistent with the unattended-by-default principle.

### Session 2026-06-20b (context7 verification — current versions, new features & best practices as of 2026-06; these supersede the design doc where it has aged)

- **DevOps → OpenTofu, not Terraform**: HashiCorp's Terraform is BSL-1.1 (non-OSI) since 1.6; the open-source successor **OpenTofu** (MPL-2.0, Linux Foundation, mature at 1.11.x) is the 2026 default. The `devops` stack installs `tofu` (binary) and the matching **`tofu-ls`** LSP. (Terraform/`terraform-ls` remain a documented opt-out for HCP-locked users.)
- **Data → Valkey, not Redis**: Redis 8 relicensed to AGPLv3; **Valkey** (BSD-3, Linux Foundation fork, drop-in Redis-protocol compatible) is the 2026 default cache. The `data` compose ships `valkey/valkey` (+ `postgres:18` — note PG18's version-specific PGDATA path — and **dbgate as a container**, the recommended local DB-GUI deployment).
- **.NET → 10 LTS** (GA Nov 2025, supported to Nov 2028) via Fedora in-distro `dnf install dotnet-sdk-10.0` (no Microsoft prod repo needed on Fedora 44). .NET 8/9 both EOL Nov 2026 — not pinned.
- **Aspire install model changed**: Aspire is now the **standalone `aspire` CLI** (`dotnet tool install -g Aspire.Cli`, or the `aspire.dev/install.sh` AOT binary), **not** the deprecated `dotnet workload install aspire`. Persistence pattern in the AppHost template: `.WithDataVolume()` + `.WithLifetime(ContainerLifetime.Persistent)`.
- **C# LSP**: the Roslyn-based language server (`Microsoft.CodeAnalysis.LanguageServer` / community `roslyn-ls`) is the 2026-recommended C# intelligence; **`csharp-ls`** remains the lightweight, cleanly-pinnable (`dotnet tool`) option and is the wired default for `fresh`, with roslyn-ls documented as the richer alternative.
- **Laravel Pint is per-project** (a composer dev-dependency), not a global tool — so it is wired as the PHP **formatter in `templates/laravel`'s project-level `.fresh/config.json`** (pointing at `vendor/bin/pint` via ddev), not in the global stack server set. Intelephense (PHP LSP) stays a global mise-provisioned `fresh` server (`npm:intelephense`).
- **watchman dropped from react-native**: no clean Fedora/mise install path and no longer required by Metro/Expo in 2026 (inotify suffices); the stack relies on inotify (ensuring adequate `fs.inotify.max_user_watches`) rather than a fragile from-source watchman build.
- **Node pinned to 22 LTS globally** (satisfies both `web` and Expo SDK's ≥22.13 floor); **JDK 17** (RN's validated version, not 21); **Android API 35** (Android 15) + build-tools 36.0.0 + cmdline-tools `latest`.
- **Expo uses `npx expo` / `npx create-expo-app`** (the global `expo-cli` is deprecated); only `eas-cli` is installed globally and only if cloud builds are wanted (out of scope for the local-build path).
- **Web LSP packaging gotchas**: the ESLint LSP ships inside `npm:vscode-langservers-extracted` (binary `vscode-eslint-language-server`); Tailwind is `npm:@tailwindcss/language-server` (unscoped binary `tailwindcss-language-server`); Python's Ruff LSP is the built-in `ruff server` (not the deprecated `ruff-lsp`); basedpyright's LSP binary is `basedpyright-langserver`. Exact pins live in `research.md` / each stack's `servers.tsv`.

## User Scenarios & Testing *(mandatory)*

The `dev-stacks` feature turns a base+editors workstation into one that can actually **build
the platform's target stacks out of the box**. Each stack is a self-contained, independently
selectable profile: selecting it installs that stack's toolchain (runtimes via mise, or uv /
rpm SDK / containers where the design dictates), wires the matching language intelligence into
the `fresh` editor (reusing the editors feature's helper), and drops a ready-to-run project
starter into `templates/`. Stacks are independent — selecting one never pulls in another's
toolchain.

### User Story 1 - Python stack (uv) (Priority: P1)

A developer selects the `python` stack and can immediately start a Python project with `uv`
(fast envs/locking), with `fresh` providing Python completion/diagnostics (basedpyright) and
format-on-save (ruff), and a `templates/python` starter to copy from. Re-running changes nothing.

**Why this priority**: `uv`-based Python is the simplest, highest-leverage stack and the cleanest
MVP — one runtime tool, no containers, fully independent. It proves the whole per-stack pattern
(toolchain + fresh-LSP wiring + template) end-to-end.

**Independent Test**: Select `python`; verify `uv` is installed, the python fresh servers
(basedpyright/ruff) are provisioned as mise-managed tools and wired into `fresh`'s config, and a
`templates/python` starter exists; re-run is a no-op; non-Fedora → unsupported.

**Acceptance Scenarios**:

1. **Given** base+editors are applied, **When** the `python` stack installs, **Then** `uv` is available and a `templates/python` starter (with a project-level `.fresh/config.json`) is present.
2. **Given** the stack installs, **When** provisioning completes, **Then** `fresh` has Python language intelligence (basedpyright + ruff) wired as mise-managed pinned tools.
3. **Given** the stack is installed, **When** it installs again, **Then** it reports already-satisfied (idempotent).
4. **Given** a non-Fedora host, **When** the stack installs, **Then** it is reported unsupported, never silently skipped.

---

### User Story 2 - Web stack (node/pnpm/bun) (Priority: P2)

A developer selects the `web` stack and can build Next.js/React apps: Node, pnpm, and bun are
installed (mise-managed, pinned), `fresh` gives TypeScript/ESLint/Tailwind intelligence and
prettier format-on-save, and a `templates/nextjs` starter is ready. Re-run is a no-op.

**Why this priority**: Web (Next.js/React) is a core build target and underpins react-native; it
exercises multiple mise-managed runtimes and the richest fresh-LSP set.

**Independent Test**: Select `web`; verify node/pnpm/bun are present (mise), the web fresh servers
+ prettier are wired, and a `templates/nextjs` starter exists; re-run no-op; non-Fedora → unsupported.

**Acceptance Scenarios**:

1. **Given** base+editors, **When** `web` installs, **Then** node, pnpm, and bun are available as mise-managed, pinned runtimes.
2. **Given** the stack installs, **Then** `fresh` has TypeScript/ESLint/Tailwind servers + prettier wired for web file types.
3. **Given** installed, **When** re-run, **Then** idempotent no-op; **and** non-Fedora → unsupported.

---

### User Story 3 - Laravel stack (ddev-only) (Priority: P3)

A developer selects the `laravel` stack and can scaffold/run a Laravel app entirely through ddev
(no host PHP/Composer) — ddev is installed, `fresh` provides PHP intelligence (intelephense) and
pint formatting, and a `templates/laravel` starter shows the ddev-based `laravel new` flow.

**Why this priority**: Laravel/ddev is a core target; it depends only on Docker (base) + ddev, and
its container-based runtime model is distinct and worth proving early.

**Independent Test**: Select `laravel`; verify ddev is installed, the laravel fresh servers
(intelephense/pint) are wired, and a `templates/laravel` ddev starter exists; re-run no-op;
non-Fedora → unsupported.

**Acceptance Scenarios**:

1. **Given** base (Docker) + editors, **When** `laravel` installs, **Then** ddev is available and a `templates/laravel` starter documenting the ddev `laravel new` flow exists.
2. **Given** the stack installs, **Then** `fresh` has PHP intelligence (intelephense) + pint formatting wired; **and** no host `php`/`composer` is installed (ddev-only).
3. **Given** installed, **When** re-run, **Then** idempotent; **and** non-Fedora → unsupported.

---

### User Story 4 - .NET stack (SDK + Aspire) (Priority: P4)

A developer selects the `dotnet` stack and can build .NET + Aspire apps: the .NET SDK (rpm) and
the Aspire tooling are installed, `fresh` gives C# intelligence (csharp-ls) + csharpier
formatting, and `templates/dotnet` ships an Aspire AppHost with shared infra set Persistent +
data volumes. Re-run is a no-op.

**Why this priority**: .NET + Aspire is a core target with a distinct install path (rpm SDK, not
mise) and the persistent-infra template requirement.

**Independent Test**: Select `dotnet`; verify the .NET SDK + Aspire workload are present, csharp-ls
+ csharpier wired into `fresh`, and a `templates/dotnet` Persistent-infra AppHost starter exists;
re-run no-op; non-Fedora → unsupported.

**Acceptance Scenarios**:

1. **Given** base+editors, **When** `dotnet` installs, **Then** the .NET SDK and Aspire tooling are available.
2. **Given** the stack installs, **Then** `fresh` has C# intelligence (csharp-ls) + csharpier wired; **and** `templates/dotnet` ships an Aspire AppHost with infra set Persistent + data volumes.
3. **Given** installed, **When** re-run, **Then** idempotent; **and** non-Fedora → unsupported.

---

### User Story 5 - Data stack (containers + dbgate) (Priority: P5)

A developer selects the `data` stack and gets local databases as **persistent containers** (not
host services): a `templates/data/compose.yaml` with PostgreSQL + Valkey (named data volumes) and
dbgate as the DB GUI. Bringing them up keeps data across restarts. Re-run is a no-op.

**Why this priority**: Databases-as-containers is a deliberate design choice and supports the other
stacks (laravel/dotnet/web) but is itself independent and infra-only (no fresh LSP).

**Independent Test**: Select `data`; verify the compose assets (postgres+redis, persistent
volumes) and dbgate are present; re-run no-op; non-Fedora → unsupported. (No host postgres/redis.)

**Acceptance Scenarios**:

1. **Given** base (Docker) is applied, **When** `data` installs, **Then** a `templates/data/compose.yaml` defining PostgreSQL + Valkey with named (persistent) data volumes is present, and dbgate is available (containerized).
2. **Given** the stack installs, **Then** NO host database service is installed (containers only).
3. **Given** installed, **When** re-run, **Then** idempotent; **and** non-Fedora → unsupported.

---

### User Story 6 - DevOps stack (OpenTofu/kubectl/helm/k9s) (Priority: P6)

A developer selects the `devops` stack and gets OpenTofu, kubectl, helm, and k9s (mise-managed,
pinned), with `fresh` providing IaC intelligence (tofu-ls). Re-run is a no-op.

**Why this priority**: Infra tooling is valuable and clean (all mise-managed), but not on the
critical app-build path, so it sequences after the app stacks.

**Independent Test**: Select `devops`; verify OpenTofu/kubectl/helm/k9s are present (mise),
tofu-ls wired into `fresh`; re-run no-op; non-Fedora → unsupported.

**Acceptance Scenarios**:

1. **Given** base+editors, **When** `devops` installs, **Then** OpenTofu, kubectl, helm, and k9s are available as mise-managed, pinned tools.
2. **Given** the stack installs, **Then** `fresh` has tofu-ls wired.
3. **Given** installed, **When** re-run, **Then** idempotent; **and** non-Fedora → unsupported.

---

### User Story 7 - React Native stack (Android/Expo) (Priority: P7)

A developer selects the `react-native` stack and can build a React Native + Expo **Android** app:
node + JDK 17 (mise), the Android SDK (cmdline-tools + platform/build-tools, licenses
auto-accepted), android-tools (adb/fastboot), and Expo tooling are present, and a
`templates/react-native` starter is ready. Re-run is a no-op.

**Why this priority**: The largest, most complex stack (Android SDK + licenses + multiple tools);
it builds on `web` (node) and is sequenced last.

**Independent Test**: Select `react-native`; verify node/jdk (mise), android-sdk (cmdline-tools +
licenses accepted), android-tools, expo, watchman present, and a `templates/react-native` starter
exists; re-run no-op; non-Fedora → unsupported.

**Acceptance Scenarios**:

1. **Given** base+editors, **When** `react-native` installs, **Then** node (22 LTS), JDK 17 (mise), the Android SDK (cmdline-tools + required packages incl. API 35 + build-tools, licenses auto-accepted), and android-tools are available, and Expo project creation works via `npx`.
2. **Given** the stack installs, **Then** a `templates/react-native` Expo starter exists.
3. **Given** installed, **When** re-run, **Then** idempotent (licenses not re-accepted, packages not reinstalled); **and** non-Fedora → unsupported.

---

### Edge Cases

- **Unsupported OS**: every stack module reports failure naming the module on a non-supported distro, never a silent skip.
- **editors not selected**: the fresh-LSP rows in a stack require the editors feature's `fresh`/`lib/fresh.sh`; a stack with fresh rows MUST declare the dependency so it is ordered after `fresh`, and fail naming the editor if `fresh` is absent at provision time (consistent with the editors feature).
- **Partial/interrupted install**: re-running completes only what is missing (mise tools, SDK packages, template files) without disturbing what is present.
- **Stack toolchain isolation**: selecting one stack MUST NOT install another stack's toolchain (no cross-stack leakage).
- **Idempotent license acceptance / template seeding**: Android license acceptance and template starter files are seeded only if absent; re-runs do not duplicate or re-prompt.
- **Templates never clobber user edits**: a stack's template starter is written into `templates/<stack>/` (repo data); deploying/copying it to a user project never overwrites an existing project file.
- **Unattended**: no stack install prompts (Android licenses auto-accepted, no interactive package pickers).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The platform MUST provide one independently-selectable profile per stack: `laravel`, `dotnet`, `python`, `web`, `react-native`, `devops`, `data`.
- **FR-002**: Each stack profile MUST declare its dependencies (`base`, and `editors` for stacks that wire fresh intelligence) so prerequisites are applied first.
- **FR-003**: The `python` stack MUST install `uv` (the primary Python tool; not mise) and provide a `templates/python` starter.
- **FR-004**: The `web` stack MUST install node, pnpm, and bun as mise-managed, version-pinned runtimes and provide a `templates/nextjs` starter.
- **FR-005**: The `laravel` stack MUST install ddev (container-based; Docker from base) and provide a `templates/laravel` ddev starter, and MUST NOT install host PHP/Composer.
- **FR-006**: The `dotnet` stack MUST install the .NET SDK (rpm) and Aspire tooling and provide a `templates/dotnet` Aspire AppHost starter whose shared infra is set Persistent with data volumes.
- **FR-007**: The `data` stack MUST provide a `templates/data/compose.yaml` defining PostgreSQL and a Redis-protocol cache (Valkey) as persistent (named-volume) containers, plus dbgate (containerized DB GUI), and MUST NOT install host database services.
- **FR-008**: The `devops` stack MUST install OpenTofu (the OSI-licensed Terraform-compatible IaC tool), kubectl, helm, and k9s as mise-managed, version-pinned tools.
- **FR-009**: The `react-native` stack MUST install node + JDK (mise), the Android SDK (cmdline-tools + required packages with licenses auto-accepted), android-tools, and expo (via `npx`, no deprecated global CLI), and provide a `templates/react-native` starter. (watchman is intentionally omitted — see Clarifications.)
- **FR-010**: Stacks with language intelligence (`laravel`, `dotnet`, `python`, `web`, `devops`) MUST wire their language servers/formatters into `fresh` by reusing the editors feature's `lib/fresh.sh` (each server/formatter installed as a mise-managed pinned tool, idempotently merged into `fresh`'s config), per the documented stack→server map.
- **FR-011**: Every runtime/tool version MUST be pinned in in-repo data so two machines built at different times converge (except where a tool's own lockfile governs, e.g. uv project locks).
- **FR-012**: Each stack module's `verify` MUST act as an idempotency guard: a satisfied stack is skipped on re-run, and re-running performs only the missing work.
- **FR-013**: Selecting one stack MUST NOT install another stack's toolchain (stacks are isolated; shared prerequisites come only via declared dependencies).
- **FR-014**: Any stack module MUST report a failure naming the module on an unsupported OS or unmet precondition — never a silent skip.
- **FR-015**: Adding a tool to a stack, changing a pin, or adding a stack→server mapping MUST be a data change (a manifest/list/map/template edit), not an engine change.
- **FR-016**: The entire dev-stacks install path MUST complete with zero interactive prompts (Android licenses auto-accepted; no package pickers).
- **FR-017**: Each stack MUST provide a `templates/<stack>` project starter; stacks needing editor config ship a project-level `.fresh/config.json`; the `data` stack ships `compose.yaml`. Template starters are repo data and MUST NOT overwrite a user's existing project files when copied.

### Key Entities *(include if data involved)*

- **Stack profile**: a named profile (`python`, `web`, …) listing the modules for that stack; selecting it installs that stack only.
- **Stack module(s)**: the per-tool/per-stack manifests + escape-hatch install logic (e.g. `ddev`, `uv`, `dotnet-sdk`, `android-sdk`, container wrappers).
- **Per-stack fresh server map** (`servers.tsv` per stack): declarative rows (lang, fresh-command, mise backend:tool@pin, args) consumed by `lib/fresh.sh`.
- **Template starter** (`templates/<stack>/`): project scaffold + project-level `.fresh/config.json` (or `compose.yaml` for data).
- **Version-pin data**: the in-repo pins for each mise-managed runtime/tool.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After selecting a stack on a fresh base+editors machine, a developer can begin building in that stack's primary language/framework with zero additional manual tool setup.
- **SC-002**: For each app stack (python, web, laravel, dotnet, react-native), the platform's stated "build out of the box" target is achievable with only that stack (plus base+editors) selected.
- **SC-003**: For every stack with language intelligence, opening that stack's primary file type in `fresh` yields working completion/diagnostics and format-on-save.
- **SC-004**: Selecting one stack installs none of another stack's toolchain (verifiable: a non-selected stack's tools are absent).
- **SC-005**: Re-running any stack install is a verified no-op (no tool, license, template, or config re-applied).
- **SC-006**: Two machines built from the same stack selection at different times converge to identical pinned tool versions.
- **SC-007**: Databases run as persistent containers — no host postgres/redis service is installed, and container data survives a restart.
- **SC-008**: Every behavior above is covered by automated tests asserting real outcomes, and the existing whole-repo suite stays green (no engine or prior-profile regression).

## Assumptions

- **`full` composition**: the design's `full` profile includes all seven stacks; assembling `full` is a later spec (Spec 12). This feature only defines the per-stack profiles.
- **mise is the runtime manager** for node/pnpm/bun, JDK, terraform/kubectl/helm/k9s via its package backends, pinned in in-repo data — EXCEPT Python (`uv`) and .NET (rpm SDK), per the design.
- **fresh-LSP reuse**: stacks reuse the editors feature's `lib/fresh.sh::fresh_lsp_provision` and the documented stack→server map; the per-stack `servers.tsv` rows are the in-repo pin source for those servers.
- **Docker is provided by base**; laravel/data rely on it (containers).
- **Host PHP/Composer are out of scope** (laravel is ddev-only); host-language opt-ins are a separate concern.
- **dbgate is the DB GUI** (DBeaver demoted to optional, out of scope here).
- **Templates are scaffolds, not deploys**: this feature ships starter content under `templates/<stack>/`; copying a starter into a real project is a developer action (and a later lifecycle feature may add an `add`/scaffold verb).
- **Supported OS is Fedora** (reference); other distros report unsupported by data (Fedora-only `[install]` keys).
- **Exact tool versions/pins and the precise Android SDK package list** are finalized in planning (grounded against current docs); the spec fixes the behavior, not the version numbers.
- **Scope note (roadmap)**: the roadmap permits splitting this into backend / web-mobile if the cycle runs long; this spec keeps all seven stacks as independent user stories so delivery can proceed story-by-story regardless.
