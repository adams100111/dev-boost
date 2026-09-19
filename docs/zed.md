# Zed — the default editor

`devboost install editors` (part of `full` and `omarchy`) installs [Zed](https://zed.dev) on
Fedora, Ubuntu and Arch/Omarchy with the official user-local installer
(`~/.local/zed.app`, `~/.local/bin/zed`; no sudo). The script is downloaded with
`curl -fsSL --proto =https --tlsv1.2` into a private temp directory (`mktemp -d`, mode 0700),
run with `sh`, and the directory is then deleted, so a failed download fails the install
instead of silently running nothing. Zed updates itself. GUI only — skipped on headless
servers. VS Code is opt-in: `devboost install optional-editors`.

## Seeded vs guaranteed

| | What | When |
|---|---|---|
| **Seeded** | `~/.config/zed/settings.json` + `keymap.json` (`[]`) | only if absent — then the files are **yours** |
| **Guaranteed** | `auto_install_extensions` (dev-boost's ids; yours are kept), `agent_servers` (Claude, Codex, Pi), `languages.CSharp.language_servers`, `lsp.<server>.binary` for dev-boost-pinned servers, `telemetry` (off) | every `devboost install` |

Guaranteed keys are **deep-merged**: your other keys (and your own keys inside those objects)
are never removed. If nothing needs changing the file is not touched — the bytes stay
identical (comments survive). If something does need changing, the original is backed up to
`settings.json.devboost-bak` — but only when no backup exists yet, or the file had comments or
trailing commas (so a later plain-JSON write never clobbers an earlier backup of your real,
commented file) — and the file is rewritten as plain JSON (non-ASCII kept as-is, file mode
kept; a symlinked `settings.json` is written through to its target, so the link survives);
comments are lost only when they were present, and a warning names the backup.

**Backup limit:** once a backup exists and your file is plain JSON (no comments or trailing
commas), a later rewrite does **not** refresh the backup — the backup keeps the older version.
That is safe because a rewrite only ever changes guaranteed keys: everything else in the
current file is carried over as-is, so the only thing not recoverable from the backup is the
previous value of a guaranteed key.

If the file doesn't parse (or isn't UTF-8), dev-boost changes nothing and reports `blocked`
with the exact keys to add.

**When the merge runs:** the `zed` module merges on every `devboost install` that includes it.
The LSP modules (`fresh-lsp`, the per-stack `*-lsp` modules, `dotnet-lsp`) also merge the
guaranteed keys right after installing their servers, whenever `~/.config/zed/settings.json`
exists on a supported Linux family — even if the run doesn't include the `editors` profile.
Dropping the `editors` profile therefore does **not** stop the merge. It never runs on macOS
(until Z2), never creates the file, and a failure there is only a warning. Setting a
guaranteed extension to `false` does not stick — remove the extension from Zed instead of
fighting the merge.

## What the seed configures

- **VS Code feel:** VS Code keymap, project panel left, minimap auto, breadcrumbs, autosave on
  focus change, format on save. Import your VS Code settings with the command palette:
  `zed: import vs code settings`.
- **Look:** Tokyo Night (follows the system light/dark mode), JetBrainsMono Nerd Font in the
  buffer and terminal, indent guides, rainbow brackets.
- **Intelligence:** inlay hints, inline git blame, diagnostics + git diff in the scrollbar.
- **Hygiene:** telemetry off; heavy/generated dirs hidden from the file tree and search
  (`node_modules`, `vendor`, `bin`, `obj`, `.venv`, `.ddev`, `.next`, `dist`, `.expo`,
  `ios/Pods`, `android/build`, `public/build`, `bootstrap/ssr`). Delete an entry from
  `file_scan_exclusions` if you need to browse it (e.g. a repo's `bin/` scripts).
- **Terminal:** your login shell.

## Per stack

| Stack | How |
|---|---|
| React / Next.js / React Native | TS/TSX via vtsls (Zed-managed); ESLint `source.fixAll.eslint` on format; Prettier on save |
| Tailwind (v3/v4) | built-in server (dev-boost-pinned); classes inside `cn()`, `clsx()`, `cva()`, `cx()`, `` tw`…` ``; also in PHP and Blade |
| Laravel / Inertia | `php` + `blade` extensions; Intelephense (free tier); Tailwind in `.blade.php` and `.tsx`. Pint is not wired into Zed — run `ddev exec vendor/bin/pint` |
| .NET | `csharp` extension with `csharp-ls` (no Roslyn/OmniSharp) |
| Python | basedpyright + ruff (formats on save) |
| DevOps | `opentofu` (tofu-ls), `dockerfile`, `docker-compose`; YAML/TOML built in |
| Misc | `toml`, `sql`, `env`, `make`, `git-firefly`, `tokyo-night` |

## Pinned language servers

Zed runs dev-boost's pinned servers — the same ones fresh uses — via their mise shims
(`$MISE_DATA_DIR/shims/<cmd>`, else `$XDG_DATA_HOME/mise/shims/<cmd>`, else
`~/.local/share/mise/shims/<cmd>`), and `csharp-ls` from `~/.dotnet/tools`. The map is
`data/zed/lsp-binaries.tsv`; the **versions** live only in `data/fresh/*.tsv`. To bump one, edit
its row there and re-run `devboost install <stack>` — the shim path doesn't change, so Zed
picks the new version up after a restart. Servers not in `data/zed/lsp-binaries.tsv` (vtsls,
ESLint, Markdown, bash, TOML) are downloaded by Zed.

## In-editor agents

Claude (`claude-acp`), Codex (`codex-acp`) and Pi (`pi-acp`) are registered as ACP registry
agents: Zed downloads each adapter on first use; each reuses its own CLI login (see
[agents](agents.md)). No keys are stored in `settings.json`.

## `$VISUAL` / `$EDITOR`

`EDITOR=fresh` everywhere. `VISUAL="zed --wait"` only in a local desktop session (not over SSH)
and only when `zed` is installed — set in `~/.config/devboost/env.sh`. git has no
`core.editor`, so commit messages open in Zed on the desktop and in fresh over SSH.

## macOS (planned — milestone Z2)

This module is Linux-only today: `_zed.SUPPORTED_FAMILIES = ("fedora", "debian", "arch")` is
both `Zed.families` and the guard on every path that writes Zed config for another module (the
LSP hook), and `zed_install_steps()` raises `UnsupportedOS` on macOS. `_zed.py` has no other
OS branches — it is written to be reused unchanged. Adding `"macos"` to `SUPPORTED_FAMILIES`
is **not** enough for Z2: `Zed.install` always calls `zed_install_steps` today, so Z2 must
also route the install through `pkg` with `per_os = OsMap(macos=BrewCask("zed"))` (the
Homebrew-cask install, M2), then call the same `ensure_config()` used on Linux.
`zed_install_steps` stays Linux-only — macOS installs through the cask, not the installer
script.
