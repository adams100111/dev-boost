# Changelog

Notable changes to dev-boost. Binaries ship as GitHub Releases (`v*` tags) —
see [releases](https://github.com/adams100111/dev-boost/releases). Format loosely follows
[Keep a Changelog](https://keepachangelog.com/). Releases **≤ v0.1.77** predate this file; see
git history and the GitHub release notes.

## [1.2.0] — 2026-09-20

dev-boost no longer ships **any** of its author's personal repos as defaults. Anyone can
install it and get a working machine; anything private is theirs to configure. New:
**[docs/configuration.md](docs/configuration.md)**, every setting and environment variable
in one place.

### Added
- **[docs/configuration.md](docs/configuration.md)** — every `config.toml` key and every
  `DEVBOOST_*` variable in one place, with precedence (env beats file) and a note that
  unknown keys are ignored, so a typo silently falls back to the default.

### Changed
- **Plugin marketplaces no longer ship a private repo.** `claude-plugins` and
  `codex-plugins` registered `adams100111/clickup-flow`, which is **private**, so every
  other install tried to register a marketplace it cannot read — and then reached into
  `pass` for a `clickup/api-token` that was never theirs. The shipped list is now entirely
  public, and personal or private marketplaces go in the user config:

  ```toml
  # ~/.config/devboost/config.toml
  extra_marketplaces = { clickup-flow-marketplace = "adams100111/clickup-flow" }
  extra_plugins = ["clickup-flow@clickup-flow-marketplace"]
  ```

  Yours win a name clash with a shipped one, so a fork can replace an upstream
  marketplace. The `CLICKUP_API_TOKEN` lookup now runs only when that plugin is actually
  enabled. `qa-e2e-pilot` and `wave-pilot` stay in the defaults: they share an owner but
  are public, and the rule is "reachable by everyone", not "not this person's".

### Changed
- **dev-boost no longer defaults to its author's private repos.** `pass_repo` defaulted to
  `adams100111/password-store` and the Pi harness to the **private**
  `adams100111/agent-harness`, so anyone else installing dev-boost tried to clone repos
  they cannot read, and got a failed clone instead of an explanation.
  - `pass_repo` now resolves: `DEVBOOST_PASS_REPO` → `pass_repo` in
    `~/.config/devboost/config.toml` → **the `origin` of an existing store clone** → else
    `blocked`, naming both ways to set it. A machine that already has the store needs no
    configuration at all.
  - `pi-harness` requires `DEVBOOST_HARNESS_REPO`; unset is reported `blocked` with the
    fix, and a full git URL (`git@…`, `https://…`) is now used as given rather than being
    forced under `github.com/`.

### Added
- **`devboost pass adopt`** — for a `~/.password-store` that exists but is not a git
  clone, which previously just said "move it aside and re-run". It moves the directory to
  `<store>.pre-devboost` (never deletes), clones your repo in its place, and reports which
  entries were only in the old copy, which are new from the repo, and how many match.
  Comparison is by entry name only: nothing is decrypted, and GPG ciphertext differs every
  time even for identical plaintext, so contents cannot be compared without the passphrase.

### Fixed
- **`ssh-setup` trusts GitHub's host keys** — a fresh machine has no `github.com` entry in
  `~/.ssh/known_hosts`, so the first `git clone git@github.com:…` fails with *"Host key
  verification failed"*, which reads like a credentials problem and is not one. Seen on a
  real Mac: two keys loaded in the agent, `gh` authenticated, every SSH clone refused.
  dev-boost now seeds the keys **GitHub publishes at `api.github.com/meta`**, fetched over
  TLS so they are authenticated by GitHub's certificate — unlike `ssh-keyscan github.com`,
  which asks the very server it is trying to authenticate. A `github.com` entry you already
  have (pinned or hashed) is never touched, and with no network the install carries on and
  the next run retries. `verify` deliberately does not check the entry: it would make a
  machine that cannot reach `api.github.com` report a broken install for something that
  is hygiene, and `install` is idempotent, so a re-run repairs a machine that predates it.

## [1.1.2] — 2026-09-20

### Fixed
- **`timemachine-exclusions` runs after the container runtime** — `tmutil addexclusion`
  only accepts paths that exist, and the largest ones the sweep targets are Colima's VM
  disks, which the `docker` module creates later in the same run. A fresh Mac therefore
  finished with `~/.colima` and `~/.config/colima` still backed up by Time Machine, and
  `devboost verify` reporting `timemachine-exclusions: missing` immediately after a
  successful install. It now declares `after = (Docker,)` — ordering only, so `docker` is
  never pulled into a plan that did not ask for it.

## [1.1.1] — 2026-09-20

### Changed
- **`curl … | bash` picks the profile for the OS it is running on** — with no profile
  named it now runs plain `devboost install` and lets the engine choose, which is what
  `devboost install` on the same machine already did (`macos` on a Mac, `omarchy` on
  Omarchy, `full` otherwise). `get.sh` had hardcoded `terminal` since the original
  bootstrap, written before macOS support existed, so a Mac had to be told `macos`
  explicitly to get the profile the engine would have chosen anyway. Naming profiles
  still works and still wins. **On other Linux the no-argument default therefore moves
  from `terminal` to `full`** — name `terminal` explicitly to keep the smaller set.

### Fixed
- **mise no longer runs into GitHub's rate limit** — unauthenticated, GitHub allows 60 API
  requests per hour **per IP**, and a `base` install resolves seven GitHub-backed tools
  (marksman, taplo, k9s, helm, kubectl, opentofu, tofu-ls). Anything else on the same IP
  shares that budget — a second machine, CI, an office NAT — and past the limit GitHub
  answers 403, so the tools fail to install. A clean-VM rehearsal hit exactly this and
  reported only `error devops-lsp: verify failed after install`, with the 403, the reset
  time and the remedy all swallowed. `devboost install mise` now sets mise's
  `github.credential_command` to `gh auth token`, lifting the limit to 5000/hour. `gh` is
  already in the `cli` profile and authenticated per user; mise runs the command on demand,
  so no token is written to disk or exported into the environment, and a credential command
  you set yourself is left alone. Where `gh` is missing or logged out the command simply
  fails and mise falls back to unauthenticated requests, exactly as before.
  See docs/architecture.md "GitHub rate limits".

## [1.1.0] — 2026-09-20

### Changed
- **`stats` sets up its own menu bar, and starts on install** — a `curl | bash` Mac used
  to get Stats installed but never launched (an app with no TCC grant skipped its `open`
  on an unattended run), so nothing appeared in the menu bar until you opened it by hand
  and clicked through its setup. Stats now opts into `launch_unattended`, and dev-boost
  seeds its readouts first: **disk, RAM, CPU and GPU, and nothing else** (Stats ships GPU
  off and Network + Battery on). Only *absent* keys are written, so a readout you toggle
  in Stats' own settings is never undone by a later run, and seeding happens before the
  app starts, because Stats caches its whole defaults domain at startup and writes it back
  on exit. See docs/macos.md "Desktop apps".

## [1.0.0] — 2026-09-20

First release with **macOS support**. One catalog now drives both Linux (Omarchy/Arch,
Fedora, Ubuntu) and Apple Silicon macOS, and `curl … | bash` sets up a fresh Mac end to
end. The 1.0 line marks that the install surface is committed to, not that the module
catalog is closed.

### Security
- **browser-mcp is opt-in everywhere** — port 8931 runs code as you for any tailnet peer
  that can reach it (`browser_run_code_unsafe`, no auth), so no profile installs it any more,
  not even `remote`. Turn it on with `devboost install browser-mcp`, and restrict tcp:8931
  with a Tailscale ACL (docs/remote-dev.md). On Linux the dotfiles still ship the systemd
  `--user` unit but no longer enable it (the `default.target.wants/` link is gone); only the
  `browser-mcp` module enables it. Machines set up earlier keep their old link until you run
  `systemctl --user disable --now browser-mcp.service`. `devboost install browser-mcp`
  prints the ACL requirement.
- **browser-mcp security** — the Playwright MCP server is pinned to `@playwright/mcp@0.0.82`
  everywhere (the `browser-mcp` launcher, the macOS LaunchAgent, `pw-mcp`, and the Claude
  Code wiring in the `playwright` module); nothing starts `@latest`. The server's
  `browser_run_code_unsafe` tool is RCE-equivalent and 0.0.82 has no flag to disable it, so
  the docs now explain the port-8931 exposure and give a Tailscale ACL. `pw-mcp` refuses to
  bind `0.0.0.0` when there is no tailnet IP and accepts its MagicDNS name as a host.

### Added
- **macOS delivery (M6)** — `curl … | bash` now works on a fresh Mac: `scripts/get.sh`
  gained a Darwin path (Homebrew + CLT bootstrap, macOS-version gate, root refusal, HTTPS-
  only fetch) that installs the frozen `devboost-darwin-arm64` binary — no clone, no
  Ventoy archive. It downloads and **verifies the binary before installing Homebrew or the
  CLT**, so a missing asset or a checksum failure leaves the Mac untouched; a release with no
  Mac binary is reported as `no devboost-darwin-arm64 in release <tag> yet — macOS support
  starts with v1.0.0`, and a download that fails for another reason (timeout, TLS, DNS) as a
  network error with curl's own message, not as a missing asset. It refuses an Intel Mac, a Rosetta-translated shell ("open a native
  (arm64) terminal" — Homebrew's installer aborts under Rosetta) and root, all before any
  network call; refuses the `usb` profile
  on macOS before any network call or filesystem change (it's Linux-only); fails **closed**
  — refuses, rather than continuing — when the macOS version can't be read at all; warns
  loudly, naming the host, whenever `DEVBOOST_RELEASE_BASE` overrides the official release
  (both the binary and the checksums that vouch for it would then come from that same
  un-official place); pins every fetch with `--proto '=https,file' --proto-redir
  '=https'` so a redirect can never downgrade to plaintext; and cleans up its temp
  download dir on every exit path — a normal return, a `set -e` abort, and `INT`/`HUP`/
  `TERM`. `scripts/build-bundle.sh` and `scripts/release.sh` build/publish it (ad-hoc
  `codesign --verify --strict`, one-line `checksums-darwin-arm64.txt`). `release.yml` is
  the one canonical release path and now publishes through a **draft**: upload every asset
  and `checksums.txt`, download and verify them, and only then publish and mark latest.
  `release.sh` does the same, but is emergency-only: it refuses while `release.yml` is
  enabled (its published draft would create the tag and start the workflow, which would
  upload over it) unless `DEVBOOST_RELEASE_EMERGENCY=1`, and even then publishes only a tag
  that is already on origin. `devboost self-update` resolves its release asset by
  `(os, arch)`, **refuses to downgrade** the running binary, refuses to run outside the
  frozen binary (it would otherwise overwrite the Python interpreter), and reports an
  unwritable install dir or a garbled `checksums.txt` as `self-update failed: …` instead of
  a traceback. CI gained a `macos-15` / `xcode-27` (preview, non-blocking) matrix
  and a `binary-compat` job proving the macos-15-built binary also runs on macos-26; the
  release workflow publishes all three binaries plus one shared `checksums.txt`, after
  checking every asset against the per-arch checksums its build runner wrote. The
  deprecated `ubuntu-22.04` runner is gone: the Linux binaries build on `ubuntu-24.04` inside
  an `ubuntu:22.04` container, keeping the **glibc 2.35 floor**, which a new
  `scripts/check-glibc-floor.sh` step enforces over libpython and every extension module
  inside the onefile (not just its bootloader stub).
  `scripts/vm-test-macos.sh` rehearses the whole install in a throwaway tart VM
  (create/snapshot/revert/list/destroy/run/shell, `--local` for an unpublished build),
  running `smoke-assert.sh` in a fresh `zsh -lc` login shell after the install;
  `.github/workflows/vm-smoke.yml` gained an advisory `linux-smoke` job (Fedora/Arch
  containers + the Ubuntu host) alongside the existing Kickstart smoke. Root-owned files a
  root-run profile leaves behind under the demoting executor are now reclaimed: after a
  root-run `devboost accounts bootstrap`, a TOCTOU-safe walk (`os.fwalk` plus
  `dir_fd`-relative `stat`/`chown`, immune to a directory being swapped for a symlink
  mid-pass) hands every root-owned path under the managed user's HOME back to them; a HOME
  that is itself a symlink is refused outright (nothing under it is touched), and because
  `chown` follows a hardlink to its inode, a multiply-linked regular file is only reclaimed
  when `fs.protected_hardlinks` is on (the default on every distro dev-boost targets). With
  it off, each candidate is opened `O_NOFOLLOW|O_NONBLOCK`, re-checked on the fd and
  `fchown`-ed through that same fd, so a hardlink planted mid-pass is caught; multiply-linked
  files (and symlinks) are then left root-owned and the skip is logged. `bash-config` is no longer
  silently skipped on an unrecognized Linux distro (only macOS drops it now,
  `provided-by-macos`), and — because it now runs there instead of being dropped from the
  plan — its `verify` fails loudly on an unrecognised distro whose own packaging already
  owns `~/.bashrc` rather than dev-boost's dotfiles, instead of the module simply never
  running.
- **macOS desktop (M5)** — `macos-defaults` with snapshot + `devboost revert
  macos-defaults [key…]`, open-files limit, firewall, Time Machine exclusions,
  Raycast/AeroSpace (+config)/AltTab/Thaw/MonitorControl/Keka/Stats/Quick Look, code files
  open in Zed, Voxtype dictation on every OS (+ opt-in `voxtype-arabic`), opt-in `ios`
  (Xcode 27), `macos-extras` and `android-emulator`, desktop checks in `doctor`.
  BetterDisplay is not shipped (paid for business use). See
  [docs/macos-primer.md](docs/macos-primer.md).
- **Docker runtimes on macOS (M4)** — Colima (default), OrbStack and Docker Desktop behind
  a common `DockerRuntime` protocol, plus `devboost docker use <runtime>` to switch between
  them (snapshots ddev first, stops the others, re-verifies what depends on Docker). ddev,
  Aspire and data-services now install on the Mac too. `aspire-gc`, `restic-backup`,
  `restic-b2`, `obsidian-sync` and `browser-mcp` (new on macOS — a Playwright MCP server for
  remote Claude Code sessions, opt-in) run as launchd agents, the macOS twin of the
  Linux systemd `--user` timers. `devboost doctor` reports the selected Docker runtime's
  health, with Apple M4/M5 and Rosetta-specific hints. `KNOWN_GAPS` is empty — M4 closes
  the macOS catalog. See [docs/docker-runtimes.md](docs/docker-runtimes.md).
- **macOS catalog (M3)** — `devboost install` on a Mac installs the workstation:
  `xcode-clt`, `homebrew`, `rosetta` modules; casks for the GUI apps; .NET 10 in `~/.dotnet`;
  Android SDK via the cmdline-tools cask; ddev (tap) + mkcert; the Tailscale app as a
  fleet client; herdr pinned per OS and arch; the agent CLIs, LSPs and dev stacks.
  Modules M4 owns (Docker, scheduled jobs) report `blocked` with a workaround.
- **Zed on macOS (Z2)** — `zed` cask, the same seeded config, and Zed as the default app
  for code/text files (`utiluti`; macOS 26.4+ asks once per file type).
- `glow` and `herdr-plugins` are in the `cli` profile on every OS.
- `~/.config/devboost/local.sh`: your own `EDITOR`/`VISUAL` and other overrides, read last.
- `devboost doctor`: Rosetta status (Intel-only apps from macOS 28).
- **macOS shell, terminal & dotfiles (M2)** — `devboost install terminal` runs on an
  Apple Silicon Mac: every terminal-set module installs through Homebrew
  (`BrewFormula`/`BrewCask` strategies, `per_os.macos`), zsh config (`shell.zsh`,
  `~/.zshrc`/`~/.zprofile` with `.local` hooks, `zsh-config`, `zsh-plugins`), brew `bash`,
  foreign rc files kept as `*.pre-devboost`, `docs/macos.md`.
- **`pass` multi-device (P1, Linux)** — per-device GPG keys (fingerprint-only access and
  trust; email ids in `.gpg-id` never grant access), enroll → approve → sync onto a shared
  private GitHub `pass` store, scoped enrollment for servers, revoke + a rotation checklist
  `devboost doctor` tracks until it's clear, a post-commit push hook plus a 15-min systemd
  user timer that also pushes a store whose first push never landed. New `devboost pass`
  CLI (`status`/`devices`/`enroll`/`approve`/`revoke`/`sync`). `pass` / `pass-store` move
  to `base` (the `security-cli` profile is now an alias for both). See
  [docs/pass.md](docs/pass.md).
- **`pass` multi-device on macOS (P2)** — pinentry-mac + the same gpg-agent cache TTLs as
  Linux, a launchd sync agent (`dev.devboost.pass-sync`, every 15 min), Notification
  Center notices (`osascript`), `devboost pass` now works on macOS too, and `pass` /
  `pass-store` join the `macos` profile. **Recipient audit** — `devboost pass audit`,
  `devboost doctor`'s `pass-recipients` check, and a sync notice flag any entry not
  encrypted to exactly its `.gpg-id` keys (reads packets only, never decrypts). See
  [docs/pass.md](docs/pass.md).
- **macOS engine core (M1)** — macOS family + arm64 normalization, Homebrew manager
  (formulae/casks/taps), launchd primitive, NeedsUser/PresentUnmanaged, macOS
  privacy-permission tracking (`devboost permissions`), macOS invocation rules (no root,
  one sudo prompt, keep-awake), gh-first/keychain credentials (`devboost secrets
  import-key`), macOS doctor, catalog contract test. Constitution v3.1.0.
- **Zed is the default editor on Linux** — `zed` module (official installer; Fedora, Ubuntu,
  Arch/Omarchy), seeded VS Code-style settings with Claude/Codex/Pi agents and dev-boost-pinned
  language servers, `config.jsonc_merge_deep` (comment-tolerant deep merge), and
  `VISUAL="zed --wait"` in local GUI sessions. See [docs/zed.md](docs/zed.md).

### Changed
- PyYAML is a new runtime dependency (Colima's `colima.yaml`).
- herdr 0.7.5 → 0.9.1 on every OS; catalog pins are keyed `<os>-<arch>`.
- `devboost install --update` on macOS upgrades Homebrew casks too, except apps that
  update themselves.
- `chezmoi-repo` runs `chezmoi init --apply --force`; a missing repo URL is `blocked`,
  not a failure.
- The Claude notify hook also shows a native macOS notification.
- **Ghostty is the default terminal on every OS**; WezTerm moved to the opt-in
  `optional-terminals` profile (deprecated) and its Ctrl+V smart paste was retired (herdr
  owns image paste).
- Shell config split into POSIX `env.sh` + shared `aliases.sh`; `shell.bash` uses
  `fzf --bash` when available (fallback for fzf < 0.48).
- One RAM/disk probe (`~/.local/bin/devboost-resources`, Linux + macOS) feeds tmux,
  starship, WezTerm and the Claude status line.
- Linux `PATH` order changed: `~/.local/bin` now comes first.
- `vscode` moved from `editors` to the opt-in `optional-editors` profile.

### Fixed
- The executor finds mise's shims where mise puts them (`MISE_DATA_DIR`, `XDG_DATA_HOME`).
- `.chezmoiignore` no longer fails on macOS (`.chezmoi.osRelease` is Linux-only).
- Ghostty config: `theme = Catppuccin Mocha` (Title Case) and `toggle_split_zoom` — the old
  values were rejected by Ghostty 1.3.
- `git credential fill` also neutralises `core.askPass`.
- Ubuntu/Debian: Ghostty installs as a classic snap (`snap install ghostty --classic`);
  Flathub has no Ghostty. A failed `flatpak install` now fails its module instead of
  passing silently.
- macOS: a dev-boost `~/.zshrc`/`~/.zprofile`/`~/.bash_profile` that another tool appended
  to is copied to `*.pre-devboost` before `chezmoi apply --force` (it used to lose those
  lines silently); a retried run makes no duplicate copy. `zsh-config` verify no longer
  crashes on a non-UTF-8 `~/.zshrc`.
- `zsh -i -c` without a terminal (an editor capturing the env) no longer prints
  `can't change option: zle`: the fzf and atuin key bindings load only on a tty.

### Removed
- `DEVBOOST_PASS_GPG_ID` — an empty store is now initialised by its first device
  ("genesis": generate the key, `pass init <fp>`, register, push) instead of a hand-made
  GPG id.

### Fixed
- systemd user units are daemon-reloaded after any rewrite (every devboost timer, not
  just `pass`'s), so a changed schedule takes effect without a re-login.
- `pass-store`'s verify now checks that the sync scheduler is actually loaded/enabled
  (systemd timer active, launchd agent loaded), not just that its unit/plist file exists.
- Unattended `pass` reads (`--pinentry-mode error`) never open a pinentry dialog nobody
  can answer; without a cached passphrase the secret is skipped, with a hint to run
  `pass show <entry> >/dev/null` once in a terminal to warm the cache.

### Docs
- Added [docs/pass.md](docs/pass.md) (the multi-device model, enroll/approve/sync, revoke
  + rotation, servers, disaster recovery); updated
  [docs/credentials.md](docs/credentials.md), [docs/recovery-runbook.md](docs/recovery-runbook.md),
  [docs/AGENTS.md](docs/AGENTS.md), [docs/architecture.md](docs/architecture.md) and
  [docs/adding-a-module.md](docs/adding-a-module.md) for the pass multi-device model and the
  `Module.after` ordering-only dependency.
- [docs/pass.md](docs/pass.md): macOS specifics (pinentry-mac, launchd sync agent,
  Notification Center), the recipient audit, and unattended-run behavior.

## [0.1.80] — 2026-09-09

### Added
- **Omarchy / Arch support** (#27) — a `pacman` package backend (official repos + AUR via
  `install_aur`), `ID_LIKE`-based Omarchy detection (`omarchy`/`cachyos`/`garuda` → `arch`), an
  `omarchy` profile, and the `omarchy-update-hook` module. Lands the previously-stranded
  `worktree-omarchy-support` work.
- **Orca module** (#28) — `orca-ide` installs [Orca](https://github.com/stablyai/orca) per-OS
  (Fedora `.rpm`, Ubuntu `.deb`, Omarchy/Arch AUR `stably-orca-bin`); `orca-serve` runs it headless
  via a systemd `--user` service (Xvfb, Tailscale-paired, linger). Opt-in `orca` / `orca-box`
  profiles. See [docs/agents.md](docs/agents.md).

### Fixed
- `test_omarchy` no longer depends on the host GPU marker (isolated `XDG_STATE_HOME`), so the suite
  is green on NVIDIA workstations as well as in CI.

### Docs
- Regenerated the README profiles/module tables for the claude/codex/pi + omarchy/orca modules (#26).
- Added this changelog and [docs/agents.md](docs/agents.md) (AI-agent module usage + env vars).

## [0.1.79] — 2026-09-08

### Added
- **`pi-harness` module** (#24) — bootstraps the operator's Pi coding-agent harness (`harness-cli`)
  and delegates `~/.pi` configuration to it (no duplication of its manifest). Opt-in `pi` profile,
  also in `full`. Informational `pi-login` doctor check. See [docs/agents.md](docs/agents.md).

## [0.1.78] — 2026-09-07

### Added
- **Claude Code config module** (#19) — `claude-code` / `claude-plugins` / `claude-skills` /
  `claude-mcp`; reproduces marketplaces, enabled plugins, skills, and MCP servers across devices.
  `claude` profile.
- **Codex config module** (#22) — `codex-code` / `codex-config` / `codex-plugins` / `codex-mcp` /
  `codex-skills` for the OpenAI Codex CLI. `codex` profile. Both `claude` and `codex` added to `full`.
- **`pass`-config validation** (#21) — `PassStore` hard-fails on missing config (clear `ConfigError`);
  informational `pass-config` doctor check.

### Fixed
- Claude CLICKUP token now written to `~/.claude/settings.json` (the file Claude actually reads), not
  the never-read user-level `settings.local.json` (#20).

---

Releases **v0.1.77 and earlier** predate this changelog — see the
[GitHub releases](https://github.com/adams100111/dev-boost/releases) and git history.
