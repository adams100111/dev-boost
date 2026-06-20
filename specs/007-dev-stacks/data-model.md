# Phase 1 Data Model: dev-stacks

No database. "Data" = per-stack module manifests, profile entries, per-stack `servers.tsv`,
`templates/<stack>/` content, and the resulting system/user state (mise pins, dotnet tools, SDK,
docker volumes). All pins context7-verified 2026-06 (research.md).

## profiles.toml (EDIT — add 7 entries)
```toml
python       = ["uv","python-lsp"]
web          = ["web-runtimes","web-lsp"]
laravel      = ["ddev","laravel-lsp"]
dotnet       = ["dotnet-sdk","aspire","dotnet-lsp"]
data         = ["data"]
devops       = ["devops-tools","devops-lsp"]
react-native = ["web-runtimes","android-sdk","expo"]   # shares web-runtimes (node@22)
```
`*-lsp` modules `requires=["fresh","mise"]` (and their toolchain module). Fedora-only `[install]`.

## Modules (all `category="dev-stacks"`, escape-hatch, only `[install].fedora`)
| module | requires | what it does |
|---|---|---|
| `uv` | `[]` | `curl -LsSf https://astral.sh/uv/0.11.23/install.sh \| sh`; verify `command -v uv` |
| `python-lsp` | `["fresh","mise","uv"]` | provision `servers.python.tsv` via `fresh_lsp_provision`; seed `templates/python` |
| `web-runtimes` | `["mise"]` | `mise use -g node@22 pnpm@11.8.0 bun@1.3.14`; verify mise-resolvable |
| `web-lsp` | `["fresh","mise","web-runtimes"]` | provision `servers.web.tsv`; seed `templates/nextjs` |
| `ddev` | `["docker"]` | write `/etc/yum.repos.d/ddev.repo` (idempotent) + `dnf install --refresh ddev` + `mkcert -install`; verify `command -v ddev` |
| `laravel-lsp` | `["fresh","mise","ddev"]` | provision `servers.laravel.tsv` (intelephense); seed `templates/laravel` (pint at template level) |
| `dotnet-sdk` | `[]` | `dnf install -y dotnet-sdk-10.0`; verify `command -v dotnet` && SDK 10 present |
| `aspire` | `["dotnet-sdk"]` | `dotnet tool install -g Aspire.Cli` (guarded); verify `command -v aspire` |
| `dotnet-lsp` | `["fresh","dotnet-sdk"]` | `dotnet tool install -g csharp-ls csharpier` (guarded) + `fresh_lsp_wire` them; seed `templates/dotnet` |
| `android-sdk` | `["mise"]` | `mise use -g java@temurin-17`; install cmdline-tools → `sdkmanager` packages (API 35, build-tools 36.0.0) + `yes \| sdkmanager --licenses`; verify SDK marker |
| `expo` | `["web-runtimes"]` | seed `templates/react-native` (npx create-expo-app flow); verify template present (no global expo-cli) |
| `devops-tools` | `["mise"]` | `mise use -g aqua:opentofu/opentofu@1.11.6 aqua:kubernetes/kubectl@1.35.2 aqua:helm/helm@4.1.4 aqua:derailed/k9s@0.51.0`; verify mise-resolvable |
| `devops-lsp` | `["fresh","mise","devops-tools"]` | provision `servers.devops.tsv` (tofu-ls) |
| `data` | `["docker"]` | seed `templates/data/compose.yaml` (postgres:18 + valkey/valkey:8.1 + dbgate/dbgate:7.2.0, named volumes); verify compose.yaml present (NO host db install) |

