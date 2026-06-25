# Ubuntu Parity & Portable Tiers — Implementation Plan (Plan 2 of N)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `devboost terminal` install unattended on a bare Ubuntu/Debian VPS and `devboost devtools` on an Ubuntu dev box — by decoupling `chezmoi` from `secrets`, fixing the Fedora-only modules to portable paths, adding `[fallback]` ladders, giving `docker` a Debian path, and hardening `profile.expand` against cycles.

**Architecture:** Pure data + small engine changes. Split the `chezmoi` module by responsibility (binary-only vs remote-clone), retag mis-tagged Fedora-only modules to `default`/`debian`, add `[fallback]` tables consumed by the existing `resolve_steps` ladder, and add one `seen`-guard to `expand`. No engine control-flow rewrite; the bash engine's `base`/zero-config behavior stays identical.

**Tech Stack:** TOML module manifests; bash `install.sh` modules (sourcing `lib/log.sh`+`lib/pkg.sh`); the typed-Python engine under `engine/` (pytest + mypy --strict); BATS for the bash engine.

## Global Constraints

- **Both test suites are the merge gate** (constitution v2.0.0): bash `bats tests/` (target ≥1118 green) AND the Python engine `pytest` (must stay ≥27) + `mypy --strict` clean.
- **Engine + Data separation:** add OS support / tools as TOML data; do not edit engine control flow except the one sanctioned `expand` guard (Task 1).
- **`terminal` profile MUST NOT transitively include `secrets`.** `devtools` MAY include `docker` (only via `ddev`); `docker` MUST NOT be in `terminal`.
- **Profile/module name-collision rule:** a module name must never equal a profile name ([[profile-module-name-collision]]). `chezmoi-repo` is safe.
- **Idempotent & verify-guarded:** every module keeps a `verify`; installs safe to re-run; clone stays non-blocking.
- **Commits:** Conventional Commits, NO Claude/Anthropic attribution, no `Co-Authored-By`.
- **Python venv:** `cd /home/dev/repos/dev-boost/engine && . .venv/bin/activate` for pytest/mypy. **bash suite:** `bats tests/` from repo root.
- **Pin install commands from live sources** (context7 / `mise registry` / `gh release`), never memory, where a step says so.

**Out of scope (later plans):** get.sh + frozen-binary bundle (Plan 3); BATS→pytest migration (Plan 4); macOS fallback parity.

---

## File Structure

```
engine/devboost/profile.py            # MODIFY: add seen-guard to expand()
engine/tests/test_profile.py          # MODIFY: cycle-raises-DependencyCycle test
engine/tests/test_ubuntu_parity.py    # CREATE: terminal resolves on Ubuntu; excludes secrets; devtools docker
modules/chezmoi/module.toml           # MODIFY: binary-only; requires=[]; verify=command -v chezmoi
modules/chezmoi/install.sh            # MODIFY: install binary only (portable), no init/clone
modules/chezmoi-repo/module.toml      # CREATE: requires=[chezmoi,secrets]; clone
modules/chezmoi-repo/install.sh       # CREATE: moved init/clone logic
modules/dotfiles/module.toml          # MODIFY: install default; requires add chezmoi
modules/starship/module.toml          # MODIFY: add default install
modules/starship/install.sh           # MODIFY: dnf fast-path else official installer
modules/fresh/module.toml             # MODIFY: add debian/default
modules/bash-config/module.toml       # MODIFY: add default
modules/ghostty/module.toml           # MODIFY: add debian
modules/ghostty/install.sh            # MODIFY: debian branch (.deb from ghostty-ubuntu)
modules/docker/module.toml            # MODIFY: add debian
modules/docker/install.sh             # MODIFY: debian branch (official apt repo)
modules/<tool>.toml (×N)              # MODIFY: add [fallback]
profiles.toml                         # MODIFY: base gains chezmoi-repo
README.md                             # MODIFY: regenerated profiles drift-gate table
tests/chezmoi.bats                    # MODIFY: keep binary tests; remove clone tests
tests/chezmoi-repo.bats               # CREATE: moved clone tests
tests/docker.bats                     # MODIFY: add debian-path test
tests/profiles.bats                   # MODIFY: chezmoi-repo in base, not terminal
```

---

