# dev-boost Engine Core — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the pure-Bash `devboost` engine that reads declarative TOML module manifests + a profiles file, resolves them per-OS, topologically sorts by dependency, and runs verify-guarded (idempotent) installs.

**Architecture:** An "engine + data" design. Small Bash libs under `lib/` each own one responsibility (logging, OS detection, TOML parsing, module model, dep-sort, profile expansion, install loop). `bin/devboost` is a thin CLI dispatcher. TOML is parsed by shelling to Python 3 `tomllib` → JSON, then queried with `jq`. Modules are data, never touched by the engine.

**Tech Stack:** Bash 5, Python 3.11+ (`tomllib`, stdlib only), `jq`, `bats-core` (tests).

## Global Constraints

- Engine language is **pure Bash**; the only external runtime deps are **`python3` (≥3.11, stdlib `tomllib`)** and **`jq`**. No other interpreters.
- TOML → JSON conversion goes through `python3 -c 'import tomllib…'` — never a hand-rolled parser.
- Cross-OS install resolution precedence is exactly **`<distro>` → `<os-family>` → `default`**; no match ⇒ module reported *unsupported*, never silently skipped.
- Installs are **idempotent / verify-guarded**: a module whose `verify` command exits 0 is skipped unless `--force`.
- All paths are overridable by env for testing: `DEVBOOST_MODULES_DIR` (default `$DEVBOOST_ROOT/modules`), `DEVBOOST_PROFILES` (default `$DEVBOOST_ROOT/profiles.toml`).
- Every `lib/*.sh` must be safely `source`-able with no side effects at source time (only function/constant definitions).
- Commit messages use Conventional Commits and contain **no Claude/Anthropic attribution and no `Co-Authored-By` trailer** (user global rule).
- Run all tests with `bats tests/`. A task is done only when its tests pass.

---

### Task 1: Project skeleton, test harness, and `lib/log.sh`

**Files:**
- Create: `lib/log.sh`
- Create: `tests/test_helper.bash`
- Create: `tests/log.bats`
- Create: `.editorconfig`

**Interfaces:**
- Consumes: nothing.
- Produces: `log_info/log_warn/log_error/log_ok/log_skip <msg>` (write to stderr); `die <msg>` (log_error + `exit 1`); `summary_reset`; `summary_add <status> <name> [detail]` (status ∈ ok|skip|fail); `summary_print` (writes a table to stderr, returns 1 if any fail recorded else 0). Summary state held in module-level arrays `SUMMARY_STATUS`, `SUMMARY_NAME`, `SUMMARY_DETAIL`.

- [ ] **Step 1: Ensure `bats` and `jq` are available**

Run: `command -v bats jq python3 || sudo dnf install -y bats jq python3`
Expected: all three resolve to paths.

- [ ] **Step 2: Write the test helper**

Create `tests/test_helper.bash`:
```bash
# Resolve repo root from the tests dir and expose it.
DEVBOOST_ROOT="$(cd "$(dirname "${BATS_TEST_FILENAME}")/.." && pwd)"
export DEVBOOST_ROOT
# Point the engine at per-test fixture dirs when set by a test.
load_lib() { source "${DEVBOOST_ROOT}/lib/$1"; }
```

- [ ] **Step 3: Write the failing test**

Create `tests/log.bats`:
```bash
load test_helper

setup() { load_lib log.sh; }

@test "log_info writes to stderr, not stdout" {
  run --separate-stderr bash -c 'source "$DEVBOOST_ROOT/lib/log.sh"; log_info hi'
  [ -z "$output" ]            # stdout empty
  [[ "$stderr" == *"hi"* ]]   # message on stderr
}

@test "die exits non-zero" {
  run bash -c 'source "$DEVBOOST_ROOT/lib/log.sh"; die boom'
  [ "$status" -eq 1 ]
  [[ "$output" == *"boom"* ]]
}

@test "summary records and prints, fails when a fail is present" {
  run bash -c 'source "$DEVBOOST_ROOT/lib/log.sh"
    summary_reset
    summary_add ok git
    summary_add fail docker "no daemon"
    summary_print'
  [ "$status" -eq 1 ]
  [[ "$output" == *"git"* ]]
  [[ "$output" == *"docker"* ]]
  [[ "$output" == *"no daemon"* ]]
}

@test "summary returns 0 when all ok/skip" {
  run bash -c 'source "$DEVBOOST_ROOT/lib/log.sh"
    summary_reset; summary_add ok git; summary_add skip fzf; summary_print'
  [ "$status" -eq 0 ]
}
```

- [ ] **Step 4: Run tests, verify they fail**

Run: `bats tests/log.bats`
Expected: FAIL (`lib/log.sh` not found / functions undefined).

- [ ] **Step 5: Implement `lib/log.sh`**

