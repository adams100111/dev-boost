# Research: pass-opt-in (design §11 oracle)
- pass = passwordstore.org CLI (GPG+git). Fedora pkg `pass`. Complements Bitwarden GUI; opt-in (not full).
- Unattended decrypt: passphrase-less GPG key (batch quick-generate-key) — acceptable for opt-in store,
  documented; gnome-keyring-unlocked is the alternative. Mirrors how `secrets` provisions `age`.
- `pass init <gpg-id>` writes ~/.password-store/.gpg-id. Optional `$DEVBOOST_PASS_REPO` clone for an
  existing store. No secrets committed. All stubbed in tests (gpg/pass/git).
