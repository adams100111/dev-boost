# Pi harness module — design

**Date:** 2026-09-07
**Status:** Design approved (brainstormed + fact-checked via context7 + web + the live `~/.pi`
+ the operator's own `agent-harness` repo).
**Mission fit:** Extends the reusable-across-devices agent pattern (see the `claude` and `codex`
modules) to the **Pi coding agent** — but by a fundamentally different mechanism, because the
operator already owns a manifest-driven Pi installer.

## The decisive fact

Pi (`@earendil-works/pi-coding-agent`, by Mario Zechner / "badlogic"; config under `~/.pi/agent/`;
docs `pi.dev`) is configured on this operator's machines by **their own first-party lifecycle CLI,
`harness-cli`**, living in the private repo **`adams100111/agent-harness`** (checked out at
`~/repos/my-harness`). `harness-cli`:

- reads a **git-tracked `harness-manifest.toml`** (the single source of truth) and reconciles a
  machine's `~/.pi/agent/*` to it — pi-packages, MCP servers (`mcp.json`), skills
  (`~/.pi/agent/skills`), a first-party `pi-assurance` pi-extension, and herdr plugins;
- installs Pi and herdr themselves as version-floor **runtimes**;
- owns **secret provisioning** via `age` (default) or **`pass`** (`harness secrets init/provision`),
  materializing `~/.pi/agent/harness.env` (0600) that `pi-mcp-adapter` reads for `${VAR}` refs;
- is idempotent (verify-then-act), supports `upgrade/downgrade/pin/rollback`, and writes
  `harness.lock`. Its design spec explicitly states it is **self-contained and "depends on nothing
  from dev-boost."**

**Consequence:** replicating Pi config directly inside dev-boost (a `pi-config`/`pi-packages`/
`pi-mcp`/`pi-skills` cluster mirroring the codex modules) would **duplicate `harness-manifest.toml`
and drift from it** the moment a pin changes in either place. The claude/codex modules configure
their agents directly *because those agents have no manifest-driven installer of their own.* Pi does.
So the faithful adaptation is **not** replication — it is a thin **bootstrap-and-delegate** module.

## What the bootstrap is good for (the residual gap)

`agent-harness`'s own `install.sh` is a **CLI bootstrapper, not a fresh-box installer**: it requires
`node ≥ 22.19` + `npm` present just to build, needs `git`, clones a **private** repo (needs a token
or `gh` auth), and then `harness install` runs `mise use -g node@22` assuming `mise` already exists.
None of node/mise/gh-auth exist on a clean laptop. dev-boost is exactly the layer that makes
`install.sh` runnable, and it adds, specifically:

1. **Fresh-box prerequisites in dependency order** — `mise`+node, `git`, `gh`, `age`, `curl` (all
   already installed by `full`/`base`/`cli`), guaranteed to precede the harness bootstrap.
2. **Automatic private-repo auth** — the `secrets` module already provisions the operator's GitHub
   PAT into `~/.git-credentials` (`credential.helper store`), so cloning `adams100111/agent-harness`
   authenticates with no manual `gh auth login`.
3. **Pre-staged `pass` store** — dev-boost's `pass-store` clones `DEVBOOST_PASS_REPO`, precisely the
   backend `harness secrets init --backend pass` consumes.
4. **One unattended run** — "bring my Pi harness up" folds into the same `devboost install` that
   builds the workstation, instead of a manual follow-up that itself needs tools not yet installed.

It adds **sequencing + credential wiring**, not capability. Everything about *what the harness
contains and how `~/.pi` is configured* stays owned by `harness-cli` off the git-tracked manifest.

## Decisions (from brainstorming)

1. **Approach: bootstrap `harness-cli`, delegate.** One thin module; no duplication of the manifest;
   single source of truth; never drifts. (Rejected: a codex-style replicate cluster.)
2. **Profile: `full`.** Pi ships on every box like claude/codex. Plus a named `pi` profile alias
   (`pi = ["pi-harness"]`) for a clean `devboost install pi` entry point, parallel to claude/codex.
3. **Automation depth: bootstrap + provision + guarded install.** The module:
   (a) **bootstraps** `harness` onto PATH (HARD — raises `ConfigError` on failure: this is the core
   deliverable); (b) **provisions** secrets from `pass` if a store is present (SOFT — skip+log
   otherwise); (c) runs **`harness install` best-effort** (SOFT — logs the finish command, never
   reds the `full` build if the manifest/secrets aren't ready). The only remaining manual touch is a
   one-time **`pi /login`** — the same one-time auth claude/codex already require.
4. **Version pin: `DEVBOOST_HARNESS_REF`.** The clone is pinned to a specific release-ready commit
   (module constant `DEFAULT_HARNESS_REF`), overridable via the `DEVBOOST_HARNESS_REF` env var;
   the fetched `install.sh` and the harness checkout use the same ref. Repo overridable via
   `DEVBOOST_HARNESS_REPO` (default `adams100111/agent-harness`).

## Two honest caveats (surfaced, not hidden)

- **`pi /login` cannot be automated** (OAuth device flow). Identical to claude/codex: the module
  configures everything, but the first session authenticates once per box. Not a parity regression.
- **The manifest isn't release-ready yet** — `HERDR_PIN.sha256` is `REPLACE_WITH_VERIFIED_SHA256`
  and the herdr-only secrets (`HERDR_RELAY_TOKEN`, `HERDR_TG_*`) aren't in the pass store. A full
  `harness install` would fail *loudly on the herdr runtime component today*. The **guarded** install
  makes this safe: Pi's own side (context7/google keys, which *are* in pass) provisions and installs
  cleanly; the herdr component logs a warning and the workstation build stays green. When the operator
  finalizes the manifest + lands the herdr secrets, the same module self-completes with no code change.

## Architecture

**One module. No dotfiles.** `harness-cli` explicitly does **not** manage model/provider prefs or
`AGENTS.md`/`CLAUDE.md` (its design puts those 100% native to Pi). So — unlike the codex module,
which shipped an `AGENTS.md` — the Pi module ships **no chezmoi dotfiles and no `pi-config`**. There
is nothing for dev-boost to write into `~/.pi`; `harness install` is the sole writer.

| Module | Job | `requires` |
|---|---|---|
| `pi-harness` | Ensure node (Mise); clone+build `agent-harness` → `harness` on PATH (HARD); guarded `harness secrets init --backend pass` + `provision` (if pass present); best-effort `harness install`. `verify` = `which harness`. | `Mise`, `Secrets` |

`requires = (Mise, Secrets)` **only** — deliberately **not** `PassStore` (it raises `ConfigError`
when pass is unconfigured, which would break `full` on pass-less boxes). Provisioning degrades
gracefully instead.

**Profiles** (`profiles.toml`): add `pi = ["pi-harness"]`; add `"pi"` to `full`. Profile name `pi`
is disjoint from the module name `pi-harness` (collision rule holds).

### `pi-harness.install(ctx)` — shape

1. **Ensure node:** `if not ctx.ex.which("node"): mise.use_global(ctx, "node@lts")` (mirrors
   `codex-code`).
2. **Bootstrap (HARD):** clone `https://github.com/<DEVBOOST_HARNESS_REPO>` at `<ref>` (authenticated
   by the `secrets`-provisioned `~/.git-credentials`) and run its `install.sh` with `HARNESS_REF=<ref>`
   → builds `~/.local/share/harness` + `~/.local/bin/harness`. On failure raise
   `ConfigError("pi-harness: cloning/building agent-harness (<repo>@<ref>) failed … check the PAT has
   repo read scope")`. (The PAT is recoverable from the age bundle via
   `age.decrypt(bundle_path(), key_path())["GITHUB_PAT"]` if the `gh api … | bash` one-liner is used
   instead of a plain git clone; either path is acceptable — both authenticate off the same PAT.)
3. **Provision (SOFT):** if a pass store is usable (`ctx.ex.which("pass")` and the store dir exists),
   run `harness secrets init --backend pass --yes` then `harness provision`; on failure `log.warn` and
   continue. If no pass store, `log.warn("pi-harness: no pass store — skipping secret provisioning;
   run `harness secrets init` later")` and continue.
4. **Install (SOFT):** run `harness install --yes`; on failure `log.warn` with the exact finish
   command (`harness doctor` / `harness install`) and continue — never raise. Log a one-line reminder
   that the first Pi session needs `pi /login`.

`verify(ctx)` → `ctx.ex.which("harness")`. Idempotent: `install.sh` re-fetches the ref and rebuilds;
`harness install` reconciles (unchanged components skipped).

## Interaction with existing modules

- **herdr:** dev-boost already ships a `herdr` module (in `cli`) and `herdr-plugins`
  (`optional-agents`). `harness install` also declares a herdr runtime + herdr plugins per its
  manifest. Both reconcile idempotently to their own pins; the guarded install means any herdr
  overlap/conflict degrades to a warning rather than a hard failure. (No attempt to unify the two
  herdr installers in this spec — deliberately deferred.)
- **pass:** for automatic provisioning in `full`, the operator includes `security-cli` (pass +
  pass-store) or otherwise ensures a pass store; without it, provisioning is skipped (guarded) and
  Pi still installs (its MCP servers just lack their `${VAR}` secrets until `harness provision` runs).

## Not in scope (owned elsewhere / excluded)

`harness-manifest.toml` contents (packages/mcp/skills/extensions/herdr — owned by `harness-cli`);
`~/.pi/agent/settings.json`, `mcp.json`, `AGENTS.md`, model/provider prefs (native Pi / harness-cli);
`auth.json` + `pi /login` (Pi-native OAuth, never automated); `~/.pi-lens/` runtime; the age secret
*values* and `HERDR_PIN.sha256` (operator-provided, pre-release placeholders today).

## Verification spike — RESOLVED (facts from the live install + the repo)

1. **Pi identity/config:** `@earendil-works/pi-coding-agent@0.84.2`, config `~/.pi/agent/`, skills
   shared at `~/.agents/skills`, MCP via `pi-mcp-adapter` reading `mcp.json` with `${VAR}`/`!cmd`
   expansion. (context7 `/earendil-works/pi`; bundled docs; live `~/.pi/agent`.)
2. **harness-cli surface:** `harness setup|doctor|status|install|remove|pin|downgrade|upgrade|
   rollback|project|import|secrets init|secrets set|secrets list|provision|exec|remote-harden`;
   secret backends `age` (default) / `pass`; writes `~/.pi/agent/{settings.json via pi install,
   mcp.json, skills/}`; **does not** manage prefs/AGENTS.md. (`packages/harness-cli/src/…`.)
3. **install.sh:** bootstraps the CLI only (requires node≥22.19+npm+git; private-repo auth via
   `GITHUB_TOKEN`/`GH_TOKEN`/`gh`/plain-git-with-credential-store); env `HARNESS_REPO`, `HARNESS_REF`,
   `HARNESS_DIR`, `HARNESS_BIN_DIR`; idempotent; installs to `~/.local/share/harness` +
   `~/.local/bin/harness`. Does **not** install node/mise/pi.
4. **dev-boost base already provides:** `mise`+node, `git`, `curl` (`base`), `gh` (`cli`), `age` +
   the GitHub PAT in `~/.git-credentials` (`secrets`), `pass`+`pass-store` (`security-cli`). Residual
   gap = exactly steps 1–2 above, which `pi-harness` performs.
5. **Patterns to mirror:** `codex-code` (Mise require + node@lts + shell installer);
   `PassStore`/`ConfigError` (actionable hard-fail); `secrets` (`age.decrypt(bundle_path(),
   key_path())` → `GITHUB_PAT`, and the `~/.git-credentials` it writes).

## Sources

- context7 `/earendil-works/pi`; `pi.dev`; `github.com/earendil-works/pi-mono`.
- Live `~/.pi/agent/{settings.json,mcp.json}`, the installed `@earendil-works/pi-coding-agent@0.84.2`
  + `pi-mcp-adapter@2.27.0` + `apmantza/pi-lens@v4.1.1` docs.
- `~/repos/my-harness`: `install.sh`, `harness-manifest.toml`, `packages/harness-cli/…`,
  `docs/harness-cli/{operator-runbook,secrets-and-auth,manifest,per-project}.md`,
  `docs/superpowers/specs/2026-08-22-harness-lifecycle-cli-design.md`.
- dev-boost `modules/{codex_code,optional,secrets,mise}.py`, `profiles.toml`.