```bash
# lib/log.sh — logging + run summary. Source-only; no side effects.
if [[ -t 2 ]]; then
  _C_RED=$'\033[31m'; _C_GRN=$'\033[32m'; _C_YEL=$'\033[33m'
  _C_BLU=$'\033[34m'; _C_DIM=$'\033[2m'; _C_RST=$'\033[0m'
else
  _C_RED=; _C_GRN=; _C_YEL=; _C_BLU=; _C_DIM=; _C_RST=
fi

log_info()  { printf '%s[*]%s %s\n' "$_C_BLU" "$_C_RST" "$*" >&2; }
log_ok()    { printf '%s[+]%s %s\n' "$_C_GRN" "$_C_RST" "$*" >&2; }
log_warn()  { printf '%s[!]%s %s\n' "$_C_YEL" "$_C_RST" "$*" >&2; }
log_error() { printf '%s[x]%s %s\n' "$_C_RED" "$_C_RST" "$*" >&2; }
log_skip()  { printf '%s[=] %s%s\n' "$_C_DIM" "$*" "$_C_RST" >&2; }
die()       { log_error "$*"; exit 1; }

SUMMARY_STATUS=(); SUMMARY_NAME=(); SUMMARY_DETAIL=()
summary_reset() { SUMMARY_STATUS=(); SUMMARY_NAME=(); SUMMARY_DETAIL=(); }
summary_add() {
  SUMMARY_STATUS+=("$1"); SUMMARY_NAME+=("$2"); SUMMARY_DETAIL+=("${3:-}")
}
summary_print() {
  local i fails=0 sym
  printf '\n%s──── summary ────%s\n' "$_C_DIM" "$_C_RST" >&2
  for i in "${!SUMMARY_NAME[@]}"; do
    case "${SUMMARY_STATUS[$i]}" in
      ok)   sym="${_C_GRN}+${_C_RST}";;
      skip) sym="${_C_DIM}=${_C_RST}";;
      fail) sym="${_C_RED}x${_C_RST}"; fails=$((fails+1));;
      *)    sym="?";;
    esac
    printf '  [%s] %-22s %s\n' "$sym" "${SUMMARY_NAME[$i]}" "${SUMMARY_DETAIL[$i]}" >&2
  done
  [ "$fails" -eq 0 ]
}
```

- [ ] **Step 6: Run tests, verify pass**

Run: `bats tests/log.bats`
Expected: PASS (4 tests).

- [ ] **Step 7: Add `.editorconfig` and commit**

Create `.editorconfig`:
```ini
root = true
[*]
end_of_line = lf
insert_final_newline = true
charset = utf-8
[*.sh]
indent_style = space
indent_size = 2
```

```bash
git add lib/log.sh tests/test_helper.bash tests/log.bats .editorconfig
git commit -m "feat(engine): logging + run-summary lib with bats harness"
```

---

### Task 2: `lib/os.sh` — OS family / distro / arch detection

**Files:**
- Create: `lib/os.sh`
- Create: `tests/os.bats`
- Create: `tests/fixtures/os-release/fedora`, `tests/fixtures/os-release/ubuntu`

**Interfaces:**
- Consumes: `lib/log.sh` (for `die`).
- Produces: `os_detect` — reads `${OS_RELEASE_FILE:-/etc/os-release}`, sets globals `OS_DISTRO` (e.g. `fedora`,`ubuntu`), `OS_FAMILY` (`fedora`|`debian`|`arch`|`macos`), `OS_ARCH` (`uname -m`). `os_family_of <distro>` echoes the family for a distro id.

- [ ] **Step 1: Create fixtures**

`tests/fixtures/os-release/fedora`:
```
ID=fedora
ID_LIKE=
VERSION_ID=44
```
`tests/fixtures/os-release/ubuntu`:
```
ID=ubuntu
ID_LIKE=debian
VERSION_ID=24.04
```

- [ ] **Step 2: Write the failing test**

`tests/os.bats`:
```bash
load test_helper
setup() { load_lib log.sh; load_lib os.sh; }

@test "detects fedora family" {
  OS_RELEASE_FILE="$DEVBOOST_ROOT/tests/fixtures/os-release/fedora" os_detect
  [ "$OS_DISTRO" = "fedora" ]; [ "$OS_FAMILY" = "fedora" ]
}
@test "ubuntu maps to debian family" {
  OS_RELEASE_FILE="$DEVBOOST_ROOT/tests/fixtures/os-release/ubuntu" os_detect
  [ "$OS_DISTRO" = "ubuntu" ]; [ "$OS_FAMILY" = "debian" ]
}
@test "arch is populated" {
  OS_RELEASE_FILE="$DEVBOOST_ROOT/tests/fixtures/os-release/fedora" os_detect
  [ -n "$OS_ARCH" ]
}
```

- [ ] **Step 3: Run, verify fail**

Run: `bats tests/os.bats`
Expected: FAIL (`os_detect` undefined).

- [ ] **Step 4: Implement `lib/os.sh`**

```bash
# lib/os.sh — OS detection. Source-only.
os_family_of() {
  case "$1" in
    fedora|rhel|centos|rocky|almalinux) echo fedora;;
    ubuntu|debian|linuxmint|pop)        echo debian;;
    arch|manjaro|endeavouros)           echo arch;;
    macos|darwin)                       echo macos;;
    *)                                  echo "$1";;
  esac
}

os_detect() {
  local f="${OS_RELEASE_FILE:-/etc/os-release}"
  if [[ "$(uname -s)" == "Darwin" ]]; then
    OS_DISTRO=macos
  elif [[ -r "$f" ]]; then
    OS_DISTRO="$(. "$f" 2>/dev/null; echo "${ID:-unknown}")"
  else
    OS_DISTRO=unknown
  fi
  OS_FAMILY="$(os_family_of "$OS_DISTRO")"
  OS_ARCH="$(uname -m)"
  export OS_DISTRO OS_FAMILY OS_ARCH
}
```

- [ ] **Step 5: Run, verify pass**

Run: `bats tests/os.bats`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add lib/os.sh tests/os.bats tests/fixtures/os-release
git commit -m "feat(engine): OS family/distro/arch detection"
```

---

### Task 3: `lib/toml.sh` — TOML → JSON via Python `tomllib`

**Files:**
- Create: `lib/toml.sh`
- Create: `tests/toml.bats`
- Create: `tests/fixtures/sample.toml`

**Interfaces:**
- Consumes: `lib/log.sh` (`die`).
- Produces: `toml_to_json <file>` — prints compact JSON to stdout; `die`s if `python3` missing or the file is invalid TOML.

- [ ] **Step 1: Create fixture**

`tests/fixtures/sample.toml`:
```toml
name = "bun"
requires = ["mise"]
[install]
default = "mise use -g bun@latest"
fedora = "dnf install -y bun"
verify = "bun --version"
```

- [ ] **Step 2: Write the failing test**

`tests/toml.bats`:
```bash
load test_helper
setup() { load_lib log.sh; load_lib toml.sh; }

