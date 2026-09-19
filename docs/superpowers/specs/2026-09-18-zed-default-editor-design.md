# Zed as the default editor — design

**Date:** 2026-09-18 · **Status:** approved (grilling) · **Depends on:**
[macOS support](2026-09-18-macos-support-design.md) M1/M3 for the macOS cask and `utiluti`;
Linux parts land independently.

## Goal

Zed is the default GUI editor on every OS, installed and **configured with best
practices for a developer coming from VS Code**, covering this developer's stacks:
Laravel/Inertia, React/Next.js, React Native/Expo, Tailwind, .NET, Python, DevOps, with
Claude, Codex and Pi as in-editor agents. VS Code becomes opt-in.

## Decisions

| Topic | Decision |
|---|---|
| Install | macOS: cask `zed`; Linux: official `curl -f https://zed.dev/install.sh \| sh` (installs to `~/.local`) |
| Profiles | `editors` = `zed`, `fresh`, `fresh-lsp`; `vscode` → `optional-editors` |
| Config source | dev-boost ships a curated `settings.json` + `keymap.json` |
| Ownership | **Seed once** (chezmoi `create_`); afterwards the user owns the file. dev-boost only guarantees must-have keys via the new `config.jsonc_merge_deep` (see below) |
| Language servers | Point Zed at **dev-boost's pinned binaries** (`lsp.<server>.binary.path` → mise pins in `data/fresh/*-lsp.tsv`); Zed's own download only where a custom path isn't supported |
| C# | `csharp-ls` (licence-safe; C# Dev Kit/Roslyn not used by default) |
| `$VISUAL` / `$EDITOR` | `VISUAL="zed --wait"` only in a local GUI session; `EDITOR=fresh` otherwise; git `core.editor` unset so git follows `$VISUAL` → `$EDITOR` |
| Default apps (macOS) | `utiluti` (duti is unmaintained): code/text extensions open in Zed; macOS 26.4+ confirms each type — applied only when interactive, once per type, recorded; shared primitive with M5 `default-apps` |

## Config

Files: `~/.config/zed/settings.json`, `~/.config/zed/keymap.json` (same path on macOS
and Linux). Seeded from `dotfiles/dot_config/zed/create_settings.json` /
`create_keymap.json`.

### Seeded `settings.json` (content outline)
- **VS Code feel:** `"base_keymap": "VSCode"`; project panel left; `minimap.show: "auto"`;
  `toolbar.breadcrumbs: true`; `autosave: "on_focus_change"`; `format_on_save: "on"`.
- **Look:** `theme: {mode: "system", dark: "Tokyo Night", light: "Tokyo Night Light"}`
  (theme extension); `buffer_font_family: "JetBrainsMono Nerd Font"`, `ui_font_family`
  system default; terminal font JetBrainsMono Nerd Font; indent guides; bracket
  colorization.
- **Intelligence:** `inlay_hints.enabled: true`; `git.inline_blame.enabled: true`;
  `scrollbar.diagnostics: "all"`, `scrollbar.git_diff: true`.
- **Hygiene:** `telemetry: {diagnostics: false, metrics: false}`;
  `file_scan_exclusions` += `**/node_modules`, `**/vendor`, `**/bin`, `**/obj`,
  `**/.venv`, `**/.ddev`, `**/.next`, `**/dist`, `**/.expo`, `**/ios/Pods`,
  `**/android/build`, `**/public/build`, `**/bootstrap/ssr`.
- **Terminal:** `terminal.shell` = system login shell (zsh on macOS, bash on Linux).
- **Per stack:**

| Stack | Settings |
|---|---|
| React / Next.js | TSX via vtsls (built-in); ESLint `codeActionOnSave` `source.fixAll.eslint`; Prettier on save (built-in) |
| React Native / Expo | same TSX; Tailwind for `className` (NativeWind) |
| Tailwind (v3/v4) | built-in `tailwindcss-language-server`; `classRegex` for `cn(`, `clsx(`, `cva(`, `tw\``; `includeLanguages` `{php: html, blade: html}` |
| Inertia (Laravel + React) | PHP + Blade + TSX together; Tailwind across `.blade.php` and `.tsx`; no dedicated Inertia extension exists |
| Laravel / PHP | extensions `php`, `blade`; `languages.PHP.language_servers: ["intelephense", "!phpactor", "..."]`; Pint via project config (per-project dev-dependency, as today) |
| .NET | extension `csharp`; `languages.CSharp.language_servers: ["csharp-ls", "!roslyn", "!omnisharp", "..."]` |
| Python | `basedpyright` + `ruff` (formatter on save) |
| DevOps | extensions `terraform` (tofu-ls), `dockerfile`, `docker-compose`; YAML/TOML built-in |
| Misc | extensions `toml`, `sql`, `env`, `make`, `git-firefly`, `tokyo-night` |

- `auto_install_extensions`: the extension ids above → `true`.
- **Agents:** `agent_servers` entries for **Claude**, **Codex** and **Pi** (built-in ACP
  external agents; reuse existing CLI logins — no keys in the file).

### Must-have keys (merged on every run, never removed)
`auto_install_extensions` (dev-boost ids only — user additions preserved),
`agent_servers` (the three entries), `languages.CSharp.language_servers`,
`lsp.<server>.binary.path` for pinned servers, `telemetry`.

The existing `config.json_merge` is **not** usable here: it is shallow (top-level keys —
it would replace the user's whole `auto_install_extensions` object) and parses strict
JSON (Zed allows comments and trailing commas). New primitive
`config.jsonc_merge_deep(ctx, path, patch) -> bool`:
- parses JSONC (strip `//` and `/* */` comments + trailing commas, string-aware);
- **deep** merge: dicts recurse, patch leaves win, user keys never removed;
- no semantic change → no write (comments untouched);
- change needed → back up to `settings.json.devboost-bak`, write merged JSON
  (comments are lost only in this case; logged as a warning);
- unparseable → `NeedsUser` with the exact keys to add, never a rewrite.
The seeded file therefore carries **no comments** (explanations live in `docs/zed.md`),
so routine runs never touch a user's commented edits.

### `keymap.json`
Empty array seed (`[]`); VS Code bindings come from `base_keymap`, personal bindings go
here. Not merged afterwards.

## Environment

`env.sh`: if a local GUI session is detected (macOS: not SSH; Linux: `DISPLAY` /
`WAYLAND_DISPLAY` set and not SSH) and `zed` is on PATH → `VISUAL="zed --wait"`;
`EDITOR=fresh` always.

## Testing

- Seeded JSON parses; contains every must-have key; extension ids match a checked-in list.
- `jsonc_merge_deep`: comments/trailing commas parse; nested user keys preserved; no-op
  run leaves the file byte-identical; a needed change writes a `.devboost-bak`;
  unparseable input → `NeedsUser`; idempotent.
- `lsp.*.binary.path` values resolve from the fresh `*-lsp.tsv` pins (single source of
  truth).
- `env.sh` sets `VISUAL` only for GUI non-SSH sessions (bash + zsh).
- Install strategy argv per OS.

## Documentation

`docs/zed.md` (what's seeded vs guaranteed, per-stack notes, agents, bumping LSP pins,
importing VS Code settings via `zed: import vs code settings`), README editors section,
`docs/agents.md` (Zed external agents).

## Rollout

| # | PR | Notes |
|---|---|---|
| Z1 | Linux: `zed` module, seeded config, JSONC-aware merge, LSP pin wiring, `env.sh` VISUAL, profile change (VS Code opt-in), docs | lands independently |
| Z2 | macOS: cask + `utiluti` default apps | shipped with macOS M3 (one PR) |
