# dev-boost — herdr optional agent-multiplexer

**Status:** Design approved — ready for implementation planning
**Date:** 2026-07-22
**Author:** dits.sa.co@gmail.com

---

## 1. Goal

Add **herdr** — a terminal-native, agent-aware multiplexer (single Rust binary) — to
dev-boost as an **opt-in, off-the-production-path** application, together with a curated,
pinned set of its plugins and a chezmoi-managed config.

herdr adopts tmux's pane/tab/session-persistence model and extends it with **AI-agent
state awareness**: processes running in herdr panes are identified as agents and their
state (working / idle / blocked / done) is surfaced in a sidebar. It runs *alongside*
tmux, not instead of it — tmux stays the core, dotfiles-managed multiplexer; herdr is an
additive convenience for the multi-agent workflow (the primary agent here is Claude Code).

### Non-goals
- Not on the "production ready, builds out of the box" default set. herdr is a young
  project and ships only under an opt-in profile.
- Not a replacement for tmux or its `tpm`/resurrect/continuum stack — those are unchanged.
- No open door to the herdr plugin marketplace. Plugins are **unsandboxed** (they run as
  the user with full permissions); only a hand-vetted, pinned set is shipped.

---

## 2. Placement & profile

- New opt-in profile **`optional-agents`** (category `optional-agents`), following the
  `optional-editors` / `security-cli` pattern in `engine/src/devboost/modules/optional.py`.
  It is not included in any default/production profile.
- New typed module file: `engine/src/devboost/modules/herdr.py` (one file, `@register`
  classes, `mypy --strict` clean).
- Profile name `optional-agents` deliberately differs from every module name (the
  profile/module name-collision rule).

---

## 3. Binary install — `Herdr` module

herdr has **no Fedora package** (upstream ships a GitHub release binary, Homebrew, and a
`curl … | sh` installer). We install the **pinned release binary** into `~/.local/bin`.

### Pin (in `catalog.toml`)
A new tooling table alongside `[ventoy]`:

```toml
[herdr]
version = "0.7.5"                       # bump deliberately; verified from live release
[herdr.x86_64]
url = "https://github.com/ogulcancelik/herdr/releases/download/v0.7.5/herdr-linux-x86_64"
sha256 = "<from the release asset digest>"
[herdr.aarch64]
url = "https://github.com/ogulcancelik/herdr/releases/download/v0.7.5/herdr-linux-aarch64"
sha256 = "<from the release asset digest>"
```

Release assets follow `herdr-linux-{x86_64,aarch64}` (no extension). Upstream publishes no
`SHA256SUMS` manifest, but the GitHub release API exposes each asset's `digest`
(`sha256:…`); the pinned value is taken from there (or by hashing the pinned download) at
pin time. `catalog.toml`'s existing load-time validation is extended to check the
`[herdr]` entry (64-hex sha256).

### Behavior
- `install()`: resolve arch via `uname -m` → select the matching `[herdr.<arch>]` entry →
  download to a temp path → **verify SHA256; on mismatch, raise and stop** → `install -Dm755`
  to `~/.local/bin/herdr`.
- `verify()`: `ctx.ex.which("herdr")`.
- **OS-dispatch seam:** Fedora is the reference implementation; a Homebrew branch is stubbed
  (`raise UnsupportedOS` / no-op) for later OSes, consistent with the engine's per-OS strategy.

### Why pinned + SHA256 (not `releases/latest` or `curl | sh`)
1. **Reproducibility** is a core principle — identical fresh machines must converge to the
   same state; `latest` diverges over time and offers no last-good rollback.
2. **Integrity on an unattended USB** — a checksum makes a tampered/corrupted download fail
   loudly instead of executing an arbitrary binary as the user; `curl | sh` has neither a
   pin nor a checksum.
3. **Matches trusted precedent** — every OS ISO and ventoy itself are already pinned with a
   SHA256 in `catalog.toml`; a single static Rust binary is the easiest possible case to pin.

---

## 4. Plugins — `HerdrPlugins` module

`requires = (Herdr,)`. Ships the **curated, pinned** set (the full recommended list), each
as an `(id, owner/repo/subdir, git-ref)` tuple. Exact repo slugs and refs are resolved at
implementation from the `herdr-plugin` GitHub topic and each is skimmed before pinning.

Intended set:

| id | purpose |
|----|---------|
| session-restore | persist agent sessions + layouts across reboot (dev-boost ethos) |
| remote / notify  | approve / get pinged (phone, Telegram) when an agent blocks |
| sessionizer      | fuzzy-open a project into a predefined TOML layout |
| herdr-plus       | Projects + Quick Actions |
| switchr          | TUI session picker showing the pane tree |
| git-diff viewer  | read-only tree + diff + rendered-markdown pane |
| herdr-mcp        | expose herdr as an MCP server (Claude Code can drive it) |
| herdr-dotfiles   | prefix-free navigation config, chezmoi-friendly |

### Behavior
- `install()`: `herdr plugin install <owner/repo/subdir>` per entry (pinned ref), **each
  step non-blocking** — a failing plugin build/network fetch logs `log.warn` and continues,
  never bricking the run (mirrors `obsidian-sync`'s tolerant style).
- `verify()`: all pinned ids present in `herdr plugin list`.
- **Secret-dependent plugins** (remote/notify → Telegram token, etc.) read from the `age`
  secrets bundle or env and **skip with a warning if the secret is absent** — never prompt,
  never fail the run.

---

## 5. Config — chezmoi-managed

herdr runs zero-config but reads an optional config file (invalid values revert to safe
defaults with a startup warning). We ship one as a chezmoi **source** file under
`dotfiles/` (exact path/filename confirmed against herdr docs at implementation), so it is
version-controlled and restored like the wezterm/tmux/starship configs — **not** written
imperatively by a module.

Config content: tmux-style keybindings (`prefix = "ctrl+b"` so muscle memory carries over),
the `tokyo-night` palette (to sit alongside the existing terminal theme), and sidebar /
notification preferences.

---

## 6. Docs

- `docs/roadmap.md` — record herdr shipped as an optional app.
- `README.md` — add herdr to the optional-apps section with a one-line profile note.
- This design doc committed under `docs/superpowers/specs/`.

---

## 7. Testing (merge gates: `mypy --strict`, ruff, pytest)

All module tests use the **injected `Executor`** — hermetic, no network:

- `catalog.toml` load-time validation covers the `[herdr]` sha256 entries.
- `Herdr`: assert the arch resolution → download → **sha256 verify** → `install -Dm755`
  command sequence, and that a checksum mismatch raises (no chmod).
- `HerdrPlugins`: assert the per-plugin `herdr plugin install` calls, idempotent `verify()`
  against `herdr plugin list`, and **non-blocking-on-failure** behavior (one plugin failing
  does not abort the rest).

---

## 8. Open items resolved during design

- Install method → **pinned release + SHA256** (§3).
- "All plugins" → **curated pinned set**, not the marketplace (§4).
- Profile name → **`optional-agents`**; config delivery → **chezmoi/`dotfiles/`** (§2, §5).
