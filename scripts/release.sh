#!/usr/bin/env bash
# scripts/release.sh — local build + publish of a dev-boost release (beside the CI workflow).
#
# PyInstaller can't cross-compile, so this builds the HOST arch only. Run it on an x86_64 box,
# an aarch64 box AND an Apple Silicon Mac to assemble the complete release. Each run:
#
#   1. (re)builds the host-arch frozen binary;
#   2. creates the v<version> release as a DRAFT if it does not exist yet (a draft is
#      invisible to `releases/latest`, so get.sh and self-update never see a half-built
#      release);
#   3. uploads this arch's assets, regenerates checksums.txt from ALL binaries on the
#      release, and uploads it;
#   4. downloads every asset back and verifies it against checksums.txt;
#   5. only then publishes the release and marks it latest — once every expected asset is
#      present (or with --publish, for a deliberately partial release). Until then it stays
#      a draft and the run says which assets are still missing.
#
# A release that is already published is never re-uploaded over: replacing an asset there
# would briefly serve it against a stale checksums.txt.
#
# Version comes from engine/pyproject.toml and must equal devboost.__version__ (the same guard
# CI enforces). Requires an authenticated gh CLI. Flags: --dry-run (-n) prints the
# build/publish commands without running them; --publish publishes even when some arch is
# still missing.
#
# NOTE: this is the manual path *beside* .github/workflows/release.yml. Creating a NEW v* tag
# here (first run for a version with no release yet) also fires that workflow, which rebuilds
# and clobbers. For a CI-free release, disable/guard release.yml, or run this only against a
# tag/release that already exists (appending an arch never re-triggers CI).
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

DRY=0
FORCE_PUBLISH=0
for arg in "$@"; do
  case "${arg}" in
    --dry-run|-n) DRY=1 ;;
    --publish) FORCE_PUBLISH=1 ;;
    *) echo "release: unknown option '${arg}' (want --dry-run, --publish)" >&2; exit 1 ;;
  esac
done
run() { if [[ ${DRY} -eq 1 ]]; then echo "+ $*"; else "$@"; fi; }

# Every asset a complete release carries. Publishing waits until all are present.
EXPECTED_ASSETS=(devboost-x86_64 devboost-x86_64.tar.gz devboost-aarch64
  devboost-aarch64.tar.gz devboost-darwin-arm64)

command -v gh >/dev/null 2>&1 || { echo "release: gh CLI required" >&2; exit 1; }
gh auth status >/dev/null 2>&1 \
  || { echo "release: gh not authenticated (run: gh auth login)" >&2; exit 1; }

RL_OS="$(uname -s)"

# rl_version FILE NAME — print the first `NAME = "x.y.z"` value in FILE. `sed -nE` (POSIX
# ERE) rather than `grep -oP`: BSD/macOS grep has no -P.
rl_version() {
  local file="$1" name="$2"
  sed -nE "s/^${name} = \"([^\"]+)\".*/\\1/p" "${file}" | head -n1
}

# rl_arch — the release asset key for this host (the same mapping as build-bundle's bb_arch;
# release.sh is standalone and does not source it).
rl_arch() {
  local machine
  machine="$(uname -m)"
  case "${RL_OS}/${machine}" in
    Linux/x86_64|Linux/amd64) echo x86_64 ;;
    Linux/aarch64|Linux/arm64) echo aarch64 ;;
    Darwin/arm64) echo darwin-arm64 ;;
    Darwin/x86_64)
      echo "release: Intel Macs are not supported (Apple Silicon only)" >&2
      return 1 ;;
    *) echo "release: unsupported platform ${RL_OS}/${machine}" >&2; return 1 ;;
  esac
}

# rl_sha256 FILE... — GNU coreutils where present, BSD/macOS `shasum` otherwise. Same output
# format, so checksums.txt is identical whichever host regenerates it.
rl_sha256() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$@"
  else echo "release: need sha256sum or shasum" >&2; return 1; fi
}

# rl_release_assets DIR — the release assets (never checksums.txt) downloaded into DIR.
rl_release_assets() {
  local f
  for f in "$1"/devboost-*; do
    [[ -f "${f}" ]] && basename "${f}"
  done
  return 0
}

# --- version guard: pyproject == __version__, tag = v<version> ---
version="$(rl_version engine/pyproject.toml version || true)"
init="$(rl_version engine/src/devboost/__init__.py __version__ || true)"
[[ -n "${version}" && "${version}" == "${init}" ]] || {
  echo "release: version mismatch — pyproject='${version}' __version__='${init}'" >&2; exit 1; }
tag="v${version}"

arch="$(rl_arch)" || exit 1
echo "release: ${tag} (host arch: ${arch})"

# --- build the host-arch frozen binary (+ injection tarball + per-arch checksums) ---
run bash scripts/build-bundle.sh

