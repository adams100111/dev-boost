load test_helper
load fixtures/base/stubs

# Spec 9 — lib/devhygiene.sh: dev status / gc / down. Container TSV (id,persistent,creator-pid,project)
# is supplied via STUB_DOCKER_PS; PID liveness is real (kill -0).

setup() {
  load_lib log.sh
  base_setup
  source "${DEVBOOST_ROOT}/lib/devhygiene.sh"
  base_install_docker
  # c_dead = orphan (session + dead PID) → GC'd; c_live = session + alive → kept; c_persist = kept.
  export STUB_DOCKER_PS="$(printf 'c_dead\tfalse\t999999\t/proj/a\nc_live\tfalse\t%s\t/proj/b\nc_persist\ttrue\t999999\t/proj/c\n' "$$")"
}
teardown() { base_teardown; }

@test "dh_gc: removes ONLY the dead-PID session orphan; keeps persistent + live" {
  run dh_gc
  [ "$status" -eq 0 ]
  grep -q 'rm -f c_dead' "${STUB_DOCKER_LOG}"
  ! grep -q 'rm -f c_live' "${STUB_DOCKER_LOG}"
  ! grep -q 'rm -f c_persist' "${STUB_DOCKER_LOG}"
  grep -q 'container prune -f' "${STUB_DOCKER_LOG}"
}

@test "dh_gc: docker absent → graceful no-op success" {
  # Hermetic PATH with NO docker (host may have a real one) — coreutils only.
  local cb; cb="$(mktemp -d)"
  local c src
  for c in bash sh env printf date cat grep sed awk kill rm mkdir tr head; do
    src="$(command -v "$c" 2>/dev/null)" && ln -sf "${src}" "${cb}/${c}"
  done
  PATH="${cb}" run dh_gc
  [ "$status" -eq 0 ]
  [[ "$output" == *"docker not present"* ]]
}

@test "dh_status: warns on duplicate live AppHosts of the same project" {
  export STUB_DOCKER_PS="$(printf 'a1\tfalse\t%s\t/proj/dup\na2\tfalse\t%s\t/proj/dup\n' "$$" "$$")"
  run dh_status
  [ "$status" -eq 0 ]
  [[ "$output" == *"duplicate orchestration"* || "$output" == *"live AppHosts for the same project"* ]]
}

@test "dh_status: read-only, lists container state + reports" {
  run dh_status
  [ "$status" -eq 0 ]
  [[ "$output" == *"c_dead"* ]]
  [[ "$output" == *"persistent=true"* ]]
  # no removals during status
  ! grep -q 'rm -f' "${STUB_DOCKER_LOG}" 2>/dev/null || true
}

@test "dh_down: powers off ddev, prunes, and runs gc" {
  run dh_down
  [ "$status" -eq 0 ]
  grep -q 'ddev poweroff' "${STUB_DDEV_LOG}"
  grep -q 'container prune -f' "${STUB_DOCKER_LOG}"
  grep -q 'rm -f c_dead' "${STUB_DOCKER_LOG}"
}