@test "converts toml to json queryable by jq" {
  run bash -c 'source "$DEVBOOST_ROOT/lib/log.sh"; source "$DEVBOOST_ROOT/lib/toml.sh"
    toml_to_json "$DEVBOOST_ROOT/tests/fixtures/sample.toml"'
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.name == "bun"'
  echo "$output" | jq -e '.install.fedora == "dnf install -y bun"'
  echo "$output" | jq -e '.requires[0] == "mise"'
}

@test "invalid toml dies non-zero" {
  tmp="$(mktemp)"; printf 'x = = =\n' > "$tmp"
  run bash -c 'source "$DEVBOOST_ROOT/lib/log.sh"; source "$DEVBOOST_ROOT/lib/toml.sh"; toml_to_json "$1"' _ "$tmp"
  [ "$status" -ne 0 ]
  rm -f "$tmp"
}
```

- [ ] **Step 3: Run, verify fail**

Run: `bats tests/toml.bats`
Expected: FAIL (`toml_to_json` undefined).

- [ ] **Step 4: Implement `lib/toml.sh`**

```bash
# lib/toml.sh — TOML→JSON using python3 stdlib tomllib (>=3.11). Source-only.
toml_to_json() {
  local file="$1"
  command -v python3 >/dev/null || die "python3 required for TOML parsing"
  python3 - "$file" <<'PY' || die "invalid TOML: $1"
import sys, json, tomllib
with open(sys.argv[1], "rb") as fh:
    data = tomllib.load(fh)
json.dump(data, sys.stdout, separators=(",", ":"))
PY
}
```

- [ ] **Step 5: Run, verify pass**

Run: `bats tests/toml.bats`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add lib/toml.sh tests/toml.bats tests/fixtures/sample.toml
git commit -m "feat(engine): TOML to JSON via python tomllib"
```

---

### Task 4: `lib/module.sh` — module model + per-OS resolution

**Files:**
- Create: `lib/module.sh`
- Create: `tests/module.bats`
- Create: `tests/fixtures/modules/git.toml`, `tests/fixtures/modules/bun.toml`, `tests/fixtures/modules/ddev/module.toml`

**Interfaces:**
- Consumes: `lib/log.sh`, `lib/toml.sh`, `lib/os.sh` (globals `OS_DISTRO`,`OS_FAMILY`).
- Produces:
  - `module_file <name>` → path to `$DEVBOOST_MODULES_DIR/<name>.toml` or `…/<name>/module.toml`; `die` if neither.
  - `module_json <name>` → JSON (cached per-name in assoc array `_MOD_JSON`).
  - `module_field <name> <jq-filter>` → raw value via jq (`-r`), empty if null.
  - `module_requires <name>` → newline-separated deps (empty if none).
  - `module_install_cmd <name>` → resolved command using precedence `install.$OS_DISTRO` → `install.$OS_FAMILY` → `install.default`; empty string if unsupported.
  - `module_verify_cmd <name>` → the `verify` string (may be empty).

- [ ] **Step 1: Create fixtures**

`tests/fixtures/modules/git.toml`:
```toml
name = "git"
[install]
default = "echo install git"
verify = "true"
```
`tests/fixtures/modules/bun.toml`:
```toml
name = "bun"
requires = ["mise"]
[install]
default = "echo default bun"
fedora = "echo fedora bun"
verify = "false"
```
`tests/fixtures/modules/ddev/module.toml`:
```toml
name = "ddev"
requires = ["docker"]
[install]
fedora = "echo fedora ddev"
verify = "true"
```

- [ ] **Step 2: Write the failing test**

`tests/module.bats`:
```bash
load test_helper
setup() {
  load_lib log.sh; load_lib toml.sh; load_lib os.sh; load_lib module.sh
  export DEVBOOST_MODULES_DIR="$DEVBOOST_ROOT/tests/fixtures/modules"
  OS_DISTRO=fedora; OS_FAMILY=fedora
}

@test "finds flat and folder modules" {
  [ "$(module_file git)"  = "$DEVBOOST_MODULES_DIR/git.toml" ]
  [ "$(module_file ddev)" = "$DEVBOOST_MODULES_DIR/ddev/module.toml" ]
}
@test "distro-specific install wins over default" {
  [ "$(module_install_cmd bun)" = "echo fedora bun" ]
}
@test "falls back to default when no distro key" {
  OS_DISTRO=ubuntu; OS_FAMILY=debian
  [ "$(module_install_cmd bun)" = "echo default bun" ]
}
@test "unsupported os yields empty install cmd" {
  OS_DISTRO=plan9; OS_FAMILY=plan9
  [ -z "$(module_install_cmd ddev)" ]   # ddev only defines fedora
}
@test "requires parsed" {
  [ "$(module_requires bun)" = "mise" ]
  [ -z "$(module_requires git)" ]
}
@test "verify cmd read" {
  [ "$(module_verify_cmd git)" = "true" ]
}
```

- [ ] **Step 3: Run, verify fail**

Run: `bats tests/module.bats`
Expected: FAIL (functions undefined).

- [ ] **Step 4: Implement `lib/module.sh`**

