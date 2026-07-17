#!/usr/bin/env bash
# scripts/preflight.sh — run the exact gates CI runs, the exact way CI runs them.
#
# Two problems this closes:
#   1. CI (ci.yml) was red for 20+ runs while releases shipped, because the release workflow
#      never ran the tests. release.yml now has a `checks` job; this is its local mirror, so
#      you can gate a tag before pushing it.
#   2. A test once passed locally (`.venv/bin/python -m pytest`) but failed only in CI, which
#      runs `uv run pytest` from a long checkout path. Run it CI's way — `uv run`, synced from
#      the lockfile — so "green locally" means "green in CI".
#
# Usage: bash scripts/preflight.sh   (from anywhere in the repo)
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}/engine"

command -v uv >/dev/null 2>&1 || { echo "preflight: uv not found — https://docs.astral.sh/uv/" >&2; exit 1; }

echo "preflight: uv sync"           && uv sync --quiet
echo "preflight: ruff"              && uv run ruff check
echo "preflight: mypy --strict"     && uv run mypy
echo "preflight: pytest"            && uv run pytest -q

# Version triple must agree, or release.yml's tag check fails.
v="$(grep -m1 -oP '^version = "\K[^"]+' pyproject.toml)"
i="$(grep -m1 -oP '^__version__ = "\K[^"]+' src/devboost/__init__.py)"
l="$(grep -A1 '^name = "devboost"' uv.lock | grep -m1 -oP 'version = "\K[^"]+')"
if [ "$v" != "$i" ] || [ "$v" != "$l" ]; then
  echo "preflight: version mismatch — pyproject=$v __version__=$i uv.lock=$l" >&2
  exit 1
fi

echo "preflight: OK — pyproject/__version__/uv.lock all $v; safe to tag v$v"
