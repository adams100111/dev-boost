# Ubuntu Parity & Portable Tiers (Plan 2) — Design

**Status:** Draft spec (approved in brainstorming; not yet committed — lands on the impl branch)
**Date:** 2026-06-25
**Builds on:** `docs/superpowers/specs/2026-06-25-portable-two-tier-installer-design.md` (Plan 1, merged `3df13f1`)
**Engine:** typed-Python `devboost` under `engine/` (constitution v2.0.0)

---

## 1. Summary

Plan 1 shipped the typed engine + `terminal`/`devtools` profiles, but the profile *data* was Fedora-first. Plan 2 makes both tiers genuinely portable so `devboost terminal` works unattended on a bare **Ubuntu/Debian VPS** (and `devtools` on an Ubuntu dev box), by:

1. **Decoupling `chezmoi` from `secrets`** via a clean single-responsibility split, so `terminal` no longer transitively pulls Fedora-only secrets provisioning.
2. **Fixing the 5 Fedora-only terminal modules** to portable install paths.
3. **Adding `[fallback]` ladders** where apt is too old/missing.
4. **Giving `docker` a Debian path** so `devtools` (which needs it via `ddev`) installs on Ubuntu.
5. **Hardening the engine**: a cycle-guard in `profile.expand` (the deferred Plan-1 finding I-2).

The opus review over-estimated the gap: **24 of 33** terminal modules already carry `debian` keys. The real work is the 5 Fedora-only modules, the coupling, the fallback ladders, and the engine guard.

---

## 2. Decisions locked (brainstorming)

| # | Decision |
|---|----------|
| 1 | **chezmoi split (Option B — best/architectural)**: `chezmoi` = binary-only (portable); new `chezmoi-repo` = remote clone+secrets (base/zero-config only); `dotfiles` = local apply. |
| 2 | Fix `starship`/`fresh`/`dotfiles`/`bash-config` to portable `default`/`debian`. |
| 3 | **ghostty: add an Ubuntu path (option i — "gui first")** so Ubuntu desktops get the GUI terminal (stays `gui=true`, still headless-skipped). |
| 4 | `docker` gets a `debian` install path; `ddev` keeps `requires=["docker"]`; docker stays **only** in devtools. |
| 5 | Add `[fallback]` ladders (mise `aqua:`/`cargo:`/`github:`) to terminal modules whose apt package is missing/stale on older Ubuntu. |
| 6 | Add the `expand` cycle-guard (Plan-1 finding I-2). |
| 7 | **One cohesive plan** (engine guard + data parity together). |

---

## 3. Component design

### 3.1 chezmoi single-responsibility split (root-cause fix for I-1)
Today `modules/chezmoi/` installs the binary **and** clones the remote dotfiles repo, and hard-requires `secrets`. Split into:

- **`chezmoi`** — *install the binary only.*
  - `requires = []`; `[install] default` = official chezmoi install script (or mise); OS-agnostic.
  - `verify = "command -v chezmoi"`.
  - Portable; safe on any box. Used by `terminal`, `devtools` (transitively via dotfiles), and `base`.
- **`chezmoi-repo`** (new module) — *provision the remote dotfiles repo.*
  - Inherits today's `chezmoi init --apply <repo>` clone logic (the credential-dependent part).
  - `requires = ["chezmoi", "secrets"]`; member of `base` (and the zero-config path) **only** — never `terminal`.
  - Clone remains non-blocking (as today).
- **`dotfiles`** — *apply the curated local dotfiles.*
  - `[install]` retagged `fedora → default` (`chezmoi apply --source <repo>/dotfiles` is OS-agnostic).
  - `requires = ["chezmoi", "starship", "atuin", "zoxide", "direnv"]` (adds explicit `chezmoi`).

**Net:** `expand(["terminal"])` no longer contains `secrets`. Zero-config/`base` behavior is unchanged because `base` gains `chezmoi-repo` (which carries the old clone+secrets requirement).

> Profile/module name-collision rule ([[profile-module-name-collision]]): `chezmoi-repo` is not a profile name — safe.

