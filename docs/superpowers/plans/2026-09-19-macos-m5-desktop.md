# macOS M5 — Desktop, iOS & Dictation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On an Apple Silicon Mac (macOS 27 primary, 26 supported), `devboost install macos` also configures the desktop: typed `defaults` with a snapshot and a tested `devboost revert macos-defaults`, a raised open-files limit, the application firewall, Time Machine exclusions, the desktop apps (Raycast, AeroSpace with its config, AltTab, Thaw, MonitorControl, Keka, Stats, the Quick Look extensions), code files opening in Zed, and Voxtype dictation. It also adds three opt-in sets: `ios` (Xcode and the iOS runtime), `macos-extras`, and the cross-OS `android-emulator` and `voxtype-arabic` modules. A new-to-Mac primer ships with it. Outcome (spec §11): **full desktop + iOS**.

**Architecture:** Almost everything is data on existing seams: casks through M2's `BrewCask` strategy, which a new `CaskApp` base wraps; privacy grants through M1's `Module.tcc`; LaunchDaemons and LaunchAgents through M1's `launchd` primitive; dotfiles through chezmoi. There are three small engine additions:
1. `Module.supported_on(os_info)`. It gates a module by macOS version (spec §0: "gated by a `min_version`/`max_version` field … rather than removed"). `plan._supported` consults it, so a gated module is reported `unsupported-os` instead of failing.
2. A typed `defaults` primitive, `macdefaults`. The `macos-defaults` module and `devboost revert` share its snapshot logic.
3. Two catalog pins: `[xcode]` and `[voxtype]`.

Voxtype is cross-OS. It uses a Homebrew cask plus Voxtype's own `setup app-bundle` on macOS, the upstream RPM/DEB on Fedora/Ubuntu, and the AUR on Arch. Omarchy provides it. Its config is one chezmoi template for every OS.