## Task 1: Engine — `expand` cycle-guard (finding I-2)

**Files:**
- Modify: `engine/devboost/profile.py`
- Test: `engine/tests/test_profile.py`

**Interfaces:**
- Consumes: `Module` (from `manifest.py`), `DependencyCycle` (from `graph.py`).
- Produces: `expand(...)` now raises `devboost.graph.DependencyCycle` on a `requires` cycle instead of recursing infinitely.

- [ ] **Step 1: Write the failing test** — add to `engine/tests/test_profile.py`:

```python
def test_expand_raises_on_requires_cycle() -> None:
    from devboost.graph import DependencyCycle
    from devboost.manifest import Module

    def _m(name: str, requires: tuple[str, ...]) -> Module:
        return Module(name, "cli", "true", requires, {"fedora": "x"}, {}, False)

    mods = {"a": _m("a", ("b",)), "b": _m("b", ("a",))}
    import pytest
    with pytest.raises(DependencyCycle):
        expand(["a"], {}, mods)
```

- [ ] **Step 2: Run it — verify it fails**

Run: `cd engine && . .venv/bin/activate && pytest tests/test_profile.py::test_expand_raises_on_requires_cycle -v`
Expected: FAIL — `RecursionError` (or hang) instead of `DependencyCycle`.

- [ ] **Step 3: Implement the guard** — edit `engine/devboost/profile.py`. Add the import at the top (after the existing imports):

```python
from devboost.graph import DependencyCycle
```

Replace the `add_module` inner function in `expand` with a path-tracked version:

```python
    out: list[str] = []
    seen: set[str] = set()
    in_progress: set[str] = set()

    def add_module(name: str) -> None:
        if name not in modules:
            raise KeyError(f"unknown module: {name}")
        if name in seen:
            return
        if name in in_progress:
            raise DependencyCycle(f"requires cycle at module: {name}")
        in_progress.add(name)
        for dep in modules[name].requires:
            add_module(dep)
        in_progress.discard(name)
        seen.add(name)
        out.append(name)
```

(Keep the rest of `expand` — `add_token`, the final loop, the `return out` — unchanged.)

- [ ] **Step 4: Run tests — verify pass + types**

Run: `cd engine && . .venv/bin/activate && pytest tests/test_profile.py -v && mypy`
Expected: all pass (incl. the existing expand tests); mypy `Success`.

- [ ] **Step 5: Commit**

```bash
git add engine/devboost/profile.py engine/tests/test_profile.py
git commit -m "fix(engine): expand() raises DependencyCycle on requires cycle instead of overflowing"
```

---

## Task 2: Split `chezmoi` into binary-only + `chezmoi-repo`

**Files:**
- Modify: `modules/chezmoi/module.toml`, `modules/chezmoi/install.sh`
- Create: `modules/chezmoi-repo/module.toml`, `modules/chezmoi-repo/install.sh`
- Modify: `tests/chezmoi.bats`; Create: `tests/chezmoi-repo.bats`

**Interfaces:**
- Produces: `chezmoi` module = binary-only, `requires=[]`, verify `command -v chezmoi`. `chezmoi-repo` module = init/clone, `requires=["chezmoi","secrets"]`.

- [ ] **Step 1: Slim `modules/chezmoi/install.sh` to binary-only**

Replace its body (keep the shebang + `set` + the two `source` lines) so it installs the binary portably and does NO init/clone:

```bash
#!/usr/bin/env bash
# modules/chezmoi/install.sh — install the chezmoi binary ONLY (portable).
# Init/clone of the remote dotfiles repo lives in the chezmoi-repo module.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME. Idempotent.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

if command -v chezmoi >/dev/null 2>&1; then
  log_skip "chezmoi: binary already installed"
else
  log_info "chezmoi: installing binary"
  mkdir -p "${HOME}/.local/bin"
  # Official installer; OS-agnostic; no prompts; pins into ~/.local/bin.
  sh -c "$(curl -fsLS get.chezmoi.io)" -- -b "${HOME}/.local/bin"
  log_ok "chezmoi: binary installed"
fi
```

- [ ] **Step 2: Retag `modules/chezmoi/module.toml`** (binary-only, no secrets, verify = binary present):