```bash
# lib/module.sh — module manifest model. Source-only.
declare -A _MOD_JSON

module_file() {
  local name="$1" base="${DEVBOOST_MODULES_DIR:-$DEVBOOST_ROOT/modules}"
  if   [[ -f "$base/$name.toml" ]];        then echo "$base/$name.toml"
  elif [[ -f "$base/$name/module.toml" ]]; then echo "$base/$name/module.toml"
  else die "module not found: $name"; fi
}

module_json() {
  local name="$1"
  [[ -n "${_MOD_JSON[$name]:-}" ]] && { printf '%s' "${_MOD_JSON[$name]}"; return; }
  local json; json="$(toml_to_json "$(module_file "$name")")"
  _MOD_JSON[$name]="$json"
  printf '%s' "$json"
}

module_field() {  # <name> <jq-filter>
  module_json "$1" | jq -r "$2 // empty"
}

module_requires() {  # newline list
  module_json "$1" | jq -r '(.requires // [])[]'
}

module_install_cmd() {
  local name="$1" cmd
  cmd="$(module_field "$name" ".install.\"$OS_DISTRO\"")"
  [[ -z "$cmd" ]] && cmd="$(module_field "$name" ".install.\"$OS_FAMILY\"")"
  [[ -z "$cmd" ]] && cmd="$(module_field "$name" '.install.default')"
  printf '%s' "$cmd"
}

module_verify_cmd() { module_field "$1" '.verify'; }
```

- [ ] **Step 5: Run, verify pass**

Run: `bats tests/module.bats`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add lib/module.sh tests/module.bats tests/fixtures/modules
git commit -m "feat(engine): module model with per-OS install resolution"
```

---

### Task 5: `lib/depsort.sh` — topological sort of `requires`

**Files:**
- Create: `lib/depsort.sh`
- Create: `tests/depsort.bats`
- Create: `tests/fixtures/modules/mise.toml`, `tests/fixtures/modules/docker.toml`

**Interfaces:**
- Consumes: `lib/module.sh` (`module_requires`), `lib/log.sh` (`die`).
- Produces: `depsort <name...>` — prints the input set plus all transitive `requires`, in dependency order (deps before dependents), one per line, de-duplicated. `die`s on a dependency cycle. Uses Kahn's algorithm.

- [ ] **Step 1: Add fixtures**

`tests/fixtures/modules/mise.toml`:
```toml
name = "mise"
[install]
default = "echo mise"
verify = "true"
```
`tests/fixtures/modules/docker.toml`:
```toml
name = "docker"
[install]
default = "echo docker"
verify = "true"
```

- [ ] **Step 2: Write the failing test**

`tests/depsort.bats`:
```bash
load test_helper
setup() {
  load_lib log.sh; load_lib toml.sh; load_lib os.sh; load_lib module.sh; load_lib depsort.sh
  export DEVBOOST_MODULES_DIR="$DEVBOOST_ROOT/tests/fixtures/modules"
  OS_DISTRO=fedora; OS_FAMILY=fedora
}

@test "pulls in transitive deps and orders them first" {
  run depsort bun ddev
  [ "$status" -eq 0 ]
  # mise before bun, docker before ddev
  out="$output"
  line() { echo "$out" | grep -nx "$1" | cut -d: -f1; }
  [ "$(line mise)" -lt "$(line bun)" ]
  [ "$(line docker)" -lt "$(line ddev)" ]
}

@test "dedupes repeated requests" {
  run depsort bun bun
  [ "$(echo "$output" | grep -cx bun)" -eq 1 ]
}

