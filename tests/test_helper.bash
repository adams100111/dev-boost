# Resolve repo root from the tests dir and expose it.
DEVBOOST_ROOT="$(cd "$(dirname "${BATS_TEST_FILENAME}")/.." && pwd)"
export DEVBOOST_ROOT
# Point the engine at per-test fixture dirs when set by a test.
load_lib() { source "${DEVBOOST_ROOT}/lib/$1"; }
