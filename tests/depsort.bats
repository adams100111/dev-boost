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