# --- ensure the release exists — as a DRAFT (create at HEAD if not) ---
published=0
if gh release view "${tag}" >/dev/null 2>&1; then
  if [[ "$(gh release view "${tag}" --json isDraft --jq .isDraft)" == "false" ]]; then
    published=1
  fi
  echo "release: ${tag} exists ($([[ ${published} -eq 1 ]] && echo published || echo draft))" \
    "— appending ${arch}"
else
  echo "release: creating ${tag} (draft) at $(git rev-parse --short HEAD)"
  run gh release create "${tag}" \
    --draft \
    --target "$(git rev-parse HEAD)" \
    --title "dev-boost ${tag}" \
    --notes "Frozen dev-boost binary for ${tag}. Install: scripts/get.sh."
fi

# --- upload this arch's assets (clobber so re-runs of a draft refresh) ---
# macOS ships the binary alone: the Ventoy injection archive is a Linux-only artifact, so
# build-bundle never produces one there.
uploads=("dist/devboost-${arch}")
[[ "${RL_OS}" == Darwin ]] || uploads+=("dist/devboost-${arch}.tar.gz")
if [[ ${published} -eq 1 ]]; then
  existing="$(gh release view "${tag}" --json assets --jq '.assets[].name')"
  for f in "${uploads[@]}"; do
    if grep -qx "$(basename "${f}")" <<<"${existing}"; then
      echo "release: ${tag} is already published and has $(basename "${f}") — refusing to" \
        "replace it (it would be served against a stale checksums.txt). Draft or delete" \
        "the release first." >&2
      exit 1
    fi
  done
fi
run gh release upload "${tag}" "${uploads[@]}" --clobber

if [[ ${DRY} -eq 1 ]]; then
  echo "+ gh release download ${tag} --pattern 'devboost-*' --dir <tmp> --clobber"
  echo "+ (cd <tmp> && rl_sha256 <every devboost-* asset> > checksums.txt)"
  echo "+ gh release upload ${tag} <tmp>/checksums.txt --clobber"
  echo "+ gh release download ${tag} --dir <verify> --clobber"
  echo "+ (cd <verify> && rl_sha256 -c checksums.txt)"
  echo "+ gh release edit ${tag} --draft=false --latest   # only once every asset is present"
  exit 0
fi

work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT
mkdir -p "${work}/sums" "${work}/verify"

# --- regenerate checksums.txt from ALL binaries now on the release ---
gh release download "${tag}" --pattern 'devboost-*' --dir "${work}/sums" --clobber
assets=()  # bash 3.2 (a stock Mac) has no mapfile
while IFS= read -r f; do assets+=("${f}"); done < <(rl_release_assets "${work}/sums")
[[ ${#assets[@]} -gt 0 ]] || { echo "release: no devboost-* assets on ${tag}" >&2; exit 1; }
( cd "${work}/sums" && rl_sha256 "${assets[@]}" > checksums.txt )
gh release upload "${tag}" "${work}/sums/checksums.txt" --clobber

# --- verify: download everything back and check it against the uploaded checksums.txt ---
gh release download "${tag}" --dir "${work}/verify" --clobber
[[ -f "${work}/verify/checksums.txt" ]] \
  || { echo "release: checksums.txt did not round-trip on ${tag}" >&2; exit 1; }
published_assets=()
while IFS= read -r f; do published_assets+=("${f}"); done < <(rl_release_assets "${work}/verify")
[[ ${#published_assets[@]} -gt 0 ]] \
  || { echo "release: no devboost-* assets came back from ${tag}" >&2; exit 1; }
for f in "${published_assets[@]}"; do
  awk -v f="${f}" '$2 == f { found = 1 } END { exit !found }' "${work}/verify/checksums.txt" \
    || { echo "release: ${f} has no entry in checksums.txt — not publishing" >&2; exit 1; }
done
( cd "${work}/verify" && rl_sha256 -c checksums.txt >/dev/null ) \
  || { echo "release: ${tag} assets do not match checksums.txt — left as a draft" >&2; exit 1; }
echo "release: verified ${#published_assets[@]} asset(s) against checksums.txt"

# --- publish + mark latest, only when the release is complete (or forced) ---
missing=()
for want in "${EXPECTED_ASSETS[@]}"; do
  [[ -f "${work}/verify/${want}" ]] || missing+=("${want}")
done
if [[ ${published} -eq 1 ]]; then
  echo "release: ${tag} published (${arch} appended); checksums.txt regenerated"
elif [[ ${#missing[@]} -eq 0 || ${FORCE_PUBLISH} -eq 1 ]]; then
  gh release edit "${tag}" --draft=false --latest
  echo "release: ${tag} published and marked latest"
else
  echo "release: ${tag} left as a DRAFT — still missing: ${missing[*]}"
  echo "release: run this on the remaining hosts (or re-run with --publish to ship as is)"
fi
gh release view "${tag}" --json assets --jq '"assets: " + ([.assets[].name] | join(", "))'
