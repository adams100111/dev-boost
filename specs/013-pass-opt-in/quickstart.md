# Quickstart: validate pass-opt-in
```sh
cd /home/dev/repos/dev-boost
bats tests/pass.bats ; bats tests/profiles.bats
```
Green proves: pass installs+verifies (SC-001); pass-store provisions GPG+init unattended, key seed-if-absent,
optional repo clone, .gpg-id present (SC-002); security-cli resolves + not in full; suite green (SC-003).
