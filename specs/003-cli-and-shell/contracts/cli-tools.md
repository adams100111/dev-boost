# Contract: `cli` tool modules

## Simple per-tool modules (pure TOML, one file each)
`eza, bat, btop, zoxide, atuin, direnv, delta, lazygit, lazydocker, dust, duf, sd, yq,
tealdeer, fastfetch`. Shape:
```toml
name="eza"; category="cli"; verify="command -v eza"
[install]
fedora="sudo dnf install -y eza"
debian="sudo apt-get install -y eza"
macos="brew install eza"
```
Binary≠package notes: `delta` pkg `git-delta` → bin `delta`; `tealdeer` → bin `tldr`;
`dust` pkg `rust-dust` (Fedora) → bin `dust`; `btop`/`bat` already-correct (bat in cli per
user request; htop stays in base). `requires=[]`.

## Escape-hatch modules
- **gh** (`modules/gh/`): add the GitHub CLI dnf repo if absent, then install; verify `command -v gh`.
- **tpm** (`modules/tpm/`): `git clone https://github.com/tmux-plugins/tpm ~/.tmux/plugins/tpm` if absent; verify `[ -d ~/.tmux/plugins/tpm ]`. `requires=[]` (tmux is base).
- **claude-code** (`modules/claude-code/`): `requires=["mise"]`; **ensure a node runtime via mise FIRST** (`mise use -g node@lts` if no node — a fresh machine's mise has no node, so `npm` would be missing), THEN `npm install -g @anthropic-ai/claude-code`; verify `command -v claude`. Config is chezmoi-managed (dotfiles). Never echo any token. (Test asserts node-ensure precedes npm in the call-log.)

## Tests (`tests/cli-tools.bats`) — stubbed dnf/npm/mise/git/sudo
- Each representative tool: resolved fedora install command + binary verify; idempotent skip; unsupported-OS → engine failure (not skip).
- claude-code: orders AFTER mise (depsort); install reached via `--force` (host-independent); npm global install attempted; no token echoed.
- gh: repo added once (not re-added); tpm: clone only when absent.