@test "detects cycles" {
  d="$(mktemp -d)/modules"; mkdir -p "$d"
  printf 'name="a"\nrequires=["b"]\nverify="true"\n[install]\ndefault="x"\n' > "$d/a.toml"
  printf 'name="b"\nrequires=["a"]\nverify="true"\n[install]\ndefault="x"\n' > "$d/b.toml"
  run env DEVBOOST_MODULES_DIR="$d" bash -c '
    source "$DEVBOOST_ROOT/lib/log.sh"; source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/os.sh"; source "$DEVBOOST_ROOT/lib/module.sh"
    source "$DEVBOOST_ROOT/lib/depsort.sh"; OS_DISTRO=fedora; OS_FAMILY=fedora; depsort a'
  [ "$status" -ne 0 ]
  [[ "$output" == *"cycle"* ]]
}
```

- [ ] **Step 3: Run, verify fail**

Run: `bats tests/depsort.bats`
Expected: FAIL (`depsort` undefined).

- [ ] **Step 4: Implement `lib/depsort.sh`**

```bash
# lib/depsort.sh — Kahn topological sort over module `requires`. Source-only.
depsort() {
  local -A seen=() indeg=() ; local -a queue=("$@") order=() all=()
  # 1. Build the full node set (BFS over requires).
  while ((${#queue[@]})); do
    local n="${queue[0]}"; queue=("${queue[@]:1}")
    [[ -n "${seen[$n]:-}" ]] && continue
    seen[$n]=1; all+=("$n")
    local dep; while IFS= read -r dep; do
      [[ -z "$dep" ]] && continue; queue+=("$dep")
    done < <(module_requires "$n")
  done
  # 2. Edges dep -> node; compute in-degrees.
  local -A radj=()  # radj[node]="space separated deps"
  local n
  for n in "${all[@]}"; do indeg[$n]=0; done
  for n in "${all[@]}"; do
    local dep
    while IFS= read -r dep; do
      [[ -z "$dep" ]] && continue
      radj[$n]+=" $dep"; indeg[$n]=$(( ${indeg[$n]} + 1 ))
    done < <(module_requires "$n")
  done
  # 3. Kahn: start with zero in-degree, but we need deps first, so process
  #    nodes whose deps are all emitted. Use reverse: emit when indeg==0.
  local -a ready=()
  for n in "${all[@]}"; do [[ "${indeg[$n]}" -eq 0 ]] && ready+=("$n"); done
  local emitted=0
  while ((${#ready[@]})); do
    local m="${ready[0]}"; ready=("${ready[@]:1}")
    order+=("$m"); emitted=$((emitted+1))
    # For every node that requires m, decrement in-degree.
    local k
    for k in "${all[@]}"; do
      [[ " ${radj[$k]:-} " == *" $m "* ]] || continue
      indeg[$k]=$(( ${indeg[$k]} - 1 ))
      [[ "${indeg[$k]}" -eq 0 ]] && ready+=("$k")
    done
  done
  [[ "$emitted" -ne "${#all[@]}" ]] && die "dependency cycle detected among modules"
  printf '%s\n' "${order[@]}"
}
```

- [ ] **Step 5: Run, verify pass**

Run: `bats tests/depsort.bats`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add lib/depsort.sh tests/depsort.bats tests/fixtures/modules/mise.toml tests/fixtures/modules/docker.toml
git commit -m "feat(engine): topological dependency sort (Kahn) with cycle detection"
```

---

### Task 6: `lib/profile.sh` — profile expansion

**Files:**
- Create: `lib/profile.sh`
- Create: `tests/profile.bats`
- Create: `tests/fixtures/profiles.toml`

**Interfaces:**
- Consumes: `lib/toml.sh`, `lib/log.sh`.
- Produces:
  - `profile_names` → newline list of defined profile names (keys under `[profiles]`).
  - `profile_expand <token...>` → flat, de-duplicated newline list of **module** names. A token is expanded if it is a profile name (recursively); otherwise it is treated as a module name. Reads `${DEVBOOST_PROFILES}`.

- [ ] **Step 1: Create fixture**

`tests/fixtures/profiles.toml`:
```toml
[profiles]
base = ["git", "mise"]
web  = ["bun"]
full = ["base", "web", "ddev"]
```

- [ ] **Step 2: Write the failing test**

`tests/profile.bats`:
```bash
load test_helper
setup() {
  load_lib log.sh; load_lib toml.sh; load_lib profile.sh
  export DEVBOOST_PROFILES="$DEVBOOST_ROOT/tests/fixtures/profiles.toml"
}

@test "lists profile names" {
  run profile_expand   # no-op guard; ensure sourced
  run bash -c 'source "$DEVBOOST_ROOT/lib/log.sh"; source "$DEVBOOST_ROOT/lib/toml.sh"; source "$DEVBOOST_ROOT/lib/profile.sh"; profile_names | sort | tr "\n" " "'
  [[ "$output" == *"base"* ]]; [[ "$output" == *"full"* ]]
}

@test "expands nested profiles to flat module set" {
  run bash -c 'source "$DEVBOOST_ROOT/lib/log.sh"; source "$DEVBOOST_ROOT/lib/toml.sh"; source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/tests/fixtures/profiles.toml" profile_expand full | sort | tr "\n" " "'
  [ "$status" -eq 0 ]
  [ "$output" = "bun ddev git mise " ]
}

@test "bare module token passes through" {
  run bash -c 'source "$DEVBOOST_ROOT/lib/log.sh"; source "$DEVBOOST_ROOT/lib/toml.sh"; source "$DEVBOOST_ROOT/lib/profile.sh"
    DEVBOOST_PROFILES="$DEVBOOST_ROOT/tests/fixtures/profiles.toml" profile_expand docker | tr "\n" " "'
  [ "$output" = "docker " ]
}
```

- [ ] **Step 3: Run, verify fail**

Run: `bats tests/profile.bats`
Expected: FAIL (`profile_expand` undefined).

- [ ] **Step 4: Implement `lib/profile.sh`**

```bash
# lib/profile.sh — expand profile tokens to a flat module set. Source-only.
_profiles_json() { toml_to_json "${DEVBOOST_PROFILES:-$DEVBOOST_ROOT/profiles.toml}"; }

profile_names() { _profiles_json | jq -r '.profiles // {} | keys[]'; }

_profile_is() { # is token a profile name?
  _profiles_json | jq -e --arg k "$1" '(.profiles // {}) | has($k)' >/dev/null
}

profile_expand() {
  local -A seen=() out=() ; local -a stack=("$@")
  while ((${#stack[@]})); do
    local t="${stack[0]}"; stack=("${stack[@]:1}")
    [[ -n "${seen[$t]:-}" ]] && continue
    seen[$t]=1
    if _profile_is "$t"; then
      local m
      while IFS= read -r m; do [[ -n "$m" ]] && stack+=("$m"); done \
        < <(_profiles_json | jq -r --arg k "$t" '.profiles[$k][]')
    else
      out[$t]=1
    fi
  done
  printf '%s\n' "${!out[@]}"
}
```

- [ ] **Step 5: Run, verify pass**

Run: `bats tests/profile.bats`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add lib/profile.sh tests/profile.bats tests/fixtures/profiles.toml
git commit -m "feat(engine): recursive profile expansion to flat module set"
```

---

### Task 7: `lib/install.sh` — verify-guarded install loop

**Files:**
- Create: `lib/install.sh`
- Create: `tests/install.bats`

**Interfaces:**
- Consumes: `lib/log.sh`, `lib/module.sh`, `lib/depsort.sh`.
- Produces: `run_install [--force] [--strict] -- <module...>` — for each module in dependency order: if `verify` exits 0 and not `--force`, record `skip`; else run the resolved install command via `bash -c`, then re-verify; record `ok`/`fail`. Continue past failures unless `--strict` (then stop). Calls `summary_print` at end; returns its status.

- [ ] **Step 1: Write the failing test**

`tests/install.bats`:
```bash
load test_helper
setup() {
  load_lib log.sh; load_lib toml.sh; load_lib os.sh; load_lib module.sh
  load_lib depsort.sh; load_lib install.sh
  export DEVBOOST_MODULES_DIR="$DEVBOOST_ROOT/tests/fixtures/modules"
  OS_DISTRO=fedora; OS_FAMILY=fedora
}

@test "already-installed module is skipped (verify passes)" {
  # git verify = true → skip
  run bash -c 'source "$DEVBOOST_ROOT/lib/log.sh"; source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/os.sh"; source "$DEVBOOST_ROOT/lib/module.sh"
    source "$DEVBOOST_ROOT/lib/depsort.sh"; source "$DEVBOOST_ROOT/lib/install.sh"
    export DEVBOOST_MODULES_DIR="'"$DEVBOOST_MODULES_DIR"'"; OS_DISTRO=fedora OS_FAMILY=fedora
    summary_reset; run_install -- git'
  [ "$status" -eq 0 ]
  [[ "$output" == *"git"* ]]
}

@test "missing module gets installed then re-verified" {
  # Make a module that is missing until installed: verify checks a marker file.
  d="$(mktemp -d)"; mkdir -p "$d/modules"; marker="$d/done"
  cat > "$d/modules/foo.toml" <<EOF
name = "foo"
[install]
default = "touch $marker"
verify = "test -f $marker"
EOF
  run bash -c 'source "$DEVBOOST_ROOT/lib/log.sh"; source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/os.sh"; source "$DEVBOOST_ROOT/lib/module.sh"
    source "$DEVBOOST_ROOT/lib/depsort.sh"; source "$DEVBOOST_ROOT/lib/install.sh"
    export DEVBOOST_MODULES_DIR="'"$d/modules"'"; OS_DISTRO=fedora OS_FAMILY=fedora
    summary_reset; run_install -- foo'
  [ "$status" -eq 0 ]
  [ -f "$marker" ]
}

@test "non-strict continues after a failure and returns non-zero" {
  d="$(mktemp -d)"; mkdir -p "$d/modules"
  printf 'name="bad"\nverify="false"\n[install]\ndefault="false"\n' > "$d/modules/bad.toml"
  printf 'name="good"\nverify="true"\n[install]\ndefault="true"\n' > "$d/modules/good.toml"
  run bash -c 'source "$DEVBOOST_ROOT/lib/log.sh"; source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/os.sh"; source "$DEVBOOST_ROOT/lib/module.sh"
    source "$DEVBOOST_ROOT/lib/depsort.sh"; source "$DEVBOOST_ROOT/lib/install.sh"
    export DEVBOOST_MODULES_DIR="'"$d/modules"'"; OS_DISTRO=fedora OS_FAMILY=fedora
    summary_reset; run_install -- bad good'
  [ "$status" -ne 0 ]              # a failure happened
  [[ "$output" == *"good"* ]]      # but good still processed
}
```

- [ ] **Step 2: Run, verify fail**

Run: `bats tests/install.bats`
Expected: FAIL (`run_install` undefined).

- [ ] **Step 3: Implement `lib/install.sh`**

```bash
# lib/install.sh — verify-guarded, dependency-ordered install loop. Source-only.
run_install() {
  local force=0 strict=0
  while [[ "${1:-}" == --* ]]; do
    case "$1" in
      --force) force=1;; --strict) strict=1;; --) shift; break;;
      *) die "run_install: unknown flag $1";;
    esac; shift
  done
  local -a order; mapfile -t order < <(depsort "$@")
  local name vcmd icmd
  for name in "${order[@]}"; do
    vcmd="$(module_verify_cmd "$name")"
    icmd="$(module_install_cmd "$name")"
    # Idempotency guard.
    if [[ "$force" -eq 0 && -n "$vcmd" ]] && bash -c "$vcmd" >/dev/null 2>&1; then
      log_skip "$name (already installed)"; summary_add skip "$name"; continue
    fi
    if [[ -z "$icmd" ]]; then
      log_error "$name: unsupported on $OS_DISTRO/$OS_FAMILY"
      summary_add fail "$name" "unsupported on $OS_DISTRO"
      [[ "$strict" -eq 1 ]] && { summary_print; return 1; }
      continue
    fi
    log_info "$name: installing"
    if ! bash -c "$icmd"; then
      log_error "$name: install failed"; summary_add fail "$name" "install cmd failed"
      [[ "$strict" -eq 1 ]] && { summary_print; return 1; }
      continue
    fi
    if [[ -n "$vcmd" ]] && ! bash -c "$vcmd" >/dev/null 2>&1; then
      log_error "$name: verify failed after install"; summary_add fail "$name" "verify failed"
      [[ "$strict" -eq 1 ]] && { summary_print; return 1; }
      continue
    fi
    log_ok "$name"; summary_add ok "$name"
  done
  summary_print
}
```

- [ ] **Step 4: Run, verify pass**

Run: `bats tests/install.bats`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add lib/install.sh tests/install.bats
git commit -m "feat(engine): verify-guarded dependency-ordered install loop"
```

---

### Task 8: `bin/devboost` — CLI dispatcher (`install`/`verify`/`list`/`doctor`)

**Files:**
- Create: `bin/devboost`
- Create: `tests/cli.bats`

**Interfaces:**
- Consumes: all libs.
- Produces: executable `bin/devboost`:
  - `devboost install [--profile X[,Y]] [--force] [--strict]` (default profile `full`) → `run_install` over `profile_expand`.
  - `devboost verify [--profile X]` → run each module's verify, report ok/fail, no changes.
  - `devboost list [--profile X]` → print resolved module order.
  - `devboost doctor` → check `python3`, `jq`, OS detected, modules dir present.
  - `devboost help` / no args → usage. Unknown verb → usage + exit 1.

- [ ] **Step 1: Write the failing test**

`tests/cli.bats`:
```bash
load test_helper
setup() {
  export DEVBOOST_MODULES_DIR="$DEVBOOST_ROOT/tests/fixtures/modules"
  export DEVBOOST_PROFILES="$DEVBOOST_ROOT/tests/fixtures/profiles.toml"
  export OS_RELEASE_FILE="$DEVBOOST_ROOT/tests/fixtures/os-release/fedora"
}

@test "help exits 0 and shows usage" {
  run "$DEVBOOST_ROOT/bin/devboost" help
  [ "$status" -eq 0 ]; [[ "$output" == *"Usage"* ]]
}
@test "unknown verb exits 1" {
  run "$DEVBOOST_ROOT/bin/devboost" frobnicate
  [ "$status" -eq 1 ]
}
@test "list resolves profile to ordered modules" {
  run "$DEVBOOST_ROOT/bin/devboost" list --profile full
  [ "$status" -eq 0 ]
  [[ "$output" == *"git"* ]]; [[ "$output" == *"mise"* ]]
}
@test "doctor passes on a sane host" {
  run "$DEVBOOST_ROOT/bin/devboost" doctor
  [ "$status" -eq 0 ]
}
@test "install full runs without crashing (echo modules)" {
  run "$DEVBOOST_ROOT/bin/devboost" install --profile full
  [[ "$output" == *"summary"* ]]
}
```

- [ ] **Step 2: Run, verify fail**

Run: `bats tests/cli.bats`
Expected: FAIL (no `bin/devboost`).

- [ ] **Step 3: Implement `bin/devboost`**

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
DEVBOOST_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; export DEVBOOST_ROOT
for l in log os toml module depsort profile install; do source "$DEVBOOST_ROOT/lib/$l.sh"; done
os_detect

_parse_profile() {  # echoes comma list → space-separated tokens; default full
  local p="full"
  while [[ $# -gt 0 ]]; do case "$1" in --profile) p="$2"; shift 2;; *) shift;; esac; done
  echo "${p//,/ }"
}

usage() {
  cat <<EOF
Usage: devboost <command> [options]

Commands:
  install [--profile a,b] [--force] [--strict]   install modules (default: full)
  verify  [--profile a,b]                         check what's installed
  list    [--profile a,b]                         show resolved module order
  doctor                                          environment preflight
  help                                            this message
EOF
}

cmd_list() {
  local toks; toks="$(_parse_profile "$@")"
  # shellcheck disable=SC2086
  depsort $(profile_expand $toks)
}

cmd_install() {
  local force="" strict="" toks
  for a in "$@"; do case "$a" in --force) force=--force;; --strict) strict=--strict;; esac; done
  toks="$(_parse_profile "$@")"
  # shellcheck disable=SC2086
  run_install $force $strict -- $(profile_expand $toks)
}

cmd_verify() {
  local toks; toks="$(_parse_profile "$@")"; summary_reset
  local n v
  # shellcheck disable=SC2086
  for n in $(depsort $(profile_expand $toks)); do
    v="$(module_verify_cmd "$n")"
    if [[ -n "$v" ]] && bash -c "$v" >/dev/null 2>&1; then summary_add ok "$n"
    else summary_add fail "$n" "not verified"; fi
  done
  summary_print
}

cmd_doctor() {
  local ok=0
  command -v python3 >/dev/null || { log_error "python3 missing"; ok=1; }
  command -v jq      >/dev/null || { log_error "jq missing"; ok=1; }
  [[ "$OS_DISTRO" != unknown ]] || { log_error "OS not detected"; ok=1; }
  [[ -d "${DEVBOOST_MODULES_DIR:-$DEVBOOST_ROOT/modules}" ]] || { log_error "modules dir missing"; ok=1; }
  [[ "$ok" -eq 0 ]] && log_ok "doctor: environment OK ($OS_DISTRO/$OS_FAMILY $OS_ARCH)"
  return "$ok"
}

main() {
  local cmd="${1:-help}"; shift || true
  case "$cmd" in
    install) cmd_install "$@";;
    verify)  cmd_verify "$@";;
    list)    cmd_list "$@";;
    doctor)  cmd_doctor "$@";;
    help|-h|--help) usage;;
    *) usage; exit 1;;
  esac
}
main "$@"
```

- [ ] **Step 4: Make executable, run, verify pass**

Run: `chmod +x bin/devboost && bats tests/cli.bats`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add bin/devboost tests/cli.bats
git commit -m "feat(engine): devboost CLI (install/verify/list/doctor)"
```

