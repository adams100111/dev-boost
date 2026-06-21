load test_helper
load fixtures/base/stubs

# scripts/make-secrets.sh — hermetic: age/age-keygen stubbed, real jq. The PAT must never leak.

setup() {
  load_lib log.sh
  base_setup
  cat > "$(base_stub_dir)/age-keygen" <<'STUB'
#!/usr/bin/env bash
# -o <file> → write a fake identity; -y <file> → print a fake recipient.
out=""; yflag=""
while (($#)); do case "$1" in -o) out="$2"; shift 2;; -y) yflag="$2"; shift 2;; *) shift;; esac; done
[[ -n "$yflag" ]] && { printf 'age1faketestrecipient000000000000000000000000000000000\n'; exit 0; }
[[ -n "$out" ]] && { printf 'AGE-SECRET-KEY-1FAKE\n' > "$out"; }
exit 0
STUB
  cat > "$(base_stub_dir)/age" <<'STUB'
#!/usr/bin/env bash
# age -r <recipient> -o <bundle> : read stdin (the JSON), write a ciphertext marker (NOT the plaintext).
printf 'age %s\n' "$*" >> "${STUB_AGE_LOG:?}"
out=""; while (($#)); do [[ "$1" == "-o" ]] && out="$2"; shift; done
cat >/dev/null   # consume the plaintext JSON; never store it
[[ -n "$out" ]] && printf 'age-encrypted-bundle\n' > "$out"
exit 0
STUB
  chmod +x "$(base_stub_dir)/age-keygen" "$(base_stub_dir)/age"
  export STUB_AGE_LOG="${BATS_TEST_TMPDIR}/age.log"; : > "${STUB_AGE_LOG}"
  OUT="${BATS_TEST_TMPDIR}/sec"
}
teardown() { base_teardown; }

_make() {
  bash -c "
    export HOME='${HOME}'; export PATH='${PATH}'; export STUB_AGE_LOG='${STUB_AGE_LOG}'
    export GIT_USER='octocat' GIT_EMAIL='o@e.x' GITHUB_PAT='ghp_SUPERSECRETvalue000'
    bash '${DEVBOOST_ROOT}/scripts/make-secrets.sh' --out '${OUT}'
  " 2>&1
}

@test "make-secrets: produces an encrypted bundle + identity" {
  run _make
  [ "$status" -eq 0 ]
  [ -f "${OUT}/secrets.age" ]
  [ -f "${OUT}/age-key.txt" ]
  [ "$(cat "${OUT}/secrets.age")" = "age-encrypted-bundle" ]   # ciphertext marker, not plaintext
}

@test "make-secrets: the PAT never appears in output, the bundle, or the age log" {
  run _make
  [ "$status" -eq 0 ]
  [[ "$output" != *"ghp_SUPERSECRETvalue000"* ]]
  ! grep -q 'ghp_SUPERSECRETvalue000' "${OUT}/secrets.age"
  ! grep -q 'ghp_SUPERSECRETvalue000' "${STUB_AGE_LOG}"
}

@test "make-secrets: encrypts to the derived recipient" {
  run _make
  [ "$status" -eq 0 ]
  grep -q -- '-r age1faketestrecipient' "${STUB_AGE_LOG}"
}

@test "make-secrets: idempotent — reuses an existing identity" {
  _make
  printf 'AGE-SECRET-KEY-1FAKE\n' > "${OUT}/age-key.txt"  # pre-existing
  run _make
  [ "$status" -eq 0 ]
  [[ "$output" == *"reusing existing identity"* ]]
}
