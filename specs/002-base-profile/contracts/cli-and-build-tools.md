# Contract: US2 essential CLI tools + build-tools bundle

## Simple per-tool modules (pure TOML, one file each)
`coreutils, git, curl, wget, unzip, jq, htop, ripgrep, fd, fzf, tmux`. Shape:
```toml
name    = "ripgrep"
category = "base"
verify  = "command -v rg"
[install]
fedora = "sudo dnf install -y ripgrep"
debian = "sudo apt-get install -y ripgrep"
macos  = "brew install ripgrep"
```
Notes on verify commands where the binary ≠ package: `ripgrep`→`rg`, `fd`→`fd` (fedora
pkg `fd-find`; on fedora the binary is `fd`), `coreutils`→`command -v ls` (always present;
module mostly a documented no-op/guard). Each module `requires=[]`. No `install.sh`.

## build-tools bundle (single module)
- `verify`: key members present, e.g. `command -v gcc && command -v make && command -v cmake`.
- `[install].fedora`: `sudo dnf install -y make automake gcc gcc-c++ kernel-devel cmake
  git wget perl vim nano unzip gnupg fastfetch unrar android-tools fuse-libs ripgrep`
  (exact design §10c set; node/python/java intentionally excluded).
- `android-tools` here also feeds the later `react-native` profile.

## Tests (`tests/tools.bats`, `tests/build-tools.bats`) — stubbed dnf + command
- Each tool module: install command attempted for the fedora key; `verify` maps to the
  binary; idempotent re-run skipped (verify green).
- build-tools: the full package list is passed to the installer; verify checks key compilers.
- A tool with no key for the active OS → engine reports unsupported (failure).
- (Tools are mostly data, so tests focus on verify/resolution + one representative install.)
