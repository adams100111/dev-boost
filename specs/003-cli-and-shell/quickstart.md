# Quickstart / Validation: cli-and-shell

Proves the cli + shell profiles end-to-end **hermetically** (no real installs/network)
using the bats stub harness. See `contracts/` for exact module interfaces.

## Prerequisites
- Repo checked out; `bats`, `jq`, `python3`. Specs 1–2 merged (mise, chezmoi, repos on `main`).
- External commands (`dnf`/`copr`, `npm`, `mise`, `cargo`, `chezmoi`, `fc-list`/`fc-cache`,
  `git`, `curl`, `sudo`) are **stubbed** by `tests/fixtures/base/`. No root/network.

## Run the tests (primary validation)
```bash
bats tests/cli-tools.bats tests/shell.bats tests/fonts.bats tests/dotfiles.bats tests/profiles.bats
# or the whole suite (incl. Spec 1/2 + engine):
bats tests/
```
Expected: all green — each tool installs+verifies, idempotent re-run, unsupported-OS
reported, claude-code orders after mise, fonts skipped when present, and `chezmoi apply`
writes the managed configs with EXACTLY ONE copy of each shell-init line on re-apply.

## Resolution smoke (list only, no installs)
```bash
DEVBOOST_MODULES_DIR="$PWD/modules" DEVBOOST_PROFILES="$PWD/profiles.toml" \
  ./bin/devboost list --profile cli,shell
```
Expected: topologically-ordered list, `mise` before `claude-code`, inited tools before
`dotfiles` before `bash-config`, no cycle.

## Manual smoke (optional, throwaway VM with Fedora)
```bash
DEVBOOST_MODULES_DIR="$PWD/modules" DEVBOOST_PROFILES="$PWD/profiles.toml" \
  ./bin/devboost install --profile cli,shell
```
Expected: all cli tools + claude-code present; starship is the prompt in a new shell;
ghostty installed with the shipped theme/font (Ptyxis still available); JetBrainsMono +
Meslo Nerd Fonts in `fc-list`; `~/.bashrc`/`~/.config/starship.toml`/`~/.tmux.conf`
applied; re-running reports every module **skipped**; `git ls-files` shows no secrets.

## Tear down
Throwaway VM only; no host changes when run via the test stubs.
