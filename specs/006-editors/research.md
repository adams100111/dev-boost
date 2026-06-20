# Phase 0 Research: editors

Spec clarifications settled in specify (VS Code channel, single curated extension list,
`fresh`-scoped LSP, mise-backend mechanism, always-on base set). Plan-level decisions
below. Package/CLI facts verified against current docs via **context7**
(`/microsoft/vscode-docs`, `/sinelaw/fresh`, `/jdx/mise`) on 2026-06-20.

## D1. VS Code install + curated extensions (US1)
**Decision**: `vscode/install.sh` adds the Microsoft yum repo and installs `code`:
```bash
sudo rpm --import https://packages.microsoft.com/keys/microsoft.asc
# write /etc/yum.repos.d/vscode.repo ([code] baseurl=…/yumrepos/vscode gpgcheck=1 gpgkey=…/microsoft.asc) — idempotent
sudo dnf install -y code
```
Then, for each ID in `modules/vscode/extensions.txt` **not** already in `code --list-extensions`,
run `code --install-extension <id> --force` (as the invoking user, not root). `verify`
(top-level): `command -v code` AND every baseline extension present in `code --list-extensions`.
**Rationale** (context7 `/microsoft/vscode-docs`): the MS repo is the documented Fedora
install and yields the native `code` CLI; `code --list-extensions` / `--install-extension`
are the documented headless extension commands and need no graphical session — so extension
provisioning is unattended (FR-015) and idempotent (FR-006). A sandboxed install would not
expose `code` on PATH nor see mise shims. `requires=[]` (the MS repo is self-contained).
**Curated baseline (language-agnostic editor quality + theme)**: `editorconfig.editorconfig`,
`esbenp.prettier-vscode`, `eamodio.gitlens`, `usernamehw.errorlens`, `gruntfuggly.todo-tree`,
`tamasfe.even-better-toml`, `redhat.vscode-yaml`, `mikestead.dotenv`,
`catppuccin.catppuccin-vsc`, `catppuccin.catppuccin-vsc-icons`. Per-language extensions
(Python, C#, …) are dev-stacks (Spec 7), not here.

## D2. `fresh` install + fallback chain (US2)
**Decision**: `fresh/install.sh` installs in this order, stopping at first success:
1. **Fedora `.rpm`** from the latest GitHub release —
   `curl -s https://api.github.com/repos/sinelaw/fresh/releases/latest` → pick the
   `browser_download_url` matching `.$(uname -m).rpm` → `curl -sL -o` → `sudo rpm -U`.
2. **Official install script** (autodetect) — `curl …/sinelaw/fresh/.../scripts/install.sh | sh`.
3. **Fallback** — `cargo install --locked fresh-editor` (cargo from base build-tools/mise).
`verify`: `command -v fresh`. `requires=[]`.
**Rationale** (context7 `/sinelaw/fresh` README): these are the three documented install
paths; rpm first keeps it dnf-managed, the script is the vendor's autodetect, cargo is the
universal fallback. A failure after all three exhausts → `die` naming `fresh` + the last
command (FR-005, FR-013 — never a silent skip).

## D3. mise as the runtime source for LSP/formatters (US3, core mechanism)
**Decision**: every `fresh` language server/formatter is installed as a **mise-managed,
pinned tool** via mise's package backends, NOT via raw `npm/cargo/go -g`:
```bash
mise use -g npm:basedpyright@<pin>      # python LSP (+ its node runtime), pinned
mise use -g npm:bash-language-server@<pin>
mise use -g cargo:taplo-cli@<pin>       # toml
# …also github:/aqua: for prebuilt binaries
```
`lib/fresh.sh::fresh_lsp_provision <lang> <fresh-command> <backend:tool@pin>`:
1. `mise use -g <backend:tool@pin>` (idempotent). The `@pin` lives in-repo in `modules/fresh-lsp/servers.base.tsv` (the source of truth); `mise use -g` records the resolved version into the user-global `~/.config/mise/config.toml` (machine state), as the base `mise` module already does.
2. resolve the absolute binary path with `mise which <fresh-command>` (PATH-independent — no reliance on shims being on PATH at editor-launch time).
3. jq-merge `{ "lsp": { "<lang>": { "command": "<abs path>", "args": [...], "enabled": true } } }`
   into `~/.config/fresh/config.json`, preserving every other key (theme, editor, formatter, languages).
**Rationale** (context7 `/jdx/mise`): `mise use -g npm:/cargo:/go:/github:/aqua:<tool>@<ver>`
installs the tool *and* provisions/​pins its runtime in one step (Principle III). Resolving
`mise which` to an absolute path makes `fresh`'s `command` robust regardless of shell PATH
ordering. This **supersedes** the legacy `workstation-config/fresh-lsp.sh` (raw
`npm/cargo/go install`, system runtimes) — same servers, but pinned + reproducible.

## D4. `fresh` config ownership + the idempotent `lsp` merge (US3)
**Decision**: `~/.config/fresh/config.json` is **owned by the `fresh-lsp` module**, not by
chezmoi. The module ships a base template `modules/fresh-lsp/config.base.json`
(`theme:"catppuccin-mocha"`, editor defaults, per-language `formatter` + format-on-save);
`install.sh` writes it **only if the file is absent** (never clobbers a user-edited file),
then `lib/fresh.sh` jq-merges each provisioned server's `lsp` entry on top.
**Rationale**: context7 `/sinelaw/fresh` confirms a single `config.json` with an `lsp` block
(per-language `command`/`args`/`enabled`) and a `theme` field (`catppuccin-mocha` is a named
theme), and formatter routing via LSP features. The design doc (§670/§676) wanted chezmoi to
own the base config with a `post.sh` merging `.lsp` — but it also flagged the resulting
clobber tension (a chezmoi re-apply would drop the merged `lsp` block). Module-ownership +
idempotent jq-merge satisfies the **same intent** (managed base config + merged LSP) while
honouring Principle II (idempotent, self-healing, no clobber). This is a deliberate
mechanism reconciliation, recorded here as the source of truth for the decision.

## D5. Profile-scoping is structural, base set is the row-6 deliverable (US3)
**Decision**: the `editors` profile = `["vscode","fresh","fresh-lsp"]`, and `fresh-lsp`
applies **only the always-on base set** (markdown→marksman, toml→taplo, bash→bash-language-server,
json/yaml→a json/yaml server) from `servers.base.tsv`. The **per-stack** servers
(intelephense↔laravel, csharp-ls/csharpier↔dotnet, basedpyright/ruff↔python,
ts/eslint/prettier/tailwind↔web, terraform-ls↔devops) are delivered by **dev-stacks (Spec 7)**
as one small fresh-lsp module per stack profile, each calling `lib/fresh.sh`.
**Rationale**: this makes FR-007/SC-004 ("a non-selected stack's server MUST NOT be installed")
**true by construction** — the engine only installs a stack's module when that profile is
selected; no conditional logic anywhere. It keeps row 6 self-contained and fully testable now
(base set + mechanism), and gives row 7 a one-file-per-stack extension point (Principle I).
The full stack→server map is documented in `data-model.md` so Spec 7 has its contract.

## D6. Unsupported-OS via data (no guard)
**Decision**: each module declares ONLY an `[install].fedora` key ⇒ on a non-Fedora OS the
engine's `module_install_cmd` finds no match and reports the module **unsupported** (a
failure), satisfying FR-013 purely by data — no in-module OS guard.

