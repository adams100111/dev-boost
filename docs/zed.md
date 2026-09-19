# Zed — the default editor

`devboost install editors` (part of `full`, `omarchy` and the macOS `macos` profile)
installs [Zed](https://zed.dev). On Fedora, Ubuntu and Arch/Omarchy it uses the official
user-local installer (`~/.local/zed.app`, `~/.local/bin/zed`; no sudo): the script is
downloaded with `curl -fsSL --proto =https --tlsv1.2` into a private temp directory
(`mktemp -d`, mode 0700), run with `sh`, and the directory is then deleted, so a failed
download fails the install instead of silently running nothing. On macOS it installs the
`zed` Homebrew cask instead (see [macOS](#macos) below). Zed updates itself either way. GUI
only — skipped on headless servers. VS Code is opt-in: `devboost install optional-editors`.

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
exists on a supported family (Fedora, Debian, Arch, or — since Z2 — macOS) — even if the run
doesn't include the `editors` profile. Dropping the `editors` profile therefore does **not**
stop the merge. Off a supported family it never runs and never creates the file, and a
failure there is only a warning. Setting a guaranteed extension to `false` does not stick —
remove the extension from Zed instead of fighting the merge.

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
`env.sh` sources `~/.config/devboost/local.sh` last if it exists (never shipped or managed by
dev-boost), so a machine that wants a different `EDITOR`/`VISUAL` can override it there.

## macOS

Same files, same guarantees: `~/.config/zed/settings.json` and `keymap.json` are seeded
once (chezmoi `create_`), and the must-have keys are merged on every run
(`_zed.SUPPORTED_FAMILIES` includes `macos`). Zed comes from the `zed` Homebrew cask
(`Zed.per_os`), which also puts the `zed` CLI on PATH. Zed updates itself, so
`devboost install --update` skips the cask's own upgrade step — but the `zed` module still
runs on `--update` (its whole macOS install is one cask), so the config merge always
happens and the default-apps step can still report `blocked` if that run is unattended.

**Default app.** Code and text files open in Zed: the Zed rows of
`data/macos/default-apps.tsv`, applied through `utiluti` (`exec/primitives/default_apps.py`,
shared with M5's `default-apps` module). macOS 26.4+ asks you to confirm every change, one
dialog per file type (extensions sharing a type share one), so dev-boost only tries when a
terminal is attached, asks each type once, and records it in
`~/.local/state/devboost/default-apps.json` — a "no" is never asked again. An unattended
run leaves `zed` **blocked** with "run `devboost install zed` in a terminal". `.ts` is also
MPEG transport-stream video on macOS; on a dev box it opens in Zed.

**Your own editor.** `~/.config/devboost/local.sh` is sourced last by `env.sh`; set
`EDITOR` / `VISUAL` there.

**First run.** The first `devboost install zed` (or any LSP module, since the LSP hook
merges Zed's config too) rewrites `~/.config/zed/settings.json` as plain JSON — every key
already in the file is kept, and dev-boost only adds `auto_install_extensions`,
`agent_servers` and the CSharp language server entries, the same must-have keys as Linux.
The original file, including its comments and trailing commas, is kept alongside it as
`settings.json.devboost-bak`. The chezmoi apply that seeds `settings.json` in the first
place only creates the file when it is absent — it never touches an existing one.

A hand-installed `/Applications/Zed.app` that Homebrew cannot adopt is kept as it is (Zed
reports `present-unmanaged`, not blocked); config and default apps are still applied to it.
