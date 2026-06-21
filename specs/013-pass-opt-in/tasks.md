# Tasks: pass-opt-in (data modules; keep 1096 green)
- [X] T001 Extend tests/fixtures/base/stubs.bash (backward-compatible): gpg stub (--list-secret-keys→STUB_GPG_KEYS; --quick-generate-key logs; STUB_GPG_LOG) + pass stub (init/show/git logs→STUB_PASS_LOG), NOT auto-installed (pass.bats calls base_install_security_stubs). Run bats tests/ → 1096 green.
- [X] T002 Add `security-cli = ["pass","pass-store"]` to profiles.toml (opt-in, NOT full); add membership test to tests/profiles.bats.
- [X] T003 [P] Write tests/pass.bats (RED): pass install+verify+unsupported-OS; pass-store gpg-gen-if-absent + pass init + repo clone + idempotent + verify .gpg-id.
- [X] T004 Implement modules/pass/{module.toml} + modules/pass-store/{module.toml,install.sh,verify.sh}. GREEN.
- [X] T005 Update docs/roadmap.md row 13 done + README (regen note); run full bats tests/ green.
