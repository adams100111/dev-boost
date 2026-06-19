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
@test "top-level verify key takes precedence over install.verify" {
  [ "$(module_verify_cmd toplevelverify)" = "echo toplevel-verify-cmd" ]
}
