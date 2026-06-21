# Contract: security-cli (pass + pass-store)
## pass (FR-001): dnf install pass; verify command -v pass; Fedora-only; idempotent; unsupported-OS.
## pass-store (FR-002): requires pass+secrets.
- GPG: if `gpg --list-secret-keys` shows none → `gpg --batch --pinentry-mode loopback --passphrase ''
  --quick-generate-key "<uid>" default default never` (passphrase-less); else no-op. gpg-id = uid/email.
- `pass init <gpg-id>` (writes ~/.password-store/.gpg-id).
- if $DEVBOOST_PASS_REPO set → `git clone "$DEVBOOST_PASS_REPO" ~/.password-store` (when store absent).
- verify: ~/.password-store/.gpg-id present.
## Tests (tests/pass.bats, stubbed gpg/pass/git):
- pass: dnf install pass attempted; verify GREEN; unsupported-OS empty.
- pass-store: no key → gpg --quick-generate-key invoked + pass init; key present → NOT regenerated;
  $DEVBOOST_PASS_REPO set → git clone to ~/.password-store; verify .gpg-id present; idempotent.
## profiles: security-cli = [pass, pass-store]; NOT in full.