**Tech Stack:** Python ≥ 3.12, Typer, Pydantic, pytest, mypy `--strict`, ruff (line length 100), `uv`; chezmoi 2.72 templates; POSIX `sh`; TOML (AeroSpace, Voxtype); `plistlib` (via M1's `launchd`).

**Spec:** `docs/superpowers/specs/2026-09-18-macos-support-design.md`. This plan covers:
- §0: the macOS 27 app checks, as explicit verification steps
- §2: the `macos-defaults` table, the new macOS-only desktop modules, `voxtype`, `voxtype-arabic`, `android-emulator`, `xcode`, `ios-tooling`, the `macos-desktop` / `ios` / `macos-extras` profiles, `base += voxtype`, and privacy permissions (TCC)
- §3: the AeroSpace config
- §8: the desktop checks in `doctor`
- §9: the `macos-defaults` tests, and the contract test covering `macos-extras`, `ios`, `voxtype-arabic` and `android-emulator`
- §10: `docs/macos-primer.md`
- the M5 row of §11

Read the spec before starting. Format exemplars: `docs/superpowers/plans/2026-09-19-macos-m1-engine-core.md` and `docs/superpowers/plans/2026-09-19-macos-m2-shell-dotfiles.md`.

## Global Constraints

- Apple Silicon only; family id `"macos"`; Homebrew prefix `/opt/homebrew` (fixed, so absolute `/opt/homebrew/bin/<tool>` paths are allowed in dotfiles that GUI apps execute, e.g. AeroSpace `exec-and-forget`). Supported: macOS 27 Golden Gate (primary, this Mac: `ProductVersion 27.0`, build `26A428`), 26 Tahoe; 15 best-effort.
- Brew is **never** run with `sudo`. Every brew call goes through `devboost.exec.primitives.pkg` or M2's `BrewFormula` / `BrewCask`. Casks install with `--adopt`. A hand-installed app that brew cannot adopt is reported `present-unmanaged` (M1).
- **Every default must be free for commercial use** (employer and client work). Licences were checked on 2026-09-19 and are recorded in the Decisions table and in `docs/macos-primer.md`. An app that is paid for business use is not shipped (see D3).
- **Tests are hermetic.** `tests/conftest.py` autouse `_tmp_home` (HOME and XDG dirs point into `tmp_path`) and `_linux_host` apply everywhere. Tests inject `OsInfo`, use `FakeExecutor` or a subclass, and **never** write real `defaults`, never load a launchd job, never touch TCC or the firewall, and never run `tmutil`/`duti`/`xcodes`. A test that needs an external binary (`chezmoi`, `aerospace`) **skips** when it is absent.
- `macos-defaults` has a **tested revert**: snapshot, restore of prior values, `defaults delete` for keys that were absent, and a partial revert by key.
- Merge gates (constitution): `uv run ruff check`, `uv run mypy` (strict), `uv run pytest`, all clean.
- Commit messages: Conventional Commits, **no `Co-Authored-By` trailer and no Claude/Anthropic/AI attribution**. Every commit step below follows this.
- All commands run from `engine/` unless a step says otherwise. Paths in `git add` are written from `engine/` (`../profiles.toml`, `../dotfiles/...`, `../docs/...`).
- `KNOWN_GAPS` (`engine/tests/core/test_macos_contract.py`): no M5 module may add a gap. Each M5-owned module is resolvable the moment it lands.
- **Parallel M4** (Docker runtimes + launchd timers) runs alongside M5. M5 keeps shared-file edits to single lines or blocks:
  - the files named in the task brief: `profiles.toml` lines, the `CHANGELOG.md` entry, and `KNOWN_GAPS`
  - the `tests/conftest.py` `profiles_file` fixture (one line per new profile)
  - `docs/macos.md` (one link line)
  - `cli/doctor.py` (one call line)
  - the generated README profiles table (re-run the generator after merging)
  M5 creates no file M4 is expected to create. Whichever PR merges second rebases and resolves these line-level conflicts by keeping both sides.

## Depends on M3 (assumptions)

The M3 + Z2 plan (branch `plan/m3-z2-catalog`) had not been pushed when this plan was written, so M5 states what it consumes from M3. **Task 0 checks each assumption.** When the real name differs, use the real name everywhere this plan uses the assumed one (imports and `requires`). Do not rename M3's code.

| # | M5 assumes M3/Z2 provides | Used by | If absent (Task 0 finds nothing) |
|---|---|---|---|
| A1 | A registered `homebrew` module class `Homebrew` (families `("macos",)`), imported below as `from devboost.modules.homebrew import Homebrew` | every cask / brew module (`requires`) | Stop. M3 has not landed, and M5 cannot run before it (spec §11 order). |
| A2 | Registered formula modules `duti` (class `Duti`) and `xcodes` (class `Xcodes`), imported below as `from devboost.modules.cli_tools import Duti, Xcodes` | `default-apps`, `xcode` | Add them to `modules/macos_system.py` / `modules/ios.py` as `PackageModule`s with `families = ("macos",)`, `cmd`/`fedora_pkg` = the name. The snippet is in Task 8 Step 3 / Task 12 Step 3. |
| A3 | Z2's duti primitive `devboost.exec.primitives.duti` with `set_default(ctx: Ctx, bundle_id: str, ext: str) -> None` (runs `duti -s <bundle_id> .<ext> all`, raising `InstallError` on failure) and `handler(ctx: Ctx, ext: str) -> str \| None` (the bundle id from the 3rd line of `duti -x <ext>`) | `default-apps` | Create it exactly as Task 8 Step 3 shows. If Z2 exists under other names, adapt the two call sites in `DefaultApps`. |
| A4 | The `zed` module (`devboost.modules.editors.Zed`) has a macOS strategy (cask `zed`, bundle id `dev.zed.Zed`) | `default-apps` requires it | Stop: Z2 has not landed. |
| A5 | `android-sdk` has a macOS strategy: cask `android-commandlinetools`, `ANDROID_HOME=~/Library/Android/sdk` via `env.sh` | `android-emulator` | `android-emulator` still resolves its SDK root itself (Task 14), so only the acceptance run is affected. |
| A6 | The `macos` profile aggregate exists and lists `base`, and the other members named in spec §2 | Task 15 | Task 15 adds `"macos-desktop"` to it if absent. |
| A7 | No generic macOS version helper exists yet. The spec's Rosetta gating could have introduced one. | Task 1 | If M3 added one (e.g. `osinfo.macos_version` or a `Module` version field), **reuse it**: drop `core/macver.py` from Task 1, and keep only `supported_on` if M3 has no equivalent. |

M2 (executing now) is also treated as landed. M5 uses these parts of it:
- `devboost.modules._brew.BrewCask` / `BrewFormula`
- `Module.os_strategy()`
- `plan._supported` treating a module's own `install()` as the fallback
- `.chezmoiignore`, which already ignores `.config/aerospace` on Linux
- the `dotfiles` module's `chezmoi apply --force --source … --destination …`
- `shell.zsh`'s `ulimit -n 524288` with its fallback (M2 D16)

## Decisions

The user was not available. Each decision below is carried into the spec in Task 17.

| # | Decision | Why |
|---|---|---|
| D1 | **Version gating is `Module.supported_on(os_info) -> bool`** (classmethod, default `True`). `plan._supported` ANDs it in, so a gated module shows as `unsupported-os` in the plan and in `devboost list`. `CaskApp` implements it from `min_macos`. `doctor` lists gated modules. | Spec §0 wants a gate field "rather than removed", plus a doctor note. A plan-level skip is honest. A `NeedsUser`/`fail` would be wrong: the user can do nothing about it. |
| D2 | **Thaw**: stable cask `thaw` 2.0.1 (GPL-3.0; `depends_on macos >= 26`; README states support for 26 and 27). Declared `min_macos = (26, 0)`, so it is gated off on 15. Task 6 has an on-Mac check; if it misbehaves on 27, set `max_macos = (26, 99)` (see D1) and add a doctor note. No `thaw@beta`. | Spec §0: never ship a preview build. |
| D3 | **BetterDisplay is dropped.** Its terms require business users to buy a licence, even for the free features (github.com/waydabber/BetterDisplay/discussions/739). **MonitorControl** (MIT) covers DDC brightness and volume. There is no free replacement for HiDPI scaling, so the primer names BetterDisplay as a manual, paid option. `macos-desktop` no longer lists `betterdisplay`. | The commercial-use rule. |
| D4 | **Keka is kept.** It is free from keka.io and Homebrew. Its terms (keka.io/termsofuse) contain only a warranty disclaimer, with no use restriction and no paid tier for business. The App Store purchase is an optional tip. | The rule rejects apps that are *paid* for commercial use. Keka is not. |
| D5 | Cask tokens were verified 2026-09-19 with local `brew info --json=v2` (Homebrew 7.0.4). Tokens: `stats`, `raycast`, `nikitabobko/tap/aerospace` (tap only, 0.21.3-Beta), `alt-tab`, `thaw`, `monitorcontrol`, `keka`, `qlmarkdown`, `syntax-highlight`, `maccy`, `ollama-app`, `lm-studio`, `pearcleaner`, `keycastr`, `linearmouse`, `android-studio`, `expo-orbit`, `herd`, `peteonrails/voxtype/voxtype` (tap only). None is deprecated or disabled. `verify` lists a tapped cask by its **short** token (`brew list --cask --versions aerospace`). | Brew resolves tapped casks by short name once they are installed. The fully-qualified token is needed only to install, which auto-taps. |
| D6 | **`CaskApp`** (`modules/_cask.py`) is the base for a single-cask macOS app. It has `cask`, an optional `launch` (app name, opened once with `open -g -a` after install so macOS registers the login item or extension and the app can request its permissions), `min_macos`, `families = ("macos",)`, `gui = True`, `requires = (Homebrew,)`, and `portable = False`. `__init_subclass__` sets `per_os = OsMap(macos=CaskInstall(...))`, so the contract test sees a real `per_os.macos`. | One line of data per app. The contract test needs no special case. |
| D7 | **TCC grants** (M1 `TccService`: `Accessibility`, `ListenEvent` = Input Monitoring, `Microphone`, `ScreenCapture` = Screen Recording). The `app` field is the display name the user sees in System Settings. | From each app's docs (sources below). Screen Recording for AltTab and Thaw follows spec §2. It is optional for Thaw, but it is needed for AltTab's thumbnails. |
| | AeroSpace, Raycast, MonitorControl, LinearMouse, Maccy | Accessibility |
| | AltTab, Thaw | Accessibility + Screen Recording |
| | KeyCastr | Input Monitoring + Accessibility |
| | Voxtype | Microphone + Input Monitoring + Accessibility. Upstream `MACOS_ARCHITECTURE.md` says typing uses CGEvent, which needs Accessibility; the spec listed only the first two. |
| D8 | **`macos-defaults` table** = spec §2, plus one row: `com.apple.driver.AppleBluetoothMultitouch.trackpad Clicking = true`. Without it, tap-to-click does not reach a Magic Trackpad. `-currentHost … com.apple.mouse.tapBehavior` is **not** written, because the primitive has no `-currentHost` form (YAGNI; it affects the login window only). Keys are addressed as `<domain>:<key>` (e.g. `com.apple.dock:tilesize`). A bare key is accepted when it is unique in the table; `Clicking` is not. | Every key was absent on this Mac when checked 2026-09-19. The three tap-to-click keys already read `1`. |
| D9 | **Restart only on change**, once per process: `Dock` (dock keys), `Finder` (finder keys + `AppleShowAllExtensions`), `SystemUIServer` (screencapture keys). Keyboard, autocorrect, trackpad and `DSDontWrite*` keys need a logout, so the module logs that once and does not force it. | Spec §2 "restart … only on change". A logout under an install run would kill the user's session. |
| D10 | **Snapshot semantics.** The file is `$XDG_STATE_HOME/devboost/macos-defaults.prev.json` (default `~/.local/state/…`, as spec §2 says). It holds `{"version": 1, "prior": {"<domain>:<key>": {"kind": …, "value": …} \| null}}`, where `null` means the key was absent. A key is recorded **once**, before its first write, and never overwritten, so the file always holds the pre-dev-boost value. `revert` restores the recorded value (`null` → `defaults delete`). A prior value of a type the primitive cannot write back (array/dict/data/date) is recorded as `{"kind": "other"}`; revert warns and leaves it alone. Reverted keys are removed from the snapshot, and the file is deleted when empty. A later `devboost install` re-applies (and re-snapshots) them, as documented. | Revert must restore the machine's own state, not the value from the previous run. |
| D11 | **`macos-limits`**: this Mac reads `kern.maxfilesperproc = 92160` and `kern.maxfiles = 184320`, and `launchctl limit maxfiles` prints `256 unlimited`. `ulimit -n` is clamped to `kern.maxfilesperproc`, so the LaunchDaemon (`dev.devboost.maxfiles`, RunAtLoad) runs `sysctl -w kern.maxfiles=524288 kern.maxfilesperproc=524288` **and** `launchctl limit maxfiles 524288 524288`. The `launchctl limit` part is best-effort (`\|\| true`): Apple has returned EPERM for it under SIP since 13.5 (developer.apple.com/forums/thread/735798). `verify` checks the two sysctls plus the daemon being loaded. `install` also runs the script once, so no reboot is needed. | The spec's `launchctl limit` alone would not lift the clamp M2 D16 falls back to. |
| D12 | **`timemachine-exclusions`** uses one POSIX `sh` sweep, run as a LaunchAgent (`dev.devboost.tm-exclusions`, `RunAtLoad` + `StartInterval` 21600 s) and once at install. It covers two things: (1) the spec's fixed paths, where each existing path is excluded with sticky `tmutil addexclusion` (no sudo); (2) `node_modules` / `vendor` directories under `~/repos` (`find -maxdepth 6 … -prune`). Missing paths are skipped: `tmutil isexcluded` prints `[UNKNOWN]` for them, and a sticky exclusion needs the item to exist. The agent excludes paths such as `~/.colima` once they appear. `verify` = every *existing* fixed path reads `[Excluded]`, and the agent is loaded. | Spec §2. A login-agent sweep is the spec's own mechanism, and it also covers late-created paths. |
| D13 | **`default-apps`**: `duti` 1.5.4 (homebrew-core, public domain) has no bottle for 26/27 (brew builds it from source with the CLT) and is unmaintained upstream. M5 keeps it (spec + Z2). Task 8 has an on-Mac check. If `duti -s` does not take effect on 27, switch Z2's primitive to `infat` (homebrew-core) — the module does not change. The extension list excludes `html`/`svg` (browser) and anything a GUI app owns better. Types macOS reserves (e.g. `.ts` as MPEG-TS) are verified on the Mac and dropped if `duti` cannot set them. | The primitive seam isolates the tool choice. |
| D14 | **Voxtype macOS install** = cask `peteonrails/voxtype/voxtype` (MIT). The tap pins **0.7.5**; upstream stable is **v1.0.1** (2026-08-31). The daemon runs through upstream's **`voxtype setup app-bundle`** (it creates `/Applications/Voxtype.app`, bundle id `io.voxtype.daemon`, plus a Login Item), **not** a `launchd.user_agent`. Upstream's own help says launchd services do not receive Microphone permission. `verify` = cask listed + model file present + `Voxtype.app` present. Task 10 checks on the Mac that the installed version has `setup app-bundle` and `record start --model`. Both exist in 0.7.5's source tree (`src/setup/app_bundle.rs`). | This deviates from spec §2's "launchd.user_agent for the daemon", because the upstream author says that path cannot get Microphone. |
| D15 | **Voxtype model**: Whisper `small.en` (466 MB) **on every OS**, with `engine = "whisper"`. Parakeet is not used: upstream's `secondary_model` exists only under `[whisper]`, and with `engine = "parakeet"` the daemon ignores model overrides (`src/daemon.rs`). Parakeet on macOS is ONNX on the CPU (no Neural Engine code in `onnx_ep.rs`). | Spec §2: "Parakeet v3 … if the secondary-model mechanism works with it, otherwise Whisper small.en". It does not work. |
| D16 | **Voxtype config** = one chezmoi template, `dotfiles/dot_config/voxtype/config.toml.tmpl`, applied on **every OS, Omarchy included**. The hotkey block is a **clearly marked placeholder**. The author's Omarchy config was not available, so defaults are used: `RIGHTALT` on macOS (upstream's macOS key set: `RIGHTALT`/`FN`/`F13…`), `SCROLLLOCK` (upstream default) on Linux, and `mode = "push_to_talk"`. The user pastes their Omarchy values later and runs `devboost install dotfiles`. If the Omarchy box shows that `omarchy-refresh-config` rewrites `~/.config/voxtype` (check its migrations), add `.config/voxtype` to the Omarchy block of `.chezmoiignore`, as for the other Omarchy-owned configs. | Spec: "shared through chezmoi (one file for every OS)". The module works with defaults until the user fills the placeholder. |
| D17 | **Arabic opt-in**: the `voxtype-arabic` module touches the marker `~/.config/devboost/voxtype-arabic`, downloads `large-v3-turbo` (1.6 GB), re-applies the two templated files with chezmoi, and restarts the daemon. The config template reads the marker (`stat`) and sets `secondary_model = "large-v3-turbo"`, `language = ["en", "ar"]`, and `cold_model_timeout_secs = 60`. **`on_demand_loading` stays `false`**. It is a global `[whisper]` flag that would also unload the *primary* model after every dictation (docs/CONFIGURATION.md). Non-primary models already load only on request and are evicted after `cold_model_timeout_secs`, which gives the spec's "no idle RAM" for Arabic. Linux gets `model_modifier = "LEFTSHIFT"` (evdev). **On macOS `model_modifier` is ignored** (the macOS listener reads only `key`), so the spec's fallback is used: the AeroSpace config binds **Ctrl+Alt+D** → `exec-and-forget /opt/homebrew/bin/voxtype record toggle --model large-v3-turbo`, only when the marker exists. It is a toggle, not push-to-talk, because AeroSpace sees key-down only. | Spec §2 intent (zero idle RAM, a separate trigger for Arabic), corrected against upstream docs. |
| D18 | **Voxtype on Linux** follows upstream `docs/INSTALL.md`: the pinned `voxtype-1.0.1-1.x86_64.rpm` (Fedora) / `voxtype_1.0.1-1_amd64.deb` (Ubuntu), SHA-256-verified, then `dnf`/`apt-get install` of the local file. Runtime deps are `wtype wl-clipboard libnotify pipewire-alsa` (Ubuntu: `libnotify-bin`). The steps are `usermod -aG input $USER` (a re-login is needed, and is logged), `voxtype setup --download --model small.en --quiet`, then `voxtype setup systemd`. On aarch64 Linux (no RPM/DEB), the pinned raw `voxtype-1.0.1-linux-aarch64-cpu` binary goes to `~/.local/bin/voxtype`. Vanilla Arch uses AUR `voxtype-bin`, which is x86_64-only (aarch64 Arch → same raw binary). The pins live in `catalog.toml` `[voxtype]`; hashes are GitHub's release-asset digests (2026-09-19). | Spec: "Fedora/Ubuntu per upstream docs/INSTALL.md". Omarchy keeps `provided_by` (it installs `voxtype-bin` from its own Install › AI › Dictation menu). |
| D19 | **`xcode` / `ios-tooling`**: the pins go in `catalog.toml` `[xcode]`: `version = "27.0"` (Xcode 27, build 27A266a, GA 2026-09-14), `ios_runtime = "27.0"`, `min_macos = "26.6"` (Xcode 27's requirement). The modules are gated by `supported_on`.<br>**Auth:** `XCODES_USERNAME` + `XCODES_PASSWORD` in the env, or an interactive terminal (xcodes may prompt for the Apple ID or 2FA, so it runs `interactive=True`). With neither, the module raises `NeedsUser`. xcodes is **never** run with captured output, because it would block forever on an invisible prompt.<br>**Verify:** `xcodes installed` shows `<pin> … (Selected)`, and `xcodebuild -license check` exits 0. | Spec §2 + the §1 `NeedsUser` rule. |
| D20 | **`android-emulator`** (cross-OS, opt-in, `gui = True`): `sdkmanager emulator "system-images;android-35;google_apis;<abi>"` (`arm64-v8a` on aarch64, `x86_64` otherwise; API 35 matches `android-sdk`'s `platforms;android-35`), then `avdmanager create avd -n devboost-pixel -d pixel_8`. Gated off on Linux aarch64: Google ships no Linux arm64 emulator host. | Spec §2. |
| D21 | `voxtype-arabic` and `android-emulator` are **module names**, not profiles, and belong to no default profile (`devboost install voxtype-arabic`). New profiles: `macos-desktop`, `ios`, `macos-extras`. `base += voxtype` (every OS, spec §2). `macos += macos-desktop` if M3 did not add it. | Spec §2 Profiles and §9. |
| D22 | `doctor` gets the desktop half of spec §8 in a new `cli/doctor_desktop.py`. It is wired into `run_checks` with one line. Firewall-off **fails** the check (spec lists it without "warn"). FileVault, SIP, Time Machine destination, iCloud Desktop & Documents (`com.apple.finder FXICloudDriveDesktop == 1`), the battery charge limit (26.4+, manual — no CLI exists), Raycast/Maccy hotkey hints and version-gated modules are informational (`ok=True`). The brew/CLT/Rosetta/Docker/`present-unmanaged`/pass checks belong to M1/M3/M4. | Keeps the `doctor.py` overlap with M3/M4 to one line. |
| D23 | Quick Look: `qlmarkdown` + `syntax-highlight`, both GPL-3.0. They are modern app extensions, **not** legacy `.qlgenerator`s, so they work on 26/27. Each app is opened once with `open -g -a` to register its extension. The user may have to enable it in System Settings → General → Login Items & Extensions → Quick Look (primer + doctor-free hint). `qlmanage -r` runs after install (harmless). | sbarex READMEs. |
| D24 | The desktop apps with a background role (`stats`, `raycast`, `aerospace`, `alt-tab`, `thaw`, `monitorcontrol`, `maccy`, `linearmouse`) are launched once after install. Launch-at-login uses each app's own setting (AeroSpace: `start-at-login = true` in the chezmoi config). dev-boost never writes Login Items through `osascript`/System Events, which would trigger an Automation permission prompt. The primer lists where each app's toggle is. | Launching an app is what makes it appear in the permission lists at all. |
| D25 | Upstream Voxtype on macOS defaults to `FN` (Globe). dev-boost uses `RIGHTALT` instead. macOS binds Globe to the emoji picker / dictation. Right Option, alone, types nothing (M2 D10 keeps right Option for accents, used only in chords). | Least surprise. The placeholder lets the author override it. |

**Sources (checked 2026-09-19):** these back the Decisions table, the verification steps and the primer's licence table. The executor re-checks the per-Mac facts in the tasks. Local facts come from command output on this Mac: `brew info --json=v2 --cask <token>` for every cask token, `defaults read-type`, `launchctl limit maxfiles`, `sysctl kern.maxfiles kern.maxfilesperproc`, `socketfilterfw --getglobalstate`, `tmutil isexcluded`, `fdesetup status`, `csrutil status` and `sw_vers`.

**Casks and licences**
- Raycast free plan allows work use: raycast.com/pricing, raycast.com/terms-of-service
- AeroSpace (MIT, tap cask): github.com/nikitabobko/homebrew-tap/blob/main/Casks/aerospace.rb
- AeroSpace default config and `reload-config --dry-run`: github.com/nikitabobko/AeroSpace/tree/main/docs
- AeroSpace open Tahoe/newer-macOS issues: github.com/nikitabobko/AeroSpace/discussions/1968, /1969, /2144
- Thaw: github.com/thaw-app/Thaw
- BetterDisplay's business-licence rule: github.com/waydabber/BetterDisplay/discussions/739 and its wiki "List of free and pro features"
- Keka: keka.io/en and keka.io/termsofuse
- LM Studio, free for internal work use since 2025-07-08: lmstudio.ai/blog/free-for-work, lmstudio.ai/app-terms
- Laravel Herd EULA (no business restriction on the free tier): herd.laravel.com/eula
- Pearcleaner (Apache-2.0 + Commons Clause, bans only selling): github.com/alienator88/Pearcleaner/blob/main/LICENSE.md
- Quick Look extensions: github.com/sbarex/QLMarkdown, github.com/sbarex/SourceCodeSyntaxHighlight

**Voxtype**
- Code and docs: github.com/peteonrails/voxtype — `docs/INSTALL.md`, `docs/INSTALL_MACOS.md`, `docs/CONFIGURATION.md`, `docs/MACOS_ARCHITECTURE.md`, `src/setup/app_bundle.rs`, `src/setup/launchd.rs`, `src/hotkey_macos.rs`, `src/daemon.rs`, `src/cli/record.rs` at v1.0.1
- Tap: github.com/peteonrails/homebrew-voxtype/blob/main/Casks/voxtype.rb
- Release asset digests: `gh api repos/peteonrails/voxtype/releases/tags/v1.0.1`
- How Omarchy installs it: omarchy.org/manual/text-extraction-dictation, github.com/omacom/omarchy/issues/6823

**macOS system settings**
- `defaults` behaviour: `man defaults`
- `launchctl limit` EPERM under SIP: developer.apple.com/forums/thread/735798
- Firewall is `socketfilterfw`-only since macOS 15: support.apple.com/en-us/121011
- `man tmutil`
- Screenshot destinations: macos-defaults.com/screenshots/location.html, macworld.com/article/673251
- Battery charge limit (GUI/Shortcuts only): support.apple.com/en-us/102338

**Formulae and Xcode**
- duti 1.5.4 (no Tahoe/27 bottle): formulae.brew.sh/formula/duti, github.com/moretension/duti
- infat, the fallback for duti: formulae.brew.sh/formula/infat
- xcodes 2.1.0: formulae.brew.sh/formula/xcodes, github.com/XcodesOrg/xcodes
- Xcode 27: developer.apple.com/documentation/xcode-release-notes/xcode-27-release-notes

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `engine/src/devboost/core/macver.py` (create) | `macos_version(os_info) -> tuple[int, int] \| None` | 1 |
| `engine/src/devboost/model.py`, `engine/src/devboost/core/plan.py` (modify) | `Module.supported_on`; `_supported` consults it | 1 |
| `engine/src/devboost/exec/primitives/macdefaults.py` (create) | typed `defaults` read/write/delete (`Value`, `Kind`) | 2 |
| `engine/tests/modules/macos_fakes.py` (create) | `PrefsExecutor`, a stateful fake of `defaults`. Other tests reuse `tests.passstore.fakes.RuleExecutor` (token rules → `Result`). | 2 |
| `engine/src/devboost/modules/macos_defaults.py` (create) | `Setting` table, snapshot, `apply` / `verify_all` / `revert` / `resolve_ids`, `MacosDefaults` module | 3 |
| `engine/src/devboost/cli/revert.py` (create); `cli/app.py` (one `add_typer` line) | `devboost revert macos-defaults [KEY…]` | 4 |
| `engine/src/devboost/modules/macos_system.py` (create) | `macos-limits`, `macos-firewall`, `timemachine-exclusions`, `default-apps` | 5, 8 |
| `engine/src/devboost/modules/_cask.py` (create) | `CaskInstall` strategy, `CaskApp` base | 6 |
| `engine/src/devboost/modules/macos_apps.py` (create) | desktop casks, `quicklook`, `macos-extras` casks | 6, 13 |
| `dotfiles/dot_config/aerospace/aerospace.toml.tmpl` (create) | AeroSpace config (Ctrl+Alt layer; Arabic dictation binding) | 7 |
| `engine/src/devboost/exec/primitives/duti.py` (create **only if Z2 did not**) | `set_default` / `handler` | 8 |
| `catalog.toml`, `engine/src/devboost/media/catalog.py` (modify) | `[xcode]`, `[voxtype]` pins + `xcode_pin()` / `voxtype_pin()` | 9 |
| `dotfiles/dot_config/voxtype/config.toml.tmpl` (create) | shared Voxtype config with the hotkey placeholder | 10 |
| `engine/src/devboost/modules/voxtype.py` (create) | `voxtype` (macOS / RPM / DEB / AUR / raw binary), `voxtype-arabic` | 10, 11 |
| `engine/src/devboost/modules/ios.py` (create) | `xcode`, `ios-tooling` | 12 |
| `engine/src/devboost/modules/android_emulator.py` (create) | `android-emulator` | 14 |
| `profiles.toml`, `engine/tests/conftest.py` (modify, line-level) | `macos-desktop`, `ios`, `macos-extras`, `base += voxtype`, `macos += macos-desktop` | 3, 6, 12, 13, 15 |
| `engine/tests/core/test_macos_contract.py` (modify) | contract covers the opt-in sets; docstring | 15 |
| `engine/src/devboost/cli/doctor_desktop.py` (create); `cli/doctor.py` (one line) | spec §8 desktop checks | 16 |
| `docs/macos-primer.md` (create); `docs/macos.md`, `docs/adding-a-module.md`, `README.md`, `CHANGELOG.md`, spec (modify) | docs | 17 |

Tests live next to their area: `engine/tests/core/`, `engine/tests/primitives/`, `engine/tests/modules/`, `engine/tests/cli/`, `engine/tests/dotfiles/`.

---

### Task 0: Branch, baseline, dependency and shared-file re-check

**Files:** none (environment only)

- [ ] **Step 1: Branch from the current main** (repo root)

```bash
git fetch origin
git checkout -b feat/macos-m5-desktop origin/main
```

- [ ] **Step 2: Baseline gate** (from `engine/`)

```bash
cd engine && uv sync
uv run ruff check && uv run mypy && uv run pytest -q 2>&1 | tail -3
```
Expected: all green. If anything is red on a clean `main`, stop and report it. M5 must start green.

- [ ] **Step 3: Check the M2/M3/Z2 assumptions** (the "Depends on M3" table)

```bash
git log --oneline -30 origin/main | grep -iE 'm2|m3|z2|m4|macos|zed' 
ls src/devboost/modules/_brew.py                                   # M2
grep -rn 'def os_strategy' src/devboost/model.py                   # M2
grep -rln 'name = "homebrew"' src/devboost/modules/                # A1
grep -rn 'name = "duti"\|name = "xcodes"' src/devboost/modules/    # A2
ls src/devboost/exec/primitives/duti.py && grep -n '^def ' src/devboost/exec/primitives/duti.py  # A3
grep -n 'macos\|cask' src/devboost/modules/editors.py | head       # A4
grep -n 'android-commandlinetools\|Library/Android' -r src/devboost/modules/ | head  # A5
grep -nE '^macos ' ../profiles.toml                                # A6
grep -rn 'def macos_version\|supported_on\|min_version\|max_version\|min_macos' src/devboost/ | head  # A7
grep -n '\.config/aerospace' ../dotfiles/.chezmoiignore            # M2
```

Write down the actual class names and import paths. For A1/A4, missing means stop. For A2/A3/A7, apply the "If absent" column. Everywhere below, `from devboost.modules.homebrew import Homebrew` and `from devboost.modules.cli_tools import Duti, Xcodes` stand for **the paths you found**.

- [ ] **Step 4: Re-check the files shared with M4**

```bash
git log --oneline origin/main -- ../profiles.toml ../CHANGELOG.md tests/core/test_macos_contract.py tests/conftest.py src/devboost/cli/doctor.py ../docs/macos.md | head
grep -c '^    "' tests/core/test_macos_contract.py
git ls-remote --heads origin | grep -i m4
```

Note whether M4 has merged, and how many `KNOWN_GAPS` remain. Task 15 uses both numbers. After merging M4, the remaining gaps should be empty. If M4 has not merged, only M4-owned names should remain: `docker`, `docker-build-gc`, `aspire-gc`, `restic-backup`, `restic-b2`, `obsidian-sync`, `browser-view`, `data-services`, `ddev`/`ddev-remote` if M3 left them to M4.

- [ ] **Step 5: Read-only snapshot of this Mac's desktop state** (it doubles as the acceptance baseline for Task 18)

```bash
sw_vers; brew --version | head -1
for k in KeyRepeat InitialKeyRepeat ApplePressAndHoldEnabled AppleShowAllExtensions; do defaults read-type NSGlobalDomain $k 2>&1; done
defaults read com.apple.dock 2>/dev/null | grep -E 'autohide|tilesize|show-recents'
launchctl limit maxfiles; sysctl kern.maxfiles kern.maxfilesperproc
/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate
tmutil destinationinfo; fdesetup status; csrutil status
ls /Applications | grep -iE 'raycast|aerospace|alt-tab|thaw|monitor|keka|stats|qlmarkdown|syntax|voxtype|xcode' || true
```
Save the output to `/tmp/m5-baseline.txt` (outside the repo). Nothing is written.

No commit.

---

### Task 1: Engine — macOS version helper and `Module.supported_on`

**Files:**
- Create: `engine/src/devboost/core/macver.py`
- Modify: `engine/src/devboost/model.py` (`Module`), `engine/src/devboost/core/plan.py` (`_supported`)
- Test: `engine/tests/core/test_macver.py` (create), `engine/tests/core/test_plan_supported_on.py` (create)

**Interfaces:**
- Produces:
  - `macos_version(os_info: OsInfo) -> tuple[int, int] | None`. Returns `(major, minor)` for `family == "macos"` with a parseable `version_id`, else `None`.
  - `Module.supported_on(cls, os_info: OsInfo) -> bool` (classmethod, default `True`).
  - `plan._supported(cls, os_info)` also returns `False` when `cls.supported_on(os_info)` is `False` (skip reason `unsupported-os`).

- [ ] **Step 1: Write the failing tests**

`tests/core/test_macver.py`:

```python
from __future__ import annotations

import pytest

from devboost.core.macver import macos_version
from devboost.core.osinfo import OsInfo


@pytest.mark.parametrize(
    ("version_id", "expected"),
    [("27.0", (27, 0)), ("26.4.1", (26, 4)), ("15", (15, 0)), ("", None), ("x.y", None)],
)
def test_macos_version_parses_major_minor(
    version_id: str, expected: tuple[int, int] | None
) -> None:
    assert macos_version(OsInfo("macos", "macos", "aarch64", version_id=version_id)) == expected


def test_macos_version_is_none_off_macos() -> None:
    assert macos_version(OsInfo("fedora", "fedora", "x86_64", version_id="44")) is None
```

`tests/core/test_plan_supported_on.py`:

```python
"""A module may decline an OS version: the plan reports it as unsupported-os."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from devboost.core.macver import macos_version
from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.model import Ctx, Module

MAC26 = OsInfo("macos", "macos", "aarch64", version_id="26.3")
MAC27 = OsInfo("macos", "macos", "aarch64", version_id="27.0")


class _Needs27(Module):
    name: ClassVar[str] = "needs-27-probe"

    @classmethod
    def supported_on(cls, os_info: OsInfo) -> bool:
        v = macos_version(os_info)
        return v is not None and v >= (27, 0)

    def verify(self, ctx: Ctx) -> bool:
        return False

    def install(self, ctx: Ctx) -> None:
        return None


MODULES: dict[str, type[Module]] = {"needs-27-probe": _Needs27}


def test_version_gate_skips_older_macos(tmp_path: Path) -> None:
    plan = build_plan(["needs-27-probe"], MODULES, MAC26, gpu_marker=tmp_path / "none")
    assert plan[0].skip_reason == "unsupported-os"


def test_version_gate_admits_newer_macos(tmp_path: Path) -> None:
    plan = build_plan(["needs-27-probe"], MODULES, MAC27, gpu_marker=tmp_path / "none")
    assert plan[0].skip_reason is None


def test_default_supported_on_is_true() -> None:
    assert Module.supported_on(MAC26) is True
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/core/test_macver.py tests/core/test_plan_supported_on.py -v`
Expected: FAIL (`ModuleNotFoundError: devboost.core.macver`; `supported_on` missing).

- [ ] **Step 3: Implement**

`src/devboost/core/macver.py`:

```python
"""macOS version as data (spec §0): modules and table rows gate on (major, minor)."""

from __future__ import annotations

from devboost.core.osinfo import OsInfo


def macos_version(os_info: OsInfo) -> tuple[int, int] | None:
    """(major, minor) of a macOS host; None off macOS or when the version is unknown."""
    if os_info.family != "macos" or not os_info.version_id:
        return None
    parts = os_info.version_id.split(".")
    try:
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
    except ValueError:
        return None
    return (major, minor)
```

In `src/devboost/model.py`, add to `class Module` directly after `per_os`:

```python
    @classmethod
    def supported_on(cls, os_info: OsInfo) -> bool:
        """False when this module must not run on *os_info* (e.g. too old a macOS).

        The plan reports a False here as ``unsupported-os`` — a clean, explained skip —
        rather than letting install fail on a version the app does not support (spec §0).
        """
        return True
```

(`OsInfo` is already imported in `model.py`.)

In `src/devboost/core/plan.py`, make `_supported` start with the gate. Keep M2's body after it unchanged:

```python
def _supported(cls: type[Module], os_info: OsInfo) -> bool:
    """Unsupported when the module declines this OS version, or when its per_os map has
    no entry for this OS and it has no install of its own (M2)."""
    if not cls.supported_on(os_info):
        return False
    # … M2's existing body continues here unchanged …
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/core -q && uv run mypy && uv run ruff check`
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/core/macver.py src/devboost/model.py src/devboost/core/plan.py tests/core/test_macver.py tests/core/test_plan_supported_on.py
git commit -m "feat(engine): Module.supported_on version gate and macos_version helper"
```

---
### Task 2: `macdefaults` primitive + stateful fake

**Files:**
- Create: `engine/src/devboost/exec/primitives/macdefaults.py`, `engine/tests/modules/macos_fakes.py`
- Test: `engine/tests/primitives/test_macdefaults.py` (create)

**Interfaces:**
- Produces:
  - `Kind = Literal["bool", "int", "float", "string", "other"]`; `Scalar = bool | int | float | str`.
  - `@dataclass(frozen=True) class Value: kind: Kind; value: Scalar`. For `other`, `value` holds the type name (`"array"`, …).
  - `read(ctx, domain: str, key: str) -> Value | None`. Returns `None` when the key is absent. Runs `defaults read-type` first, then `defaults read`.
  - `write(ctx, domain, key, v: Value) -> None`. Runs `defaults write <domain> <key> -bool true|false / -int N / -float X / -string S`. Raises `InstallError("macos-defaults", …)` on a non-zero exit, and `ValueError` for `kind == "other"`.
  - `delete(ctx, domain, key) -> None`. Runs `defaults delete`; an absent key is not an error.
  - Test fake `tests.modules.macos_fakes.PrefsExecutor(FakeExecutor)`. Its field `prefs: dict[tuple[str, str], tuple[str, str]]` maps `(domain, key)` to `(type name as read-type prints it, raw text as read prints it)`, and the fake implements `read-type`/`read`/`write`/`delete` over it. Every other argv behaves like `FakeExecutor`.

- [ ] **Step 1: Write the fake and the failing tests**

`tests/modules/macos_fakes.py`:

```python
"""Test doubles for macOS system tools (no real `defaults` is ever run in tests)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from devboost.exec.executor import FakeExecutor, Result

_WRITE_TYPES = {"-bool": "boolean", "-int": "integer", "-float": "float", "-string": "string"}


@dataclass
class PrefsExecutor(FakeExecutor):
    """A stateful fake of `defaults`.

    ``prefs[(domain, key)] = (type, raw)`` where *type* is what ``defaults read-type``
    names (``boolean``/``integer``/``float``/``string``/``array``…) and *raw* is what
    ``defaults read`` prints (bools as ``1``/``0``). Writes and deletes update it.
    """

    prefs: dict[tuple[str, str], tuple[str, str]] = field(default_factory=dict)

    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        interactive: bool = False,
    ) -> Result:
        res = super().run(argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive)
        if len(argv) < 4 or argv[0] != "defaults":
            return res
        verb, domain, key = argv[1], argv[2], argv[3]
        cur = self.prefs.get((domain, key))
        if verb == "read-type":
            if cur is None:
                return Result(1, "", f"Could not find key '{key}' in domain '{domain}'\n")
            return Result(0, f"Type is {cur[0]}\n")
        if verb == "read":
            return Result(0, cur[1] + "\n") if cur is not None else Result(1)
        if verb == "write":
            flag, raw = argv[4], argv[5]
            if flag == "-bool":
                raw = "1" if raw == "true" else "0"
            self.prefs[(domain, key)] = (_WRITE_TYPES[flag], raw)
            return Result(0)
        if verb == "delete":
            return Result(0) if self.prefs.pop((domain, key), None) is not None else Result(1)
        return res
```

`tests/primitives/test_macdefaults.py`:

```python
from __future__ import annotations

import pytest

from devboost.core.errors import InstallError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import macdefaults
from devboost.exec.primitives.macdefaults import Value
from devboost.model import Ctx
from tests.modules.macos_fakes import PrefsExecutor

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
DOCK = "com.apple.dock"


def _ctx(ex: FakeExecutor) -> Ctx:
    return Ctx(os=MAC, ex=ex)


def test_read_absent_is_none() -> None:
    assert macdefaults.read(_ctx(PrefsExecutor()), DOCK, "tilesize") is None


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        (("boolean", "1"), Value("bool", True)),
        (("boolean", "0"), Value("bool", False)),
        (("integer", "48"), Value("int", 48)),
        (("float", "0.5"), Value("float", 0.5)),
        (("string", "Nlsv"), Value("string", "Nlsv")),
        (("array", "(\n)"), Value("other", "array")),
    ],
)
def test_read_is_typed(stored: tuple[str, str], expected: Value) -> None:
    ex = PrefsExecutor(prefs={(DOCK, "k"): stored})
    assert macdefaults.read(_ctx(ex), DOCK, "k") == expected


@pytest.mark.parametrize(
    ("value", "flag"),
    [
        (Value("bool", True), ["-bool", "true"]),
        (Value("bool", False), ["-bool", "false"]),
        (Value("int", 48), ["-int", "48"]),
        (Value("float", 0.5), ["-float", "0.5"]),
        (Value("string", "clipboard"), ["-string", "clipboard"]),
    ],
)
def test_write_argv_is_typed(value: Value, flag: list[str]) -> None:
    ex = FakeExecutor()
    macdefaults.write(_ctx(ex), DOCK, "k", value)
    assert ex.calls == [["defaults", "write", DOCK, "k", *flag]]


def test_write_round_trips_through_read() -> None:
    ex = PrefsExecutor()
    macdefaults.write(_ctx(ex), DOCK, "autohide", Value("bool", True))
    assert macdefaults.read(_ctx(ex), DOCK, "autohide") == Value("bool", True)


def test_write_failure_raises() -> None:
    ex = FakeExecutor(scripts={"defaults": Result(1)})
    with pytest.raises(InstallError):
        macdefaults.write(_ctx(ex), DOCK, "k", Value("int", 1))


def test_write_other_kind_is_refused() -> None:
    with pytest.raises(ValueError, match="other"):
        macdefaults.write(_ctx(FakeExecutor()), DOCK, "k", Value("other", "array"))


def test_delete_absent_is_not_an_error() -> None:
    ex = PrefsExecutor()
    macdefaults.delete(_ctx(ex), DOCK, "tilesize")
    assert ex.calls == [["defaults", "delete", DOCK, "tilesize"]]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/primitives/test_macdefaults.py -v`
Expected: FAIL (`ImportError: cannot import name 'macdefaults'`).

- [ ] **Step 3: Implement** `src/devboost/exec/primitives/macdefaults.py`

```python
"""Typed access to macOS user defaults via the `defaults` CLI (never by editing plists).

`defaults` owns cfprefsd's cache, so writing through it needs no `killall cfprefsd`.
Values are typed on the way out (`-bool`/`-int`/`-float`/`-string`) and on the way in
(`read-type` first), so a revert can restore exactly what was there.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from devboost.core.errors import InstallError
from devboost.model import Ctx

Kind = Literal["bool", "int", "float", "string", "other"]
Scalar = bool | int | float | str

#: `defaults read-type` prints "Type is <name>"; anything not listed is kept as "other".
_READ_TYPES: dict[str, Kind] = {
    "boolean": "bool",
    "integer": "int",
    "float": "float",
    "string": "string",
}


@dataclass(frozen=True)
class Value:
    """A typed defaults value. For kind "other" *value* is the type name (not writable)."""

    kind: Kind
    value: Scalar


def _parse(kind: Kind, raw: str) -> Scalar:
    if kind == "string":
        return raw.rstrip("\n")
    text = raw.strip()
    if kind == "bool":
        return text in ("1", "true", "YES")
    if kind == "int":
        return int(text)
    if kind == "float":
        return float(text)
    return text


def read(ctx: Ctx, domain: str, key: str) -> Value | None:
    """The key's typed value, or None when it is absent."""
    typed = ctx.ex.run(["defaults", "read-type", domain, key])
    if not typed.ok:
        return None
    type_name = typed.stdout.strip().removeprefix("Type is ").strip()
    kind = _READ_TYPES.get(type_name)
    if kind is None:
        return Value("other", type_name)
    res = ctx.ex.run(["defaults", "read", domain, key])
    if not res.ok:
        return None
    return Value(kind, _parse(kind, res.stdout))


def _flag(v: Value) -> list[str]:
    if v.kind == "bool":
        return ["-bool", "true" if v.value else "false"]
    if v.kind == "int":
        return ["-int", str(int(v.value))]
    if v.kind == "float":
        return ["-float", repr(float(v.value))]
    if v.kind == "string":
        return ["-string", str(v.value)]
    raise ValueError(f"cannot write a defaults value of kind 'other' ({v.value})")


def write(ctx: Ctx, domain: str, key: str, v: Value) -> None:
    argv = ["defaults", "write", domain, key, *_flag(v)]
    res = ctx.ex.run(argv)
    if not res.ok:
        raise InstallError("macos-defaults", " ".join(argv), res.code)


def delete(ctx: Ctx, domain: str, key: str) -> None:
    """Remove the key, bringing back the system default. Absent is fine (exit 1 ignored)."""
    ctx.ex.run(["defaults", "delete", domain, key])
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/primitives/test_macdefaults.py -v && uv run mypy && uv run ruff check`
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/exec/primitives/macdefaults.py tests/modules/macos_fakes.py tests/primitives/test_macdefaults.py
git commit -m "feat(macos): typed defaults primitive"
```

---

### Task 3: `macos-defaults` module — table, snapshot, apply, revert

**Files:**
- Create: `engine/src/devboost/modules/macos_defaults.py`
- Modify: `profiles.toml` (new `macos-desktop` line), `engine/tests/conftest.py` (`profiles_file`: one line)
- Test: `engine/tests/modules/test_macos_defaults.py` (create)

**Interfaces:**
- Consumes: `macdefaults.read/write/delete`, `Value` (Task 2); `macos_version` (Task 1).
- Produces (module `devboost.modules.macos_defaults`):
  - `@dataclass(frozen=True) class Setting`: fields `domain`, `key`, `value: Value`, `restart: str | None = None`, `min_macos: tuple[int, int] | None = None`, `max_macos: tuple[int, int] | None = None`. Property `id -> "<domain>:<key>"`. Method `applies(os_info: OsInfo) -> bool`.
  - `SETTINGS: tuple[Setting, ...]` (the D8 table, 20 rows).
  - `snapshot_path() -> Path`, `load_snapshot() -> dict[str, Value | None]`, `save_snapshot(prior) -> None`.
  - `apply(ctx) -> list[str]`: the ids it changed. `verify_all(ctx) -> bool`.
  - `resolve_ids(names: Sequence[str]) -> list[str]`: raises `ValueError` for an unknown or ambiguous name.
  - `revert(ctx, ids: Sequence[str] | None = None) -> list[str]`: the ids it restored.
  - Registered module `macos-defaults` (`MacosDefaults`, `families = ("macos",)`, `portable = True`, `profiles = ("macos-desktop",)`).

- [ ] **Step 1: Write the failing tests** — `tests/modules/test_macos_defaults.py`

```python
from __future__ import annotations

import json

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.primitives.macdefaults import Value
from devboost.model import Ctx
from devboost.modules import macos_defaults as md
from tests.modules.macos_fakes import PrefsExecutor

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
DOCK = "com.apple.dock"


def _ctx(ex: PrefsExecutor) -> Ctx:
    return Ctx(os=MAC, ex=ex)


def _writes(ex: PrefsExecutor) -> list[list[str]]:
    return [c for c in ex.calls if c[:2] == ["defaults", "write"]]


def _kills(ex: PrefsExecutor) -> list[list[str]]:
    return [c for c in ex.calls if c[0] == "killall"]


def test_table_matches_the_spec_with_typed_values() -> None:
    by_id = {s.id: s.value for s in md.SETTINGS}
    assert by_id["NSGlobalDomain:KeyRepeat"] == Value("int", 2)
    assert by_id["NSGlobalDomain:InitialKeyRepeat"] == Value("int", 15)
    assert by_id["NSGlobalDomain:ApplePressAndHoldEnabled"] == Value("bool", False)
    assert by_id["com.apple.finder:FXPreferredViewStyle"] == Value("string", "Nlsv")
    assert by_id["com.apple.dock:tilesize"] == Value("int", 48)
    assert by_id["com.apple.screencapture:target"] == Value("string", "clipboard")
    assert by_id["com.apple.screencapture:type"] == Value("string", "png")
    assert by_id["com.apple.AppleMultitouchTrackpad:Clicking"] == Value("bool", True)
    bt = "com.apple.driver.AppleBluetoothMultitouch.trackpad:Clicking"
    assert by_id[bt] == Value("bool", True)
    assert len(by_id) == len(md.SETTINGS) == 20  # ids are unique


def test_apply_writes_typed_values_and_restarts_each_process_once() -> None:
    ex = PrefsExecutor()
    changed = md.apply(_ctx(ex))
    assert len(changed) == len(md.SETTINGS)
    assert ["defaults", "write", DOCK, "tilesize", "-int", "48"] in ex.calls
    assert ["defaults", "write", "NSGlobalDomain", "ApplePressAndHoldEnabled",
            "-bool", "false"] in ex.calls
    assert ["defaults", "write", "com.apple.screencapture", "target",
            "-string", "clipboard"] in ex.calls
    assert _kills(ex) == [["killall", "Dock"], ["killall", "Finder"],
                          ["killall", "SystemUIServer"]]


def test_nothing_changes_and_nothing_restarts_when_already_applied() -> None:
    ex = PrefsExecutor()
    md.apply(_ctx(ex))
    ex.calls.clear()
    assert md.apply(_ctx(ex)) == []
    assert _writes(ex) == []
    assert _kills(ex) == []


def test_only_changed_processes_restart() -> None:
    ex = PrefsExecutor()
    md.apply(_ctx(ex))
    ex.prefs[(DOCK, "tilesize")] = ("integer", "64")  # the user moved the slider
    ex.calls.clear()
    assert md.apply(_ctx(ex)) == ["com.apple.dock:tilesize"]
    assert _kills(ex) == [["killall", "Dock"]]


def test_snapshot_records_prior_values_and_absence() -> None:
    ex = PrefsExecutor(prefs={(DOCK, "tilesize"): ("integer", "64")})
    md.apply(_ctx(ex))
    raw = json.loads(md.snapshot_path().read_text(encoding="utf-8"))
    assert raw["version"] == 1
    assert raw["prior"]["com.apple.dock:tilesize"] == {"kind": "int", "value": 64}
    assert raw["prior"]["com.apple.dock:autohide"] is None


def test_snapshot_keeps_the_first_prior_across_runs() -> None:
    ex = PrefsExecutor(prefs={(DOCK, "tilesize"): ("integer", "64")})
    md.apply(_ctx(ex))
    ex.prefs[(DOCK, "tilesize")] = ("integer", "30")
    md.apply(_ctx(ex))
    assert md.load_snapshot()["com.apple.dock:tilesize"] == Value("int", 64)


def test_verify_is_true_only_when_every_key_matches() -> None:
    ex = PrefsExecutor()
    assert md.verify_all(_ctx(ex)) is False
    md.apply(_ctx(ex))
    assert md.verify_all(_ctx(ex)) is True
    ex.prefs[(DOCK, "autohide")] = ("boolean", "0")
    assert md.verify_all(_ctx(ex)) is False


def test_full_revert_restores_values_deletes_absent_keys_and_clears_snapshot() -> None:
    ex = PrefsExecutor(prefs={(DOCK, "tilesize"): ("integer", "64")})
    md.apply(_ctx(ex))
    ex.calls.clear()
    restored = md.revert(_ctx(ex))
    assert len(restored) == len(md.SETTINGS)
    assert ex.prefs == {(DOCK, "tilesize"): ("integer", "64")}  # everything else deleted
    assert ["defaults", "delete", DOCK, "autohide"] in ex.calls
    assert not md.snapshot_path().exists()
    assert ["killall", "Dock"] in ex.calls


def test_partial_revert_restores_only_the_named_keys() -> None:
    ex = PrefsExecutor(prefs={(DOCK, "tilesize"): ("integer", "64")})
    md.apply(_ctx(ex))
    assert md.revert(_ctx(ex), ["com.apple.dock:tilesize"]) == ["com.apple.dock:tilesize"]
    assert ex.prefs[(DOCK, "tilesize")] == ("integer", "64")
    assert ex.prefs[(DOCK, "autohide")] == ("boolean", "1")
    snap = md.load_snapshot()
    assert "com.apple.dock:tilesize" not in snap
    assert "com.apple.dock:autohide" in snap


def test_revert_leaves_an_unrestorable_prior_alone() -> None:
    ex = PrefsExecutor(prefs={(DOCK, "tilesize"): ("array", "(\n)")})
    md.apply(_ctx(ex))
    assert md.revert(_ctx(ex), ["com.apple.dock:tilesize"]) == []
    assert ex.prefs[(DOCK, "tilesize")] == ("integer", "48")
    assert "com.apple.dock:tilesize" in md.load_snapshot()


def test_revert_of_unrecorded_key_is_a_noop() -> None:
    ex = PrefsExecutor()
    assert md.revert(_ctx(ex), ["com.apple.dock:tilesize"]) == []
    touched = [c for c in ex.calls if c[:2] in (["defaults", "write"], ["defaults", "delete"])]
    assert touched == []


def test_resolve_ids_accepts_full_or_unique_bare_keys() -> None:
    assert md.resolve_ids(["tilesize", "NSGlobalDomain:KeyRepeat"]) == [
        "com.apple.dock:tilesize",
        "NSGlobalDomain:KeyRepeat",
    ]
    with pytest.raises(ValueError, match="ambiguous"):
        md.resolve_ids(["Clicking"])
    with pytest.raises(ValueError, match="unknown"):
        md.resolve_ids(["nope"])


def test_version_gated_rows() -> None:
    row = md.Setting(DOCK, "x", Value("bool", True), min_macos=(28, 0))
    assert row.applies(MAC) is False
    assert row.applies(OsInfo("macos", "macos", "aarch64", version_id="28.1")) is True
    old_only = md.Setting(DOCK, "y", Value("bool", True), max_macos=(26, 99))
    assert old_only.applies(MAC) is False


def test_module_is_macos_only_and_in_macos_desktop() -> None:
    assert md.MacosDefaults.families == ("macos",)
    assert md.MacosDefaults.profiles == ("macos-desktop",)
    ex = PrefsExecutor()
    md.MacosDefaults().install(_ctx(ex))
    assert md.MacosDefaults().verify(_ctx(ex)) is True
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_macos_defaults.py -v`
Expected: FAIL (`ImportError: cannot import name 'macos_defaults'`).

- [ ] **Step 3: Implement** `src/devboost/modules/macos_defaults.py`

```python
"""macos-defaults — the spec §2 `defaults` table: snapshotted first, applied, revertible.

The snapshot records each key's value from *before dev-boost first wrote it* (absent keys
as null) and is never overwritten, so `devboost revert macos-defaults` restores the
machine's own state. Processes restart only when one of their keys changed.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from devboost.core import log
from devboost.core.macver import macos_version
from devboost.core.osinfo import OsInfo
from devboost.core.registry import register
from devboost.exec.primitives import macdefaults
from devboost.exec.primitives.macdefaults import Value
from devboost.model import Ctx, Module


@dataclass(frozen=True)
class Setting:
    domain: str
    key: str
    value: Value
    #: Process to `killall` when this key changed (None: takes effect at next login).
    restart: str | None = None
    min_macos: tuple[int, int] | None = None
    max_macos: tuple[int, int] | None = None

    @property
    def id(self) -> str:
        return f"{self.domain}:{self.key}"

    def applies(self, os_info: OsInfo) -> bool:
        v = macos_version(os_info)
        if v is None:
            return True
        if self.min_macos is not None and v < self.min_macos:
            return False
        return not (self.max_macos is not None and v > self.max_macos)


def _b(x: bool) -> Value:
    return Value("bool", x)


def _i(x: int) -> Value:
    return Value("int", x)


def _s(x: str) -> Value:
    return Value("string", x)


_G = "NSGlobalDomain"
_FINDER = "com.apple.finder"
_DOCK = "com.apple.dock"
_SHOT = "com.apple.screencapture"
_DS = "com.apple.desktopservices"
#: Restart order, so `killall` calls are deterministic.
_PROCS = ("Dock", "Finder", "SystemUIServer")

SETTINGS: tuple[Setting, ...] = (
    Setting(_G, "KeyRepeat", _i(2)),
    Setting(_G, "InitialKeyRepeat", _i(15)),
    Setting(_G, "ApplePressAndHoldEnabled", _b(False)),
    Setting(_G, "AppleShowAllExtensions", _b(True), "Finder"),
    Setting(_G, "NSAutomaticSpellingCorrectionEnabled", _b(False)),
    Setting(_G, "NSAutomaticQuoteSubstitutionEnabled", _b(False)),
    Setting(_G, "NSAutomaticDashSubstitutionEnabled", _b(False)),
    Setting(_FINDER, "AppleShowAllFiles", _b(True), "Finder"),
    Setting(_FINDER, "ShowPathbar", _b(True), "Finder"),
    Setting(_FINDER, "ShowStatusBar", _b(True), "Finder"),
    Setting(_FINDER, "FXPreferredViewStyle", _s("Nlsv"), "Finder"),
    Setting(_DS, "DSDontWriteNetworkStores", _b(True)),
    Setting(_DS, "DSDontWriteUSBStores", _b(True)),
    Setting(_DOCK, "autohide", _b(True), "Dock"),
    Setting(_DOCK, "tilesize", _i(48), "Dock"),
    Setting(_DOCK, "show-recents", _b(False), "Dock"),
    # Screenshots land on the clipboard, ready for `herdr --remote` Ctrl+V image paste;
    # ⌘⇧5 → Options → "Save to" still saves files.
    Setting(_SHOT, "target", _s("clipboard"), "SystemUIServer"),
    Setting(_SHOT, "type", _s("png"), "SystemUIServer"),
    Setting("com.apple.AppleMultitouchTrackpad", "Clicking", _b(True)),
    Setting("com.apple.driver.AppleBluetoothMultitouch.trackpad", "Clicking", _b(True)),
)

Prior = dict[str, Value | None]


def snapshot_path() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path(os.environ["HOME"]) / ".local" / "state")
    return Path(base) / "devboost" / "macos-defaults.prev.json"


def _encode(v: Value | None) -> dict[str, Any] | None:
    if v is None:
        return None
    if v.kind == "other":
        return {"kind": "other"}
    return {"kind": v.kind, "value": v.value}


def _decode(raw: Any) -> Value | None:
    if raw is None:
        return None
    return Value(raw["kind"], raw.get("value", ""))


def load_snapshot() -> Prior:
    try:
        raw = json.loads(snapshot_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: _decode(v) for k, v in raw.get("prior", {}).items()}


def save_snapshot(prior: Prior) -> None:
    path = snapshot_path()
    if not prior:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {"version": 1, "prior": {k: _encode(v) for k, v in sorted(prior.items())}}
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")


def _applicable(ctx: Ctx) -> list[Setting]:
    return [s for s in SETTINGS if s.applies(ctx.os)]


def _restart(ctx: Ctx, procs: set[str]) -> None:
    for proc in sorted(procs, key=_PROCS.index):
        ctx.ex.run(["killall", proc])  # not running → non-zero, harmless


def apply(ctx: Ctx) -> list[str]:
    """Snapshot unrecorded keys, write every key that differs, restart what changed."""
    settings = _applicable(ctx)
    current = {s.id: macdefaults.read(ctx, s.domain, s.key) for s in settings}
    prior = load_snapshot()
    for s in settings:
        prior.setdefault(s.id, current[s.id])
    save_snapshot(prior)  # before the first write, so a crash never loses a prior value
    changed = [s for s in settings if current[s.id] != s.value]
    for s in changed:
        macdefaults.write(ctx, s.domain, s.key, s.value)
    _restart(ctx, {r for s in changed if (r := s.restart) is not None})
    if any(s.restart is None for s in changed):
        log.info("macos-defaults: keyboard, autocorrect, trackpad and .DS_Store changes "
                 "apply fully after you log out and back in")
    return [s.id for s in changed]


def verify_all(ctx: Ctx) -> bool:
    return all(macdefaults.read(ctx, s.domain, s.key) == s.value for s in _applicable(ctx))


def resolve_ids(names: Sequence[str]) -> list[str]:
    """Map `<domain>:<key>` or a table-unique bare key to its id."""
    ids = [s.id for s in SETTINGS]
    out: list[str] = []
    for name in names:
        if name in ids:
            out.append(name)
            continue
        hits = [i for i in ids if i.split(":", 1)[1] == name]
        if len(hits) == 1:
            out.append(hits[0])
        elif hits:
            raise ValueError(f"ambiguous key {name!r}; use one of: {', '.join(hits)}")
        else:
            raise ValueError(f"unknown macos-defaults key {name!r}; known: {', '.join(ids)}")
    return out


def revert(ctx: Ctx, ids: Sequence[str] | None = None) -> list[str]:
    """Restore recorded prior values (all, or *ids*); returns the ids restored."""
    prior = load_snapshot()
    wanted = list(prior) if ids is None else list(ids)
    restart = {s.id: s.restart for s in SETTINGS}
    done: list[str] = []
    procs: set[str] = set()
    for i in wanted:
        if i not in prior:
            log.warn(f"macos-defaults: nothing recorded for {i} — left as is")
            continue
        old = prior[i]
        domain, key = i.split(":", 1)
        if old is not None and old.kind == "other":
            log.warn(f"macos-defaults: {i} held a value dev-boost cannot restore — left as is")
            continue
        if old is None:
            macdefaults.delete(ctx, domain, key)
        else:
            macdefaults.write(ctx, domain, key, old)
        del prior[i]
        done.append(i)
        if (proc := restart.get(i)) is not None:
            procs.add(proc)
    save_snapshot(prior)
    _restart(ctx, procs)
    return done


@register
class MacosDefaults(Module):
    name = "macos-defaults"
    category = "macos-desktop"
    description = "macOS developer defaults (Finder, Dock, keyboard, screenshots); revertible."
    profiles = ("macos-desktop",)
    families = ("macos",)
    portable = True

    def verify(self, ctx: Ctx) -> bool:
        return verify_all(ctx)

    def install(self, ctx: Ctx) -> None:
        apply(ctx)
```

In `profiles.toml`, add after the `hardware-nvidia` line (Tasks 5, 6 and 8 extend it):

```toml
# macos-desktop — the macOS desktop layer (spec §2); Linux drops every member via `families`.
macos-desktop    = ["macos-defaults"]
```

In `tests/conftest.py` `profiles_file`, add one line before `'macos = ["ripgrep"]\n'`:

```python
        'macos-desktop = ["macos-defaults"]\n'
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/modules/test_macos_defaults.py tests/core -q && uv run mypy && uv run ruff check`
Expected: PASS, clean. `test_no_new_macos_gaps` stays green because `portable = True`.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/modules/macos_defaults.py tests/modules/test_macos_defaults.py tests/conftest.py ../profiles.toml
git commit -m "feat(macos): macos-defaults with snapshot and revert"
```

---

### Task 4: `devboost revert macos-defaults [KEY…]`

**Files:**
- Create: `engine/src/devboost/cli/revert.py`
- Modify: `engine/src/devboost/cli/app.py` (one import + one `add_typer` line)
- Test: `engine/tests/cli/test_revert.py` (create)

**Interfaces:**
- Consumes: `macos_defaults.resolve_ids`, `macos_defaults.revert` (Task 3).
- Produces: the Typer sub-app `revert` with the command `macos-defaults`. It exits 2 (`BadParameter`) off macOS or for an unknown/ambiguous key, and exits 0 otherwise.

- [ ] **Step 1: Write the failing tests** — `tests/cli/test_revert.py`

```python
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from devboost.cli import revert as revert_cli
from devboost.cli.app import app
from devboost.core import osinfo
from devboost.core.osinfo import OsInfo
from devboost.model import Ctx
from devboost.modules import macos_defaults as md
from tests.modules.macos_fakes import PrefsExecutor

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
DOCK = "com.apple.dock"


@pytest.fixture
def mac_prefs(monkeypatch: pytest.MonkeyPatch) -> PrefsExecutor:
    ex = PrefsExecutor(prefs={(DOCK, "tilesize"): ("integer", "64")})
    monkeypatch.setattr(osinfo, "detect", lambda **_: MAC)
    monkeypatch.setattr(revert_cli, "RealExecutor", lambda: ex)
    md.apply(Ctx(os=MAC, ex=ex))
    return ex


def test_revert_one_key(mac_prefs: PrefsExecutor) -> None:
    res = CliRunner().invoke(app, ["revert", "macos-defaults", "tilesize"])
    assert res.exit_code == 0, res.output
    assert mac_prefs.prefs[(DOCK, "tilesize")] == ("integer", "64")
    assert mac_prefs.prefs[(DOCK, "autohide")] == ("boolean", "1")


def test_revert_everything(mac_prefs: PrefsExecutor) -> None:
    res = CliRunner().invoke(app, ["revert", "macos-defaults"])
    assert res.exit_code == 0, res.output
    assert mac_prefs.prefs == {(DOCK, "tilesize"): ("integer", "64")}
    assert not md.snapshot_path().exists()


def test_unknown_key_is_a_usage_error(mac_prefs: PrefsExecutor) -> None:
    res = CliRunner().invoke(app, ["revert", "macos-defaults", "nope"])
    assert res.exit_code == 2
    assert "unknown" in res.output


def test_linux_is_refused() -> None:
    res = CliRunner().invoke(app, ["revert", "macos-defaults"])
    assert res.exit_code == 2
    assert "macOS-only" in res.output
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cli/test_revert.py -v`
Expected: FAIL (`ImportError` for `devboost.cli.revert`).

- [ ] **Step 3: Implement**

`src/devboost/cli/revert.py`:

```python
"""`devboost revert` — undo what a module changed on this machine."""

from __future__ import annotations

from typing import Annotated

import typer

from devboost.core import log, osinfo
from devboost.exec.executor import RealExecutor
from devboost.model import Ctx
from devboost.modules import macos_defaults as md

app = typer.Typer(help="undo a module's changes", no_args_is_help=True)


@app.command("macos-defaults")
def macos_defaults(
    keys: Annotated[
        list[str] | None,
        typer.Argument(
            help="keys to restore (`com.apple.dock:tilesize` or `tilesize`); none = all"
        ),
    ] = None,
) -> None:
    """Restore the macOS defaults recorded before dev-boost changed them."""
    ctx = Ctx(os=osinfo.detect(), ex=RealExecutor())
    if ctx.os.family != "macos":
        raise typer.BadParameter("revert macos-defaults is macOS-only")
    try:
        ids = md.resolve_ids(keys) if keys else None
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    done = md.revert(ctx, ids)
    if done:
        log.ok(f"revert: restored {len(done)} setting(s): {', '.join(done)}")
        log.info("revert: `devboost install` re-applies them; leave macos-defaults out of "
                 "the profiles you install to keep them reverted")
    else:
        log.info("revert: nothing recorded to restore")
```

In `src/devboost/cli/app.py`, add the import next to the other `cli` sub-app imports (`from devboost.cli import revert as _revert`), and add one line after `app.add_typer(_secrets_cmd.app, name="secrets")`:

```python
app.add_typer(_revert.app, name="revert")
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/cli -q && uv run mypy && uv run ruff check`
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/cli/revert.py src/devboost/cli/app.py tests/cli/test_revert.py
git commit -m "feat(cli): devboost revert macos-defaults [key...]"
```

---

### Task 5: `macos-limits`, `macos-firewall`, `timemachine-exclusions`

**Files:**
- Create: `engine/src/devboost/modules/macos_system.py`
- Modify: `profiles.toml` (`macos-desktop` line)
- Test: `engine/tests/modules/test_macos_system.py` (create)

**Interfaces:**
- Consumes: `launchd.system_daemon`, `launchd.user_agent`, `launchd.daemon_loaded`, `launchd.agent_loaded`, `launchd.label` (M1); `tests.passstore.fakes.RuleExecutor`.
- Produces (module `devboost.modules.macos_system`):
  - Constants: `MAXFILES = 524288`, `SOCKETFILTERFW = "/usr/libexec/ApplicationFirewall/socketfilterfw"`, `TM_PATHS: tuple[str, ...]` (relative to HOME).
  - `firewall_enabled(ctx) -> bool` (Task 16's doctor reuses it).
  - `tm_sweep_script() -> str` (POSIX sh).
  - Registered modules `macos-limits` (`MacosLimits`), `macos-firewall` (`MacosFirewall`), `timemachine-exclusions` (`TimemachineExclusions`). All have `families = ("macos",)`, `portable = True`, `profiles = ("macos-desktop",)`.

- [ ] **Step 1: Write the failing tests** — `tests/modules/test_macos_system.py`

```python
from __future__ import annotations

import os
import plistlib
import stat
import subprocess
from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.exec.primitives import launchd
from devboost.model import Ctx
from devboost.modules import macos_system as ms
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")


def _ctx(ex: RuleExecutor) -> Ctx:
    return Ctx(os=MAC, ex=ex)


@pytest.fixture(autouse=True)
def _daemons(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launchd, "DAEMONS_DIR", tmp_path / "LaunchDaemons")


# --- macos-limits -------------------------------------------------------------------------


def test_limits_verify_needs_both_sysctls_and_the_daemon() -> None:
    high = RuleExecutor(rules=[(("sysctl", "-n"), Result(0, "524288\n524288\n"))])
    assert ms.MacosLimits().verify(_ctx(high)) is True
    clamped = RuleExecutor(rules=[(("sysctl", "-n"), Result(0, "184320\n92160\n"))])
    assert ms.MacosLimits().verify(_ctx(clamped)) is False
    unloaded = RuleExecutor(rules=[
        (("sysctl", "-n"), Result(0, "524288\n524288\n")),
        (("launchctl", "print"), Result(113)),
    ])
    assert ms.MacosLimits().verify(_ctx(unloaded)) is False


def test_limits_install_writes_the_daemon_and_applies_now(tmp_path: Path) -> None:
    ex = RuleExecutor(rules=[(("launchctl", "print"), Result(113))])
    ms.MacosLimits().install(_ctx(ex))
    plist = tmp_path / "LaunchDaemons" / "dev.devboost.maxfiles.plist"
    assert ["sudo", "tee", str(plist)] in ex.calls
    body = plistlib.loads(ex.stdins[ex.calls.index(["sudo", "tee", str(plist)])].encode())
    assert body["ProgramArguments"][:2] == ["/bin/sh", "-c"]
    script = body["ProgramArguments"][2]
    assert "sysctl -w kern.maxfiles=524288 kern.maxfilesperproc=524288" in script
    assert "launchctl limit maxfiles 524288 524288 || true" in script
    assert body["RunAtLoad"] is True
    assert ["sudo", "sh", "-c", script] in ex.calls


# --- macos-firewall -----------------------------------------------------------------------


def test_firewall_state_parsing() -> None:
    on = RuleExecutor(
        rules=[(("--getglobalstate",), Result(0, "Firewall is enabled. (State = 1)\n"))]
    )
    off = RuleExecutor(
        rules=[(("--getglobalstate",), Result(0, "Firewall is disabled. (State = 0)\n"))]
    )
    assert ms.firewall_enabled(_ctx(on)) is True
    assert ms.firewall_enabled(_ctx(off)) is False
    assert ms.MacosFirewall().verify(_ctx(on)) is True


def test_firewall_install_uses_sudo() -> None:
    ex = RuleExecutor()
    ms.MacosFirewall().install(_ctx(ex))
    assert ex.calls == [["sudo", ms.SOCKETFILTERFW, "--setglobalstate", "on"]]


# --- timemachine-exclusions ---------------------------------------------------------------


def test_tm_paths_match_the_spec() -> None:
    assert ms.TM_PATHS == (
        "Library/Caches", ".colima", ".gradle", ".npm", ".cache", ".nuget/packages",
        "Library/Developer/Xcode/DerivedData",
    )


def test_tm_verify_checks_existing_paths_only_and_the_agent(tmp_path: Path) -> None:
    (tmp_path / ".npm").mkdir()
    excluded = RuleExecutor(rules=[(("tmutil", "isexcluded"), Result(0, "[Excluded]  x\n"))])
    assert ms.TimemachineExclusions().verify(_ctx(excluded)) is True
    checked = [c[2] for c in excluded.calls if c[:2] == ["tmutil", "isexcluded"]]
    assert checked == [str(tmp_path / ".npm")]  # missing paths are not probed
    included = RuleExecutor(rules=[(("tmutil", "isexcluded"), Result(0, "[Included]  x\n"))])
    assert ms.TimemachineExclusions().verify(_ctx(included)) is False


def test_tm_install_registers_the_sweep_agent_and_runs_it(tmp_path: Path) -> None:
    ex = RuleExecutor(rules=[(("launchctl", "print"), Result(113))])
    ms.TimemachineExclusions().install(_ctx(ex))
    plist = tmp_path / "Library" / "LaunchAgents" / "dev.devboost.tm-exclusions.plist"
    body = plistlib.loads(plist.read_bytes())
    assert body["ProgramArguments"] == ["/bin/sh", "-c", ms.tm_sweep_script()]
    assert body["StartInterval"] == 21600
    assert body["RunAtLoad"] is True
    assert ["/bin/sh", "-c", ms.tm_sweep_script()] in ex.calls


def test_tm_sweep_script_excludes_existing_paths_and_prunes_repos(tmp_path: Path) -> None:
    """Run the real POSIX script against a fake `tmutil` (never the real one)."""
    home = tmp_path
    (home / ".npm").mkdir()
    (home / "repos" / "app" / "node_modules" / "dep" / "node_modules").mkdir(parents=True)
    (home / "repos" / "app" / "vendor").mkdir(parents=True)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "tmutil.log"
    fake = bindir / "tmutil"
    fake.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> "{log}"\n'
        'if [ "$1" = isexcluded ]; then echo "[Included]  $2"; fi\n',
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    env = {**os.environ, "HOME": str(home), "PATH": f"{bindir}:/usr/bin:/bin"}
    subprocess.run(["/bin/sh", "-c", ms.tm_sweep_script()], env=env, check=True)
    added = [ln.split(" ", 1)[1] for ln in log.read_text().splitlines()
             if ln.startswith("addexclusion ")]
    assert added[0] == str(home / ".npm")  # fixed paths are swept first
    assert sorted(added) == sorted([
        str(home / ".npm"),
        str(home / "repos" / "app" / "node_modules"),  # find order is unspecified
        str(home / "repos" / "app" / "vendor"),
    ])
    assert not any(".colima" in a for a in added)  # missing → skipped
    assert not any("dep/node_modules" in a for a in added)  # pruned


def test_modules_are_macos_only_and_in_macos_desktop() -> None:
    for cls in (ms.MacosLimits, ms.MacosFirewall, ms.TimemachineExclusions):
        assert cls.families == ("macos",)
        assert cls.profiles == ("macos-desktop",)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_macos_system.py -v`
Expected: FAIL (`ImportError: cannot import name 'macos_system'`).

- [ ] **Step 3: Implement** `src/devboost/modules/macos_system.py`

```python
"""macOS system modules: open-files limit, application firewall, Time Machine exclusions.

(`default-apps` joins this file in Task 8.)
"""

from __future__ import annotations

import os
from pathlib import Path

from devboost.core import log
from devboost.core.errors import InstallError
from devboost.core.registry import register
from devboost.exec.primitives import launchd
from devboost.model import Ctx, Module

# --- macos-limits -------------------------------------------------------------------------

MAXFILES = 524288
_LIMITS_LABEL = launchd.label("maxfiles")
#: sysctl lifts the kernel clamp (`ulimit -n` can never exceed kern.maxfilesperproc);
#: `launchctl limit` raises launchd's own limit for GUI apps — best-effort, because Apple
#: returns EPERM for it under SIP on some releases (spec D11).
_LIMITS_SCRIPT = (
    f"sysctl -w kern.maxfiles={MAXFILES} kern.maxfilesperproc={MAXFILES} && "
    f"{{ launchctl limit maxfiles {MAXFILES} {MAXFILES} || true; }}"
)


def _sysctl_ints(ctx: Ctx, *names: str) -> list[int]:
    res = ctx.ex.run(["sysctl", "-n", *names])
    if not res.ok:
        return []
    try:
        return [int(tok) for tok in res.stdout.split()]
    except ValueError:
        return []


@register
class MacosLimits(Module):
    name = "macos-limits"
    category = "macos-desktop"
    description = "Open-files limit 524288 (LaunchDaemon: sysctl + launchctl limit)."
    profiles = ("macos-desktop",)
    families = ("macos",)
    portable = True

    def verify(self, ctx: Ctx) -> bool:
        vals = _sysctl_ints(ctx, "kern.maxfiles", "kern.maxfilesperproc")
        return (
            len(vals) == 2
            and min(vals) >= MAXFILES
            and launchd.daemon_loaded(ctx, _LIMITS_LABEL)
        )

    def install(self, ctx: Ctx) -> None:
        launchd.system_daemon(ctx, _LIMITS_LABEL, ["/bin/sh", "-c", _LIMITS_SCRIPT])
        # Apply now as well: an unchanged plist is not re-bootstrapped, and the user
        # should not need a reboot.
        res = ctx.ex.run(["sh", "-c", _LIMITS_SCRIPT], sudo=True)
        if not res.ok:
            raise InstallError("macos-limits", f"sudo sh -c '{_LIMITS_SCRIPT}'", res.code)
        log.info("macos-limits: new terminals get `ulimit -n 524288` (shell.zsh)")


# --- macos-firewall -----------------------------------------------------------------------

SOCKETFILTERFW = "/usr/libexec/ApplicationFirewall/socketfilterfw"


def firewall_enabled(ctx: Ctx) -> bool:
    """True when the application firewall is on ("Firewall is enabled. (State = 1)")."""
    res = ctx.ex.run([SOCKETFILTERFW, "--getglobalstate"])
    return res.ok and "enabled" in res.stdout


@register
class MacosFirewall(Module):
    name = "macos-firewall"
    category = "macos-desktop"
    description = "Turn on the macOS application firewall."
    profiles = ("macos-desktop",)
    families = ("macos",)
    portable = True

    def verify(self, ctx: Ctx) -> bool:
        return firewall_enabled(ctx)

    def install(self, ctx: Ctx) -> None:
        res = ctx.ex.run([SOCKETFILTERFW, "--setglobalstate", "on"], sudo=True)
        if not res.ok:
            raise InstallError("macos-firewall", f"{SOCKETFILTERFW} --setglobalstate on",
                               res.code)


# --- timemachine-exclusions ---------------------------------------------------------------

#: Regenerable caches and VMs (relative to HOME) — spec §2.
TM_PATHS: tuple[str, ...] = (
    "Library/Caches",
    ".colima",
    ".gradle",
    ".npm",
    ".cache",
    ".nuget/packages",
    "Library/Developer/Xcode/DerivedData",
)
_TM_LABEL = launchd.label("tm-exclusions")
_TM_INTERVAL = 6 * 60 * 60


def _home() -> Path:
    return Path(os.environ["HOME"])


def tm_sweep_script() -> str:
    """Sticky-exclude the fixed paths that exist, plus node_modules/vendor under ~/repos.

    Sticky (`tmutil addexclusion` without -p) needs no sudo and follows the item if it
    moves; a path that does not exist yet is skipped and picked up by a later sweep.
    """
    fixed = " ".join(f'"$HOME/{p}"' for p in TM_PATHS)
    return (
        'ex() { [ -e "$1" ] || return 0; '
        "tmutil isexcluded \"$1\" | grep -q '^\\[Excluded\\]' || tmutil addexclusion \"$1\"; }\n"
        f'for p in {fixed}; do ex "$p"; done\n'
        'if [ -d "$HOME/repos" ]; then\n'
        '  find "$HOME/repos" -maxdepth 6 -type d \\( -name node_modules -o -name vendor \\) '
        '-prune -print | while IFS= read -r d; do ex "$d"; done\n'
        "fi\n"
        "exit 0\n"
    )


def _excluded(ctx: Ctx, path: Path) -> bool:
    res = ctx.ex.run(["tmutil", "isexcluded", str(path)])
    return res.ok and res.stdout.lstrip().startswith("[Excluded]")


@register
class TimemachineExclusions(Module):
    name = "timemachine-exclusions"
    category = "macos-desktop"
    description = "Keep caches, VMs, node_modules and vendor out of Time Machine."
    profiles = ("macos-desktop",)
    families = ("macos",)
    portable = True

    def verify(self, ctx: Ctx) -> bool:
        present = [p for p in (_home() / rel for rel in TM_PATHS) if p.exists()]
        return all(_excluded(ctx, p) for p in present) and launchd.agent_loaded(ctx, _TM_LABEL)

    def install(self, ctx: Ctx) -> None:
        argv = ["/bin/sh", "-c", tm_sweep_script()]
        launchd.user_agent(ctx, _TM_LABEL, argv, start_interval=_TM_INTERVAL, run_at_load=True)
        res = ctx.ex.run(argv)
        if not res.ok:
            raise InstallError("timemachine-exclusions", "tm-exclusions sweep", res.code)
```

In `profiles.toml` the `macos-desktop` line becomes:

```toml
macos-desktop    = ["macos-defaults","macos-limits","macos-firewall","timemachine-exclusions"]
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/modules/test_macos_system.py -v && uv run mypy && uv run ruff check`
Expected: PASS, clean.

- [ ] **Step 5: §0 on-Mac check (read-only)**

```bash
launchctl limit maxfiles                       # expect: maxfiles 256 unlimited (before M5)
sysctl kern.maxfiles kern.maxfilesperproc      # expect: 184320 / 92160 (before M5)
/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate   # "Firewall is (en|dis)abled. (State = N)"
tmutil isexcluded ~/Library/Caches /nonexistent   # "[Excluded] …" and "[UNKNOWN] …"
```
The output must match the strings the code parses: `enabled`, `[Excluded]`, and two integers from `sysctl -n`. If macOS 27 prints something else, fix the parser and its test **before** committing. Record the output in the PR description.

- [ ] **Step 6: Commit**

```bash
git add src/devboost/modules/macos_system.py tests/modules/test_macos_system.py ../profiles.toml
git commit -m "feat(macos): open-files limit, application firewall, Time Machine exclusions"
```

---

### Task 6: `CaskApp` base + desktop apps + Quick Look

**Files:**
- Create: `engine/src/devboost/modules/_cask.py`, `engine/src/devboost/modules/macos_apps.py`
- Modify: `profiles.toml` (`macos-desktop` line)
- Test: `engine/tests/modules/test_macos_apps.py` (create)

**Interfaces:**
- Consumes: `pkg.install_cask`, `pkg.cask_installed` (M1); `Homebrew` (A1); `Dotfiles` (`devboost.modules.shell`); `TccGrant` (M1); `macos_version` (Task 1).
- Produces:
  - `devboost.modules._cask.CaskInstall(cask: str, launch: str | None = None)`: a frozen dataclass that implements `Installer`. Its `token` property is the short cask name.
  - `devboost.modules._cask.CaskApp(Module)`: ClassVars `cask: str`, `launch: str | None = None`, `min_macos` / `max_macos: tuple[int, int] | None = None`; `families = ("macos",)`, `gui = True`, `requires = (Homebrew,)`. A subclass that defines `cask` gets `per_os = OsMap(macos=CaskInstall(cask, launch))`. `supported_on` applies `min_macos` / `max_macos`.
  - Registered desktop modules: `stats`, `raycast`, `aerospace`, `alt-tab`, `thaw`, `monitorcontrol`, `keka`, `quicklook`.

- [ ] **Step 1: Write the failing tests** — `tests/modules/test_macos_apps.py`

```python
from __future__ import annotations

from pathlib import Path

from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx, TccGrant
from devboost.modules import macos_apps as apps
from devboost.modules._cask import CaskApp, CaskInstall

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
MAC15 = OsInfo("macos", "macos", "aarch64", version_id="15.6")
FEDORA = OsInfo("fedora", "fedora", "x86_64")

DESKTOP = {
    # module: (cask, launch, TCC services)
    "stats": ("stats", "Stats", ()),
    "raycast": ("raycast", "Raycast", ("Accessibility",)),
    "aerospace": ("nikitabobko/tap/aerospace", "AeroSpace", ("Accessibility",)),
    "alt-tab": ("alt-tab", "AltTab", ("Accessibility", "ScreenCapture")),
    "thaw": ("thaw", "Thaw", ("Accessibility", "ScreenCapture")),
    "monitorcontrol": ("monitorcontrol", "MonitorControl", ("Accessibility",)),
    "keka": ("keka", None, ()),
}


def test_desktop_cask_table() -> None:
    mods = load()
    for name, (cask, launch, services) in DESKTOP.items():
        cls = mods[name]
        assert issubclass(cls, CaskApp), name
        assert cls.per_os.macos == CaskInstall(cask, launch), name
        assert tuple(g.service for g in cls.tcc) == services, name
        assert cls.profiles == ("macos-desktop",), name


def test_betterdisplay_is_not_shipped() -> None:
    assert "betterdisplay" not in load()  # paid for business use (D3)


def test_tapped_cask_installs_fully_qualified_and_verifies_short() -> None:
    ex = FakeExecutor()
    ctx = Ctx(os=MAC, ex=ex)
    apps.Aerospace().install(ctx)
    assert ex.calls == [
        ["brew", "install", "--cask", "-y", "--adopt", "nikitabobko/tap/aerospace"],
        ["open", "-g", "-a", "AeroSpace"],
    ]
    ex.calls.clear()
    apps.Aerospace().verify(ctx)
    assert ex.calls == [["brew", "list", "--cask", "--versions", "aerospace"]]


def test_app_without_launch_is_not_opened() -> None:
    ex = FakeExecutor()
    apps.Keka().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [["brew", "install", "--cask", "-y", "--adopt", "keka"]]


def test_aerospace_runs_after_the_dotfiles() -> None:
    assert "dotfiles" in {c.name for c in apps.Aerospace.after}


def test_thaw_is_gated_below_macos_26(tmp_path: Path) -> None:
    assert apps.Thaw.supported_on(MAC) is True
    assert apps.Thaw.supported_on(MAC15) is False
    plan = build_plan(["thaw"], load(), MAC15, gpu_marker=tmp_path / "none")
    assert plan[0].skip_reason == "unsupported-os"


def test_linux_drops_every_cask_app(tmp_path: Path) -> None:
    names = [*DESKTOP, "quicklook"]
    assert build_plan(names, load(), FEDORA, gpu_marker=tmp_path / "none") == []


def test_quicklook_installs_both_extensions_and_registers_them() -> None:
    ex = FakeExecutor()
    apps.Quicklook().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [
        ["brew", "install", "--cask", "-y", "--adopt", "qlmarkdown"],
        ["open", "-g", "-a", "QLMarkdown"],
        ["brew", "install", "--cask", "-y", "--adopt", "syntax-highlight"],
        ["open", "-g", "-a", "Syntax Highlight"],
        ["qlmanage", "-r"],
    ]


def test_tcc_grants_name_the_app_the_user_sees() -> None:
    assert apps.Raycast.tcc == (TccGrant("Accessibility", "Raycast"),)
    assert apps.AltTab.tcc == (
        TccGrant("Accessibility", "AltTab"),
        TccGrant("ScreenCapture", "AltTab"),
    )
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_macos_apps.py -v`
Expected: FAIL (`ImportError` for `_cask` / `macos_apps`).

- [ ] **Step 3: Implement**

`src/devboost/modules/_cask.py`:

```python
"""CaskApp — a macOS app that is exactly one Homebrew cask (spec §2 casks).

A subclass is data: `cask`, optionally `launch` (opened once after install so macOS
registers its login item / extension and the app can ask for its permissions),
`min_macos`/`max_macos` (a version gate the plan reports as unsupported-os), and `tcc`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from devboost.core.macver import macos_version
from devboost.core.osinfo import OsInfo, OsMap
from devboost.exec.primitives import pkg
from devboost.model import Ctx, Module
from devboost.modules.homebrew import Homebrew  # A1 — use the path Task 0 found


@dataclass(frozen=True)
class CaskInstall:
    """Install one cask (a `tap/name/cask` token auto-taps), then open the app once."""

    cask: str
    launch: str | None = None

    @property
    def token(self) -> str:
        """The short token brew lists an installed cask under (`aerospace`)."""
        return self.cask.rsplit("/", 1)[-1]

    def verify(self, ctx: Ctx) -> bool:
        return pkg.cask_installed(ctx, self.token)

    def install(self, ctx: Ctx) -> None:
        pkg.install_cask(ctx, self.cask)
        if self.launch is not None:
            ctx.ex.run(["open", "-g", "-a", self.launch])


class CaskApp(Module):
    """Base for single-cask macOS apps. Subclasses set `cask` (and optionally the rest)."""

    cask: ClassVar[str]
    launch: ClassVar[str | None] = None
    min_macos: ClassVar[tuple[int, int] | None] = None
    max_macos: ClassVar[tuple[int, int] | None] = None
    families = ("macos",)
    gui = True
    requires = (Homebrew,)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if "cask" in cls.__dict__:
            cls.per_os = OsMap(macos=CaskInstall(cls.cask, cls.launch))

    @classmethod
    def supported_on(cls, os_info: OsInfo) -> bool:
        v = macos_version(os_info)
        if v is None:
            return True
        if cls.min_macos is not None and v < cls.min_macos:
            return False
        return not (cls.max_macos is not None and v > cls.max_macos)
```

`src/devboost/modules/macos_apps.py`:

```python
"""macOS desktop apps (spec §2 casks). Every one is free for commercial use (D3–D5)."""

from __future__ import annotations

from dataclasses import dataclass

from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import Ctx, Module, TccGrant
from devboost.modules._cask import CaskApp
from devboost.modules.homebrew import Homebrew  # A1
from devboost.modules.shell import Dotfiles

_DESKTOP = ("macos-desktop",)


@register
class Stats(CaskApp):
    name = "stats"
    category = "macos-desktop"
    description = "Stats — menu-bar CPU/RAM/disk/network monitor (MIT)."
    profiles = _DESKTOP
    cask = "stats"
    launch = "Stats"


@register
class Raycast(CaskApp):
    name = "raycast"
    category = "macos-desktop"
    description = "Raycast — launcher and clipboard/window tools (free plan; OK for work)."
    profiles = _DESKTOP
    cask = "raycast"
    launch = "Raycast"
    tcc = (TccGrant("Accessibility", "Raycast"),)


@register
class Aerospace(CaskApp):
    name = "aerospace"
    category = "macos-desktop"
    description = "AeroSpace — i3-like tiling window manager (MIT); config via dotfiles."
    profiles = _DESKTOP
    cask = "nikitabobko/tap/aerospace"
    launch = "AeroSpace"
    after = (Dotfiles,)  # first launch reads ~/.config/aerospace/aerospace.toml
    tcc = (TccGrant("Accessibility", "AeroSpace"),)


@register
class AltTab(CaskApp):
    name = "alt-tab"
    category = "macos-desktop"
    description = "AltTab — Windows-style window switcher with previews (GPL-3.0)."
    profiles = _DESKTOP
    cask = "alt-tab"
    launch = "AltTab"
    tcc = (TccGrant("Accessibility", "AltTab"), TccGrant("ScreenCapture", "AltTab"))


@register
class Thaw(CaskApp):
    name = "thaw"
    category = "macos-desktop"
    description = "Thaw — menu-bar item manager (GPL-3.0; macOS 26+)."
    profiles = _DESKTOP
    cask = "thaw"
    launch = "Thaw"
    min_macos = (26, 0)
    tcc = (TccGrant("Accessibility", "Thaw"), TccGrant("ScreenCapture", "Thaw"))


@register
class MonitorControl(CaskApp):
    name = "monitorcontrol"
    category = "macos-desktop"
    description = "MonitorControl — external-display brightness/volume over DDC (MIT)."
    profiles = _DESKTOP
    cask = "monitorcontrol"
    launch = "MonitorControl"
    tcc = (TccGrant("Accessibility", "MonitorControl"),)


@register
class Keka(CaskApp):
    name = "keka"
    category = "macos-desktop"
    description = "Keka — archiver (7z, zip, rar, …); free from keka.io."
    profiles = _DESKTOP
    cask = "keka"


#: (cask, app name) — both are Quick Look *app extensions*, registered by one launch.
_QUICKLOOK = (("qlmarkdown", "QLMarkdown"), ("syntax-highlight", "Syntax Highlight"))


@dataclass(frozen=True)
class _QuickLookInstall:
    def verify(self, ctx: Ctx) -> bool:
        return all(pkg.cask_installed(ctx, cask) for cask, _ in _QUICKLOOK)

    def install(self, ctx: Ctx) -> None:
        for cask, app in _QUICKLOOK:
            pkg.install_cask(ctx, cask)
            ctx.ex.run(["open", "-g", "-a", app])
        ctx.ex.run(["qlmanage", "-r"])


@register
class Quicklook(Module):
    name = "quicklook"
    category = "macos-desktop"
    description = "Quick Look previews for Markdown and source code (GPL-3.0)."
    profiles = _DESKTOP
    families = ("macos",)
    gui = True
    requires = (Homebrew,)
    per_os = OsMap(macos=_QuickLookInstall())
```

In `profiles.toml` the `macos-desktop` line becomes:

```toml
macos-desktop    = ["macos-defaults","macos-limits","macos-firewall","timemachine-exclusions",
                    "stats","raycast","aerospace","alt-tab","thaw","monitorcontrol","keka",
                    "quicklook"]
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/modules/test_macos_apps.py tests/core -q && uv run mypy && uv run ruff check`
Expected: PASS, clean. The contract test sees `per_os.macos` on every new module.

- [ ] **Step 5: §0 on-Mac check (read-only metadata)**

```bash
brew info --json=v2 --cask stats raycast alt-tab thaw monitorcontrol keka qlmarkdown syntax-highlight \
  | jq -r '.casks[] | [.token, .version, (.deprecated|tostring), (.disabled|tostring),
           ((.depends_on.macos // {})|tostring), (.auto_updates|tostring)] | @tsv'
brew tap nikitabobko/tap && brew info --cask nikitabobko/tap/aerospace | head -5
```
Expected: no `true` in the deprecated/disabled columns; thaw `>= 26`; aerospace resolves (the tap is harmless; the acceptance run needs it anyway). If a token has moved or been deprecated, fix the module **and** the D5 row. The *behavioural* §0 checks for Thaw, AeroSpace and AltTab on macOS 27 run after the real install, in Task 18 Step 4. Their outcome may flip `Thaw.max_macos` (D2).

- [ ] **Step 6: Commit**

```bash
git add src/devboost/modules/_cask.py src/devboost/modules/macos_apps.py tests/modules/test_macos_apps.py ../profiles.toml
git commit -m "feat(macos): CaskApp base, desktop apps and Quick Look extensions"
```

---

### Task 7: AeroSpace config (chezmoi)

**Files:**
- Create: `dotfiles/dot_config/aerospace/aerospace.toml.tmpl`, `engine/tests/dotfiles/render.py`
- Test: `engine/tests/dotfiles/test_aerospace_config.py` (create)

**Interfaces:**
- Produces:
  - `~/.config/aerospace/aerospace.toml` on macOS. M2's `.chezmoiignore` already keeps it off Linux.
  - Every binding in `[mode.main.binding]` is `ctrl-alt-…`. Workspaces 1–9 are on `ctrl-alt-<n>`; focus is `ctrl-alt-hjkl`; move is `ctrl-alt-shift-hjkl`. When `~/.config/devboost/voxtype-arabic` exists, `ctrl-alt-d` = Arabic dictation (D17).
  - Test helper `tests.dotfiles.render.render_template(rel: str, os_name: str, home: Path) -> str`. It renders a source template with `chezmoi execute-template --override-data`. If M2's `tests/dotfiles/conftest.py` already offers an equivalent, use M2's and skip creating `render.py`.

- [ ] **Step 1: Write the failing tests**

`tests/dotfiles/render.py`:

```python
"""Render a chezmoi template from the in-repo source for a chosen OS and HOME."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "dotfiles"
CHEZMOI = shutil.which("chezmoi")


def render_template(rel: str, os_name: str, home: Path) -> str:
    assert CHEZMOI is not None
    data = json.dumps({"chezmoi": {"os": os_name, "homeDir": str(home)}})
    res = subprocess.run(
        [CHEZMOI, "execute-template", "--override-data", data],
        input=(SRC / rel).read_text(encoding="utf-8"),
        text=True,
        capture_output=True,
        env={**os.environ, "HOME": str(home)},
        check=True,
    )
    return res.stdout
```

`tests/dotfiles/test_aerospace_config.py`:

```python
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from tests.dotfiles.render import CHEZMOI, render_template

pytestmark = pytest.mark.skipif(CHEZMOI is None, reason="chezmoi not installed")
REL = "dot_config/aerospace/aerospace.toml.tmpl"


def _main(home: Path) -> dict[str, object]:
    cfg = tomllib.loads(render_template(REL, "darwin", home))
    assert cfg["start-at-login"] is True
    binding = cfg["mode"]["main"]["binding"]
    assert isinstance(binding, dict)
    return binding


def test_every_main_binding_is_on_ctrl_alt(tmp_path: Path) -> None:
    keys = _main(tmp_path)
    assert keys, "no bindings rendered"
    assert all(k.startswith("ctrl-alt-") for k in keys), sorted(keys)


def test_workspaces_focus_and_move(tmp_path: Path) -> None:
    keys = _main(tmp_path)
    for n in range(1, 10):
        assert keys[f"ctrl-alt-{n}"] == f"workspace {n}"
        assert keys[f"ctrl-alt-shift-{n}"] == f"move-node-to-workspace {n}"
    for key, direction in zip("hjkl", ("left", "down", "up", "right"), strict=True):
        assert keys[f"ctrl-alt-{key}"] == f"focus {direction}"
        assert keys[f"ctrl-alt-shift-{key}"] == f"move {direction}"


def test_nothing_binds_paste(tmp_path: Path) -> None:
    keys = _main(tmp_path)
    assert not [k for k in keys if k.endswith("-v")]  # herdr owns Ctrl+V (spec §3)


def test_arabic_dictation_binding_only_with_the_marker(tmp_path: Path) -> None:
    assert "ctrl-alt-d" not in _main(tmp_path)
    marker = tmp_path / ".config" / "devboost" / "voxtype-arabic"
    marker.parent.mkdir(parents=True)
    marker.touch()
    assert _main(tmp_path)["ctrl-alt-d"] == (
        "exec-and-forget /opt/homebrew/bin/voxtype record toggle --model large-v3-turbo"
    )
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/dotfiles/test_aerospace_config.py -v`
Expected: FAIL (template file missing; `subprocess.CalledProcessError` / `FileNotFoundError`).

- [ ] **Step 3: Create** `dotfiles/dot_config/aerospace/aerospace.toml.tmpl`

```toml
{{- /* devboost — managed by chezmoi. Linux never gets this file (.chezmoiignore). */ -}}
{{- $arabic := stat (joinPath .chezmoi.homeDir ".config/devboost/voxtype-arabic") -}}
# devboost — managed by chezmoi (dotfiles/dot_config/aerospace/aerospace.toml.tmpl)
# AeroSpace tiling window manager — https://nikitabobko.github.io/AeroSpace/guide
# Every binding is Ctrl+Alt: AeroSpace hotkeys are global, and plain Alt would swallow
# readline/fzf Alt bindings in the terminal. Nothing here binds Ctrl+V (herdr owns paste).
# Validate after editing: aerospace reload-config --dry-run --no-gui

start-at-login = true
after-startup-command = []
enable-normalization-flatten-containers = true
enable-normalization-opposite-orientation-for-nested-containers = true
accordion-padding = 30
default-root-container-layout = 'tiles'
default-root-container-orientation = 'auto'
on-focused-monitor-changed = ['move-mouse monitor-lazy-center']
automatically-unhide-macos-hidden-apps = false
key-mapping.preset = 'qwerty'

gaps.inner.horizontal = 8
gaps.inner.vertical = 8
gaps.outer.left = 8
gaps.outer.bottom = 8
gaps.outer.top = 8
gaps.outer.right = 8

[mode.main.binding]
ctrl-alt-slash = 'layout tiles horizontal vertical'
ctrl-alt-comma = 'layout accordion horizontal vertical'
ctrl-alt-f = 'fullscreen'

ctrl-alt-h = 'focus left'
ctrl-alt-j = 'focus down'
ctrl-alt-k = 'focus up'
ctrl-alt-l = 'focus right'

ctrl-alt-shift-h = 'move left'
ctrl-alt-shift-j = 'move down'
ctrl-alt-shift-k = 'move up'
ctrl-alt-shift-l = 'move right'

ctrl-alt-minus = 'resize smart -50'
ctrl-alt-equal = 'resize smart +50'

ctrl-alt-1 = 'workspace 1'
ctrl-alt-2 = 'workspace 2'
ctrl-alt-3 = 'workspace 3'
ctrl-alt-4 = 'workspace 4'
ctrl-alt-5 = 'workspace 5'
ctrl-alt-6 = 'workspace 6'
ctrl-alt-7 = 'workspace 7'
ctrl-alt-8 = 'workspace 8'
ctrl-alt-9 = 'workspace 9'

ctrl-alt-shift-1 = 'move-node-to-workspace 1'
ctrl-alt-shift-2 = 'move-node-to-workspace 2'
ctrl-alt-shift-3 = 'move-node-to-workspace 3'
ctrl-alt-shift-4 = 'move-node-to-workspace 4'
ctrl-alt-shift-5 = 'move-node-to-workspace 5'
ctrl-alt-shift-6 = 'move-node-to-workspace 6'
ctrl-alt-shift-7 = 'move-node-to-workspace 7'
ctrl-alt-shift-8 = 'move-node-to-workspace 8'
ctrl-alt-shift-9 = 'move-node-to-workspace 9'

ctrl-alt-tab = 'workspace-back-and-forth'
ctrl-alt-shift-tab = 'move-workspace-to-monitor --wrap-around next'
ctrl-alt-shift-semicolon = 'mode service'
{{- if $arabic }}

# Arabic dictation (devboost voxtype-arabic): press to start, press again to stop.
# macOS Voxtype ignores `model_modifier`, so the secondary model gets its own key.
ctrl-alt-d = 'exec-and-forget /opt/homebrew/bin/voxtype record toggle --model large-v3-turbo'
{{- end }}

[mode.service.binding]
esc = ['reload-config', 'mode main']
r = ['flatten-workspace-tree', 'mode main']
f = ['layout floating tiling', 'mode main']
backspace = ['close-all-windows-but-current', 'mode main']
ctrl-alt-shift-h = ['join-with left', 'mode main']
ctrl-alt-shift-j = ['join-with down', 'mode main']
ctrl-alt-shift-k = ['join-with up', 'mode main']
ctrl-alt-shift-l = ['join-with right', 'mode main']
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/dotfiles/test_aerospace_config.py tests/dotfiles -v`
Expected: PASS (it skips only where chezmoi is absent; Task 0 of M2 installed it on this Mac). The M2 `.chezmoiignore` tests still pass.

- [ ] **Step 5: On-Mac validation** (it runs once AeroSpace is installed; Task 18 Step 3 installs it)

```bash
chezmoi execute-template --override-data "{\"chezmoi\":{\"os\":\"darwin\",\"homeDir\":\"$HOME\"}}" \
  < ../dotfiles/dot_config/aerospace/aerospace.toml.tmpl > /tmp/aerospace.toml
command -v aerospace && aerospace reload-config --dry-run --no-gui
```
Expected: `--dry-run` exits 0 with no errors against the applied config. An unknown key, e.g. on an older AeroSpace, is a `--dry-run` error. Remove that key and re-run the tests.

- [ ] **Step 6: Commit**

```bash
git add ../dotfiles/dot_config/aerospace/aerospace.toml.tmpl tests/dotfiles/render.py tests/dotfiles/test_aerospace_config.py
git commit -m "feat(dotfiles): AeroSpace config on a Ctrl+Alt layer"
```

---

### Task 8: `default-apps` (code files open in Zed)

**Files:**
- Modify: `engine/src/devboost/modules/macos_system.py` (add `DefaultApps`), `profiles.toml` (`macos-desktop` line)
- Create **only if Task 0 found no A2/A3**: `engine/src/devboost/exec/primitives/duti.py` and a `Duti` module
- Test: `engine/tests/modules/test_default_apps.py` (create); `engine/tests/primitives/test_duti.py` (create only with the primitive)

**Interfaces:**
- Consumes: `duti.set_default(ctx, bundle_id, ext)`, `duti.handler(ctx, ext) -> str | None` (A3); `Duti` (A2); `Zed` (A4).
- Produces: `ZED_BUNDLE = "dev.zed.Zed"`, `CODE_EXTENSIONS: tuple[str, ...]`, and the registered module `default-apps` (`DefaultApps`, `families = ("macos",)`, `portable = True`, `requires = (Duti, Zed)`).

- [ ] **Step 1: Write the failing tests** — `tests/modules/test_default_apps.py`

```python
from __future__ import annotations

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.modules import macos_system as ms
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
ZED = Result(0, "Zed\n/Applications/Zed.app\ndev.zed.Zed\n")
TEXTEDIT = Result(0, "TextEdit\n/System/Applications/TextEdit.app\ncom.apple.TextEdit\n")


def test_extension_list_covers_code_and_leaves_the_browser_alone() -> None:
    assert {"md", "json", "yaml", "toml", "py", "php", "ts", "tsx", "cs", "sh"} <= set(
        ms.CODE_EXTENSIONS
    )
    assert not {"html", "htm", "svg", "pdf"} & set(ms.CODE_EXTENSIONS)
    assert len(set(ms.CODE_EXTENSIONS)) == len(ms.CODE_EXTENSIONS)


def test_verify_reads_every_extension() -> None:
    ex = RuleExecutor(rules=[(("duti", "-x"), ZED)])
    assert ms.DefaultApps().verify(Ctx(os=MAC, ex=ex)) is True
    assert len([c for c in ex.calls if c[:2] == ["duti", "-x"]]) == len(ms.CODE_EXTENSIONS)
    other = RuleExecutor(rules=[(("duti", "-x", "md"), TEXTEDIT), (("duti", "-x"), ZED)])
    assert ms.DefaultApps().verify(Ctx(os=MAC, ex=other)) is False


def test_install_sets_only_what_differs() -> None:
    ex = RuleExecutor(rules=[(("duti", "-x", "md"), TEXTEDIT), (("duti", "-x"), ZED)])
    ms.DefaultApps().install(Ctx(os=MAC, ex=ex))
    sets = [c for c in ex.calls if c[:2] == ["duti", "-s"]]
    assert sets == [["duti", "-s", "dev.zed.Zed", ".md", "all"]]


def test_requires_duti_and_zed() -> None:
    assert {c.name for c in ms.DefaultApps.requires} == {"duti", "zed"}
    assert ms.DefaultApps.families == ("macos",)
```

If you create the primitive (A3 absent), also add `tests/primitives/test_duti.py`:

```python
from __future__ import annotations

import pytest

from devboost.core.errors import InstallError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import duti
from devboost.model import Ctx

MAC = OsInfo("macos", "macos", "aarch64")


def test_handler_is_the_third_line() -> None:
    ex = FakeExecutor(scripts={"duti": Result(0, "Zed\n/Applications/Zed.app\ndev.zed.Zed\n")})
    assert duti.handler(Ctx(os=MAC, ex=ex), "md") == "dev.zed.Zed"
    assert ex.calls == [["duti", "-x", "md"]]


def test_handler_none_when_unknown() -> None:
    ex = FakeExecutor(scripts={"duti": Result(1)})
    assert duti.handler(Ctx(os=MAC, ex=ex), "zzz") is None


def test_set_default_argv_and_failure() -> None:
    ex = FakeExecutor()
    duti.set_default(Ctx(os=MAC, ex=ex), "dev.zed.Zed", "md")
    assert ex.calls == [["duti", "-s", "dev.zed.Zed", ".md", "all"]]
    with pytest.raises(InstallError):
        duti.set_default(Ctx(os=MAC, ex=FakeExecutor(scripts={"duti": Result(1)})),
                         "dev.zed.Zed", "md")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_default_apps.py -v`
Expected: FAIL (`AttributeError: module 'devboost.modules.macos_system' has no attribute 'CODE_EXTENSIONS'`).

- [ ] **Step 3: Implement**

**Only if A3 is absent**, create `src/devboost/exec/primitives/duti.py`:

```python
"""duti — read and set macOS default apps (LaunchServices) by file extension."""

from __future__ import annotations

from devboost.core.errors import InstallError
from devboost.model import Ctx


def set_default(ctx: Ctx, bundle_id: str, ext: str) -> None:
    argv = ["duti", "-s", bundle_id, f".{ext}", "all"]
    res = ctx.ex.run(argv)
    if not res.ok:
        raise InstallError("duti", " ".join(argv), res.code)


def handler(ctx: Ctx, ext: str) -> str | None:
    """Bundle id of the app that opens `.ext` (3rd line of `duti -x`), or None."""
    res = ctx.ex.run(["duti", "-x", ext])
    lines = res.stdout.strip().splitlines() if res.ok else []
    return lines[2].strip() if len(lines) >= 3 else None
```

**Only if A2 is absent**, add this to `macos_system.py`. Then use it in `requires`, and add `"duti"` to `macos-desktop` before `default-apps`:

```python
@register
class Duti(PackageModule):
    name = "duti"
    category = "macos-desktop"
    description = "duti — set macOS default apps by extension/UTI."
    cmd = "duti"
    fedora_pkg = "duti"
    families = ("macos",)
```
(`from devboost.modules._pkgmodule import PackageModule`.)

Append to `src/devboost/modules/macos_system.py` (imports at the top of the file):

```python
from devboost.exec.primitives import duti
from devboost.modules.cli_tools import Duti  # A2 — use the path Task 0 found
from devboost.modules.editors import Zed

# --- default-apps -------------------------------------------------------------------------

ZED_BUNDLE = "dev.zed.Zed"
#: Code/text extensions that open in Zed. Browser-owned (html, svg) and document types
#: stay with their apps; types macOS reserves are dropped after the on-Mac check (D13).
CODE_EXTENSIONS: tuple[str, ...] = (
    "txt", "md", "markdown", "json", "jsonc", "yaml", "yml", "toml", "ini", "cfg", "conf",
    "env", "log", "sh", "bash", "zsh", "fish", "py", "rb", "php", "js", "mjs", "cjs", "jsx",
    "ts", "tsx", "css", "scss", "vue", "svelte", "cs", "csproj", "fs", "go", "rs", "java",
    "kt", "swift", "c", "h", "cpp", "hpp", "lua", "sql", "xml", "diff", "patch", "tf", "hcl",
    "dockerfile", "gitignore", "editorconfig",
)


@register
class DefaultApps(Module):
    name = "default-apps"
    category = "macos-desktop"
    description = "Open code and text files in Zed (duti)."
    profiles = ("macos-desktop",)
    families = ("macos",)
    portable = True
    requires = (Duti, Zed)

    def verify(self, ctx: Ctx) -> bool:
        return all(duti.handler(ctx, ext) == ZED_BUNDLE for ext in CODE_EXTENSIONS)

    def install(self, ctx: Ctx) -> None:
        for ext in CODE_EXTENSIONS:
            if duti.handler(ctx, ext) != ZED_BUNDLE:
                duti.set_default(ctx, ZED_BUNDLE, ext)
```

`profiles.toml`: append `"default-apps"` to the end of the `macos-desktop` list.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/modules/test_default_apps.py tests/primitives tests/core -q && uv run mypy && uv run ruff check`
Expected: PASS, clean.

- [ ] **Step 5: §0 / D13 on-Mac check** (it runs once `duti` and Zed are installed. Task 18 Step 3 installs them; do this step then and amend this task's commit only if the list changes.)

```bash
brew info duti | head -3                  # expect 1.5.4; built from source on 27 if no bottle
for e in md json ts tsx py; do duti -x "$e" | tail -1; done   # read-only: current handlers
duti -s dev.zed.Zed .md all && duti -x md | tail -1           # the module's own write; expect dev.zed.Zed
duti -s dev.zed.Zed .ts all; duti -x ts | tail -1             # macOS may map .ts to MPEG-TS
```
If `duti -s` has no effect on macOS 27 (the handler stays the same), switch the Z2 primitive to `infat` (`brew install infat`; `infat set Zed --ext md`), keeping the same function signatures, and record it in D13. Drop from `CODE_EXTENSIONS` any extension that `duti` cannot set, and note it in D13.

- [ ] **Step 6: Commit**

```bash
git add src/devboost/modules/macos_system.py tests/modules/test_default_apps.py ../profiles.toml
# plus, only if created here: src/devboost/exec/primitives/duti.py tests/primitives/test_duti.py
git commit -m "feat(macos): default-apps opens code files in Zed"
```

---

### Task 9: Catalog pins — `[xcode]` and `[voxtype]`

**Files:**
- Modify: `catalog.toml`, `engine/src/devboost/media/catalog.py`
- Test: `engine/tests/media/test_catalog_m5_pins.py` (create)

**Interfaces:**
- Produces (in `devboost.media.catalog`):
  - `@dataclass(frozen=True) class XcodeSpec: version: str; ios_runtime: str; min_macos: tuple[int, int]`, returned by `xcode_pin() -> XcodeSpec` (cached).
  - `@dataclass(frozen=True) class ReleaseAsset: url: str; sha256: str`.
  - `@dataclass(frozen=True) class VoxtypeSpec: version: str; assets: dict[str, ReleaseAsset]`, returned by `voxtype_pin() -> VoxtypeSpec` (cached). Asset keys: `rpm-x86_64`, `deb-x86_64`, `bin-aarch64`.
  - Both raise `MediaError` when their section is missing or invalid (same contract as `herdr_pin`).
  - `_NON_OS_SECTIONS` also contains `"xcode"` and `"voxtype"`.

- [ ] **Step 1: Write the failing tests** — `tests/media/test_catalog_m5_pins.py`

```python
from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from devboost.core.settings import settings
from devboost.media import catalog


def test_xcode_pin_is_the_newest_ga() -> None:
    pin = catalog.xcode_pin()
    assert pin.version == "27.0"
    assert pin.ios_runtime == "27.0"
    assert pin.min_macos == (26, 6)


def test_voxtype_pin_assets_are_hashed_release_urls() -> None:
    pin = catalog.voxtype_pin()
    assert pin.version == "1.0.1"
    assert set(pin.assets) == {"rpm-x86_64", "deb-x86_64", "bin-aarch64"}
    for asset in pin.assets.values():
        assert re.fullmatch(r"[0-9a-f]{64}", asset.sha256)
        assert asset.url.startswith(
            "https://github.com/peteonrails/voxtype/releases/download/v1.0.1/"
        )


def test_os_catalog_still_loads_with_the_new_sections() -> None:
    assert catalog.load_catalog(settings.catalog_path)  # sections are stripped, not parsed


def test_bad_xcode_version_is_rejected() -> None:
    with pytest.raises(ValidationError):
        catalog._XcodeRow.model_validate(
            {"version": "latest", "ios_runtime": "27.0", "min_macos": "26.6"}
        )
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/media/test_catalog_m5_pins.py -v`
Expected: FAIL (`AttributeError: module 'devboost.media.catalog' has no attribute 'xcode_pin'`).

- [ ] **Step 3: Implement**

Append to `catalog.toml`:

```toml
[xcode]
# Opt-in `ios` profile (xcodes). Newest GA at M5: Xcode 27 (27A266a, 2026-09-14), which
# requires macOS 26.6+ — the xcode/ios-tooling modules are gated on min_macos.
version = "27.0"
ios_runtime = "27.0"
min_macos = "26.6"

[voxtype]
# Voxtype (MIT) on Linux — upstream packages from docs/INSTALL.md. sha256 = the GitHub
# release-asset digests (gh api repos/peteonrails/voxtype/releases/tags/v1.0.1).
# macOS uses the peteonrails/voxtype Homebrew tap instead (brew verifies the cask).
version = "1.0.1"

[voxtype.assets.rpm-x86_64]
url = "https://github.com/peteonrails/voxtype/releases/download/v1.0.1/voxtype-1.0.1-1.x86_64.rpm"
sha256 = "be103de733f376030180ac734bb845779bf6ee963419a8e72518b5df150525bf"

[voxtype.assets.deb-x86_64]
url = "https://github.com/peteonrails/voxtype/releases/download/v1.0.1/voxtype_1.0.1-1_amd64.deb"
sha256 = "2308e762f9fd2986a2052c931388b13e7e1c74f067b6be25cacbe710546c4a0e"

[voxtype.assets.bin-aarch64]
url = "https://github.com/peteonrails/voxtype/releases/download/v1.0.1/voxtype-1.0.1-linux-aarch64-cpu"
sha256 = "b5e31a85aaa952d1a78c12b8a16ba5cbdcd92eb31adc7d1a908f3c9d06edd4f1"
```

In `src/devboost/media/catalog.py`:

1. Add `"xcode"` and `"voxtype"` to `_NON_OS_SECTIONS`. Keep any sections M3 added, e.g. `frozenset({"ventoy", "herdr", …, "xcode", "voxtype"})`.
2. Add these next to the herdr types and loader:

```python
@dataclass(frozen=True)
class XcodeSpec:
    """Pinned Xcode + iOS simulator runtime (the ``[xcode]`` block)."""

    version: str
    ios_runtime: str
    min_macos: tuple[int, int]


@dataclass(frozen=True)
class ReleaseAsset:
    url: str
    sha256: str


@dataclass(frozen=True)
class VoxtypeSpec:
    """Pinned Voxtype Linux release (the ``[voxtype]`` block)."""

    version: str
    assets: dict[str, ReleaseAsset]  # "rpm-x86_64" | "deb-x86_64" | "bin-aarch64"


_VERSION = r"^\d+\.\d+(\.\d+)?$"


class _XcodeRow(BaseModel):
    version: str = Field(pattern=_VERSION)
    ios_runtime: str = Field(pattern=_VERSION)
    min_macos: str = Field(pattern=r"^\d+\.\d+$")


class _VoxtypeRow(BaseModel):
    version: str = Field(pattern=_VERSION)
    assets: dict[str, _HerdrAssetRow] = Field(min_length=1)  # url + 64-hex sha256


def _section(name: str) -> object:
    path = settings.catalog_path
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))[name]
    except (OSError, KeyError, ValueError) as exc:
        raise MediaError(f"[{name}] pin missing or invalid in {path}: {exc}") from exc


@cache
def xcode_pin() -> XcodeSpec:
    """The pinned Xcode (cached). Read from the ``[xcode]`` block in catalog.toml."""
    try:
        row = _XcodeRow.model_validate(_section("xcode"))
    except ValueError as exc:
        raise MediaError(f"[xcode] pin invalid: {exc}") from exc
    major, minor = (int(p) for p in row.min_macos.split("."))
    return XcodeSpec(version=row.version, ios_runtime=row.ios_runtime,
                     min_macos=(major, minor))


@cache
def voxtype_pin() -> VoxtypeSpec:
    """The pinned Voxtype Linux release (cached). Read from ``[voxtype]`` in catalog.toml."""
    try:
        row = _VoxtypeRow.model_validate(_section("voxtype"))
    except ValueError as exc:
        raise MediaError(f"[voxtype] pin invalid: {exc}") from exc
    return VoxtypeSpec(
        version=row.version,
        assets={k: ReleaseAsset(url=a.url, sha256=a.sha256) for k, a in row.assets.items()},
    )
```

(`pydantic.ValidationError` subclasses `ValueError`, so the `except ValueError` catches it.)

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/media -q && uv run mypy && uv run ruff check`
Expected: PASS, clean.

- [ ] **Step 5: Re-check the pins against upstream (read-only)**

```bash
gh api repos/peteonrails/voxtype/releases/latest --jq .tag_name     # still v1.0.1? if newer and stable, bump version, URLs and digests together
gh api repos/peteonrails/voxtype/releases/tags/v1.0.1 --jq '.assets[] | select(.name|test("x86_64.rpm$|amd64.deb$|aarch64-cpu$")) | [.name,.digest] | @tsv'
xcodes list 2>/dev/null | tail -3 || echo "xcodes not installed yet (Task 12 installs it)"
```
The digests must equal the `sha256` values above. Xcode stays `27.0` unless a newer **GA** (not beta/RC) exists at execution time. Bump `version` and `ios_runtime` together, and update D19.

- [ ] **Step 6: Commit**

```bash
git add ../catalog.toml src/devboost/media/catalog.py tests/media/test_catalog_m5_pins.py
git commit -m "feat(catalog): pin Xcode 27 and Voxtype 1.0.1 Linux packages"
```

---

### Task 10: `voxtype` module (every OS) + shared config template

**Files:**
- Create: `engine/src/devboost/modules/voxtype.py`, `dotfiles/dot_config/voxtype/config.toml.tmpl`
- Modify: `profiles.toml` (`base` += `"voxtype"`)
- Test: `engine/tests/modules/test_voxtype.py`, `engine/tests/dotfiles/test_voxtype_config.py` (create)

**Interfaces:**
- Consumes: `voxtype_pin()` (Task 9); `pkg.install`, `pkg.install_cask`, `pkg.cask_installed`, `pkg.install_aur` (M1); `Homebrew` (A1); `Dotfiles`; `render_template` (Task 7).
- Produces (module `devboost.modules.voxtype`):
  - Constants: `CASK = "peteonrails/voxtype/voxtype"`, `MODEL = "small.en"`, `ARABIC_MODEL = "large-v3-turbo"`, `BUNDLE_ID = "io.voxtype.daemon"`, `APP_BUNDLE: Path` (`/Applications/Voxtype.app`; a module attribute so tests can redirect it).
  - `models_dir() -> Path` (`$XDG_DATA_HOME/voxtype/models`), `model_file(name) -> Path` (`ggml-<name>.bin`), `download_model(ctx, name) -> None` (skipped when the file exists).
  - Strategies `MacosVoxtype()` and `LinuxVoxtype(kind: Literal["rpm", "deb", "aur"])`.
  - Registered module `voxtype` (`Voxtype`): `profiles = ("base",)`, `provided_by = ("omarchy",)`, `gui = True`, `requires = (Homebrew,)`, `after = (Dotfiles,)`, `tcc` = Microphone + Input Monitoring + Accessibility for "Voxtype".
  - Config: `~/.config/voxtype/config.toml` on every OS. It has `engine = "whisper"`, `[whisper] model = "small.en"`, `language = "en"`, and a marked hotkey placeholder (D16).

- [ ] **Step 1: Write the failing tests**

`tests/modules/test_voxtype.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules import voxtype as vox
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
FEDORA_ARM = OsInfo("fedora", "fedora", "aarch64")
UBUNTU = OsInfo("ubuntu", "debian", "x86_64")
ARCH = OsInfo("arch", "arch", "x86_64")
OMARCHY = OsInfo("omarchy", "arch", "x86_64", id_like=("arch",))


@pytest.fixture(autouse=True)
def _user(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("USER", "dev")
    monkeypatch.setattr(vox, "APP_BUNDLE", tmp_path / "Applications" / "Voxtype.app")


def _scripts(ex: FakeExecutor) -> list[str]:
    return [c[2] for c in ex.calls if c[:2] == ["sh", "-c"]]


def test_model_paths_follow_xdg_data_home(tmp_path: Path) -> None:
    assert vox.model_file("small.en") == (
        tmp_path / ".local" / "share" / "voxtype" / "models" / "ggml-small.en.bin"
    )


def test_macos_install_cask_model_then_app_bundle() -> None:
    ex = FakeExecutor()
    vox.Voxtype().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [
        ["brew", "install", "--cask", "-y", "--adopt", "peteonrails/voxtype/voxtype"],
        ["voxtype", "setup", "--download", "--model", "small.en", "--quiet"],
        ["voxtype", "setup", "app-bundle"],
    ]


def test_model_download_is_skipped_when_present() -> None:
    vox.model_file("small.en").parent.mkdir(parents=True)
    vox.model_file("small.en").touch()
    ex = FakeExecutor()
    vox.download_model(Ctx(os=MAC, ex=ex), "small.en")
    assert ex.calls == []


def test_macos_verify_needs_cask_model_and_bundle() -> None:
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    assert vox.Voxtype().verify(ctx) is False
    vox.model_file("small.en").parent.mkdir(parents=True)
    vox.model_file("small.en").touch()
    vox.APP_BUNDLE.mkdir(parents=True)
    assert vox.Voxtype().verify(ctx) is True


def test_fedora_installs_the_pinned_rpm_deps_group_model_and_service() -> None:
    ex = FakeExecutor()
    vox.Voxtype().install(Ctx(os=FEDORA, ex=ex))
    script = _scripts(ex)[0]
    assert "voxtype-1.0.1-1.x86_64.rpm" in script
    assert "be103de733f376030180ac734bb845779bf6ee963419a8e72518b5df150525bf" in script
    assert "sha256sum -c -" in script
    assert 'sudo dnf install -y "$tmp/voxtype.rpm"' in script
    assert ["sudo", "dnf", "install", "-y", "wtype", "wl-clipboard", "libnotify",
            "pipewire-alsa"] in ex.calls
    assert ["sudo", "usermod", "-aG", "input", "dev"] in ex.calls
    assert ex.calls[-2:] == [
        ["voxtype", "setup", "--download", "--model", "small.en", "--quiet"],
        ["voxtype", "setup", "systemd"],
    ]


def test_ubuntu_installs_the_pinned_deb() -> None:
    ex = FakeExecutor()
    vox.Voxtype().install(Ctx(os=UBUNTU, ex=ex))
    script = _scripts(ex)[0]
    assert "voxtype_1.0.1-1_amd64.deb" in script
    assert 'sudo apt-get install -y "$tmp/voxtype.deb"' in script
    assert any("libnotify-bin" in c for c in ex.calls)


def test_linux_aarch64_installs_the_raw_binary(tmp_path: Path) -> None:
    ex = FakeExecutor()
    vox.Voxtype().install(Ctx(os=FEDORA_ARM, ex=ex))
    script = _scripts(ex)[0]
    assert "voxtype-1.0.1-linux-aarch64-cpu" in script
    assert f'install -Dm755 "$tmp/voxtype" "{tmp_path}/.local/bin/voxtype"' in script
    assert "dnf install -y \"$tmp" not in script


def test_arch_uses_the_aur_package() -> None:
    ex = FakeExecutor(present={"yay"})
    vox.Voxtype().install(Ctx(os=ARCH, ex=ex))
    assert ["yay", "-S", "--needed", "--noconfirm", "voxtype-bin"] in ex.calls


def test_linux_verify_needs_binary_model_and_enabled_service() -> None:
    vox.model_file("small.en").parent.mkdir(parents=True)
    vox.model_file("small.en").touch()
    ok = RuleExecutor(present={"voxtype"})
    assert vox.Voxtype().verify(Ctx(os=FEDORA, ex=ok)) is True
    off = RuleExecutor(present={"voxtype"}, rules=[(("is-enabled",), Result(1))])
    assert vox.Voxtype().verify(Ctx(os=FEDORA, ex=off)) is False


def test_omarchy_provides_it_and_headless_skips_it(tmp_path: Path) -> None:
    mods = load()
    assert build_plan(["voxtype"], mods, OMARCHY, gpu_marker=tmp_path / "x")[-1].skip_reason \
        == "provided-by-omarchy"
    headless = OsInfo("fedora", "fedora", "x86_64", headless=True)
    assert build_plan(["voxtype"], mods, headless, gpu_marker=tmp_path / "x")[-1].skip_reason \
        == "headless"


def test_permissions_and_profile() -> None:
    assert {g.service for g in vox.Voxtype.tcc} == {"Microphone", "ListenEvent", "Accessibility"}
    assert {g.app for g in vox.Voxtype.tcc} == {"Voxtype"}
    assert vox.Voxtype.profiles == ("base",)
```

`tests/dotfiles/test_voxtype_config.py`:

```python
from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest

from tests.dotfiles.render import CHEZMOI, render_template

pytestmark = pytest.mark.skipif(CHEZMOI is None, reason="chezmoi not installed")
REL = "dot_config/voxtype/config.toml.tmpl"


def _cfg(os_name: str, home: Path) -> tuple[str, dict[str, Any]]:
    raw = render_template(REL, os_name, home)
    return raw, tomllib.loads(raw)


@pytest.mark.parametrize(("os_name", "key"), [("darwin", "RIGHTALT"), ("linux", "SCROLLLOCK")])
def test_english_default_everywhere(os_name: str, key: str, tmp_path: Path) -> None:
    raw, cfg = _cfg(os_name, tmp_path)
    assert "devboost — managed by chezmoi" in raw
    assert "PLACEHOLDER" in raw  # the author's Omarchy hotkey goes here (D16)
    assert cfg["engine"] == "whisper"
    assert cfg["hotkey"] == {"key": key, "mode": "push_to_talk"}
    assert cfg["whisper"] == {"model": "small.en", "language": "en"}


def _arabic(home: Path) -> None:
    marker = home / ".config" / "devboost" / "voxtype-arabic"
    marker.parent.mkdir(parents=True)
    marker.touch()


def test_arabic_adds_an_on_demand_secondary_model(tmp_path: Path) -> None:
    _arabic(tmp_path)
    _, cfg = _cfg("linux", tmp_path)
    assert cfg["whisper"] == {
        "model": "small.en",
        "language": ["en", "ar"],
        "secondary_model": "large-v3-turbo",
        "cold_model_timeout_secs": 60,
    }
    assert "on_demand_loading" not in cfg["whisper"]  # would unload the primary too (D17)
    assert cfg["hotkey"]["model_modifier"] == "LEFTSHIFT"


def test_macos_arabic_has_no_model_modifier(tmp_path: Path) -> None:
    _arabic(tmp_path)
    _, cfg = _cfg("darwin", tmp_path)
    assert cfg["whisper"]["secondary_model"] == "large-v3-turbo"
    assert "model_modifier" not in cfg["hotkey"]  # ignored on macOS; AeroSpace binds it
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_voxtype.py tests/dotfiles/test_voxtype_config.py -v`
Expected: FAIL (`ImportError` for `devboost.modules.voxtype`; template missing).

- [ ] **Step 3: Implement**

`dotfiles/dot_config/voxtype/config.toml.tmpl`:

```toml
{{- /* devboost — managed by chezmoi. One Voxtype config for every OS (spec §2). */ -}}
{{- $arabic := stat (joinPath .chezmoi.homeDir ".config/devboost/voxtype-arabic") -}}
# devboost — managed by chezmoi (dotfiles/dot_config/voxtype/config.toml.tmpl)
# Voxtype push-to-talk dictation — https://github.com/peteonrails/voxtype (docs/CONFIGURATION.md)
# Edit the template in the dev-boost repo, then run: devboost install dotfiles

engine = "whisper"

[hotkey]
# ── PLACEHOLDER: hotkey ───────────────────────────────────────────────────────────
# Replace `key` and `mode` below with the values from the author's Omarchy
# ~/.config/voxtype/config.toml. Linux takes evdev names (SCROLLLOCK, PAUSE, F13, …);
# macOS takes RIGHTALT, FN, F13 … (macOS ignores `modifiers`). Until then these defaults
# work: hold the key, speak, release.
{{- if eq .chezmoi.os "darwin" }}
key = "RIGHTALT"
{{- else }}
key = "SCROLLLOCK"
{{- end }}
mode = "push_to_talk"
# ── END PLACEHOLDER ───────────────────────────────────────────────────────────────
{{- if and $arabic (ne .chezmoi.os "darwin") }}
# voxtype-arabic: hold Left Shift with the hotkey to dictate with the Arabic model.
model_modifier = "LEFTSHIFT"
{{- end }}

[whisper]
model = "small.en"
{{- if $arabic }}
# voxtype-arabic: large-v3-turbo loads only when asked for (macOS: Ctrl+Alt+D, bound in
# the AeroSpace config) and is evicted after 60 s idle — no RAM between Arabic dictations.
language = ["en", "ar"]
secondary_model = "large-v3-turbo"
cold_model_timeout_secs = 60
{{- else }}
language = "en"
{{- end }}
```

`src/devboost/modules/voxtype.py`:

```python
"""voxtype — local push-to-talk dictation (MIT), on every OS (spec §2).

macOS: the peteonrails tap cask, then upstream's `voxtype setup app-bundle`, which wraps
the daemon in /Applications/Voxtype.app with a Login Item. Upstream warns that a plain
launchd service never receives Microphone access (D14). Linux: the upstream RPM/DEB
(pinned + hashed in catalog.toml), or the AUR on Arch, or the raw binary on aarch64, plus
a systemd user service. Omarchy ships it through its own menu (provided_by).
"""

from __future__ import annotations

import getpass
import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from devboost.core import log
from devboost.core.errors import InstallError
from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.media.catalog import voxtype_pin
from devboost.model import Ctx, Module, TccGrant
from devboost.modules.homebrew import Homebrew  # A1
from devboost.modules.shell import Dotfiles

CASK = "peteonrails/voxtype/voxtype"
MODEL = "small.en"
ARABIC_MODEL = "large-v3-turbo"
BUNDLE_ID = "io.voxtype.daemon"
#: Created by `voxtype setup app-bundle`. Module attribute so tests can redirect it.
APP_BUNDLE = Path("/Applications/Voxtype.app")

#: Runtime deps per upstream docs/INSTALL.md: typing (wtype), clipboard, notifications,
#: and the ALSA→PipeWire bridge the audio capture uses.
_LINUX_DEPS: dict[str, tuple[str, ...]] = {
    "fedora": ("wtype", "wl-clipboard", "libnotify", "pipewire-alsa"),
    "debian": ("wtype", "wl-clipboard", "libnotify-bin", "pipewire-alsa"),
    "arch": ("wtype", "wl-clipboard", "libnotify", "pipewire-alsa"),
}


def _home() -> Path:
    return Path(os.environ["HOME"])


def models_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(_home() / ".local" / "share")
    return Path(base) / "voxtype" / "models"


def model_file(name: str) -> Path:
    return models_dir() / f"ggml-{name}.bin"


def download_model(ctx: Ctx, name: str) -> None:
    if model_file(name).exists():
        return
    res = ctx.ex.run(["voxtype", "setup", "--download", "--model", name, "--quiet"])
    if not res.ok:
        raise InstallError("voxtype", f"voxtype setup --download --model {name}", res.code)


@dataclass(frozen=True)
class MacosVoxtype:
    def verify(self, ctx: Ctx) -> bool:
        return (
            pkg.cask_installed(ctx, "voxtype")
            and model_file(MODEL).exists()
            and APP_BUNDLE.exists()
        )

    def install(self, ctx: Ctx) -> None:
        pkg.install_cask(ctx, CASK)
        download_model(ctx, MODEL)
        res = ctx.ex.run(["voxtype", "setup", "app-bundle"])
        if not res.ok:
            raise InstallError("voxtype", "voxtype setup app-bundle", res.code)


def _fetch_then(url: str, sha256: str, name: str, then: str) -> str:
    """Download → verify SHA-256 (fails the `set -e` script on mismatch) → *then*."""
    return (
        "set -e\n"
        "tmp=$(mktemp -d)\n"
        f'curl -fL --retry 2 -o "$tmp/{name}" {shlex.quote(url)}\n'
        f'echo "{sha256}  $tmp/{name}" | sha256sum -c -\n'
        f"{then}\n"
        'rm -rf "$tmp"\n'
    )


@dataclass(frozen=True)
class LinuxVoxtype:
    kind: Literal["rpm", "deb", "aur"]

    def verify(self, ctx: Ctx) -> bool:
        return (
            ctx.ex.which("voxtype")
            and model_file(MODEL).exists()
            and ctx.ex.run(["systemctl", "--user", "is-enabled", "voxtype.service"]).ok
        )

    def _binary(self, ctx: Ctx) -> None:
        pin = voxtype_pin()
        if ctx.os.arch == "aarch64":  # no RPM/DEB/AUR build for arm64 Linux
            key, name = "bin-aarch64", "voxtype"
            then = f'install -Dm755 "$tmp/voxtype" "{_home()}/.local/bin/voxtype"'
        elif self.kind == "aur":
            pkg.install_aur(ctx, "voxtype-bin")
            return
        elif self.kind == "rpm":
            key, name = "rpm-x86_64", "voxtype.rpm"
            then = 'sudo dnf install -y "$tmp/voxtype.rpm"'
        else:
            key, name = "deb-x86_64", "voxtype.deb"
            then = 'sudo apt-get install -y "$tmp/voxtype.deb"'
        asset = pin.assets[key]
        res = ctx.ex.run(["sh", "-c", _fetch_then(asset.url, asset.sha256, name, then)])
        if not res.ok:
            raise InstallError("voxtype", "download or checksum verification failed", res.code)

    def install(self, ctx: Ctx) -> None:
        self._binary(ctx)
        pkg.install(ctx, *_LINUX_DEPS[ctx.os.family])
        user = os.environ.get("USER") or getpass.getuser()
        # evdev hotkeys read /dev/input; membership applies at the next login.
        ctx.ex.run(["usermod", "-aG", "input", user], sudo=True)
        log.info("voxtype: log out and back in once so the `input` group (hotkey) applies")
        download_model(ctx, MODEL)
        res = ctx.ex.run(["voxtype", "setup", "systemd"])
        if not res.ok:
            raise InstallError("voxtype", "voxtype setup systemd", res.code)


@register
class Voxtype(Module):
    name = "voxtype"
    category = "base"
    description = "Voxtype — local push-to-talk dictation (Whisper small.en; MIT)."
    profiles = ("base",)
    provided_by = ("omarchy",)  # Omarchy: Install › AI › Dictation (voxtype-bin)
    gui = True
    requires = (Homebrew,)  # dropped from Linux plans (families = macos)
    after = (Dotfiles,)  # the daemon should start with ~/.config/voxtype/config.toml in place
    tcc = (
        TccGrant("Microphone", "Voxtype"),
        TccGrant("ListenEvent", "Voxtype"),
        TccGrant("Accessibility", "Voxtype"),
    )
    per_os = OsMap(
        macos=MacosVoxtype(),
        fedora=LinuxVoxtype("rpm"),
        debian=LinuxVoxtype("deb"),
        arch=LinuxVoxtype("aur"),
    )
```

`profiles.toml`: append `"voxtype"` to the end of the `base` list.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/modules/test_voxtype.py tests/dotfiles -v && uv run pytest -q && uv run mypy && uv run ruff check`
Expected: PASS, clean. The full suite matters here: `voxtype` is now in `base`, so any Linux test that pins the exact module list of `full`/`omarchy`/`base` needs `voxtype` added. Keep the test's intent and add only that name.

- [ ] **Step 5: §0 on-Mac check (Voxtype, D14–D17; read-only until the acceptance install)**

```bash
brew info --cask peteonrails/voxtype/voxtype | head -3   # taps; note the version (0.7.5 at plan time)
```
After Task 18 Step 3 has installed it:
```bash
voxtype --version
voxtype setup app-bundle --help >/dev/null && echo app-bundle-ok
voxtype record start --help | grep -- '--model'           # the fallback trigger exists
ls ~/.local/share/voxtype/models/                         # must contain ggml-small.en.bin (model_file naming)
ls -l /Applications/Voxtype.app/Contents/MacOS/           # copy or symlink of the brew binary?
```
Acceptance:
- If the model file name differs, fix `model_file` and its test.
- If `Voxtype.app` holds a **copy** of the binary, `brew upgrade` leaves it stale. In that case, note in `docs/macos.md` that `voxtype setup app-bundle` must be re-run after an upgrade, and have `MacosVoxtype.install` always re-run it under `--update` (`ctx.force`).
- If the tap is still 0.7.5 and any command above is missing, switch the macOS strategy to the pinned upstream binary `voxtype-1.0.1-macos-universal` (sha256 `275df56b1e9463d8c8888d208bcfae4ed2ab4cb5aa0177dbfc6044d4b8d3ae78`, from `SHA256SUMS-macos.txt`), add it as `[voxtype.assets.macos-universal]`, and record that in D14.

- [ ] **Step 6: Commit**

```bash
git add src/devboost/modules/voxtype.py tests/modules/test_voxtype.py ../dotfiles/dot_config/voxtype/config.toml.tmpl tests/dotfiles/test_voxtype_config.py ../profiles.toml
git commit -m "feat(voxtype): push-to-talk dictation on every OS with a shared config"
```

---

### Task 11: `voxtype-arabic` (opt-in)

**Files:**
- Modify: `engine/src/devboost/modules/voxtype.py` (add `VoxtypeArabic`)
- Test: `engine/tests/modules/test_voxtype_arabic.py` (create)

**Interfaces:**
- Consumes: `download_model`, `model_file`, `ARABIC_MODEL`, `BUNDLE_ID`, `Voxtype` (Task 10); `settings.root`; the Task 7 / Task 10 templates read the marker.
- Produces:
  - `arabic_marker() -> Path` (`~/.config/devboost/voxtype-arabic`).
  - Registered module `voxtype-arabic` (`VoxtypeArabic`). It is in no profile, has `requires = (Voxtype,)`, `after = (Dotfiles,)`, `gui = True`, and `portable = True`.
  - `install`:
    1. Raises `NeedsUser` when `voxtype` is not on PATH (e.g. Omarchy without its Dictation install).
    2. Touches the marker and downloads `large-v3-turbo`.
    3. Runs `chezmoi apply --force --source <root>/dotfiles --destination $HOME <targets>` for the voxtype config (plus the AeroSpace config on macOS).
    4. Restarts the daemon: on macOS, `osascript` quit + `open -g -b io.voxtype.daemon` + `aerospace reload-config`; on Linux, `systemctl --user restart voxtype.service`.
  - `verify`: the marker exists, the model file exists, and the rendered config contains `secondary_model = "large-v3-turbo"`.

- [ ] **Step 1: Write the failing tests** — `tests/modules/test_voxtype_arabic.py`

```python
from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.errors import NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.core.settings import settings
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules import voxtype as vox

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")


def test_needs_voxtype_first() -> None:
    ex = FakeExecutor()
    with pytest.raises(NeedsUser):
        vox.VoxtypeArabic().install(Ctx(os=FEDORA, ex=ex))
    assert ex.calls == []
    assert not vox.arabic_marker().exists()


def test_macos_install_marks_downloads_reapplies_and_restarts(tmp_path: Path) -> None:
    ex = FakeExecutor(present={"voxtype", "aerospace"})
    vox.VoxtypeArabic().install(Ctx(os=MAC, ex=ex))
    assert vox.arabic_marker().is_file()
    assert ex.calls == [
        ["voxtype", "setup", "--download", "--model", "large-v3-turbo", "--quiet"],
        ["chezmoi", "apply", "--force", "--source", str(settings.root / "dotfiles"),
         "--destination", str(tmp_path),
         str(tmp_path / ".config" / "voxtype" / "config.toml"),
         str(tmp_path / ".config" / "aerospace" / "aerospace.toml")],
        ["osascript", "-e", 'tell application id "io.voxtype.daemon" to quit'],
        ["open", "-g", "-b", "io.voxtype.daemon"],
        ["aerospace", "reload-config"],
    ]


def test_linux_install_reapplies_only_the_voxtype_config(tmp_path: Path) -> None:
    ex = FakeExecutor(present={"voxtype"})
    vox.VoxtypeArabic().install(Ctx(os=FEDORA, ex=ex))
    apply = next(c for c in ex.calls if c[:2] == ["chezmoi", "apply"])
    assert apply[-1] == str(tmp_path / ".config" / "voxtype" / "config.toml")
    assert not any("aerospace" in part for part in apply)
    assert ex.calls[-1] == ["systemctl", "--user", "restart", "voxtype.service"]


def test_verify_reads_marker_model_and_rendered_config(tmp_path: Path) -> None:
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    assert vox.VoxtypeArabic().verify(ctx) is False
    vox.arabic_marker().parent.mkdir(parents=True)
    vox.arabic_marker().touch()
    vox.model_file("large-v3-turbo").parent.mkdir(parents=True)
    vox.model_file("large-v3-turbo").touch()
    cfg = tmp_path / ".config" / "voxtype" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('[whisper]\nsecondary_model = "large-v3-turbo"\n', encoding="utf-8")
    assert vox.VoxtypeArabic().verify(ctx) is True


def test_opt_in_only() -> None:
    assert vox.VoxtypeArabic.profiles == ()
    assert [c.name for c in vox.VoxtypeArabic.requires] == ["voxtype"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_voxtype_arabic.py -v`
Expected: FAIL (`AttributeError: … has no attribute 'VoxtypeArabic'`).

- [ ] **Step 3: Implement** — append to `src/devboost/modules/voxtype.py` (add `NeedsUser` to the `errors` import and `from devboost.core.settings import settings`):

```python
def arabic_marker() -> Path:
    """Read by the voxtype and AeroSpace templates (`stat`): Arabic dictation is on."""
    return _home() / ".config" / "devboost" / "voxtype-arabic"


def _config_file() -> Path:
    return _home() / ".config" / "voxtype" / "config.toml"


def _restart_daemon(ctx: Ctx) -> None:
    if ctx.os.family == "macos":
        ctx.ex.run(["osascript", "-e", f'tell application id "{BUNDLE_ID}" to quit'])
        ctx.ex.run(["open", "-g", "-b", BUNDLE_ID])
        if ctx.ex.which("aerospace"):
            ctx.ex.run(["aerospace", "reload-config"])
    else:
        ctx.ex.run(["systemctl", "--user", "restart", "voxtype.service"])


@register
class VoxtypeArabic(Module):
    name = "voxtype-arabic"
    category = "base"
    description = "Arabic dictation: Whisper large-v3-turbo (1.6 GB), loaded only on demand."
    requires = (Voxtype,)
    after = (Dotfiles,)
    gui = True
    portable = True

    def verify(self, ctx: Ctx) -> bool:
        cfg = _config_file()
        return (
            arabic_marker().exists()
            and model_file(ARABIC_MODEL).exists()
            and cfg.is_file()
            and f'secondary_model = "{ARABIC_MODEL}"' in cfg.read_text(encoding="utf-8")
        )

    def install(self, ctx: Ctx) -> None:
        if not ctx.ex.which("voxtype"):
            raise NeedsUser(
                "Voxtype is not installed",
                "install it first — `devboost install voxtype` (Omarchy: menu → Install → "
                "AI → Dictation)",
            )
        marker = arabic_marker()
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        download_model(ctx, ARABIC_MODEL)
        targets = [str(_config_file())]
        if ctx.os.family == "macos":
            targets.append(str(_home() / ".config" / "aerospace" / "aerospace.toml"))
        res = ctx.ex.run([
            "chezmoi", "apply", "--force", "--source", str(settings.root / "dotfiles"),
            "--destination", str(_home()), *targets,
        ])
        if not res.ok:
            raise InstallError("voxtype-arabic", "chezmoi apply (voxtype/aerospace config)",
                               res.code)
        _restart_daemon(ctx)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/modules/test_voxtype_arabic.py tests/modules/test_voxtype.py tests/core -q && uv run mypy && uv run ruff check`
Expected: PASS, clean (`portable = True` keeps the contract test green).

- [ ] **Step 5: D17 on-Mac check** (it runs after Task 18 installs `voxtype-arabic`)

```bash
pgrep -fl voxtype; ps -o rss= -p "$(pgrep -f 'Voxtype.app' | head -1)"   # idle RSS ≈ small.en only
# Press Ctrl+Alt+D, say a short Arabic sentence, press Ctrl+Alt+D again → Arabic text is typed.
ps -o rss= -p "$(pgrep -f 'Voxtype.app' | head -1)"   # higher while large-v3-turbo is resident
sleep 70; ps -o rss= -p "$(pgrep -f 'Voxtype.app' | head -1)"   # back down: evicted after 60 s
# Push-to-talk English still works and stays English with language = ["en","ar"] on small.en.
```
If English dictation starts coming out as Arabic, or the `.en` model complains about the language array, change the Arabic branch of the template to keep `language = "en"`. Then check whether `record … --model large-v3-turbo` still auto-detects Arabic. If it does not, add a Voxtype profile (`[hotkey.profile_modifiers]`) whose language is `ar`, and record the outcome in D17.

- [ ] **Step 6: Commit**

```bash
git add src/devboost/modules/voxtype.py tests/modules/test_voxtype_arabic.py
git commit -m "feat(voxtype): opt-in Arabic dictation with an on-demand secondary model"
```

---

### Task 12: `ios` — `xcode` + `ios-tooling`

**Files:**
- Create: `engine/src/devboost/modules/ios.py`
- Modify: `profiles.toml` (new `ios` line), `engine/tests/conftest.py` (`profiles_file`: one line)
- Test: `engine/tests/modules/test_ios.py` (create)

**Interfaces:**
- Consumes: `xcode_pin()` (Task 9); `macos_version` (Task 1); `pkg.install`, `pkg.installed` (M1); `Homebrew`, `Xcodes` (A1/A2).
- Produces:
  - Registered `xcode` (`Xcode`) and `ios-tooling` (`IosTooling`). Both have `families = ("macos",)`, `profiles = ("ios",)`, and `supported_on` = macOS ≥ `xcode_pin().min_macos`. `IosTooling.requires = (Xcode,)`.
  - `_interactive() -> bool` (a module function, so tests can patch it).
  - xcodes always runs with `interactive=True`. With neither the `XCODES_USERNAME` / `XCODES_PASSWORD` env vars nor a tty, the module raises `NeedsUser`.

- [ ] **Step 1: Write the failing tests** — `tests/modules/test_ios.py`

```python
from __future__ import annotations

import pytest

from devboost.core.errors import NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.modules import ios
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
INSTALLED = (
    "26.4 (17E192)\t/Applications/Xcode-26.4.0.app\n"
    "27.0 (27A266a) (Selected)\t/Applications/Xcode-27.0.0.app\n"
)
RUNTIMES = (
    "== Runtimes ==\n"
    "iOS 27.0 (27.0 - 23A5287e) - com.apple.CoreSimulator.SimRuntime.iOS-27-0\n"
)


@pytest.fixture
def creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XCODES_USERNAME", "dev@example.com")
    monkeypatch.setenv("XCODES_PASSWORD", "secret")


@pytest.fixture
def no_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XCODES_USERNAME", raising=False)
    monkeypatch.delenv("XCODES_PASSWORD", raising=False)
    monkeypatch.setattr(ios, "_interactive", lambda: False)


def test_gated_on_xcodes_minimum_macos() -> None:
    assert ios.Xcode.supported_on(MAC) is True
    assert ios.Xcode.supported_on(OsInfo("macos", "macos", "aarch64", version_id="26.6")) is True
    assert ios.Xcode.supported_on(OsInfo("macos", "macos", "aarch64", version_id="26.3")) is False
    assert ios.IosTooling.supported_on(OsInfo("macos", "macos", "aarch64", version_id="15.6")) \
        is False


def test_xcode_install_is_interactive_then_license_and_first_launch(creds: None) -> None:
    ex = RuleExecutor()
    ios.Xcode().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [
        ["xcodes", "install", "27.0", "--select", "--experimental-unxip", "--empty-trash"],
        ["sudo", "xcodebuild", "-license", "accept"],
        ["sudo", "xcodebuild", "-runFirstLaunch"],
    ]
    assert ex.interactive[0] is True  # never capture xcodes: it may prompt (Apple ID/2FA)


def test_xcode_without_credentials_or_terminal_needs_the_user(no_tty: None) -> None:
    ex = RuleExecutor()
    with pytest.raises(NeedsUser, match="Apple ID"):
        ios.Xcode().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == []


def test_xcode_verify_needs_the_pin_selected_and_the_license() -> None:
    ok = RuleExecutor(rules=[(("xcodes", "installed"), Result(0, INSTALLED))])
    assert ios.Xcode().verify(Ctx(os=MAC, ex=ok)) is True
    other = RuleExecutor(rules=[(("xcodes", "installed"), Result(0, "26.4 (17E192) (Selected)\n"))])
    assert ios.Xcode().verify(Ctx(os=MAC, ex=other)) is False
    unlicensed = RuleExecutor(rules=[
        (("xcodes", "installed"), Result(0, INSTALLED)),
        (("-license", "check"), Result(1)),
    ])
    assert ios.Xcode().verify(Ctx(os=MAC, ex=unlicensed)) is False


def test_ios_tooling_installs_formulae_then_the_runtime(creds: None) -> None:
    ex = RuleExecutor()
    ios.IosTooling().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [
        ["brew", "install", "--formula", "-y", "cocoapods", "watchman"],
        ["xcodes", "runtimes", "install", "iOS 27.0"],
    ]
    assert ex.interactive[-1] is True


def test_ios_tooling_verify_reads_simctl() -> None:
    ok = RuleExecutor(rules=[(("simctl", "list"), Result(0, RUNTIMES))])
    assert ios.IosTooling().verify(Ctx(os=MAC, ex=ok)) is True
    none = RuleExecutor(rules=[(("simctl", "list"), Result(0, "== Runtimes ==\n"))])
    assert ios.IosTooling().verify(Ctx(os=MAC, ex=none)) is False


def test_profile_and_order() -> None:
    assert ios.Xcode.profiles == ios.IosTooling.profiles == ("ios",)
    assert [c.name for c in ios.IosTooling.requires] == ["xcode"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_ios.py -v`
Expected: FAIL (`ImportError: cannot import name 'ios'`).

- [ ] **Step 3: Implement** `src/devboost/modules/ios.py`

```python
"""ios — Xcode and the iOS simulator runtime via xcodes (opt-in `ios` profile, spec §2).

xcodes may prompt for an Apple ID password or a 2FA code, so it always runs attached to
the terminal (never with captured output, where it would block on an invisible prompt).
With neither XCODES_USERNAME/XCODES_PASSWORD nor a terminal, the module reports what the
user must do (`blocked`) instead.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from devboost.core.errors import InstallError, NeedsUser
from devboost.core.macver import macos_version
from devboost.core.osinfo import OsInfo, OsMap
from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.media.catalog import xcode_pin
from devboost.model import Ctx, Module
from devboost.modules.cli_tools import Xcodes  # A2 — use the path Task 0 found
from devboost.modules.homebrew import Homebrew  # A1

_IOS = ("ios",)


def _interactive() -> bool:
    return sys.stdin.isatty()


def _require_auth(what: str) -> None:
    creds = os.environ.get("XCODES_USERNAME") and os.environ.get("XCODES_PASSWORD")
    if not (creds or _interactive()):
        raise NeedsUser(
            f"{what} needs an Apple ID",
            "export XCODES_USERNAME and XCODES_PASSWORD, or run "
            "`devboost install ios` in a terminal",
        )


def _supported(os_info: OsInfo) -> bool:
    v = macos_version(os_info)
    return v is None or v >= xcode_pin().min_macos


@dataclass(frozen=True)
class _XcodeInstall:
    def verify(self, ctx: Ctx) -> bool:
        pin = xcode_pin()
        res = ctx.ex.run(["xcodes", "installed"])
        selected = res.ok and any(
            line.startswith(f"{pin.version} ") and "(Selected)" in line
            for line in res.stdout.splitlines()
        )
        return selected and ctx.ex.run(["xcodebuild", "-license", "check"]).ok

    def install(self, ctx: Ctx) -> None:
        pin = xcode_pin()
        _require_auth("Downloading Xcode")
        argv = ["xcodes", "install", pin.version, "--select", "--experimental-unxip",
                "--empty-trash"]
        res = ctx.ex.run(argv, interactive=True)
        if not res.ok:
            raise InstallError("xcode", " ".join(argv), res.code)
        for step in (["xcodebuild", "-license", "accept"], ["xcodebuild", "-runFirstLaunch"]):
            done = ctx.ex.run(step, sudo=True)
            if not done.ok:
                raise InstallError("xcode", "sudo " + " ".join(step), done.code)


@register
class Xcode(Module):
    name = "xcode"
    category = "ios"
    description = "Xcode (pinned in catalog.toml) via xcodes; license accepted, first launch run."
    profiles = _IOS
    families = ("macos",)
    gui = True
    requires = (Homebrew, Xcodes)
    per_os = OsMap(macos=_XcodeInstall())

    @classmethod
    def supported_on(cls, os_info: OsInfo) -> bool:
        return _supported(os_info)


@dataclass(frozen=True)
class _IosToolingInstall:
    def verify(self, ctx: Ctx) -> bool:
        runtime = f"iOS {xcode_pin().ios_runtime}"
        sims = ctx.ex.run(["xcrun", "simctl", "list", "runtimes"])
        return (
            pkg.installed(ctx, "cocoapods")
            and pkg.installed(ctx, "watchman")
            and sims.ok
            and runtime in sims.stdout
        )

    def install(self, ctx: Ctx) -> None:
        runtime = f"iOS {xcode_pin().ios_runtime}"
        pkg.install(ctx, "cocoapods", "watchman")
        _require_auth("Downloading the iOS simulator runtime")
        res = ctx.ex.run(["xcodes", "runtimes", "install", runtime], interactive=True)
        if not res.ok:
            raise InstallError("ios-tooling", f"xcodes runtimes install {runtime!r}", res.code)


@register
class IosTooling(Module):
    name = "ios-tooling"
    category = "ios"
    description = "CocoaPods, watchman and the pinned iOS simulator runtime."
    profiles = _IOS
    families = ("macos",)
    requires = (Xcode,)
    per_os = OsMap(macos=_IosToolingInstall())

    @classmethod
    def supported_on(cls, os_info: OsInfo) -> bool:
        return _supported(os_info)
```

**Only if A2 is absent:** define `Xcodes` in `ios.py` instead of importing it (and add it to `ios` before `xcode`):

```python
@register
class Xcodes(PackageModule):
    name = "xcodes"
    category = "ios"
    description = "xcodes — install and switch Xcode versions (MIT)."
    cmd = "xcodes"
    fedora_pkg = "xcodes"
    families = ("macos",)
```

In `profiles.toml`, after `macos-desktop`:

```toml
# ios — opt-in: Xcode + the iOS simulator runtime (pins in catalog.toml [xcode]).
ios              = ["xcode","ios-tooling"]
```

In `tests/conftest.py` `profiles_file`, add `'ios = ["xcode"]\n'` after the `macos-desktop` line.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/modules/test_ios.py tests/core -q && uv run mypy && uv run ruff check`
Expected: PASS, clean.

- [ ] **Step 5: §0 / D19 on-Mac check (read-only)**

```bash
brew info xcodes | head -2                           # 2.1.0 (homebrew-core) at plan time
xcodes version 2>/dev/null; xcodes installed 2>/dev/null   # output format the verify parses
xcrun simctl list runtimes | head -5                 # "iOS 27.0 (…)" format
security find-generic-password -s com.robotsandpencils.xcodes 2>/dev/null | head -2 || echo "no stored xcodes session"
```
Check the formats against the test fixtures (`INSTALLED`, `RUNTIMES`). If they differ, fix the parser and its fixture before committing. If a stored xcodes session exists (the last line), note it in `docs/macos.md`. The module still asks for a terminal or env credentials (a conservative choice; D19).

- [ ] **Step 6: Commit**

```bash
git add src/devboost/modules/ios.py tests/modules/test_ios.py tests/conftest.py ../profiles.toml
git commit -m "feat(ios): opt-in Xcode and iOS simulator runtime via xcodes"
```

---

### Task 13: `macos-extras` (opt-in casks)

**Files:**
- Modify: `engine/src/devboost/modules/macos_apps.py`, `profiles.toml` (new `macos-extras` line), `engine/tests/conftest.py` (`profiles_file`: one line)
- Test: `engine/tests/modules/test_macos_extras.py` (create)

**Interfaces:**
- Consumes: `CaskApp` (Task 6); `Wezterm` (M2; already registered, with profile `optional-terminals`).
- Produces: registered `maccy`, `ollama-app`, `lm-studio`, `pearcleaner`, `keycastr`, `linearmouse`, `android-studio`, `expo-orbit`, `herd`, each with `profiles = ("macos-extras",)`. The profile `macos-extras` = those nine + `wezterm`.

- [ ] **Step 1: Write the failing tests** — `tests/modules/test_macos_extras.py`

```python
from __future__ import annotations

from pathlib import Path

from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load
from devboost.modules._cask import CaskApp, CaskInstall

REPO_ROOT = Path(__file__).resolve().parents[3]

EXTRAS = {
    # module: (cask, launch, TCC services)
    "maccy": ("maccy", "Maccy", ("Accessibility",)),
    "ollama-app": ("ollama-app", None, ()),
    "lm-studio": ("lm-studio", None, ()),
    "pearcleaner": ("pearcleaner", None, ()),
    "keycastr": ("keycastr", None, ("ListenEvent", "Accessibility")),
    "linearmouse": ("linearmouse", "LinearMouse", ("Accessibility",)),
    "android-studio": ("android-studio", None, ()),
    "expo-orbit": ("expo-orbit", None, ()),
    "herd": ("herd", None, ()),
}


def test_extras_cask_table() -> None:
    mods = load()
    for name, (cask, launch, services) in EXTRAS.items():
        cls = mods[name]
        assert issubclass(cls, CaskApp), name
        assert cls.per_os.macos == CaskInstall(cask, launch), name
        assert tuple(g.service for g in cls.tcc) == services, name
        assert cls.profiles == ("macos-extras",), name


def test_macos_extras_profile_is_the_extras_plus_wezterm() -> None:
    got = expand(["macos-extras"], load_profiles(REPO_ROOT / "profiles.toml"), load())
    assert got == [*EXTRAS, "wezterm"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_macos_extras.py -v`
Expected: FAIL (`KeyError: 'maccy'`).

- [ ] **Step 3: Implement** — append to `src/devboost/modules/macos_apps.py`:

```python
# --- macos-extras (opt-in) ----------------------------------------------------------------
# Licences checked 2026-09-19 (D3–D5): all free for work use.

_EXTRAS = ("macos-extras",)


@register
class Maccy(CaskApp):
    name = "maccy"
    category = "macos-extras"
    description = "Maccy — clipboard history (MIT)."
    profiles = _EXTRAS
    cask = "maccy"
    launch = "Maccy"
    tcc = (TccGrant("Accessibility", "Maccy"),)


@register
class OllamaApp(CaskApp):
    name = "ollama-app"
    category = "macos-extras"
    description = "Ollama — run local LLMs (MIT)."
    profiles = _EXTRAS
    cask = "ollama-app"


@register
class LmStudio(CaskApp):
    name = "lm-studio"
    category = "macos-extras"
    description = "LM Studio — local LLM app (free for work use since 2025-07)."
    profiles = _EXTRAS
    cask = "lm-studio"


@register
class Pearcleaner(CaskApp):
    name = "pearcleaner"
    category = "macos-extras"
    description = "Pearcleaner — app uninstaller (Apache-2.0 + Commons Clause)."
    profiles = _EXTRAS
    cask = "pearcleaner"


@register
class Keycastr(CaskApp):
    name = "keycastr"
    category = "macos-extras"
    description = "KeyCastr — show keystrokes on screen for demos (BSD-3-Clause)."
    profiles = _EXTRAS
    cask = "keycastr"
    tcc = (TccGrant("ListenEvent", "KeyCastr"), TccGrant("Accessibility", "KeyCastr"))


@register
class Linearmouse(CaskApp):
    name = "linearmouse"
    category = "macos-extras"
    description = "LinearMouse — per-device mouse/trackpad tuning (MIT)."
    profiles = _EXTRAS
    cask = "linearmouse"
    launch = "LinearMouse"
    tcc = (TccGrant("Accessibility", "LinearMouse"),)


@register
class AndroidStudio(CaskApp):
    name = "android-studio"
    category = "macos-extras"
    description = "Android Studio (Apache-2.0 + Google SDK terms)."
    profiles = _EXTRAS
    cask = "android-studio"


@register
class ExpoOrbit(CaskApp):
    name = "expo-orbit"
    category = "macos-extras"
    description = "Expo Orbit — launch builds on simulators/emulators from the menu bar (MIT)."
    profiles = _EXTRAS
    cask = "expo-orbit"


@register
class Herd(CaskApp):
    name = "herd"
    category = "macos-extras"
    description = "Laravel Herd — native PHP/Laravel environment (free tier; Pro optional)."
    profiles = _EXTRAS
    cask = "herd"
```

In `profiles.toml`, after `ios`:

```toml
# macos-extras — opt-in Mac apps (all free for work use; licences in docs/macos-primer.md).
macos-extras     = ["maccy","ollama-app","lm-studio","pearcleaner","keycastr","linearmouse",
                    "android-studio","expo-orbit","herd","wezterm"]
```

In `tests/conftest.py` `profiles_file`, add `'macos-extras = ["maccy"]\n'` after the `ios` line.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/modules/test_macos_extras.py tests/core -q && uv run mypy && uv run ruff check`
Expected: PASS, clean.

- [ ] **Step 5: On-Mac metadata check (read-only)**

```bash
brew info --json=v2 --cask maccy ollama-app lm-studio pearcleaner keycastr linearmouse android-studio expo-orbit herd \
  | jq -r '.casks[] | [.token, .version, (.deprecated|tostring), (.disabled|tostring)] | @tsv'
```
Expected: no deprecated or disabled cask. Fix any renamed token, and its D5 row, before committing.

- [ ] **Step 6: Commit**

```bash
git add src/devboost/modules/macos_apps.py tests/modules/test_macos_extras.py tests/conftest.py ../profiles.toml
git commit -m "feat(macos): opt-in macos-extras apps"
```

---

### Task 14: `android-emulator` (opt-in, every OS)

**Files:**
- Create: `engine/src/devboost/modules/android_emulator.py`
- Test: `engine/tests/modules/test_android_emulator.py` (create)

**Interfaces:**
- Consumes: `AndroidSdk` (`devboost.modules.dev_stacks`, with M3's macOS strategy per A5).
- Produces:
  - `API = 35`, `AVD = "devboost-pixel"`, `DEVICE = "pixel_8"`.
  - `system_image(os_info) -> str`.
  - `sdk_root(os_info) -> Path`: `$ANDROID_HOME`, else `~/Library/Android/sdk` on macOS and `~/Android/Sdk` on Linux.
  - `avd_ini() -> Path`.
  - Registered `android-emulator` (`AndroidEmulator`): no profile, `requires = (AndroidSdk,)`, `gui = True`, `portable = True`, and `supported_on` = not (Linux and aarch64).

- [ ] **Step 1: Write the failing tests** — `tests/modules/test_android_emulator.py`

```python
from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules import android_emulator as emu

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
FEDORA_ARM = OsInfo("fedora", "fedora", "aarch64")


@pytest.fixture(autouse=True)
def _no_sdk_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let a developer's real ANDROID_HOME / ANDROID_AVD_HOME leak into a test."""
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.delenv("ANDROID_AVD_HOME", raising=False)


def test_image_abi_follows_the_host() -> None:
    assert emu.system_image(MAC) == "system-images;android-35;google_apis;arm64-v8a"
    assert emu.system_image(FEDORA) == "system-images;android-35;google_apis;x86_64"


def test_sdk_root_defaults_per_os(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert emu.sdk_root(MAC) == tmp_path / "Library" / "Android" / "sdk"
    assert emu.sdk_root(FEDORA) == tmp_path / "Android" / "Sdk"
    monkeypatch.setenv("ANDROID_HOME", "/opt/sdk")
    assert emu.sdk_root(MAC) == Path("/opt/sdk")


def test_no_linux_arm64_emulator_host() -> None:
    assert emu.AndroidEmulator.supported_on(MAC) is True
    assert emu.AndroidEmulator.supported_on(FEDORA) is True
    assert emu.AndroidEmulator.supported_on(FEDORA_ARM) is False


def test_install_fetches_emulator_and_image_then_creates_the_avd(tmp_path: Path) -> None:
    ex = FakeExecutor()
    emu.AndroidEmulator().install(Ctx(os=MAC, ex=ex))
    root = tmp_path / "Library" / "Android" / "sdk"
    sdkm = ex.calls[0]
    assert sdkm[:2] == ["sh", "-c"]
    assert f"--sdk_root={root}" in sdkm[2]
    assert "emulator 'system-images;android-35;google_apis;arm64-v8a'" in sdkm[2]
    assert ex.calls[1] == [
        "avdmanager", "create", "avd", "-n", "devboost-pixel",
        "-k", "system-images;android-35;google_apis;arm64-v8a", "-d", "pixel_8",
    ]


def test_existing_avd_is_kept(tmp_path: Path) -> None:
    emu.avd_ini().parent.mkdir(parents=True)
    emu.avd_ini().touch()
    ex = FakeExecutor()
    emu.AndroidEmulator().install(Ctx(os=MAC, ex=ex))
    assert not [c for c in ex.calls if c[:1] == ["avdmanager"]]


def test_verify_needs_emulator_image_and_avd() -> None:
    ctx = Ctx(os=MAC, ex=FakeExecutor())
    assert emu.AndroidEmulator().verify(ctx) is False
    root = emu.sdk_root(MAC)
    (root / "emulator").mkdir(parents=True)
    (root / "emulator" / "emulator").touch()
    (root / "system-images" / "android-35" / "google_apis" / "arm64-v8a").mkdir(parents=True)
    emu.avd_ini().parent.mkdir(parents=True)
    emu.avd_ini().touch()
    assert emu.AndroidEmulator().verify(ctx) is True
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/modules/test_android_emulator.py -v`
Expected: FAIL (`ImportError: cannot import name 'android_emulator'`).

- [ ] **Step 3: Implement** `src/devboost/modules/android_emulator.py`

```python
"""android-emulator — the Android emulator + one Pixel AVD (opt-in, every OS; spec §2)."""

from __future__ import annotations

import os
import shlex
from pathlib import Path

from devboost.core.errors import InstallError
from devboost.core.osinfo import OsInfo
from devboost.core.registry import register
from devboost.model import Ctx, Module
from devboost.modules.dev_stacks import AndroidSdk

API = 35  # matches android-sdk's platforms;android-35
AVD = "devboost-pixel"
DEVICE = "pixel_8"


def _abi(os_info: OsInfo) -> str:
    return "arm64-v8a" if os_info.arch == "aarch64" else "x86_64"


def system_image(os_info: OsInfo) -> str:
    return f"system-images;android-{API};google_apis;{_abi(os_info)}"


def sdk_root(os_info: OsInfo) -> Path:
    if env := os.environ.get("ANDROID_HOME"):
        return Path(env)
    home = Path(os.environ["HOME"])
    if os_info.family == "macos":
        return home / "Library" / "Android" / "sdk"
    return home / "Android" / "Sdk"


def avd_ini() -> Path:
    base = os.environ.get("ANDROID_AVD_HOME") or str(Path(os.environ["HOME"]) / ".android" / "avd")
    return Path(base) / f"{AVD}.ini"


def _tool(root: Path, name: str) -> str:
    """The SDK's own cmdline-tools copy if present, else PATH (brew's android-commandlinetools)."""
    local = root / "cmdline-tools" / "latest" / "bin" / name
    return str(local) if local.exists() else name


@register
class AndroidEmulator(Module):
    name = "android-emulator"
    category = "react-native"
    description = "Android emulator + a Pixel AVD (API 35; arm64-v8a on Apple Silicon)."
    requires = (AndroidSdk,)
    gui = True
    portable = True

    @classmethod
    def supported_on(cls, os_info: OsInfo) -> bool:
        # Google ships no Linux arm64 emulator host.
        return not (os_info.family != "macos" and os_info.arch == "aarch64")

    def verify(self, ctx: Ctx) -> bool:
        root = sdk_root(ctx.os)
        image = root / "system-images" / f"android-{API}" / "google_apis" / _abi(ctx.os)
        return (root / "emulator" / "emulator").exists() and image.is_dir() and avd_ini().exists()

    def install(self, ctx: Ctx) -> None:
        root = sdk_root(ctx.os)
        env = {"ANDROID_HOME": str(root), "ANDROID_SDK_ROOT": str(root)}
        image = system_image(ctx.os)
        sdkmanager = _tool(root, "sdkmanager")
        script = (
            f"yes | {shlex.quote(sdkmanager)} --sdk_root={shlex.quote(str(root))} "
            f"emulator {shlex.quote(image)}"
        )
        res = ctx.ex.run(["sh", "-c", script], env=env)
        if not res.ok:
            raise InstallError("android-emulator", f"sdkmanager emulator {image}", res.code)
        if avd_ini().exists():
            return
        argv = [_tool(root, "avdmanager"), "create", "avd", "-n", AVD, "-k", image, "-d", DEVICE]
        made = ctx.ex.run(argv, stdin="no\n", env=env)  # "no" = no custom hardware profile
        if not made.ok:
            raise InstallError("android-emulator", " ".join(argv), made.code)
```

Note: `shlex.quote` leaves a path without special characters unquoted, which is why the test matches `--sdk_root=<root>` literally. The tmp path has no spaces.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/modules/test_android_emulator.py tests/core -q && uv run mypy && uv run ruff check`
Expected: PASS, clean.

- [ ] **Step 5: On-Mac check** (after Task 18 Step 7 installs it)

```bash
"$ANDROID_HOME/emulator/emulator" -list-avds          # devboost-pixel
"$ANDROID_HOME/emulator/emulator" -avd devboost-pixel -no-window -no-audio -no-snapshot &
sleep 90; adb devices; adb emu kill                   # one "emulator-5554 device" line
```
If brew's `avdmanager` ignores `ANDROID_HOME` and writes the AVD elsewhere, pass `--sdk_root` through `AVDMANAGER_OPTS="-Dcom.android.sdkmanager.toolsdir=…"` or call the SDK-local copy. Record the fix in D20.

- [ ] **Step 6: Commit**

```bash
git add src/devboost/modules/android_emulator.py tests/modules/test_android_emulator.py
git commit -m "feat(react-native): opt-in android-emulator with a Pixel AVD"
```

---

### Task 15: Profiles wiring + macOS contract for the opt-in sets

**Files:**
- Modify: `profiles.toml` (`macos` += `"macos-desktop"` if A6 said absent), `engine/tests/core/test_macos_contract.py`
- Test: `engine/tests/cli/test_macos_desktop_profiles.py` (create)

**Interfaces:**
- Consumes: every module above; `expand`, `load_profiles`, `toposort`, `build_plan`.
- Produces: tests pinning the M5 profile shape and spec §9's contract. On macOS 27, `macos` + `macos-extras` + `ios` + `optional-terminals` + `voxtype-arabic` + `android-emulator` plan with no `unsupported-os` module outside `KNOWN_GAPS`.

- [ ] **Step 1: Write the failing tests**

`tests/cli/test_macos_desktop_profiles.py`:

```python
from __future__ import annotations

from pathlib import Path

from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load

REPO_ROOT = Path(__file__).resolve().parents[3]
FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _expand(*tokens: str) -> list[str]:
    return expand(list(tokens), load_profiles(REPO_ROOT / "profiles.toml"), load())


def test_macos_desktop_members() -> None:
    assert _expand("macos-desktop") == [
        "macos-defaults", "macos-limits", "macos-firewall", "timemachine-exclusions",
        "stats", "raycast", "aerospace", "alt-tab", "thaw", "monitorcontrol", "keka",
        "quicklook", "default-apps",
    ]


def test_ios_members() -> None:
    assert _expand("ios") == ["xcode", "ios-tooling"]


def test_macos_includes_the_desktop_and_voxtype() -> None:
    mac = set(_expand("macos"))
    assert set(_expand("macos-desktop")) <= mac
    assert "voxtype" in mac


def test_voxtype_is_in_base_everywhere() -> None:
    for aggregate in ("base", "full", "omarchy", "macos"):
        assert "voxtype" in _expand(aggregate), aggregate


def test_opt_ins_stay_out_of_every_default() -> None:
    for aggregate in ("full", "omarchy", "macos"):
        got = set(_expand(aggregate))
        assert not {"voxtype-arabic", "android-emulator", "xcode", "maccy"} & got, aggregate


def test_linux_drops_the_mac_only_sets(tmp_path: Path) -> None:
    mods = load()
    mac_only = _expand("macos-desktop", "ios")
    order = toposort(mac_only, mods)  # also pulls cross-OS requirements such as `zed`
    planned = {p.name for p in build_plan(order, mods, FEDORA, gpu_marker=tmp_path / "none")}
    assert not planned & set(mac_only)
    assert "homebrew" not in planned
```

Add to `tests/core/test_macos_contract.py`, next to its other imports and tests:

```python
from pathlib import Path

from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.profiles import expand, load_profiles

REPO_ROOT = Path(__file__).resolve().parents[3]
MAC27 = OsInfo("macos", "macos", "aarch64", version_id="27.0")
#: Spec §9: the sets whose every module must resolve on a Mac.
MAC_SETS = ["macos", "macos-extras", "ios", "optional-terminals", "voxtype-arabic",
            "android-emulator"]


def test_mac_sets_plan_without_unsupported_modules(tmp_path: Path) -> None:
    modules = load()
    order = toposort(expand(MAC_SETS, load_profiles(REPO_ROOT / "profiles.toml"), modules),
                     modules)
    plan = build_plan(order, modules, MAC27, gpu_marker=tmp_path / "none")
    unsupported = {p.name for p in plan if p.skip_reason == "unsupported-os"}
    assert unsupported <= KNOWN_GAPS, sorted(unsupported - KNOWN_GAPS)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cli/test_macos_desktop_profiles.py tests/core/test_macos_contract.py -v`
Expected: `test_macos_includes_the_desktop_and_voxtype` FAILS if M3 did not put `macos-desktop` in `macos`. Everything else passes. That is expected, because Tasks 3–14 built the profile lines as they went.

- [ ] **Step 3: Implement**

1. `profiles.toml`: make sure the `macos` aggregate lists `"macos-desktop"`. Per spec §2, it goes after `"apps"`. Add it only if missing, and do not reorder M3's list.
2. `KNOWN_GAPS`. Use the Task 0 Step 4 numbers, re-checked after rebasing on the latest `main`:
   - If **M4 has merged** and `unresolved()` is empty, replace the set with `KNOWN_GAPS: frozenset[str] = frozenset()`. Change the module docstring to: "KNOWN_GAPS lists modules with no macOS path. It became empty with M5 (spec §9) and must stay empty: every new module ships its macOS answer."
   - If **M4 has not merged**, leave only M4-owned names (Task 0 Step 4 list). Any other remaining name is an M3 miss: stop and report it, and do not paper over it here. M4's PR then empties the set and updates the docstring.
3. `tests/core/test_macos_contract.py` docstring otherwise unchanged.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -q && uv run mypy && uv run ruff check`
Expected: the whole suite PASSES, clean.

- [ ] **Step 5: Commit**

```bash
git add ../profiles.toml tests/core/test_macos_contract.py tests/cli/test_macos_desktop_profiles.py
git commit -m "test(macos): pin the desktop/ios/extras profiles and the Mac plan contract"
```

---

### Task 16: `doctor` — desktop checks (spec §8)

**Files:**
- Create: `engine/src/devboost/cli/doctor_desktop.py`
- Modify: `engine/src/devboost/cli/doctor.py` (two lines in `run_checks`'s macOS branch)
- Test: `engine/tests/cli/test_doctor_desktop.py` (create)

**Interfaces:**
- Consumes: `Check` (`devboost.cli.doctor`); `firewall_enabled` (Task 5); `macdefaults.read` (Task 2); `pkg.cask_installed`; `macos_version`; the registry.
- Produces: `desktop_checks(ctx) -> list[Check]` with the names `firewall`, `filevault`, `sip`, `time-machine`, `icloud-desktop`, `charge-limit`, `hotkeys`, `version-gated`. Only `firewall` can be `ok=False`. The others are informational: `WARN …` / `hint: …` details with `ok=True` (D22).

- [ ] **Step 1: Write the failing tests** — `tests/cli/test_doctor_desktop.py`

```python
from __future__ import annotations

from pathlib import Path

from devboost.cli.doctor import run_checks
from devboost.cli.doctor_desktop import desktop_checks
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
MAC15 = OsInfo("macos", "macos", "aarch64", version_id="15.6")
REPO_ROOT = Path(__file__).resolve().parents[3]
FW_ON = (("--getglobalstate",), Result(0, "Firewall is enabled. (State = 1)\n"))
FW_OFF = (("--getglobalstate",), Result(0, "Firewall is disabled. (State = 0)\n"))


def _checks(ex: RuleExecutor, os_info: OsInfo = MAC) -> dict[str, tuple[bool, str]]:
    return {c.name: (c.ok, c.detail) for c in desktop_checks(Ctx(os=os_info, ex=ex))}


def test_firewall_off_fails() -> None:
    assert _checks(RuleExecutor(rules=[FW_OFF]))["firewall"][0] is False
    assert _checks(RuleExecutor(rules=[FW_ON]))["firewall"][0] is True


def test_everything_else_warns_without_failing() -> None:
    ex = RuleExecutor(rules=[
        FW_ON,
        (("fdesetup",), Result(0, "FileVault is Off.\n")),
        (("csrutil",), Result(0, "System Integrity Protection status: disabled.\n")),
        (("destinationinfo",), Result(0, "tmutil: No destinations configured.\n")),
        (("read-type", "FXICloudDriveDesktop"), Result(0, "Type is boolean\n")),
        (("FXICloudDriveDesktop",), Result(0, "1\n")),
        (("pmset",), Result(0, " -InternalBattery-0 (id=1)\t63%; discharging\n")),
    ])
    got = _checks(ex)
    assert all(ok for ok, _ in got.values())
    for name in ("filevault", "sip", "time-machine", "icloud-desktop"):
        assert got[name][1].startswith("WARN"), name
    assert got["charge-limit"][1].startswith("hint:")
    assert "Raycast" in got["hotkeys"][1] and "Maccy" in got["hotkeys"][1]


def test_healthy_mac_reads_clean() -> None:
    ex = RuleExecutor(rules=[
        FW_ON,
        (("fdesetup",), Result(0, "FileVault is On.\n")),
        (("csrutil",), Result(0, "System Integrity Protection status: enabled.\n")),
        (("destinationinfo",), Result(0, "Name : Backup\nKind : Local\n")),
        (("read-type",), Result(1)),
        (("pmset",), Result(0, "Now drawing from 'AC Power'\n")),
        (("brew", "list"), Result(1)),
    ])
    got = _checks(ex)
    assert not any(detail.startswith("WARN") for _, detail in got.values())
    assert got["charge-limit"][1] == "n/a"
    assert got["hotkeys"][1] == "none"


def test_version_gated_modules_are_listed() -> None:
    detail = _checks(RuleExecutor(rules=[FW_ON]), MAC15)["version-gated"][1]
    assert "thaw" in detail and "xcode" in detail


def test_run_checks_includes_the_desktop_on_macos() -> None:
    names = {c.name for c in run_checks(Ctx(os=MAC, ex=RuleExecutor(rules=[FW_ON])), REPO_ROOT)}
    assert {"firewall", "filevault", "version-gated"} <= names
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/cli/test_doctor_desktop.py -v`
Expected: FAIL (`ImportError: cannot import name 'desktop_checks'`).

- [ ] **Step 3: Implement**

`src/devboost/cli/doctor_desktop.py`:

```python
"""doctor — the macOS desktop checks (spec §8, desktop half; D22).

Only a disabled firewall fails: dev-boost manages it (macos-firewall). FileVault, SIP,
Time Machine, iCloud Desktop & Documents and the battery charge limit are the user's
choice, so they are reported as WARN/hint lines that never fail `doctor`.
"""

from __future__ import annotations

from devboost.cli.doctor import Check
from devboost.core.macver import macos_version
from devboost.core.registry import load
from devboost.exec.primitives import macdefaults, pkg
from devboost.exec.primitives.macdefaults import Value
from devboost.model import Ctx
from devboost.modules.macos_system import firewall_enabled


def _firewall(ctx: Ctx) -> Check:
    on = firewall_enabled(ctx)
    return Check("firewall", on, "on" if on else "off — run `devboost install macos-firewall`")


def _filevault(ctx: Ctx) -> Check:
    on = "FileVault is On" in ctx.ex.run(["fdesetup", "status"]).stdout
    return Check("filevault", True, "on" if on else
                 "WARN off — System Settings → Privacy & Security → FileVault")


def _sip(ctx: Ctx) -> Check:
    on = "status: enabled" in ctx.ex.run(["csrutil", "status"]).stdout
    return Check("sip", True, "enabled" if on else
                 "WARN disabled — re-enable from Recovery: csrutil enable")


def _time_machine(ctx: Ctx) -> Check:
    res = ctx.ex.run(["tmutil", "destinationinfo"])
    none = not res.ok or "No destinations configured" in res.stdout + res.stderr
    return Check("time-machine", True,
                 "WARN no backup destination — System Settings → General → Time Machine"
                 if none else "destination configured")


def _icloud_desktop(ctx: Ctx) -> Check:
    on = macdefaults.read(ctx, "com.apple.finder", "FXICloudDriveDesktop") == Value("bool", True)
    return Check("icloud-desktop", True,
                 "WARN iCloud Desktop & Documents is on — keep repos out of ~/Desktop and "
                 "~/Documents (node_modules churn)" if on else "off")


def _charge_limit(ctx: Ctx) -> Check:
    v = macos_version(ctx.os)
    battery = "InternalBattery" in ctx.ex.run(["pmset", "-g", "batt"]).stdout
    if battery and v is not None and v >= (26, 4):
        return Check("charge-limit", True, "hint: set a charge limit — System Settings → "
                                           "Battery → Charging (no CLI)")
    return Check("charge-limit", True, "n/a")


def _hotkeys(ctx: Ctx) -> Check:
    hints: list[str] = []
    if pkg.cask_installed(ctx, "raycast"):
        hints.append("Raycast: free ⌘Space (System Settings → Keyboard → Keyboard Shortcuts "
                     "→ Spotlight), then set it as Raycast's hotkey")
    if pkg.cask_installed(ctx, "maccy"):
        hints.append("Maccy: ⇧⌘C opens clipboard history")
    return Check("hotkeys", True, "; ".join(hints) or "none")


def _gated(ctx: Ctx) -> Check:
    gated = sorted(
        name for name, cls in load().items()
        if (not cls.families or "macos" in cls.families) and not cls.supported_on(ctx.os)
    )
    detail = (", ".join(gated) + " — not supported on this macOS version") if gated else "none"
    return Check("version-gated", True, detail)


def desktop_checks(ctx: Ctx) -> list[Check]:
    return [
        _firewall(ctx), _filevault(ctx), _sip(ctx), _time_machine(ctx),
        _icloud_desktop(ctx), _charge_limit(ctx), _hotkeys(ctx), _gated(ctx),
    ]
```

In `src/devboost/cli/doctor.py`, `run_checks`'s macOS branch becomes the following. The import is local because `doctor_desktop` imports `Check` from this module.

```python
    if ctx.os.family == "macos":
        checks.append(_permissions_check(ctx))
        from devboost.cli.doctor_desktop import desktop_checks
        checks.extend(desktop_checks(ctx))
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/cli -q && uv run mypy && uv run ruff check`
Expected: PASS, clean. If ruff's import-placement rule (`PLC0415`) is enabled, add `# noqa: PLC0415` to the local import, the same way `_permissions_check` does.

- [ ] **Step 5: Commit**

```bash
git add src/devboost/cli/doctor_desktop.py src/devboost/cli/doctor.py tests/cli/test_doctor_desktop.py
git commit -m "feat(doctor): macOS desktop checks (firewall, FileVault, SIP, Time Machine, iCloud)"
```

---

### Task 17: Docs — primer, macOS guide link, module guide, spec, changelog, README

**Files:**
- Create: `docs/macos-primer.md`
- Modify: `docs/macos.md` (one link line), `docs/adding-a-module.md` (macOS section), `docs/omarchy.md` (Provided-by list), `docs/superpowers/specs/2026-09-18-macos-support-design.md`, `CHANGELOG.md`, `README.md` (generated table)

No code. Every commit in this task is docs only.

- [ ] **Step 1: Write `docs/macos-primer.md`** with exactly these sections. The content is given, so fill every table from the Decisions and the tasks above:

1. **"New to the Mac? Start here"**. Mention ⌘ (Command) vs Ctrl: ⌘ is the app shortcut key, and Ctrl stays the terminal key. Mention ⌥ (Option): left ⌥ = Alt in Ghostty (M2), right ⌥ types accents. Mention the fn/🌐 key.
2. **"What `devboost install macos` set up"**. A table with one row per `macos-desktop` module: what it does, where to see it, and how to undo it. It must include `devboost revert macos-defaults [key…]` with an example (`devboost revert macos-defaults tilesize`). Add the note: `devboost install` re-applies a reverted key unless `macos-defaults` is left out.
3. **"The defaults, key by key"**. The 20-row D8 table (`<domain>:<key>` → value → effect), plus which ones need a logout (D9).
4. **"Windows: AeroSpace + AltTab"**. The Ctrl+Alt key table from Task 7 (workspaces, focus, move, layout, fullscreen, service mode). AltTab is ⌥⇥. Say why the layer is Ctrl+Alt and not Alt.
5. **"Launcher, menu bar, monitors"**. Raycast and how to hand it ⌘Space. Thaw (macOS 26+). Stats. MonitorControl. Why BetterDisplay is not installed (D3: paid for business use; buy it yourself if you need HiDPI scaling).
6. **"Files"**. Quick Look (Space; enable the extensions under System Settings → General → Login Items & Extensions → Quick Look). Keka. Code files open in Zed (`default-apps`); change one with `duti -s <bundle id> .<ext> all`.
7. **"Screenshots go to the clipboard"**. ⌘⇧3 / ⌘⇧4 / ⌘⇧5, paste into `herdr --remote` with Ctrl+V; ⌘⇧5 → Options → Save to for files.
8. **"Dictation (Voxtype)"**. Hold Right Option (the placeholder default), speak, release. How to paste the Omarchy hotkey into `dotfiles/dot_config/voxtype/config.toml.tmpl` (the PLACEHOLDER block) and run `devboost install dotfiles`. Arabic: `devboost install voxtype-arabic`, then Ctrl+Alt+D toggles Arabic dictation on macOS, or LeftShift+hotkey on Linux. Model sizes and the no-idle-RAM behaviour (D17).
9. **"Privacy permissions"**. The D7 table (app → permission). `devboost permissions`, `devboost permissions --confirm <module>`. Why scripts cannot grant these.
10. **"Launch at login"**. Where each app's toggle lives (D24). AeroSpace is already set by its config.
11. **"Safety net"**. Firewall, Time Machine exclusions (what is excluded, and the `~/repos` sweep every 6 h), open-files limit (524288), and `devboost doctor`'s desktop lines (D22).
12. **"iOS (opt-in)"**. `XCODES_USERNAME` / `XCODES_PASSWORD` or run in a terminal, `devboost install ios`, the Xcode 27 / iOS 27 pins and how to bump them (`catalog.toml [xcode]`).
13. **"Extras (opt-in)"**. The `macos-extras` table with each licence (D5), plus `android-emulator` (`emulator -avd devboost-pixel`).
14. **"Licences"**. One table covering every app M5 installs: licence, and why it is OK for work use, with the source links from the Sources list.

- [ ] **Step 2: Other docs**

- `docs/macos.md`: add one line under its profiles/section list: ``- Desktop layer, iOS and extras (M5): see [macos-primer.md](macos-primer.md).`` Nothing else, to keep the overlap with M4 to one line.
- `docs/adding-a-module.md` `## macOS`: add three bullets:
  - "A GUI app that is one cask: subclass `CaskApp` (`modules/_cask.py`) and set `cask`, plus optionally `launch`, `tcc`, `min_macos`."
  - "Version gates: override `supported_on(os_info)` (the plan reports `unsupported-os`); use `core.macver.macos_version`."
  - "A setting you change on the user's machine must be revertible; see `macos_defaults.py` (snapshot first, `devboost revert`)."
- `docs/omarchy.md`: add `voxtype` to the "Provided by Omarchy" paragraph: Omarchy installs `voxtype-bin` from Install › AI › Dictation. dev-boost still ships the shared config.
- Spec `docs/superpowers/specs/2026-09-18-macos-support-design.md`:
  - Decisions table, Desktop row: replace `MonitorControl + BetterDisplay` with `MonitorControl (BetterDisplay dropped: paid for business use)`.
  - "Licensing constraints" list: add a BetterDisplay bullet and a Keka bullet (D3, D4).
  - §0, the Thaw bullet: add "stable `thaw` 2.0.1 declares macOS ≥ 26; checked on 27 at M5 (see plan D2)".
  - §2 Casks table: drop `betterdisplay`.
  - §2 new-modules table:
    - `macos-limits` row → `sysctl kern.maxfiles/maxfilesperproc 524288` + best-effort `launchctl limit` (D11)
    - `timemachine-exclusions` row → "sweep LaunchAgent every 6 h + at login"
    - `default-apps` row → `duti`
  - §2 macos-defaults table: add the Bluetooth trackpad `Clicking` row (D8).
  - §2 Voxtype paragraph → D14–D18:
    - daemon via `voxtype setup app-bundle`, not a launchd agent
    - Whisper `small.en` default (Parakeet cannot pair with a secondary model)
    - Arabic = `secondary_model` + `cold_model_timeout_secs`, with `on_demand_loading` off
    - macOS trigger = AeroSpace Ctrl+Alt+D
    - Linux = pinned RPM/DEB/AUR
    - permissions add Accessibility
  - §2 Profiles: remove `betterdisplay` from `macos-desktop`.
  - §2 TCC paragraph: Voxtype also needs Accessibility; KeyCastr, MonitorControl and LinearMouse are listed.
- `CHANGELOG.md` `[Unreleased]` → `### Added`, one bullet:
  "**macOS desktop (M5)** — `macos-defaults` with snapshot + `devboost revert macos-defaults [key…]`, open-files limit, firewall, Time Machine exclusions, Raycast/AeroSpace (+config)/AltTab/Thaw/MonitorControl/Keka/Stats/Quick Look, code files open in Zed, Voxtype dictation on every OS (+ opt-in `voxtype-arabic`), opt-in `ios` (Xcode 27), `macos-extras` and `android-emulator`, desktop checks in `doctor`. BetterDisplay is not shipped (paid for business use). See [docs/macos-primer.md](docs/macos-primer.md)."
- `README.md`: regenerate the profiles table:
  ```bash
  uv run --project engine python scripts/gen_profiles_table.py
  ```
  (repo root). Paste its output between the `BEGIN`/`END generated profiles table` markers. Add `docs/macos-primer.md` to the README's Docs list.

- [ ] **Step 3: Check the docs build nothing broken**

```bash
grep -n 'betterdisplay' -r ../profiles.toml src ../docs/macos-primer.md | grep -v 'not shipped\|dropped\|paid' || echo ok
cd .. && git diff --stat -- docs README.md CHANGELOG.md
```
Expected: `ok` (no stray BetterDisplay module references). The diff touches only the files listed.

- [ ] **Step 4: Commit**

```bash
git add ../docs/macos-primer.md ../docs/macos.md ../docs/adding-a-module.md ../docs/omarchy.md ../docs/superpowers/specs/2026-09-18-macos-support-design.md ../CHANGELOG.md ../README.md
git commit -m "docs(macos): new-to-Mac primer, desktop/iOS/voxtype docs, spec updates"
```

---

### Task 18: Acceptance on this Mac (macOS 27) + Linux regression

This is the milestone's outcome, "full desktop + iOS". It changes this Mac for real (that is the point) and records every §0 verification. Run from `engine/` unless noted.

- [ ] **Step 1: Gates**

```bash
uv run ruff check && uv run mypy && uv run pytest -q 2>&1 | tail -3
```
Expected: all green. No test was skipped for a missing binary other than ones not installed yet (`aerospace`).

- [ ] **Step 2: Dry run**

```bash
uv run devboost install macos --dry-run 2>&1 | tee /tmp/m5-dry.txt | grep -E 'skip|would install' | head -80
uv run devboost install macos-extras ios voxtype-arabic android-emulator --dry-run 2>&1 | grep -c 'would install'
```
Expected: every `macos-desktop` module and `voxtype` appears as `would install` (or already installed). No `unsupported-os` appears, except `KNOWN_GAPS` members if M4 has not merged.

- [ ] **Step 3: Install the desktop**

```bash
uv run devboost install macos-desktop voxtype
uv run devboost permissions        # opens each System Settings pane; grant, then confirm per module
```
Expected:
- Every module ends `ok`, or `blocked` only with a `needs-user: grant permissions` detail. Those clear once the grants are done and `devboost permissions --confirm <module>` has run for each.
- Re-running `devboost install macos-desktop voxtype` reports everything `already-installed`.

- [ ] **Step 4: §0 behavioural checks on macOS 27.** Record each result in the PR description.

```bash
sw_vers -productVersion                                     # 27.x
# Thaw (D2): open Thaw, hide two menu-bar items, quit + relaunch Thaw → they stay hidden; no crash in Console.
# AeroSpace: Ctrl+Alt+2 switches workspace; Ctrl+Alt+Shift+1 moves a window; then:
aerospace list-workspaces --all && aerospace reload-config --dry-run --no-gui
# AltTab: hold ⌥, press ⇥ → switcher with window thumbnails (needs Screen Recording).
# Raycast opens; Stats shows in the menu bar; MonitorControl (only with an external display).
# Quick Look: select a .md and a .py file in Finder, press Space → rendered / highlighted.
duti -x md | tail -1; duti -x py | tail -1                  # dev.zed.Zed (Task 8 Step 5 decisions applied)
# Screenshots: ⌘⇧4, drag, then:
osascript -e 'clipboard info' | grep -i png                 # «class PNGf» → target=clipboard works (D8)
defaults read com.apple.screencapture target                # clipboard
```
If Thaw misbehaves, set `Thaw.max_macos = (26, 99)` in `macos_apps.py`, add a test asserting it is gated on 27, rerun Step 1, and commit `fix(macos): gate Thaw off on macOS 27 until upstream support is stable`. `doctor`'s `version-gated` line then lists it. Do the same for AeroSpace and AltTab if they fail.

- [ ] **Step 5: System settings and the real revert**

```bash
sysctl kern.maxfiles kern.maxfilesperproc; launchctl limit maxfiles   # 524288 (launchctl may stay lower: D11)
zsh -lic 'ulimit -n'                                                  # 524288
/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate      # enabled
tmutil isexcluded ~/Library/Caches ~/.npm 2>/dev/null                 # [Excluded] for existing paths
launchctl print "gui/$(id -u)/dev.devboost.tm-exclusions" | head -3
cat ~/.local/state/devboost/macos-defaults.prev.json | head -20       # prior values, as recorded before the first write
uv run devboost revert macos-defaults tilesize
defaults read com.apple.dock tilesize                                 # the Task 0 baseline value (or "does not exist")
uv run devboost install macos-defaults                                # re-applies; tilesize 48 again
```
Expected: each line matches its comment. The revert restores the Task 0 baseline for `tilesize` and leaves every other key applied.

- [ ] **Step 6: Voxtype**

Run the Task 10 Step 5 checks. Then hold Right Option in a text field, say "hello world", and release: the text is typed. Then:
```bash
uv run devboost install voxtype-arabic
```
Run the Task 11 Step 5 checks (Ctrl+Alt+D Arabic round trip, RSS back down after 70 s).

- [ ] **Step 7: iOS and extras**

```bash
uv run devboost install ios              # in this terminal; xcodes prompts for the Apple ID / 2FA
uv run devboost install maccy linearmouse android-emulator
uv run devboost install macos-extras --dry-run
```
Expected:
- `xcode` and `ios-tooling` end `ok`. If no Apple ID is available in the session, they end `blocked` with the `needs-user` detail from D19. That is an accepted outcome: record it, and the owner runs `devboost install ios` later.
- `xcrun simctl list runtimes | grep 'iOS 27'` is non-empty when `ok`.
- The Task 14 Step 5 emulator check passes.

- [ ] **Step 8: Doctor**

```bash
uv run devboost doctor
```
Expected: `firewall` ok, the WARN/hint lines per D22, `version-gated` = `none` on 27, and `permissions` listing nothing outstanding.

- [ ] **Step 9: Linux regression** (spec §9: shared changes also run Fedora + Ubuntu)

`base` now contains `voxtype`, and `catalog.toml` / `plan.py` changed. Run the repo's Linux VM test for Fedora and for Ubuntu with the `full` profile, as `docs/vm-testing.md` describes (`scripts/vm-test.sh`):
- On a **GUI** VM: `voxtype` ends `ok`, `systemctl --user is-enabled voxtype.service` = `enabled`, and `id -nG | grep -w input`.
- On a **headless** VM: `voxtype` is `skip (headless)`.
- Nothing else changes status compared with the last green run.

If no GUI Linux VM is available, record "Linux voxtype install exercised by unit tests only" as a Known gap in `docs/macos-primer.md` §8.

- [ ] **Step 10: Finish**

Rebase on `origin/main`, re-run Step 1, resolve M4 line conflicts (keep both sides), then use `superpowers:finishing-a-development-branch`. The PR description lists: the §0 results (Steps 4–7), D2/D13/D14/D17 outcomes, and any decision changed during execution. No AI attribution in commits or the PR body.

---

## Self-review (done while writing this plan)

- **Spec coverage:**
  - §0 → Tasks 5/6/8/10/11/12 verification steps + Task 18 Step 4.
  - §2 macOS-only modules → Tasks 3, 5, 6, 8, 12.
  - §2 `voxtype` → Tasks 10 and 11. `android-emulator` → Task 14. Profiles → Tasks 3/6/8/10/12/13/15. TCC → Tasks 6/10/13.
  - §2 `macos-defaults` table + snapshot/revert → Tasks 2–4.
  - §3 AeroSpace → Task 7.
  - §8 desktop half → Task 16.
  - §9 `macos-defaults` tests + contract over the opt-in sets → Tasks 3/15.
  - §10 primer → Task 17. §11 outcome → Task 18.
  - Not in M5 (owned elsewhere): brew/CLT/Rosetta/Docker/pass doctor lines (M1/M3/M4); `aerospace-config` as a module (spec lists it "via dotfiles", so the `dotfiles` module applies it).
- **Placeholder scan:** the only "placeholder" is the deliberate, user-facing hotkey block in the Voxtype config (D16), required by the brief. Conditional steps (A2/A3 fallbacks) carry full code.
- **Type/name consistency:**
  - `Value` / `Kind` (Task 2) are used unchanged in Tasks 3 and 16.
  - `CaskInstall(cask, launch)` equality is used by the Task 6/13 tests.
  - `model_file` / `download_model` / `ARABIC_MODEL` / `BUNDLE_ID` are shared by Tasks 10/11.
  - `xcode_pin().min_macos: tuple[int, int]` is compared with `macos_version()` in Task 12.
  - `firewall_enabled` (Task 5) is reused in Task 16.
  - `render_template` (Task 7) is reused in Task 10.
- **Hermeticity:**
  - No test runs `defaults`, `launchctl`, `tmutil`, `duti`, `xcodes`, `socketfilterfw` or `brew` for real. The one subprocess test runs the sweep script against a fake `tmutil` on a temp PATH.
  - The chezmoi render tests skip without chezmoi. HOME/XDG come from the autouse `_tmp_home`.
