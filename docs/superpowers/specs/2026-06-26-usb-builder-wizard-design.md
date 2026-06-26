# `devboost usb` — Interactive Bootable-USB Builder — Design

**Status:** Draft spec (not yet approved for implementation)
**Date:** 2026-06-26
**Author:** brainstorming session
**Constitution:** aligns with v3.0.1 (typed Python + Typer; bash only as the non-logic
bootstrap stub; pytest + `mypy --strict` + ruff gates)
**Builds on:** the typed engine (`specs/014-python-engine-core`), the verified Ventoy
injection loop (`ventoy/ks.cfg` + `devboost-firstboot.service` + `devboost-<arch>.tar.gz`).

---

## 1. Summary

Add a typed-Python Typer command, **`devboost usb`**, that builds a complete bootable USB from
the terminal — interactively (a `questionary` wizard, every question with a default) or fully
scripted (one flag per question). It **replaces** `ventoy/make-usb.sh` (removing another bash file).
It downloads and caches the required boot artifacts (Fedora ISO + the frozen `devboost` binary +
Ventoy), lays out the Ventoy USB, and offers optional extras (additional ISOs, standalone
installers) and — as a later phase **within this spec** — an offline dnf+flatpak package mirror.

**One spec, two implementation phases (nothing deferred to a separate spec):**
- **Phase 1** — wizard + boot artifacts + caching + optional extras; replaces `make-usb.sh`.
- **Phase 2** — offline dnf+flatpak mirror + an offline-aware firstboot.

---

## 2. Decisions locked (brainstorming)

