# Contract: `vscode` (US1)

Escape-hatch module sourcing `lib/log.sh`+`lib/pkg.sh`. `category="editors"`,
`requires=[]`, only `[install].fedora`. Curated extension IDs live in
`modules/vscode/extensions.txt` (data, one ID per line).

## `install.sh`
1. **MS repo** (idempotent): `sudo rpm --import https://packages.microsoft.com/keys/microsoft.asc`;
   write `/etc/yum.repos.d/vscode.repo` (`[code]`, `baseurl=https://packages.microsoft.com/yumrepos/vscode`,
   `enabled=1`, `gpgcheck=1`, `gpgkey=https://packages.microsoft.com/keys/microsoft.asc`) only
   if absent/different.
2. `sudo dnf install -y code`.
3. For each ID in `extensions.txt` **not** already in `code --list-extensions`:
   `code --install-extension <id> --force` (run as the invoking user, not root). Leave
   already-installed extensions untouched.
- `verify` (top-level): `command -v code` AND every `extensions.txt` ID present in
  `code --list-extensions`.
- Failure (e.g. `dnf install` fails) → `die` naming `vscode` + the command (FR-013).

## Tests (`tests/vscode.bats`) — stubbed dnf/rpm/code
- Fresh host: MS `vscode.repo` written; `dnf install -y code` attempted; each baseline
  extension installed via `code --install-extension`; verify GREEN.
- Partial state (`STUB_CODE_EXTENSIONS` already has some): only the **missing** extensions
  are installed; the present ones are NOT reinstalled.
- Idempotent: with `code` + all extensions present, the module verifies satisfied (engine skip).
- Repo idempotency: re-run does not duplicate `vscode.repo`.
- Unsupported-OS (non-fedora `OS_DISTRO`) → engine failure.