## Per-stack fresh server maps (`modules/<stack-lsp>/servers.tsv`, TAB-separated: lang, command, spec, args)
**python** (`python-lsp/servers.tsv`):
```
python	basedpyright-langserver	pipx:basedpyright@1.39.8	--stdio
pythonfmt	ruff	pipx:ruff@0.15.18	server
```
**web** (`web-lsp/servers.tsv`):
```
typescript	typescript-language-server	npm:typescript-language-server@5.3.0	--stdio
eslint	vscode-eslint-language-server	npm:vscode-langservers-extracted@4.10.0	--stdio
tailwindcss	tailwindcss-language-server	npm:@tailwindcss/language-server@0.14.29	--stdio
```
(prettier provisioned as a mise tool `npm:prettier@3.8.4`; wired as the web formatter in `templates/nextjs/.fresh/config.json`.)
**laravel** (`laravel-lsp/servers.tsv`):
```
php	intelephense	npm:intelephense@1.14.4	--stdio
```
(pint = per-project composer dep; wired in `templates/laravel/.fresh/config.json` → `vendor/bin/pint`.)
**devops** (`devops-lsp/servers.tsv`):
```
terraform	tofu-ls	aqua:opentofu/tofu-ls@0.38.7	serve
```
**dotnet** (NOT a tsv — dotnet-tool servers, wired via `fresh_lsp_wire`): csharp-ls → `~/.dotnet/tools/csharp-ls`; csharpier formatter in `templates/dotnet/.fresh/config.json`.

## `lib/fresh.sh` (EDIT — additive)
Extract a merge-only primitive used by both mise- and dotnet-tool-based stacks:
```
fresh_lsp_wire <lang> <absolute-command> [args…]   # jq-merge lsp.<lang>={command,args,enabled:true}, idempotent, preserve keys
fresh_lsp_provision <lang> <cmd> <backend:tool@pin> [args…]  # mise use -g; abs=$(mise which cmd); fresh_lsp_wire "$lang" "$abs" args…
```
Behavior of `fresh_lsp_provision` is unchanged (editors suite must stay green).

## templates/<stack>/
| template | key contents |
|---|---|
| `python/` | `.fresh/config.json` (tab 4), `pyproject.toml` starter (uv), README |
| `nextjs/` | `.fresh/config.json` (tab 2, formatter prettier), README (pnpm/bun) |
| `laravel/` | `.fresh/config.json` (php formatter `vendor/bin/pint`), README ddev `laravel new` flow |
| `dotnet/` | `.fresh/config.json` (csharpier), AppHost starter with `.WithDataVolume()`+`.WithLifetime(ContainerLifetime.Persistent)`, README aspire CLI |
| `react-native/` | `.fresh/config.json`, README `npx create-expo-app` / `npx expo prebuild -p android` |
| `data/compose.yaml` | postgres:18 (vol `/var/lib/postgresql/18/docker`), valkey/valkey:8.1 (`--save 60 1 --appendonly yes`, vol `/data`), dbgate/dbgate:7.2.0 (`:3000`, vol `/root/.dbgate`) |

## Validation rules (from FRs)
| Rule | Source |
|---|---|
| 7 independent stack profiles, deps declared | FR-001, FR-002 |
| python=uv + template | FR-003 |
| web=node/pnpm/bun (mise) + template | FR-004 |
| laravel=ddev only, no host php/composer | FR-005 |
| dotnet=.NET10 SDK + aspire CLI + persistent-infra template | FR-006 |
| data=postgres+valkey+dbgate compose, no host db | FR-007 |
| devops=opentofu/kubectl/helm/k9s (mise) | FR-008 |
| react-native=node/jdk17/android-sdk(API35,licenses)/android-tools/expo(npx) | FR-009 |
| LSP stacks wire fresh via lib/fresh.sh | FR-010 |
| versions pinned in-repo | FR-011 |
| verify = idempotency guard | FR-012 |
| stack isolation | FR-013 |
| unsupported/precondition → named failure | FR-014 |
| add tool/pin/mapping = data change | FR-015 |
| zero prompts (licenses auto-accepted) | FR-016 |
| templates present, never clobber | FR-017 |

## Ordering (depsort via requires)
```
mise, docker, fresh (base/editors) → web-runtimes → {web-lsp, expo, android-sdk(java)}
uv → python-lsp ; ddev → laravel-lsp ; dotnet-sdk → {aspire, dotnet-lsp} ; devops-tools → devops-lsp
data → (docker only)
non-Fedora: engine reports each unsupported
```