| # | Question | Decision |
|---|----------|----------|
| 1 | Download scope | **Boot artifacts mandatory; everything else optional** (wizard toggles, default off). |
| 2 | Offline mirror | **In this spec, as Phase 2** (not a separate future spec). Honest scope: dnf + flatpak only (§7). |
| 3 | Mechanism | **Ventoy** (the project's existing multi-ISO approach), not raw `dd`. |
| 4 | Replace `make-usb.sh`? | **Yes** — `devboost usb` is the typed replacement (furthers minimal-bash). |
| 5 | Interactive lib | **`questionary`** (context7 `/tmbo/questionary`, High rep) — `select`/`checkbox`/`text`/`path`/`confirm`, all with defaults + validation. |
| 6 | Downloads | **stdlib `urllib`** (no new HTTP dep, consistent with the constitution) + a `rich` progress bar (`rich` is already a Typer dep). |
| 7 | Cross-arch | Supported by **downloading** the matching ISO/binary (PyInstaller can't cross-compile); the wizard notes it. |
| 8 | Caching | `--cache-dir` (default: a temp dir — "caching in temp"); keyed by name+SHA256; re-runs skip the ~2 GB ISO re-download. |

---

## 3. Goals / Non-goals

**Goals**
- One command, from a clean terminal, to a bootable dev-boost Ventoy USB.
- Interactive (defaults everywhere) **and** non-interactive (flags) from the same config.
- Download + SHA256-verify + cache the Fedora ISO, the frozen binary, and Ventoy.
- Safe: only a removable, whole, unmounted disk; explicit wipe confirmation.
- Optional extras (multi-boot ISOs, installers) and (Phase 2) an offline dnf+flatpak mirror.
- Typed, tested (builder behind `Executor` + `Downloader` seams), `mypy --strict` + ruff clean.

**Non-goals**
- Not a 100%-offline installer — only dnf+flatpak are mirror-able (§7); mise/npm/github/curl
  tools still need network (documented).
- Not raw single-ISO `dd` writing (Ventoy multi-boot is the model).
- Not a GUI — terminal only.
- Not cross-compiling the binary (non-host arch downloads the release asset).

---

## 4. Architecture — wizard ⟂ builder

Two cleanly separated units (the house DI pattern), so the command is interactive, scriptable,
and testable:

```
cli/usb.py            # the `devboost usb` Typer command: flags + (if interactive) run the wizard → UsbBuildConfig → builder
usb/config.py         # UsbBuildConfig (Pydantic) — every decision in one typed value object
usb/wizard.py         # questionary prompts; thin; fills a UsbBuildConfig (each Q has a default)
usb/builder.py        # takes UsbBuildConfig, runs Stages over ctx.ex + a Downloader
usb/download.py       # Downloader Protocol + UrllibDownloader (urllib + rich progress) + FakeDownloader
usb/cache.py          # Cache: name+sha256 → path under --cache-dir (default temp); verify+reuse
usb/devices.py        # list/validate removable block devices (lsblk via Executor); safety guards
usb/stages.py         # the ordered stages (boot artifacts, extras, mirror)
```

- **`UsbBuildConfig`** (Pydantic): `device`, `arch`, `iso` (id+url+sha256), `profiles`, `secrets_path`,
  `extra_isos`, `installers`, `offline_mirror: bool`, `cache_dir`, `assume_yes`.
- **Wizard** fills it via `questionary`, each prompt seeded with a default; **CLI flags** set the same
  fields and skip the corresponding prompt → `devboost usb --device … --iso … --yes` is fully
  non-interactive.
- **Builder** runs stages over the injected `Executor` (all subprocess: `ventoy`, `lsblk`, `cp`,
  `mount`) and the injected `Downloader`. No prompts, no globals → unit-testable with fakes.

---

## 5. The wizard (Phase 1) — each step has a default

1. **Target device** — `questionary.select` over removable disks (size + model from `lsblk -dn`),
   then the ported `make-usb.sh` guards (whole disk, `RM=1`, unmounted) + a typed-`yes` wipe confirm.
2. **Architecture** — default host arch; `x86_64`/`aarch64`.
3. **Fedora ISO** — `select` a version (default Fedora-44); resolve its URL + published SHA256;
   download (cached) and verify.
4. **devboost binary** — if `dist/devboost-<arch>` exists for the host arch, use/rebuild it
   (`build-bundle.sh` equivalent); else download the release asset. Produce the injection tarball.
5. **Profiles for firstboot** — `checkbox` (default `full`); written into the staged `ks.cfg`.
6. **Secrets** — `path` to `secrets.age` (default: skip).
7. **Optional** (`confirm`, default No each): extra ISOs · installers · offline mirror (Phase 2).

The wizard returns a `UsbBuildConfig`; the builder does the rest.

## 6. Boot-artifact + extras stages (Phase 1)

- **Mandatory boot stage:** `ventoy -i <device>` (guarded) → mount VTOY → lay out `ventoy/ventoy.json`,
  `Bootstrap/ks.cfg` (with chosen profiles), `Bootstrap/devboost.tar.gz` (injection archive),
  optional `Bootstrap/secrets.age`. This is the existing, verified loop — now driven from Python.
- **Extra ISOs (optional):** add local/downloaded ISOs into `ISO/` for Ventoy's multi-boot menu.
- **Installers (optional):** stage standalone installers into `Installers/`.

## 7. Offline mirror (Phase 2 — in this spec)

**Honest scope:** a *complete* offline install isn't achievable with today's modules — several fetch
from `mise` (aqua/npm/cargo backends), npm, GitHub releases, and `curl|sh` at install time. Phase 2
mirrors the **dnf + flatpak** majority (all system/base packages + every Flathub GUI app) and makes
firstboot offline-aware for those; the rest is documented as network-required.

- **dnf:** resolve the package set for the chosen profiles (the `pkg.install` names across the
  selected modules, gathered via a typed introspection of the catalog) and `dnf download --resolve`
  / `reposync` into `Bootstrap/repo/dnf/`; generate repo metadata (`createrepo_c`).
- **flatpak:** `flatpak create-usb` / bundle the app set into `Bootstrap/repo/flatpak/`.
- **firstboot `--offline`:** point dnf at the local repo and flatpak at the local remote; modules
  whose installs require network (mise/npm/github/curl) are **skipped with a clear "needs network"
  report** under `--offline` (verify stays red for them, surfaced in the summary).
- The wizard warns up front about size (~tens of GB) and the documented gaps.

> Phase 2 introduces a small typed "what packages does this profile install?" introspection over the
> catalog. Because modules are now typed Python, this is a structured query (collect `pkg`/`flatpak`
> primitive calls), not log-scraping — a direct benefit of the migration.

## 8. Caching & downloads

- **`Downloader`** Protocol → `UrllibDownloader` (stdlib `urllib` + a `rich.progress` bar) +
  `FakeDownloader` (tests). One seam, like the engine's `Executor`/`github` HTTP.
- **`Cache`:** files keyed by `<name>-<sha256>`; `--cache-dir` defaults to a temp dir (the
  "caching in temp"), `--cache-dir ~/.cache/devboost` for persistence. A cache hit verifies the
  checksum and reuses (skips the big ISO re-download); a mismatch re-fetches.

## 9. Safety, errors, testing

- **Safety:** every destructive action runs through `ctx.ex`; device guards reject
  non-removable/partition/mounted targets; explicit `yes` confirm; `--yes` for automation.
- **Errors:** a typed `UsbError` hierarchy (`DeviceError`, `DownloadError`, `VentoyError`,
  `MirrorError`); a failed stage names the device/file/command.
- **Testing (constitution gates):** the builder + each stage tested with `FakeExecutor` +
  `FakeDownloader` — cache hit/miss, bad checksum, device-guard rejections, config→stage
  orchestration, ks.cfg profile injection, mirror package-set introspection. The wizard
  (`questionary`) is thin and excluded from unit tests. `mypy --strict` + ruff clean.

## 10. Phasing (one spec, two build phases)

| Phase | Scope |
|---|---|
| **P1** | `UsbBuildConfig` + wizard + `Downloader`/`Cache` + device guards + boot-artifact stage + extras; **delete `ventoy/make-usb.sh`**; `devboost usb` wired into the CLI. |
| **P2** | Catalog package-set introspection + dnf reposync + flatpak bundles + offline-aware firstboot (`--offline`) + the wizard's offline-mirror step. |

## 11. Constitution alignment

Typed Python + Typer; stdlib HTTP; no new heavy deps (questionary + rich; rich already present).
Bash unchanged at the boundary (`get.sh` + Kickstart `%post`); `make-usb.sh` is **removed**, not
ported as bash. `mypy --strict` + pytest + ruff gates apply. Adds `questionary` to `pyproject.toml`.

## 12. Open questions (resolve in the plan)

- Fedora ISO source-of-truth for URLs/checksums (mirror list vs a pinned `getfedora.org` path) and
  which ISO edition (Everything/netinst for the Kickstart path vs Workstation Live).
- Exact mechanism to enumerate a profile's dnf/flatpak package set from the typed catalog (a small
  read-only "describe" pass over modules vs a declared package manifest per module).
- Whether `devboost usb` requires root for `ventoy`/mount, or shells those specific steps via `sudo`
  through the executor.