### 3.2 The 5 Fedora-only terminal modules → portable
- **`starship`** → `[install] default` = official `https://starship.rs/install.sh` (any distro); keep Fedora dnf as the `fedora` fast-path.
- **`fresh`** → add `debian`/`default` using its existing script→cargo fallback chain.
- **`dotfiles`** → `default` (see 3.1).
- **`bash-config`** → `default` (verify-gate meta-module; install is effectively a no-op + verify).
- **`ghostty`** → add a `debian` path (official `.deb`/snap) so Ubuntu desktops get it; keep `fedora` COPR; remains `gui=true` (headless-skipped).

### 3.3 devtools → Ubuntu
- **`docker`** → add `[install] debian` = official Docker apt repo (`docker-ce` + compose plugin) mirroring the Fedora script; keep service-enable + group-add idempotent + verify unchanged.
- `ddev` unchanged (`requires=["docker"]`, legitimate). docker never enters `terminal`.

### 3.4 `[fallback]` ladders (apt-too-old safety net)
Add `[fallback]` to terminal modules whose Ubuntu apt package is absent/stale on 22.04:
`atuin, delta, lazygit, dust, duf, sd, fastfetch, tealdeer, btop, fresh, starship` (eza, zoxide done in Plan 1).
Prefer `mise = "aqua:<owner/repo>"`; `cargo:`/`github:` where no aqua entry. Exact backends pinned from live context7/registry during implementation. The engine ladder (`resolve_steps`) already consumes these.

### 3.5 Engine: `expand` cycle-guard (I-2)
In `engine/devboost/profile.py::expand`, track an in-progress/seen set in `add_module`; on re-entry into a module already on the current path, raise `graph.DependencyCycle` (import or mirror the type) instead of recursing. Keeps `toposort`'s cycle detection reachable for transitive-requires cycles.

---

## 4. Testing (both suites green = merge gate, per constitution v2.0.0)

**Python engine (pytest + mypy --strict):**
- Parameterized: for **every** module in the real `terminal` profile, `resolve_steps(mod, UBUNTU)` returns a **non-empty** ladder (assert none → `unsupported-os` on Ubuntu).
- `expand(["terminal"], …)` does **not** contain `secrets`.
- `expand(["devtools"], …)` contains `docker`, reached via `ddev`; `docker` manifest has a `debian` key.
- Cycle-guard: a synthetic A→B→A module set makes `expand` raise `DependencyCycle` (not RecursionError).
- Headless unchanged: ghostty/nerd-fonts still skip when headless.

**bats (existing bash engine):**
- Stays green (target ≥1118). Move `chezmoi` clone tests → `chezmoi-repo` tests; keep chezmoi-binary tests on `chezmoi`.
- Add a `docker` debian-path test; add `chezmoi-repo` membership in `base` (and absence from `terminal`).
- Profiles drift-gate (README table) regenerated for any new module.

---

## 5. Out of scope (later plans)
- **get.sh** public `curl | bash` bootstrap + frozen-binary bundle (Plan 3).
- BATS→pytest migration of the bash engine (Plan 4).
- macOS fallback parity (schema already supports `macos`; not a goal here).

---

## 6. Risks
- **Touching existing bats-covered modules** (`chezmoi` split, `docker` debian, `dotfiles`/`starship` retag). Mitigation: additive where possible; move (not delete) clone tests to `chezmoi-repo`; run the full bats suite as a gate; keep the bash engine's behavior for `base`/zero-config identical.
- **`base` profile composition change** (adds `chezmoi-repo`): must reproduce today's zero-config clone behavior exactly — verify via the existing chezmoi/secrets bats.
- **Fallback backend accuracy**: pin each `mise`/`cargo`/`github` backend from live registry/context7, not memory.

---

## 7. Decomposition note
Cohesive as one plan, but naturally ordered: **(A)** engine cycle-guard → **(B)** chezmoi split + dotfiles/base rewiring → **(C)** 5 Fedora-only fixes + ghostty Ubuntu → **(D)** docker debian → **(E)** fallback ladders → **(F)** tests. The writing-plans step turns these into TDD tasks.
