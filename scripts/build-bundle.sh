#!/usr/bin/env bash
# scripts/build-bundle.sh — build the frozen devboost binary (typed engine) + checksums.
# Runnable locally and in CI. Output in dist/. A non-logic build helper; the engine itself
# is pure typed Python (no bash modules/lib to bundle anymore).
#
# Platforms: Linux x86_64/aarch64 and Apple Silicon (Darwin arm64). The body lives in
# `bb_main`, so the tests can source this file and call one function without building.
set -Eeuo pipefail

BB_OS="$(uname -s)"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="${ROOT}/dist"

# bb_arch — print the release asset key for this host, or fail with a reason.
bb_arch() {
  local machine
  machine="$(uname -m)"
  case "${BB_OS}/${machine}" in
    Linux/x86_64|Linux/amd64) echo x86_64 ;;
    Linux/aarch64|Linux/arm64) echo aarch64 ;;
    Darwin/arm64) echo darwin-arm64 ;;
    Darwin/x86_64)
      echo "build-bundle: Intel Macs are not supported (Apple Silicon only)" >&2
      return 1 ;;
    *) echo "build-bundle: unsupported platform ${BB_OS}/${machine}" >&2; return 1 ;;
  esac
}

# bb_sha256 FILE... — GNU coreutils where it exists, BSD/macOS `shasum` otherwise.
# Both print the same `<hash>  <name>` format, so checksums files stay interchangeable.
bb_sha256() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$@"
  else echo "build-bundle: need sha256sum or shasum" >&2; return 1; fi
}

bb_main() {
  local arch stage data_args
  arch="$(bb_arch)" || return 1

  cd "${ROOT}"
  rm -rf "${DIST}" "${ROOT}/engine/build" "${ROOT}/engine/dist"
  mkdir -p "${DIST}"

  # Bundle the static data the engine reads at runtime (resolved via devboost.exec.resources).
  data_args=(--add-data "${ROOT}/profiles.toml:.")
  [[ -f "${ROOT}/catalog.toml" ]] && data_args+=(--add-data "${ROOT}/catalog.toml:.")
  [[ -d "${ROOT}/templates" ]] && data_args+=(--add-data "${ROOT}/templates:templates")
  [[ -d "${ROOT}/data" ]] && data_args+=(--add-data "${ROOT}/data:data")
  # ventoy/ is bundled on Darwin too. The `installer` module is Linux-only, so the payload is
  # inert there; shipping it keeps ONE bundle layout across platforms (nothing downstream has
  # to branch on which resources exist inside the binary).
  [[ -d "${ROOT}/ventoy" ]] && data_args+=(--add-data "${ROOT}/ventoy:ventoy")
  # chezmoi dotfiles source — read by the Dotfiles module via settings.root/dotfiles so the
  # online (curl|bash) install also *configures* the tools it installs (no secrets in here).
  [[ -d "${ROOT}/dotfiles" ]] && data_args+=(--add-data "${ROOT}/dotfiles:dotfiles")

  # Build the frozen one-file binary from the src-layout package.
  #   --collect-submodules devboost  → ships modules/*.py so registry auto-discovery works frozen.
  ( cd "${ROOT}/engine"
    uv run --with pyinstaller pyinstaller --onefile --name devboost \
      --collect-submodules devboost \
      "${data_args[@]}" \
      --distpath "${DIST}" --workpath "${ROOT}/engine/build" --specpath "${ROOT}/engine/build" \
      pyinstaller_entry.py )

  mv "${DIST}/devboost" "${DIST}/devboost-${arch}"

  if [[ "${BB_OS}" == Darwin ]]; then
    # PyInstaller already ad-hoc signs the executable and every collected binary, and a onefile
    # cannot be re-signed afterwards (its payload is embedded). So: never pass
    # --codesign-identity, never re-sign — only verify, and fail the build if the check fails.
    codesign --verify --strict "${DIST}/devboost-${arch}"
    echo "build-bundle: codesign --verify --strict ok (ad-hoc signature from PyInstaller)"
  fi

  # Smoke-test the frozen binary (no Python runtime needed).
  "${DIST}/devboost-${arch}" --version >/dev/null
  echo "build-bundle: smoke ok ($("${DIST}/devboost-${arch}" --version))"
  if [[ "${BB_OS}" == Darwin ]]; then
    "${DIST}/devboost-${arch}" list macos >/dev/null
    echo "build-bundle: smoke ok (list macos)"
  fi

  if [[ "${BB_OS}" == Darwin ]]; then
    # No Ventoy staging on macOS: the Ventoy/USB builder is Linux-only, so there is no
    # injection archive and the checksums file lists the binary alone.
    ( cd "${DIST}" && bb_sha256 "devboost-${arch}" > "checksums-${arch}.txt" )
    echo "build-bundle: wrote ${DIST}/devboost-${arch}, checksums-${arch}.txt (no Ventoy archive)"
    return 0
  fi

  # Ventoy injection archive: lands the arch-matched binary at /opt/dev-boost/devboost on the
  # installed system (Ventoy unpacks /Bootstrap/devboost.tar.gz into the install root). The
  # Kickstart firstboot oneshot then runs `/opt/dev-boost/devboost install full`.
  stage="$(mktemp -d)"
  mkdir -p "${stage}/opt/dev-boost"
  install -m 0755 "${DIST}/devboost-${arch}" "${stage}/opt/dev-boost/devboost"
  tar -czf "${DIST}/devboost-${arch}.tar.gz" -C "${stage}" opt
  rm -rf "${stage}"

  ( cd "${DIST}" \
      && bb_sha256 "devboost-${arch}" "devboost-${arch}.tar.gz" > "checksums-${arch}.txt" )
  echo "build-bundle: wrote ${DIST}/devboost-${arch}, devboost-${arch}.tar.gz" \
       "(Ventoy injection), checksums-${arch}.txt"
}

# Run only when executed, not when sourced for tests (the same idiom as get.sh).
if ! (return 0 2>/dev/null); then
  bb_main "$@"
fi
