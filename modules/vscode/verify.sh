#!/usr/bin/env bash
# modules/vscode/verify.sh — idempotency guard for the vscode module.
# GREEN iff `code` is on PATH AND every curated baseline extension (extensions.txt)
# is already installed (present in `code --list-extensions`). No prompts; read-only.
set -Eeuo pipefail

command -v code >/dev/null 2>&1 || exit 1

ext_file="${DEVBOOST_ROOT}/modules/vscode/extensions.txt"
[[ -f "${ext_file}" ]] || exit 1

# Snapshot installed extensions once.
installed="$(code --list-extensions 2>/dev/null || true)"

while IFS= read -r line || [[ -n "${line}" ]]; do
  # Skip blanks and comments.
  [[ -z "${line}" || "${line}" == \#* ]] && continue
  grep -qxF "${line}" <<<"${installed}" || exit 1
done < "${ext_file}"

exit 0