## D7. Testing (no installs/network/editor)
**Decision**: extend `tests/fixtures/base/stubs.bash` (backward-compatible) with:
- `code` stub: `--list-extensions` emits a `STUB_CODE_EXTENSIONS` knob; `--install-extension`
  appends to that set + a call log; repo-add via the existing `dnf`/`rpm`/file stubs.
- `mise` stub: `use -g <spec>` records to a log + marks the tool installed (`STUB_MISE_TOOLS`);
  `which <bin>` prints a deterministic fake absolute path (or fails if not installed).
- `fresh` install: stub `curl`/`rpm -U`/`cargo` outcomes via a `STUB_FRESH_INSTALL_VIA`
  knob (rpm|script|cargo|none) so the fallback chain is exercised; `command -v fresh` honours it.
Real `jq` runs the merge against a temp `config.json`. Tests assert: MS repo written + `code`
install + only-missing extensions installed + idempotent skip; fresh primary install and each
fallback + all-fail→named die; `fresh_lsp_provision` does `mise use -g` + `mise which` + merges
the `lsp` entry, preserves non-`lsp` keys, seeds base config when absent, re-run no-op;
editor-missing→named fail; unsupported-OS (non-fedora `OS_DISTRO`) → engine failure.
**Rationale**: hermetic, §V real-behavior; mirrors Specs 1–5.

## Outcome
No unresolved NEEDS CLARIFICATION. Ready for Phase 1.
