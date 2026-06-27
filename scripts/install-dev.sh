#!/usr/bin/env bash
# Install dev-boost as a global CLI from this clone so `devboost` runs from any
# directory (not just `cd engine && uv run`).
#
# Uses an EDITABLE uv tool install: the package keeps pointing at this checkout,
# so (a) profiles.toml / catalog.toml / ventoy data resolve correctly (resolved
# relative to the engine source, which stays in the clone) and (b) code edits are
# picked up live with no reinstall. A non-editable/wheel install would NOT work —
# the data files live at the repo root, outside the packaged module.
#
# Uninstall with:  uv tool uninstall devboost
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
uv tool install --editable "${ROOT}/engine"

echo
echo "Installed 'devboost' to your uv tool bin (usually ~/.local/bin)."
echo "If the command isn't found, put that dir on PATH:  uv tool update-shell"
