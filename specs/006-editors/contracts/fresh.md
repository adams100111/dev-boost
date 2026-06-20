# Contract: `fresh` (US2)

Escape-hatch module sourcing `lib/log.sh`+`lib/pkg.sh`. `category="editors"`,
`requires=[]`, only `[install].fedora`. Installs the `sinelaw/fresh` terminal editor.

## `install.sh`
Try in order, stop at first success (skip whole step if `command -v fresh` already true):
1. **Fedora `.rpm`** (latest GitHub release):
   `url=$(curl -s https://api.github.com/repos/sinelaw/fresh/releases/latest | <pick browser_download_url matching ".$(uname -m).rpm">)`;
   `curl -sL "$url" -o /tmp/fresh-editor.rpm && sudo rpm -U /tmp/fresh-editor.rpm`.
2. **Official install script**: `curl -fsSL https://raw.githubusercontent.com/sinelaw/fresh/refs/heads/master/scripts/install.sh | sh`.
3. **Fallback**: `cargo install --locked fresh-editor` (cargo from base build-tools/mise).
After each step, re-check `command -v fresh`; on success stop. If all three fail → `die`
naming `fresh` + the last command attempted (FR-005, FR-013 — never a silent skip).
- `verify` (top-level): `command -v fresh`.

## Tests (`tests/fresh.bats`) — stubbed curl/rpm/cargo via `STUB_FRESH_INSTALL_VIA`
- `STUB_FRESH_INSTALL_VIA=rpm`: GitHub-release `.rpm` fetched + `rpm -U` attempted; verify GREEN.
- `STUB_FRESH_INSTALL_VIA=script`: rpm path "fails", install script attempted; verify GREEN.
- `STUB_FRESH_INSTALL_VIA=cargo`: rpm + script "fail", `cargo install --locked fresh-editor`
  attempted; verify GREEN.
- `STUB_FRESH_INSTALL_VIA=none`: all three "fail" → module FAILS naming `fresh` + the command.
- Idempotent: `fresh` already present → engine skip (no install attempted).
- Unsupported-OS → engine failure.
