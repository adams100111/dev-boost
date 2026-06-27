#!/usr/bin/env bash
# scripts/release.sh — local build + publish of a dev-boost release (beside the CI workflow).
#
# PyInstaller can't cross-compile, so this builds the HOST arch only. Run it on an x86_64 box
# AND on an aarch64 box to assemble a complete 2-arch release; run on one for a single-arch
# release. Each run (re)builds the host-arch frozen binary, uploads it to the v<version>
# release (creating the release if it doesn't exist yet), and regenerates checksums.txt from
# ALL binaries currently on the release — so get.sh's fetch+verify keeps working either way.
#
# Version comes from engine/pyproject.toml and must equal devboost.__version__ (the same guard
# CI enforces). Requires an authenticated gh CLI. Pass --dry-run to print the build/publish
# commands without running them.
#
# NOTE: this is the manual path *beside* .github/workflows/release.yml. Creating a NEW v* tag
# here (first run for a version with no release yet) also fires that workflow, which rebuilds
# and clobbers. For a CI-free release, disable/guard release.yml, or run this only against a
# tag/release that already exists (appending an arch never re-triggers CI).
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

DRY=0
[[ "${1:-}" == "--dry-run" || "${1:-}" == "-n" ]] && DRY=1
run() { if [[ ${DRY} -eq 1 ]]; then echo "+ $*"; else "$@"; fi; }

command -v gh >/dev/null 2>&1 || { echo "release: gh CLI required" >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "release: gh not authenticated (run: gh auth login)" >&2; exit 1; }

# --- version guard: pyproject == __version__, tag = v<version> ---
version="$(grep -m1 -oP '^version = "\K[^"]+' engine/pyproject.toml || true)"
init="$(grep -m1 -oP '^__version__ = "\K[^"]+' engine/src/devboost/__init__.py || true)"
[[ -n "${version}" && "${version}" == "${init}" ]] || {
  echo "release: version mismatch — pyproject='${version}' __version__='${init}'" >&2; exit 1; }
tag="v${version}"

case "$(uname -m)" in
  x86_64|amd64) arch=x86_64 ;;
  aarch64|arm64) arch=aarch64 ;;
  *) echo "release: unsupported arch $(uname -m)" >&2; exit 1 ;;
esac
echo "release: ${tag} (host arch: ${arch})"

# --- build the host-arch frozen binary (+ injection tarball + per-arch checksums) ---
run bash scripts/build-bundle.sh

# --- ensure the release exists (create at HEAD if not) ---
if gh release view "${tag}" >/dev/null 2>&1; then
  echo "release: ${tag} exists — appending ${arch}"
else
  echo "release: creating ${tag} at $(git rev-parse --short HEAD)"
  run gh release create "${tag}" \
    --target "$(git rev-parse HEAD)" \
    --title "dev-boost ${tag}" \
    --notes "Frozen dev-boost binary for ${tag}. Install: scripts/get.sh." \
    --latest
fi

# --- upload this arch's assets (clobber so re-runs refresh) ---
run gh release upload "${tag}" \
  "dist/devboost-${arch}" "dist/devboost-${arch}.tar.gz" --clobber

# --- regenerate checksums.txt from ALL binaries now on the release (get.sh verifies against it) ---
if [[ ${DRY} -eq 1 ]]; then
  echo "+ gh release download ${tag} --pattern 'devboost-*' --dir <tmp> --clobber"
  echo "+ (cd <tmp> && sha256sum devboost-* > checksums.txt)"
  echo "+ gh release upload ${tag} <tmp>/checksums.txt --clobber"
else
  sums="$(mktemp -d)"
  trap 'rm -rf "${sums}"' EXIT
  gh release download "${tag}" --pattern 'devboost-*' --dir "${sums}" --clobber
  ( cd "${sums}" && sha256sum devboost-* > checksums.txt )
  gh release upload "${tag}" "${sums}/checksums.txt" --clobber
fi

echo "release: ${tag} published (${arch}); checksums.txt regenerated"
if [[ ${DRY} -eq 0 ]]; then
  gh release view "${tag}" --json assets --jq '"assets: " + ([.assets[].name] | join(", "))'
fi