---

### Task 9: `install.sh` entrypoint + bootstrap preflight

**Files:**
- Create: `install.sh`
- Create: `tests/entrypoint.bats`

**Interfaces:**
- Consumes: `bin/devboost`.
- Produces: repo-root `install.sh` — ensures `python3`, `jq` exist (installs via the host package manager when missing and `sudo` is available), then `exec`s `bin/devboost install "$@"`. Honors `DEVBOOST_DRYRUN=1` to print what it would do and skip execution (for tests).

- [ ] **Step 1: Write the failing test**

`tests/entrypoint.bats`:
```bash
load test_helper
@test "entrypoint dry-run reports deps and forwards args" {
  run env DEVBOOST_DRYRUN=1 \
      DEVBOOST_MODULES_DIR="$DEVBOOST_ROOT/tests/fixtures/modules" \
      DEVBOOST_PROFILES="$DEVBOOST_ROOT/tests/fixtures/profiles.toml" \
      OS_RELEASE_FILE="$DEVBOOST_ROOT/tests/fixtures/os-release/fedora" \
      bash "$DEVBOOST_ROOT/install.sh" --profile full
  [ "$status" -eq 0 ]
  [[ "$output" == *"python3"* ]]
  [[ "$output" == *"--profile full"* ]]
}
```