```toml
name        = "chezmoi"
category    = "base"
description = "Install the chezmoi binary (portable, binary-only; remote clone lives in chezmoi-repo)"
requires    = []
profiles    = ["base"]
verify      = "command -v chezmoi"

[install]
default = "bash \"$DEVBOOST_ROOT/modules/chezmoi/install.sh\""
```

- [ ] **Step 3: Create `modules/chezmoi-repo/install.sh`** — move the init/clone logic here verbatim from the old chezmoi script:

```bash
#!/usr/bin/env bash
# modules/chezmoi-repo/install.sh — chezmoi init + clone of the remote dotfiles repo.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME. Requires: chezmoi, secrets.
# Clone uses ~/.git-credentials seeded by secrets; no token on the command line.
# No prompts; idempotent; clone failure is non-blocking.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

if [[ -n "${DEVBOOST_DOTFILES_REPO:-}" ]]; then
  log_info "chezmoi-repo: cloning dotfiles from ${DEVBOOST_DOTFILES_REPO} (via credential store)"
  if chezmoi init --apply "${DEVBOOST_DOTFILES_REPO}"; then
    log_ok "chezmoi-repo: dotfiles cloned and applied"
  else
    log_warn "chezmoi-repo: init/clone failed — dotfiles not synced (non-blocking)"
    return 0 2>/dev/null || exit 0
  fi
else
  log_info "chezmoi-repo: DEVBOOST_DOTFILES_REPO not set — running local init (no clone)"
  if chezmoi init; then
    log_ok "chezmoi-repo: local init succeeded"
  else
    log_warn "chezmoi-repo: local init failed (non-blocking)"
    return 0 2>/dev/null || exit 0
  fi
fi

log_ok "chezmoi-repo: setup complete"
```

- [ ] **Step 4: Create `modules/chezmoi-repo/module.toml`** (carries the old verify of dir-present + requires secrets):

```toml
name        = "chezmoi-repo"
category    = "base"
description = "chezmoi init + clone the remote dotfiles repo (non-blocking); base/zero-config only"
requires    = ["chezmoi", "secrets"]
profiles    = ["base"]
verify      = "[ -d \"$HOME/.local/share/chezmoi\" ]"

[install]
default = "bash \"$DEVBOOST_ROOT/modules/chezmoi-repo/install.sh\""
```

