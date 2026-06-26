#!/usr/bin/env bash
# scripts/build-bundle.sh — build the frozen devboost binary (typed engine) + checksums.
# Runnable locally and in CI. Output in dist/. A non-logic build helper; the engine itself
# is pure typed Python (no bash modules/lib to bundle anymore).
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
DIST="${ROOT}/dist"
rm -rf "${DIST}" "${ROOT}/engine/build" "${ROOT}/engine/dist"
mkdir -p "${DIST}"

case "$(uname -m)" in
  x86_64|amd64) ARCH=x86_64 ;;
  aarch64|arm64) ARCH=aarch64 ;;
  *) echo "build-bundle: unsupported arch $(uname -m)" >&2; exit 1 ;;
esac

# Bundle the static data the engine reads at runtime (resolved via devboost.exec.resources).
data_args=(--add-data "${ROOT}/profiles.toml:.")
[[ -d "${ROOT}/templates" ]] && data_args+=(--add-data "${ROOT}/templates:templates")
[[ -d "${ROOT}/data" ]] && data_args+=(--add-data "${ROOT}/data:data")

# Build the frozen one-file binary from the src-layout package.
#   --collect-submodules devboost  → ships modules/*.py so registry auto-discovery works frozen.
( cd "${ROOT}/engine"
  uv run --with pyinstaller pyinstaller --onefile --name devboost \
    --collect-submodules devboost \
    "${data_args[@]}" \
    --distpath "${DIST}" --workpath "${ROOT}/engine/build" --specpath "${ROOT}/engine/build" \
    pyinstaller_entry.py )

mv "${DIST}/devboost" "${DIST}/devboost-${ARCH}"

# Smoke-test the frozen binary (no Python runtime needed).
"${DIST}/devboost-${ARCH}" --version >/dev/null
echo "build-bundle: smoke ok ($("${DIST}/devboost-${ARCH}" --version))"

( cd "${DIST}" && sha256sum "devboost-${ARCH}" > "checksums-${ARCH}.txt" )
echo "build-bundle: wrote ${DIST}/devboost-${ARCH} + checksums-${ARCH}.txt"