- [ ] **Step 2: Run, verify fail**

Run: `bats tests/entrypoint.bats`
Expected: FAIL (no `install.sh`).

- [ ] **Step 3: Implement `install.sh`**

```bash
#!/usr/bin/env bash
set -Eeuo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ensure_dep() {  # <cmd> <fedora-pkg>
  command -v "$1" >/dev/null && return 0
  if [[ "${DEVBOOST_DRYRUN:-0}" == 1 ]]; then echo "would install dep: $1 ($2)"; return 0; fi
  if command -v sudo >/dev/null && command -v dnf >/dev/null; then
    sudo dnf install -y "$2"
  else
    echo "ERROR: missing $1 and cannot auto-install" >&2; exit 1
  fi
}

ensure_dep python3 python3
ensure_dep jq jq

if [[ "${DEVBOOST_DRYRUN:-0}" == 1 ]]; then
  echo "would run: bin/devboost install $*"; exit 0
fi
exec "$HERE/bin/devboost" install "$@"
```

- [ ] **Step 4: Run, verify pass**

Run: `chmod +x install.sh && bats tests/entrypoint.bats`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add install.sh tests/entrypoint.bats
git commit -m "feat(engine): curl|bash entrypoint with dependency preflight"
```

---

### Task 10: End-to-end integration test + README

**Files:**
- Create: `tests/integration.bats`
- Create: `README.md`

**Interfaces:**
- Consumes: the whole engine.
- Produces: a black-box test proving install→skip idempotency across a multi-module profile; a README documenting usage and how to add a module.

- [ ] **Step 1: Write the integration test**

`tests/integration.bats`:
```bash
load test_helper
@test "install then re-install is idempotent (second run all skips)" {
  work="$(mktemp -d)"; mkdir -p "$work/modules"; mark="$work/m"
  cat > "$work/modules/alpha.toml" <<EOF
name = "alpha"
[install]
default = "touch $mark.a"
verify  = "test -f $mark.a"
EOF
  cat > "$work/modules/beta.toml" <<EOF
name = "beta"
requires = ["alpha"]
[install]
default = "touch $mark.b"
verify  = "test -f $mark.b"
EOF
  printf '[profiles]\nstack=["beta"]\n' > "$work/profiles.toml"
  common=(DEVBOOST_MODULES_DIR="$work/modules" DEVBOOST_PROFILES="$work/profiles.toml"
          OS_RELEASE_FILE="$DEVBOOST_ROOT/tests/fixtures/os-release/fedora")

  run env "${common[@]}" "$DEVBOOST_ROOT/bin/devboost" install --profile stack
  [ -f "$mark.a" ]; [ -f "$mark.b" ]

  run env "${common[@]}" "$DEVBOOST_ROOT/bin/devboost" install --profile stack
  [ "$status" -eq 0 ]
  [[ "$output" == *"already installed"* ]]
}
```

- [ ] **Step 2: Run, verify it passes against the built engine**

Run: `bats tests/integration.bats`
Expected: PASS.

- [ ] **Step 3: Run the whole suite**

Run: `bats tests/`
Expected: ALL pass (log, os, toml, module, depsort, profile, install, cli, entrypoint, integration).

- [ ] **Step 4: Write `README.md`**

```markdown
# dev-boost engine