- [ ] **Step 5: Split the bats tests.** In `tests/chezmoi.bats`, **remove** the init/clone/dir tests (every `@test` whose name mentions `init`, `DEVBOOST_DOTFILES_REPO`, `clone-failure`, or `~/.local/share/chezmoi directory`), and update the two `verify`-dir tests: `chezmoi` verify is now just `command -v chezmoi` (drop the dir assertion). Keep: module.toml exists, requires=[] (changed from secrets — update that test's expectation to empty), verify contains `command -v chezmoi`, install references install.sh, success-path installs binary, idempotent verify-guard. Create `tests/chezmoi-repo.bats` with the moved tests, retargeted at `modules/chezmoi-repo/` (init called, repo-arg passed, no-token-on-cmdline, clone-failure non-blocking returns 0 + warn, local-init path, dir exists after init, verify GREEN/RED on dir presence, requires=["chezmoi","secrets"]).

- [ ] **Step 6: Run the bash suite for these two files**

Run: `bats tests/chezmoi.bats tests/chezmoi-repo.bats`
Expected: all green; combined count ≈ the original 22 (tests moved, not lost).

- [ ] **Step 7: Commit**

```bash
git add modules/chezmoi modules/chezmoi-repo tests/chezmoi.bats tests/chezmoi-repo.bats
git commit -m "refactor(chezmoi): split into binary-only chezmoi + chezmoi-repo (clone+secrets)"
```

---

## Task 3: Rewire `dotfiles` + `base`, prove `terminal` excludes `secrets`

**Files:**
- Modify: `modules/dotfiles/module.toml`, `profiles.toml`
- Test: `engine/tests/test_ubuntu_parity.py` (create), `tests/profiles.bats`

**Interfaces:**
- Consumes: the split modules from Task 2.
- Produces: `dotfiles` install `default`, `requires` includes `chezmoi`; `base` profile includes `chezmoi-repo`; `terminal` resolves without `secrets`.

- [ ] **Step 1: Retag `modules/dotfiles/module.toml`** — change `[install] fedora` → `default` and add `chezmoi` to requires:

```toml
requires    = ["chezmoi", "starship", "atuin", "zoxide", "direnv"]
```
```toml
[install]
default = "bash \"$DEVBOOST_ROOT/modules/dotfiles/install.sh\""
```

- [ ] **Step 2: Add `chezmoi-repo` to `base` in `profiles.toml`.** In the `base = [...]` array, add `"chezmoi-repo"` immediately after `"chezmoi"`. (Leave `terminal`/`devtools` unchanged — `terminal` already lists `chezmoi` + `dotfiles`, and neither now requires `secrets`.)

- [ ] **Step 3: Write the failing Python test** — create `engine/tests/test_ubuntu_parity.py`:

```python
from pathlib import Path

from devboost.manifest import load_modules
from devboost.profile import expand, load_profiles

ROOT = Path(__file__).resolve().parents[2]


def _profiles_and_modules():
    return load_profiles(ROOT / "profiles.toml"), load_modules(ROOT / "modules")


def test_terminal_excludes_secrets() -> None:
    profs, mods = _profiles_and_modules()
    resolved = expand(["terminal"], profs, mods)
    assert "secrets" not in resolved
    assert "chezmoi" in resolved and "dotfiles" in resolved


def test_devtools_includes_docker_via_ddev() -> None:
    profs, mods = _profiles_and_modules()
    resolved = expand(["devtools"], profs, mods)
    assert "docker" in resolved
    assert "debian" in mods["docker"].install
```

- [ ] **Step 4: Run it — verify the secrets test passes and docker test fails**

Run: `cd engine && . .venv/bin/activate && pytest tests/test_ubuntu_parity.py -v`
Expected: `test_terminal_excludes_secrets` PASS (after Task 2/this task); `test_devtools_includes_docker_via_ddev` FAIL (no `debian` key on docker yet — fixed in Task 6).

- [ ] **Step 5: Update `tests/profiles.bats`** — add assertions: `chezmoi-repo` is a member of `base`; `chezmoi-repo` is NOT a member of `terminal`; `secrets` is NOT reachable from `terminal` (membership-level check mirroring the bash profile expander if present, else assert the array contents).

- [ ] **Step 6: Run bats profiles**

Run: `bats tests/profiles.bats`
Expected: green.

- [ ] **Step 7: Commit**

```bash
git add modules/dotfiles/module.toml profiles.toml engine/tests/test_ubuntu_parity.py tests/profiles.bats
git commit -m "feat(profiles): base gains chezmoi-repo; dotfiles portable; terminal no longer pulls secrets"
```

---

## Task 4: `starship`, `fresh`, `bash-config` → portable

**Files:**
- Modify: `modules/starship/module.toml`, `modules/starship/install.sh`, `modules/fresh/module.toml`, `modules/bash-config/module.toml`

**Interfaces:**
- Produces: each of these three modules resolves a non-empty install step on `OsInfo(family="debian")`.

- [ ] **Step 1: `starship` — dnf fast-path else official installer.** Replace the dnf line in `modules/starship/install.sh` Step 1 with:

```bash
log_info "starship: installing binary"
if command -v starship >/dev/null 2>&1; then
  log_skip "starship: already installed"
elif [[ "${OS_FAMILY}" == "fedora" ]]; then
  sudo dnf install -y starship
else
  # Official installer; OS-agnostic; -y non-interactive; into ~/.local/bin.
  mkdir -p "${HOME}/.local/bin"
  curl -sS https://starship.rs/install.sh | sh -s -- -y -b "${HOME}/.local/bin"
fi
log_ok "starship: binary installed"
```

Retag `modules/starship/module.toml` `[install]` from `fedora` to `default` (the script branches internally):

```toml
[install]
default = "bash \"$DEVBOOST_ROOT/modules/starship/install.sh\""
```

- [ ] **Step 2: `fresh` — make install OS-agnostic.** `modules/fresh/install.sh` already has a Fedora-rpm → official-script → cargo fallback chain; retag its manifest so it runs on any OS:

```toml
[install]
default = "bash \"$DEVBOOST_ROOT/modules/fresh/install.sh\""
```

Verify the script's non-Fedora branch does not hard-require dnf (read `modules/fresh/install.sh`; it must fall through to the script/cargo path when `OS_FAMILY != fedora`). If it gates the whole script on Fedora, add an `OS_FAMILY` branch so Debian reaches the script/cargo path.

- [ ] **Step 3: `bash-config` — default no-op verify-gate.** Retag `modules/bash-config/module.toml`:

```toml
[install]
default = "true"
```

(It is a meta-module; its value is the `verify` that the rc is wired. `true` is the OS-agnostic no-op.)

- [ ] **Step 4: Run the bash suites for these modules**

Run: `bats tests/shell.bats tests/fresh.bats`
Expected: green (retags are additive to behavior; if a test asserts the `fedora` key specifically, update it to `default`).

- [ ] **Step 5: Commit**

```bash
git add modules/starship modules/fresh/module.toml modules/bash-config/module.toml
git commit -m "feat(modules): starship/fresh/bash-config portable (default install on any OS)"
```

---

## Task 5: `ghostty` Ubuntu path (gui first)

**Files:**
- Modify: `modules/ghostty/module.toml`, `modules/ghostty/install.sh`

**Interfaces:**
- Produces: `ghostty` resolves a `debian` install on Ubuntu desktops; stays `gui=true` (headless-skipped).

- [ ] **Step 1: Confirm the current Ubuntu packaging source.** Ghostty has no official apt package; the de-facto Ubuntu packaging is the community `ghostty-ubuntu` project, which publishes per-release `.deb` assets. Run, to pin the current asset URL pattern (do NOT hardcode from memory):

```bash
gh release view --repo mkasberg/ghostty-ubuntu --json tagName,assets --jq '.tagName, (.assets[].name)'
```

Note the `.deb` asset naming for the current release (e.g. `ghostty_<ver>_amd64_<codename>.deb`). If `gh` is unavailable, fetch `https://api.github.com/repos/mkasberg/ghostty-ubuntu/releases/latest` with curl and read `.assets[].browser_download_url`.

- [ ] **Step 2: Add a `debian` branch to `modules/ghostty/install.sh`.** Wrap the existing Fedora COPR logic in an `OS_FAMILY` switch and add the Debian branch that downloads + installs the matching `.deb` (arch from `dpkg --print-architecture`, Ubuntu codename from `. /etc/os-release; echo "$VERSION_CODENAME"`), idempotent (skip if `command -v ghostty`):

```bash
if command -v ghostty >/dev/null 2>&1; then
  log_skip "ghostty: already installed"
elif [[ "${OS_FAMILY}" == "debian" ]]; then
  log_info "ghostty: installing .deb from ghostty-ubuntu releases"
  _arch="$(dpkg --print-architecture)"
  _codename="$(. /etc/os-release; echo "${VERSION_CODENAME}")"
  _url="$(curl -fsSL https://api.github.com/repos/mkasberg/ghostty-ubuntu/releases/latest \
          | grep -oE 'https://[^"]+_'"${_arch}"'_'"${_codename}"'\.deb' | head -1)"
  if [[ -n "${_url}" ]]; then
    _tmp="$(mktemp --suffix=.deb)"
    curl -fsSL "${_url}" -o "${_tmp}"
    sudo apt-get install -y "${_tmp}"
    rm -f "${_tmp}"
    log_ok "ghostty: installed from ${_url}"
  else
    log_warn "ghostty: no matching .deb for ${_arch}/${_codename} (non-blocking)"
  fi
else
  # ... existing Fedora COPR install logic unchanged ...
fi
```

Retag `modules/ghostty/module.toml` `[install]` to add the debian key (keep `gui = true`):

```toml
[install]
fedora = "bash \"$DEVBOOST_ROOT/modules/ghostty/install.sh\""
debian = "bash \"$DEVBOOST_ROOT/modules/ghostty/install.sh\""
```

- [ ] **Step 3: Run the bats shell/ghostty tests**

Run: `bats tests/shell.bats`
Expected: green; if a test asserts ghostty is fedora-only, update it to allow the debian branch (the stub should exercise `OS_FAMILY=debian` reaching the `.deb` path).

- [ ] **Step 4: Commit**

```bash
git add modules/ghostty
git commit -m "feat(ghostty): Ubuntu .deb install path (gui first); stays headless-skipped"
```

---

## Task 6: `docker` Debian path (devtools on Ubuntu)

**Files:**
- Modify: `modules/docker/module.toml`, `modules/docker/install.sh`
- Test: `tests/docker.bats`; re-run `engine/tests/test_ubuntu_parity.py`

**Interfaces:**
- Produces: `docker` module has a `debian` install key; `test_devtools_includes_docker_via_ddev` passes.

- [ ] **Step 1: Add a `debian` branch to `modules/docker/install.sh`.** Wrap the existing Fedora repo+dnf logic in an `OS_FAMILY` switch; add the Debian branch using Docker's official apt repo (idempotent repo add; ubuntu vs debian from `/etc/os-release ID`):

```bash
if [[ "${OS_FAMILY}" == "debian" ]]; then
  _id="$(. /etc/os-release; echo "${ID}")"        # ubuntu | debian
  _codename="$(. /etc/os-release; echo "${VERSION_CODENAME}")"
  if [[ ! -f /etc/apt/sources.list.d/docker.list ]]; then
    log_info "docker: adding Docker apt repository"
    sudo apt-get update -y
    sudo apt-get install -y ca-certificates curl
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl -fsSL "https://download.docker.com/linux/${_id}/gpg" -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${_id} ${_codename} stable" \
      | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
    sudo apt-get update -y
    log_ok "docker: repository added"
  else
    log_skip "docker: repository already configured"
  fi
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
else
  # ... existing Fedora repo + dnf_install logic unchanged ...
fi
# (the service-enable + usermod -aG docker steps that follow stay shared, after the switch)
```

- [ ] **Step 2: Retag `modules/docker/module.toml`** to declare both keys (both run the same branching script):

```toml
[install]
fedora = "bash \"$DEVBOOST_ROOT/modules/docker/install.sh\""
debian = "bash \"$DEVBOOST_ROOT/modules/docker/install.sh\""
```

- [ ] **Step 3: Add a `tests/docker.bats` debian-path test** — stub `OS_FAMILY=debian` + a fake `/etc/os-release` (ID=ubuntu, VERSION_CODENAME=noble) and assert the install path calls `apt-get install -y docker-ce ...` and adds the docker.list repo idempotently (no duplicate on re-run). Mirror the existing fedora test's stub harness.

- [ ] **Step 4: Run docker bats + the parity python test**

Run: `bats tests/docker.bats` then `cd engine && . .venv/bin/activate && pytest tests/test_ubuntu_parity.py -v`
Expected: docker bats green; both parity tests now PASS.

- [ ] **Step 5: Commit**

```bash
git add modules/docker tests/docker.bats
git commit -m "feat(docker): Debian apt-repo install path; devtools installs on Ubuntu"
```

---

## Task 7: `[fallback]` ladders for apt-stale tools

**Files:**
- Modify: `modules/atuin.toml`, `modules/delta.toml`, `modules/lazygit.toml`, `modules/dust.toml`, `modules/duf.toml`, `modules/sd.toml`, `modules/fastfetch.toml`, `modules/tealdeer.toml`, `modules/btop.toml`, `modules/fresh/module.toml`, `modules/starship/module.toml`

**Interfaces:**
- Produces: each listed module has a `[fallback]` table so `resolve_steps` yields a non-empty ladder on Ubuntu even when apt lacks/staled the package.

- [ ] **Step 1: Pin the backends from the live mise registry** (not memory). For each tool, run:

```bash
mise registry | grep -iE '^(atuin|delta|git-delta|lazygit|dust|duf|sd|fastfetch|tealdeer|tldr|btop|fresh|starship)\b'
```

Record the canonical backend id for each (prefer `aqua:<owner/repo>`; fall back to `cargo:<crate>` or `github:<owner/repo>`). If a tool is absent from the registry, use its `cargo:` crate (e.g. `cargo:du-dust` for dust, `cargo:sd`, `cargo:tealdeer`) or `github:<owner/repo>` release.

- [ ] **Step 2: Add a `[fallback]` table to each module** using the pinned ids. Example shape (use the values from Step 1, do not copy these verbatim without confirming):

```toml
[fallback]
mise = "aqua:atuinsh/atuin"
```

For `delta` the binary/crate is `git-delta`; for `tealdeer` the command is `tldr`. Use the form the engine consumes: `[fallback] mise = "<backend-id>"` (or `script = "<url>"` where mise has no entry).

- [ ] **Step 3: Add the Ubuntu-parity engine test** — append to `engine/tests/test_ubuntu_parity.py`:

```python
import pytest
from devboost.osinfo import OsInfo
from devboost.plan import resolve_steps

UBUNTU = OsInfo("ubuntu", "debian", "x86_64")


def _terminal_modules():
    profs, mods = _profiles_and_modules()
    return [(n, mods[n]) for n in expand(["terminal"], profs, mods)]


@pytest.mark.parametrize("name", [n for n, _ in _terminal_modules()])
def test_every_terminal_module_resolves_on_ubuntu(name: str) -> None:
    profs, mods = _profiles_and_modules()
    steps = resolve_steps(mods[name], UBUNTU)
    assert steps, f"{name} resolves to no install step on Ubuntu (would be unsupported-os)"
```

- [ ] **Step 4: Run the parity test + full engine suite + mypy**

Run: `cd engine && . .venv/bin/activate && pytest -v && mypy`
Expected: every terminal module resolves a non-empty ladder on Ubuntu; full suite green; mypy clean.

- [ ] **Step 5: Commit**

```bash
git add modules engine/tests/test_ubuntu_parity.py
git commit -m "feat(modules): [fallback] ladders so terminal tools resolve on older Ubuntu"
```

---

## Task 8: Regenerate the README drift-gate + full-suite gate

**Files:**
- Modify: `README.md`
- Test: full `bats tests/` + full engine `pytest`

**Interfaces:**
- Produces: README profiles table reflects `chezmoi-repo` in `base`; both suites green.

- [ ] **Step 1: Regenerate the README profiles table.** The repo has a drift-gate (a bats test that the generated `<!-- ... generated profiles ... -->` table matches `profiles.toml`). Update the `base` row to include `chezmoi-repo` (alphabetical position) and add a `chezmoi-repo` entry if the table lists per-module rows. Match the existing generator's exact formatting (read the current table first).

- [ ] **Step 2: Run the full bash suite**

Run: `bats tests/`
Expected: all green (target ≥1118; count may rise from the new `chezmoi-repo.bats` / docker debian test).

- [ ] **Step 3: Run the full engine suite + mypy**

Run: `cd engine && . .venv/bin/activate && pytest -q && mypy`
Expected: all pass; mypy clean.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: regenerate profiles drift-gate table for chezmoi-repo"
```

---

## Self-Review

**Spec coverage:**
- §2.1 chezmoi split → Task 2 (+ rewire Task 3). ✅
- §2.2 starship/fresh/dotfiles/bash-config portable → Task 3 (dotfiles) + Task 4. ✅
- §2.3 ghostty Ubuntu (gui first) → Task 5. ✅
- §3.3 docker Debian / devtools-on-Ubuntu → Task 6. ✅
- §3.4 fallback ladders → Task 7. ✅
- §3.5 expand cycle-guard (I-2) → Task 1. ✅
- §4 tests both suites → Tasks 1,3,6,7,8 (pytest parity + cycle; bats chezmoi-repo/docker/profiles/drift-gate). ✅
- terminal-excludes-secrets / devtools-docker invariants → Task 3 + Task 6 (`test_ubuntu_parity.py`). ✅

**Placeholder scan:** The few "pin from live source" steps (ghostty `.deb` URL, mise fallback ids) are explicit verification commands with the exact tool to run and the expected output shape — not deferred work. No "TBD/handle edge cases".

**Type consistency:** `expand(names, profiles, modules)`, `resolve_steps(mod, os_info)`, `OsInfo(distro,family,arch)`, `Module(...)`, `load_modules`, `load_profiles`, `DependencyCycle` — all match the Plan-1 engine signatures (verified against merged `main`).

**Ordering:** Task 1 (engine guard, independent) → Task 2 (split) → Task 3 (rewire + secrets-invariant) → Tasks 4/5 (portable modules) → Task 6 (docker + docker-invariant) → Task 7 (fallbacks + Ubuntu-resolves-all) → Task 8 (drift-gate + full-suite gate). Each task ends green on its own slice.
