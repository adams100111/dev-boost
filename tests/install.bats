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

@test "run_install with no modules exits 0 and does not crash" {
  run bash -c 'source "$DEVBOOST_ROOT/lib/log.sh"; source "$DEVBOOST_ROOT/lib/toml.sh"
    source "$DEVBOOST_ROOT/lib/os.sh"; source "$DEVBOOST_ROOT/lib/module.sh"
    source "$DEVBOOST_ROOT/lib/depsort.sh"; source "$DEVBOOST_ROOT/lib/install.sh"
    export DEVBOOST_MODULES_DIR="'"$DEVBOOST_MODULES_DIR"'"; OS_DISTRO=fedora OS_FAMILY=fedora
    run_install --'
  [ "$status" -eq 0 ]
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