`./install.sh [--profile a,b]` — bootstrap a workstation from declarative modules.

## Commands
- `bin/devboost install [--profile full] [--force] [--strict]`
- `bin/devboost verify  [--profile full]`
- `bin/devboost list    [--profile full]`
- `bin/devboost doctor`

## Add a module
Drop `modules/<name>.toml`:
\`\`\`toml
name = "ripgrep"
requires = []            # optional
[install]
default = "mise use -g ..."   # or fedora/ubuntu/macos/windows keys
verify  = "rg --version"      # success => already installed => skipped
\`\`\`
Complex tools: `modules/<name>/module.toml` (+ run logic referenced from an install command).

## Requirements
bash 5, python3 ≥3.11, jq. Tests: `bats tests/`.
```

- [ ] **Step 5: Commit**

```bash
git add tests/integration.bats README.md
git commit -m "test(engine): end-to-end idempotency integration + README"
```

---

## Self-Review

**Spec coverage (engine-core slice of §2–§4):** module schema parsing (T3,T4) ✓; cross-OS precedence distro→family→default (T4) ✓; `requires` topo-sort + cycle detection (T5) ✓; profile expansion incl. nested (T6) ✓; verify-guarded idempotent install, non-strict/strict, summary (T7) ✓; CLI `install/verify/list/doctor` (T8) ✓; curl|bash entrypoint + python3/jq preflight (T9) ✓; idempotency proven end-to-end (T10) ✓. **Deferred to later plans (out of this slice):** `update/export/diff/add/self-update` verbs, `devboost.lock`, secrets/auth, the real module library, dotfiles/chezmoi, GNOME/system/Kickstart/Windows — each its own plan.

**Placeholder scan:** no TBD/TODO; every code step has complete code; every command has expected output. ✓

**Type/name consistency:** `module_install_cmd`/`module_verify_cmd`/`module_requires` (T4) used identically in T5/T7/T8; `run_install --force/--strict -- <mods>` (T7) matches T8 `cmd_install`; `profile_expand`/`depsort` signatures consistent across T6/T8/T10; globals `OS_DISTRO/OS_FAMILY/OS_ARCH` set in T2, consumed in T4/T8; `summary_reset/add/print` (T1) used in T7/T8. ✓
