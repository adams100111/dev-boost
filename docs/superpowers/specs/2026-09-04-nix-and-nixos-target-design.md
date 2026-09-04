# Nix on Fedora + NixOS as a second target — design

**Date:** 2026-09-04
**Status:** Draft for review
**Motivation (user):** Keep Fedora primary; *also* serve NixOS and offer Nix-managed apps/config as a
second option. Not a constitution-level pivot — an additive second target.

---

## 1. Context and mission fit

dev-boost today is an **imperative configuration manager**: a typed-Python engine (`Executor` seam,
`Installer` Protocol, ~100 verify-guarded `Module`s, `OsMap` per-OS data) that *mutates a mutable
Fedora* into a fully-configured developer workstation, shipped as a frozen per-arch binary and an
unattended Ventoy/Kickstart USB. The DoD is "builds out of the box: Laravel/ddev, .NET+Aspire,
Python/uv, Next.js, RN+Expo Android" plus editors, GUI apps, desktop, and chezmoi-restored dotfiles.

A large fraction of that engine's hardest work re-implements, imperatively, guarantees a declarative
Nix world provides by construction: `devboost.lock` ≈ `flake.lock`; snapper+grub-btrfs ≈ atomic
generations; the `verify()`/idempotency loop ≈ declarative convergence; `diff`/`export`/mise-drift ≈
"there is no drift." The roadmap's own expensive lesson — *"the whole USB→install chain was a stack of
individually-buggy layers, each hiding the next"* and *"the full end-to-end has never completed once"*
— is exactly the imperative-non-convergence bug class that declarative provisioning eliminates.

