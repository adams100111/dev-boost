# dev-boost engine

`./install.sh [--profile a,b]` — bootstrap a workstation from declarative modules.

## Commands
- `bin/devboost install [--profile full] [--force] [--strict]`
- `bin/devboost verify  [--profile full]`
- `bin/devboost list    [--profile full]`
- `bin/devboost doctor`

## Add a module
Drop `modules/<name>.toml`:
```toml
name = "ripgrep"
requires = []            # optional
[install]
default = "mise use -g ..."   # or fedora/ubuntu/macos/windows keys
verify  = "rg --version"      # success => already installed => skipped
```
Complex tools: `modules/<name>/module.toml` (+ run logic referenced from an install command).

## Requirements
bash 5, python3 ≥3.11, jq. Tests: `bats tests/`.
