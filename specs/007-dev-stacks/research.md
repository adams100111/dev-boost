# Phase 0 Research: dev-stacks

All tool/version facts below were **verified against current docs via context7 on 2026-06-20**
(four parallel research passes: python+web, laravel+dotnet, react-native, devops+data). Pins are
the live-registry latest as of that date; the in-repo source of truth for each is the relevant
`servers.tsv` / module data, finalizable against `mise ls-remote` on the target Fedora image.

## Cross-cutting decisions
- **D0. Runtime manager = mise**, via its package backends, EXCEPT Python (`uv`) and .NET (rpm/dnf SDK). Prefer the **`aqua:` backend** for CLIs (checksum/signature, non-interactive) and `npm:`/`pipx:` for LSP servers/formatters. **Global node pinned to 22 LTS** (satisfies both `web` and Expo's ≥22.13 floor — one global node avoids a web-vs-RN conflict).
- **D1. fresh LSP reuse**: each stack with intelligence ships `modules/<stack>/servers.tsv` and its `install.sh` loops it through the editors feature's `fresh_lsp_provision` (lib/fresh.sh). Per-project formatters that are *project dependencies* (Pint) are wired in the stack's `templates/*/.fresh/config.json`, NOT the global servers.tsv.
- **D2. Each stack = its own profile**; isolation is structural (selecting one installs only its modules). Fedora-only `[install]` keys ⇒ engine reports unsupported elsewhere by data.

## Python stack (US1)
**Decision**: `uv` via the pinned Astral installer `curl -LsSf https://astral.sh/uv/<pin>/install.sh | sh` (canonical reproducible path; uv is primary, mise defers). fresh servers via mise:
| lang | command | mise spec | args |
|---|---|---|---|
| python | basedpyright-langserver | `pipx:basedpyright@1.39.8` | `--stdio` |
| python (fmt) | ruff | `pipx:ruff@0.15.18` | `server` |
**Rationale**: basedpyright LSP binary is `basedpyright-langserver` (PyPI bundles Node — no separate runtime); Ruff's LSP is the built-in `ruff server` (the deprecated `ruff-lsp` is gone). `uv` ≈ 0.11.23. Template `templates/python` + project `.fresh/config.json` (tab_size 4).

## Web stack (US2)
**Decision**: runtimes via mise — `node@22` (LTS), `pnpm@11.8.0`, `bun@1.3.14` (**drop corepack** → mise). fresh servers via mise `npm:`:
| lang | command | mise spec | args |
|---|---|---|---|
| typescript | typescript-language-server | `npm:typescript-language-server@5.3.0` | `--stdio` |
| eslint | vscode-eslint-language-server | `npm:vscode-langservers-extracted@4.10.0` | `--stdio` |
| tailwindcss | tailwindcss-language-server | `npm:@tailwindcss/language-server@0.14.29` | `--stdio` |
| (fmt) prettier | prettier | `npm:prettier@3.8.4` | — |
**Rationale/gotchas**: eslint LSP binary lives inside `vscode-langservers-extracted` (no standalone pkg); tailwind pkg is scoped but binary unscoped; ESLint flat-config auto-detected. Template `templates/nextjs` + project `.fresh/config.json` (tab_size 2).

## Laravel stack (US3, ddev-only)
**Decision**: `ddev` via its Fedora dnf repo — write `/etc/yum.repos.d/ddev.repo` (`baseurl=https://pkg.ddev.com/yum/`, `gpgcheck=0`) then `sudo dnf install --refresh ddev` (+ `mkcert -install`). NO host php/composer. fresh server: intelephense (global); Pint is per-project (template).
| lang | command | mise spec | args |
|---|---|---|---|
| php | intelephense | `npm:intelephense@1.12.0` | `--stdio` |
**Rationale**: intelephense is still the leading PHP LSP (npm pkg `intelephense`, run `--stdio`). Pint ships as a composer dev-dependency in `templates/laravel`; that project's `.fresh/config.json` sets the PHP formatter to `vendor/bin/pint` (run via ddev). `templates/laravel` documents the ddev `laravel new` flow (`ddev config --project-type=laravel --docroot=public` + `ddev composer create laravel/laravel`).

## .NET stack (US4)
**Decision**: **.NET 10 LTS** via Fedora in-distro `sudo dnf install -y dotnet-sdk-10.0` (no MS prod repo needed on Fedora 44; .NET 8/9 EOL Nov 2026 — not pinned). **Aspire = standalone CLI**: `dotnet tool install -g Aspire.Cli` (binary `aspire`; the old `dotnet workload install aspire` is deprecated). fresh server: csharp-ls (clean dotnet-tool, pinnable, wired default); csharpier (global dotnet tool) for C# formatting; roslyn-ls documented as the richer alternative.
| lang | command | provisioning | args |
|---|---|---|---|
| csharp | csharp-ls | `dotnet tool install -g csharp-ls` | — |
| csharp (fmt) | csharpier | `dotnet tool install -g csharpier` | — |

> Delivered: csharp-ls / csharpier / Aspire.Cli install **unpinned** (`dotnet tool install -g <pkg>`,
> latest LTS-compatible) — the .NET SDK (`dotnet-sdk-10.0`) is the pinned reproducibility anchor for
> this stack; the dotnet-tool layer tracks the SDK. Pin with `--version` later if drift bites.
**Rationale**: csharp-ls installs cleanly as a pinnable dotnet global tool (Roslyn-ls ships inside the C# extension — no clean standalone pinned install, so it's the documented upgrade, not the wired default). `templates/dotnet` Aspire AppHost sets shared infra `.WithDataVolume()` + `.WithLifetime(ContainerLifetime.Persistent)`. (.NET tools are not mise-managed; they're `dotnet tool` — so the dotnet stack's fresh wiring uses dotnet-tool installs, resolved to absolute paths for the fresh config; `lib/fresh.sh` assumes mise, so the dotnet stack either extends the helper or wires csharp-ls/csharpier via a small dotnet-tool variant — finalized in data-model.)

## DevOps stack (US6) — **OpenTofu over Terraform**
**Decision**: all via mise `aqua:` backend, pinned:
| tool | mise spec | binary |
|---|---|---|
| OpenTofu | `aqua:opentofu/opentofu@1.11.6` | `tofu` |
| kubectl | `aqua:kubernetes/kubectl@1.35.2` | `kubectl` |
| helm | `aqua:helm/helm@4.1.4` | `helm` (Helm 4 GA) |
| k9s | `aqua:derailed/k9s@0.51.0` | `k9s` |
fresh server:
| lang | command | mise spec | args |
|---|---|---|---|
| terraform | tofu-ls | `aqua:opentofu/tofu-ls@0.0.22` | `serve` |
**Rationale**: Terraform is BSL-1.1 (non-OSI); OpenTofu (MPL-2.0) is the 2026 open default → `tofu` + `tofu-ls`. Helm 4 is GA.

## Data stack (US5) — **Valkey over Redis**, containers only
**Decision**: ship `templates/data/compose.yaml` (no host installs):
| service | image | volume | notes |
|---|---|---|---|
| postgres | `postgres:18` | `pgdata:/var/lib/postgresql/18/docker` | PG18's version-specific PGDATA path |
| valkey | `valkey/valkey:8.1` | `valkeydata:/data` | `--save 60 1 --appendonly yes` |
| dbgate | `dbgate/dbgate:7.2.0` | `dbgatedata:/root/.dbgate` | web GUI on :3000 |
**Rationale**: Redis 8 → AGPLv3; Valkey (BSD-3, drop-in) is the 2026 default. dbgate runs best as a container (web GUI, joins the compose network). No fresh LSP (infra stack).

## React Native stack (US7) — Android/Expo, **watchman dropped**
**Decision**: `node@22` (mise, shared global), `java@temurin-17` (mise — RN's validated JDK, not 21), android-tools (adb/fastboot — base build-tools already pulls `android-tools`; ensure present), Android SDK via cmdline-tools:
```
ANDROID_HOME=$HOME/Android/Sdk ; cmdline-tools unzipped to $ANDROID_HOME/cmdline-tools/latest/
sdkmanager "platform-tools" "platforms;android-35" "build-tools;36.0.0" "cmdline-tools;latest"
yes | sdkmanager --licenses        # unattended license accept
```
Expo: NO global `expo-cli` (deprecated) — `templates/react-native` uses `npx create-expo-app` / `npx expo`. `eas-cli` global only for cloud builds (out of scope). **watchman omitted** (no clean Fedora/mise install; Metro uses inotify in 2026 — ensure `fs.inotify.max_user_watches`). No fresh LSP rows (the web stack's TS servers cover RN/JS if `web` is also selected). Expo SDK 55 (RN 0.83) conservative / 56 (RN 0.85) newest.
**Rationale**: JDK 17 + Android API 35 + build-tools 36.0.0 are RN's current validated chain; unattended licenses via `yes | sdkmanager --licenses`.

## Testing (no real installs/network/containers/SDK)
**Decision**: extend `tests/fixtures/base/stubs.bash` (backward-compatible) with stubs for: `ddev`, `dotnet` (`tool install`/`workload`), `sdkmanager`+cmdline-tools download, `uv` (installer via curl|sh), `npx`/`expo`, and reuse the existing `mise`/`curl`/`rpm`/`dnf`/`docker` stubs. Per-stack bats assert: tool install attempted (right command/pin), fresh servers provisioned + wired (reusing fresh-lsp assertions), template files present, idempotent re-run no-op, unsupported-OS → engine failure, and stack isolation (a non-selected stack's tools absent). Real `jq` for config merges. No real SDK/containers/network.

## Outcome
No unresolved NEEDS CLARIFICATION (all self-resolved + context7-verified). Pins recorded per-stack
in `servers.tsv` / module data. Ready for Phase 1.
