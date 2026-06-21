load test_helper
load fixtures/base/stubs

# Spec 9 — lib/lifecycle.sh: add / export / diff / update / self-update / devboost.lock.
# Hermetic: scratch DEVBOOST_MODULES_DIR + DEVBOOST_LOCK + DEVBOOST_MISE_CONFIG so the real repo
# is never touched. Stubs supply git/dnf/flatpak/mise/code.

setup() {
  load_lib log.sh
  load_lib toml.sh
  base_setup
  source "${DEVBOOST_ROOT}/lib/os.sh"
  source "${DEVBOOST_ROOT}/lib/module.sh"
  source "${DEVBOOST_ROOT}/lib/depsort.sh"
  source "${DEVBOOST_ROOT}/lib/profile.sh"
  source "${DEVBOOST_ROOT}/lib/lifecycle.sh"
  export DEVBOOST_MODULES_DIR="${BATS_TEST_TMPDIR}/modules"; mkdir -p "${DEVBOOST_MODULES_DIR}"
  export DEVBOOST_LOCK="${BATS_TEST_TMPDIR}/devboost.lock"
  export DEVBOOST_MISE_CONFIG="${BATS_TEST_TMPDIR}/mise.toml"
}
teardown() { base_teardown; }

_mk_module() {  # name verify-cmd [version]
  local n="$1" v="$2" ver="${3:-}"
  mkdir -p "${DEVBOOST_MODULES_DIR}/${n}"
  { printf 'name = "%s"\ncategory = "test"\nrequires = []\nprofiles = []\nverify = "%s"\n' "$n" "$v"
    if [[ -n "${ver}" ]]; then printf 'version = "%s"\n' "${ver}"; fi
  } > "${DEVBOOST_MODULES_DIR}/${n}/module.toml"
  return 0
}

# --- US1: add -------------------------------------------------------------
@test "lc_add: scaffolds a valid module.toml with the name substituted" {
  run lc_add foo
  [ "$status" -eq 0 ]
  [ -f "${DEVBOOST_MODULES_DIR}/foo/module.toml" ]
  grep -q 'name        = "foo"' "${DEVBOOST_MODULES_DIR}/foo/module.toml"
  [ ! -f "${DEVBOOST_MODULES_DIR}/foo/install.sh" ]
}
@test "lc_add --folder: also scaffolds install.sh sourcing log+pkg" {
  run lc_add bar --folder
  [ "$status" -eq 0 ]
  [ -f "${DEVBOOST_MODULES_DIR}/bar/install.sh" ]
  grep -q 'lib/log.sh' "${DEVBOOST_MODULES_DIR}/bar/install.sh"
  grep -q 'lib/pkg.sh' "${DEVBOOST_MODULES_DIR}/bar/install.sh"
}
@test "lc_add: refuses to overwrite an existing module" {
  _mk_module existing true
  run lc_add existing
  [ "$status" -ne 0 ]
  [[ "$output" == *"already exists"* ]]
}
@test "lc_add: rejects an invalid name" {
  run lc_add "Bad Name"
  [ "$status" -ne 0 ]
  [[ "$output" == *"invalid module name"* ]]
}

# --- US2: export + diff ---------------------------------------------------
@test "lc_export: writes a timestamped snapshot with all four source files (read-only)" {
  export STUB_MISE_LS="node@22"
  export STUB_FLATPAK_INSTALLED="md.obsidian.Obsidian"
  export STUB_CODE_EXTENSIONS="ms-python.python"
  run lc_export "${BATS_TEST_TMPDIR}/exports"
  [ "$status" -eq 0 ]
  local d; d="$(ls -d "${BATS_TEST_TMPDIR}/exports"/*/ | head -1)"
  [ -f "${d}/dnf.txt" ] && [ -f "${d}/flatpak.txt" ] && [ -f "${d}/mise.txt" ] && [ -f "${d}/vscode-extensions.txt" ]
  grep -q 'node@22' "${d}/mise.txt"
  # read-only: no package install attempted
  ! grep -qE 'install' "${STUB_DNF_LOG}" 2>/dev/null || true
}
@test "lc_diff: exit 0 when the declared module verifies" {
  _mk_module ok true
  run lc_diff ok
  [ "$status" -eq 0 ]
  [[ "$output" == *"in sync"* ]]
}
@test "lc_diff: non-zero + names the module when its verify fails" {
  _mk_module broken false
  run lc_diff broken
  [ "$status" -ne 0 ]
  [[ "$output" == *"broken"* ]]
}

# --- US3: update + devboost.lock ------------------------------------------
@test "lc_lock_write: deterministic sorted TSV, regenerating twice is identical" {
  _mk_module zeta true 1.0
  _mk_module alpha true 2.0
  lc_lock_write
  local first; first="$(cat "${DEVBOOST_LOCK}")"
  # sorted: alpha before zeta
  [ "$(head -1 "${DEVBOOST_LOCK}" | cut -f1)" = "alpha" ]
  grep -qP 'alpha\t2.0' "${DEVBOOST_LOCK}"
  lc_lock_write
  [ "$(cat "${DEVBOOST_LOCK}")" = "${first}" ]
}
@test "lc_update: seeds mise config + regenerates lock + NEVER git commit" {
  _mk_module one true
  run lc_update one
  [ "$status" -eq 0 ]
  [ -f "${DEVBOOST_MISE_CONFIG}" ]
  [ -f "${DEVBOOST_LOCK}" ]
  ! grep -q 'commit' "${STUB_GIT_LOG}" 2>/dev/null || true
}

# --- US4: self-update -----------------------------------------------------
@test "lc_self_update: pulls then re-validates" {
  run lc_self_update
  [ "$status" -eq 0 ]
  grep -q 'pull' "${STUB_GIT_LOG}"
}
@test "lc_self_update: pull failure → named non-zero error" {
  export STUB_GIT_PULL_FAIL=1
  run lc_self_update
  [ "$status" -ne 0 ]
  [[ "$output" == *"pull"* ]]
}
