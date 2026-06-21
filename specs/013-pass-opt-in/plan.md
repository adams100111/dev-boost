# Implementation Plan: pass-opt-in
**Branch**: `013-pass-opt-in` | **Date**: 2026-06-21 | **Spec**: [spec.md](./spec.md)
## Summary
Add `security-cli` opt-in profile = `pass` (CLI install) + `pass-store` (GPG key + `pass init` + optional
store-repo clone, unattended). Data modules; zero engine touch. Stub gpg/pass/git; test-first.
## Technical Context
Bash modules; deps pass, gpg, git (PATH-stubbable). Reuses lib/secrets.sh (requires secrets). No engine change.
## Constitution Check
I Engine+Data — PASS (modules only). II Idempotent — PASS (key/init seed-if-absent). III Reproducible — PASS
(no secrets committed; passphrase-less key documented). IV Unattended — PASS (batch key, no prompts). V Test-First
— PASS. VI Cross-OS — PASS (Fedora-only [install]). Result PASS.
## Project Structure
profiles.toml (+ security-cli) ; modules/pass/ ; modules/pass-store/ ; tests/pass.bats ;
tests/fixtures/base/stubs.bash (+ gpg/pass stubs, backward-compatible) ; tests/profiles.bats (membership)
## Phases: 0 (decisions in spec) · 1 (data-model below + contract) · 2 (tasks).
## Data model
| module | requires | install | verify |
|---|---|---|---|
| pass | [] | dnf install pass | command -v pass |
| pass-store | ["pass","secrets"] | gpg key if absent (batch, passphrase-less) + `pass init <gpg-id>` + clone $DEVBOOST_PASS_REPO→~/.password-store if set | ~/.password-store/.gpg-id present |
profiles.toml: security-cli = ["pass","pass-store"]  (opt-in; NOT in full)