This design adds Nix/NixOS **without** discarding the Fedora engine and **without** falling into
imperative-Nix (running `nix profile install` per module — an anti-pattern that keeps the fragility
and gains none of Nix's benefits).

## 2. Two targets, one shared declarative core

The load-bearing insight: **Home Manager configuration is declarative Nix that runs in both worlds** —
standalone on Fedora *and* as a module inside a NixOS flake. So we write the reusable part (the user
environment) once, as declarative Nix, and consume it from two delivery targets. Nothing is
"transpiled" or generated from the imperative modules; the shared part is authored directly as Nix
with full Nix tooling (`nix flake check`, editor LSP, `nixpkgs-fmt`).

```
        ┌─────────────────────────────────────────────┐
        │   Home Manager config  (the shared core)     │  written ONCE, declarative Nix
        │   dotfiles · CLI tools · per-project devshells│
        └───────────────┬───────────────────┬──────────┘
                        │                   │
      Target B ─────────┘                   └───────── Target A
   NIX + HOME MANAGER ON FEDORA                    NIXOS  (second OS)
   opt-in `nix` profile in the EXISTING            a flake importing the SAME HM core,
   Python engine. Fedora keeps OS, drivers/        plus configuration.nix, hardware,
   GPU/nvidia-MOK, GUI apps (Flatpak), Secure      lanzaboote (Secure Boot), GNOME.
   Boot. Nix/HM owns dotfiles + CLI + devshells.
```

### Division of labor

| Concern | Target B (Nix on Fedora) | Target A (NixOS) |
|---|---|---|
| OS base, kernel, systemd | Fedora (unchanged) | NixOS (`configuration.nix`) |
| Drivers / GPU / nvidia Secure Boot | **Fedora** (existing `gpu-detect`, MOK/akmods) | `hardware.nvidia` + `nixos-hardware`; **lanzaboote** for Secure Boot |
| GUI apps | **Flatpak** (unchanged — better than Nix GUI on Fedora) | Flatpak or nixpkgs (decide per app) |
| Dotfiles | **Home Manager** (replaces chezmoi *for this profile*) | Home Manager (same core) |
| CLI + dev tooling | Home Manager + `nix develop` devshells | same |
| Dev stacks (.NET, Android, uv…) | Fedora-native (mise/dnf) **or** Nix devshells — mix | Nix (with `nix-ld`/FHS shims where needed) |
| Rollback | Fedora snapper + Nix generations (user env) | NixOS generations (whole system) |

## 3. Validated facts (2026-09, current sources)

- **Nix on Fedora 44 is first-class.** Fedora 44 (our exact target) ships Nix in-repo:
  `sudo dnf install nix` + `systemctl enable --now nix-daemon` yields **multi-user daemon mode with
  SELinux fully enforcing**. The historic `/nix`-store SELinux pain and third-party installer hacks are
  gone. → The Target-B bootstrap is a trivial fit for existing engine primitives (`pkg` + `systemd`).
  Sources: Fedora Change page "Nix package tool"; "Setting up Nix on Fedora 44".
- **Home Manager standalone** runs root-free on non-NixOS, manages dotfiles as symlinks, and cleans up
  old links on `switch`. Caveats: Nix-language learning curve, occasionally cryptic errors, and
  **GUI-app desktop integration is the known soft spot** → keep GUI apps on Flatpak for Target B.
  Source: NixOS Wiki "Home Manager".
- **lanzaboote reached v1.0.0** with auto-generate + auto-enroll Secure Boot keys on first boot
  (requires UEFI + systemd-boot). Roughly parity with Fedora's one-time MOK screen, different
  mechanism. Source: NixOS Wiki "Lanzaboote".

## 3a. Prior art / precedent

- **omarchy-nix** (`henrysipp/omarchy-nix`) — a NixOS flake that reimplements the opinionated
  Arch/Hyprland "Omarchy" dev setup in Nix. It exposes **both** a `nixosModules.default` and a
  `homeManagerModules.default` — i.e. the exact two-module shape of Target A in §2 (system config +
  shared Home Manager core). **Confirms the shape.** It also confirms the risk: it is NixOS-only,
  explicitly disclaims full feature parity ("likely never will be, especially with how fast … feature
  development has been" upstream), and the author has **reverted to native Arch Omarchy and now
  maintains the Nix port passively.** This is the *parity treadmill* — a declarative twin chasing a
  fast-moving imperative upstream. For dev-boost the "upstream" is our own actively-developed Fedora
  engine, so a full NixOS twin would chase our own tail. → reinforces §6/§8: Target A is a throwaway
  VM experiment in v1, **not** a parity commitment.
- **omarchy discussion #987** — a guide for running **Home Manager on top of an imperative distro
  (Arch), coexisting** with the native Omarchy layer. This is Target B's pattern. Two lessons folded
  into this design: (1) an **explicit ownership split** — HM is told *not* to manage the paths the
  native layer owns (e.g. `.config/hypr`, `.config/alacritty`); HM manages a *disjoint* set. (2) a
  **bootstrap gotcha** — HM is not on `PATH` until the first `home-manager switch`, so the bootstrap
  needs explicit PATH handling / a wrapper.

## 4. Why *not* the alternatives

- **Imperative Nix as one more `OsMap` key** (each module shells out to `nix profile install`): keeps
  every imperative-fragility failure mode, discards atomic-generation / single-source-of-truth
  benefits. Widely-reviled anti-pattern. **Rejected.**
- **Generate the flake from the catalog now** (a Python→Nix emitter): premature. The FHS-hostile dev
  stacks are the *unknowns*; you cannot template output whose shape you haven't discovered. And a
  `Module`'s value is its imperative `install()`/`verify()`, which doesn't transpile — only metadata
  does, giving ~30% mechanical leverage while forcing **Nix-in-Python-strings** (loses all Nix
  tooling). Kept as a *future option* (see §7), bought only if hand-maintained parity actually hurts.
- **Fully separate sister project sharing nothing:** risks permanent drift with no path to
  unification. Avoided by sharing the HM core and aligning names.

## 5. Chosen integration model: **hybrid, HM-core-first**

Hand-write real Nix now (full Nix tooling), structured so a generator *could* be retrofitted later:

1. **Author the Home Manager core** as declarative Nix. Mirror the catalog's profile/app names
   (`hm/profiles/cli.nix`, `hm/profiles/shell.nix`, `hm/profiles/dotnet.nix` … matching
   `profiles.toml`) so future generation is a mechanical mapping and parity is auditable by name.
2. **Target B** = a new opt-in `nix` profile in the Python engine: modules `nix` (dnf-install +
   enable daemon, idempotent/verify-guarded) and `home-manager` (bootstrap + `home-manager switch`
   against the in-repo HM core). Legitimate engine work: imperative *bootstrap of a declarative tool*,
   not per-package imperative Nix. GUI apps and drivers stay on the existing Fedora path. The
   `home-manager` module must handle the **PATH bootstrap gotcha** (HM is not on `PATH` until the
   first `switch`) via an explicit path/wrapper. HM and chezmoi **coexist by an ownership split**
   (§10.2): HM manages a declared, *non-overlapping* set of paths; chezmoi keeps the paths it already
   owns; an explicit HM exclusion list prevents the two writing the same file.
3. **Target A** = a `flake.nix` that imports the same HM core and adds `configuration.nix`, hardware
   (`nixos-hardware`, `hardware.nvidia`), lanzaboote, GNOME, and an autoinstall image via
   `nixos-generators` (the declarative parallel to the Ventoy/Kickstart Fedora path).

## 6. Phasing (risk-first)

- **Slice 0 — HM core skeleton + Target B on Fedora.** `nix` + `home-manager` engine modules; HM core
  delivering dotfiles + the `cli`/`shell` tool set on a stock Fedora box. Verifiable immediately, reuses
  all Fedora hardware/GUI investment. Lowest risk, fastest payoff.
- **Slice 1 — first hostile dev stack: `.NET + Aspire`** as a Nix devshell (FHS-hostile but
  well-trodden in nixpkgs). Establishes the `nix-ld`/`buildFHSUserEnv` pattern for later stacks.
- **Slice 2 — Target A minimal NixOS VM.** `flake.nix` importing the HM core + `configuration.nix` +
  GNOME, booting under `nixos-generators` in a VM. No installer USB yet.
- **Slice 3 — NixOS drivers + Secure Boot** (`hardware.nvidia`/`nixos-hardware` + lanzaboote), the one
  area that regresses vs. Fedora; prove auto-enroll on a Secure-Boot VM/box.
- **Final boss (deferred) — `Expo/Android`** on Nix (androidenv, SDK licenses, emulator): the hardest
  terrain, attempted only after the FHS pattern is proven. Explicitly out of scope for v1.

Each slice is independently useful and test-green on its own (constitution §Development Workflow).

## 7. Future option (not now): catalog-driven generation

Once the HM core is proven and stable, a generator *may* emit the name-aligned HM profiles from
`profiles.toml` metadata, collapsing Target B/A config authoring back into the single catalog. Built
**only if** maintaining the HM core in parity with the catalog becomes a real burden (YAGNI). Name
alignment in §5 keeps this cheap to add later.

## 8. Non-goals (v1)

- Making NixOS the primary target or touching the Fedora critical path.
- Imperative per-package Nix in the engine.
- Full DoD parity on NixOS in v1 (Expo/Android deferred; Laravel/Next.js/Python after the pattern).
- Replacing Flatpak GUI apps with Nix on Fedora.
- A NixOS *installer USB* in v1 (VM-first; USB is a later slice mirroring Ventoy/Kickstart).

## 9. Testing & constitution alignment

- **Nix side:** `nix flake check`, `nixos-rebuild build` (no switch) in CI, and a `nixosTest` VM
  assertion for Target A slices. HM core gets a `home-manager build` check.
- **Engine side (Target B modules):** ordinary pytest + `mypy --strict` + ruff over `FakeExecutor`
  recordings, exactly like every other module. The `nix`/`home-manager` modules are verify-guarded and
  idempotent (Principle II). Reproducibility (Principle III) is strengthened, not weakened, by
  `flake.lock`. Fedora remains the reference OS (Principle VI); this adds a target, not a rewrite.

## 10. Open questions for review

1. **Repo location of the Nix code:** in-repo (`nixos/` + `hm/` under dev-boost) vs. a sister repo the
   engine references. Recommendation: **in-repo** initially (single source of truth, one CI), split out
   only if it grows unwieldy.
2. **Dotfiles authority on Target B (chezmoi vs Home Manager):** the omarchy #987 precedent argues
   against "HM replaces chezmoi." Preferred model is **coexistence by ownership split** — chezmoi keeps
   the paths it owns today; HM manages a declared, *non-overlapping* set (its own tools/dotfiles) with
   an explicit exclusion list so the two never write the same file. Reversible and low-risk. Open sub-
   question: which exact paths move to HM in v1 (recommend: only the new Nix-tool dotfiles, chezmoi
   unchanged).
3. **First dev stack:** `.NET+Aspire` recommended for slice 1; confirm vs. preferring a different stack.
4. **GUI apps on Target A (NixOS):** Flatpak (parity with Fedora) vs. nixpkgs. Recommendation: Flatpak
   for parity in v1.
