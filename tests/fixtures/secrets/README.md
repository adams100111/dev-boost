# tests/fixtures/secrets — stub harness for secrets-and-auth tests

This directory provides hermetic test infrastructure for `lib/secrets.sh`,
`lib/github.sh`, and `modules/secrets` / `modules/ssh-setup`. No real network
calls, no real credentials.

## Files

| File | Purpose |
|------|---------|
| `bundle.json` | Sample decrypted secrets bundle with `GIT_USER`, `GIT_EMAIL`, `GITHUB_PAT`. Used as the output of the `age` stub. |
| `profiles.toml` | Minimal TOML with an empty `[profiles]` table so `profile_expand` resolves bare module tokens without a missing-file error. |
| `stubs.bash` | Sourced bats helper. Provides PATH-stub functions for `age`, `curl`, `ssh-keygen`; scratch HOME/XDG setup; `DEVBOOST_SECRETS*` wiring. |

## Using the stubs

In any `.bats` file:

```bash
load test_helper
load fixtures/secrets/stubs

setup() {
  stubs_setup   # installs stub bins + sets a scratch HOME
}

teardown() {
  stubs_teardown
}
```

### Env knobs

| Variable | Effect |
|----------|--------|
| `STUB_AGE_FAIL=1` | `age` stub exits 1 (simulates bad key / decrypt failure) |
| `STUB_CURL_STATUS` | HTTP status code the `curl` stub returns (default 200) |
| `STUB_CURL_BODY` | Raw body the `curl` stub returns (overrides URL-keyed canned responses) |
| `STUB_CURL_LOG` | Path to the call-log file written by the `curl` stub (default `$BATS_TEST_TMPDIR/curl-calls.log`) |
