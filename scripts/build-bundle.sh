#!/usr/bin/env bash
# scripts/build-bundle.sh — build the frozen devboost binary + data tarball + checksums.
# Runnable locally and in CI. Output in dist/.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
DIST="${ROOT}/dist"
rm -rf "${DIST}" build *.spec
mkdir -p "${DIST}"

# Resolve arch label.
case "$(uname -m)" in
  x86_64|amd64) ARCH=x86_64 ;;
  aarch64|arm64) ARCH=aarch64 ;;
  *) echo "build-bundle: unsupported arch $(uname -m)" >&2; exit 1 ;;
esac

# Build the frozen binary in an isolated venv.
python3 -m venv "${DIST}/.buildvenv"
# shellcheck disable=SC1091
. "${DIST}/.buildvenv/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet ./engine pyinstaller
pyinstaller --onefile --name devboost \
  --collect-all typer --collect-all click \
  "${ROOT}/engine/devboost/__main__.py"
mv "${ROOT}/dist/devboost" "${DIST}/devboost-${ARCH}"
deactivate

# Data tarball (noarch): exactly the data the engine reads at runtime.
tar -czf "${DIST}/devboost-data.tar.gz" -C "${ROOT}" modules lib dotfiles profiles.toml

# Checksums.
( cd "${DIST}" && sha256sum "devboost-${ARCH}" devboost-data.tar.gz > checksums.txt )

echo "build-bundle: wrote ${DIST}/devboost-${ARCH}, devboost-data.tar.gz, checksums.txt"
