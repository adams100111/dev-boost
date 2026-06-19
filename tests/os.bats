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
