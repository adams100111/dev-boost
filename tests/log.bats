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
