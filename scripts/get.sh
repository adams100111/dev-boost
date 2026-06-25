#!/usr/bin/env bash
# scripts/get.sh — dev-boost public bootstrap.
# Usage: curl -fsSL https://raw.githubusercontent.com/adams100111/dev-boost/main/scripts/get.sh | bash -s -- terminal
# Downloads the arch-matched frozen devboost binary + data tarball from the latest
# GitHub Release, verifies SHA256, installs to ~/.local/share/devboost, and runs install.
set -Eeuo pipefail

GS_REPO="adams100111/dev-boost"
GS_BASE="https://github.com/${GS_REPO}/releases/latest/download"
GS_PREFIX="${HOME}/.local/share/devboost"

gs_err() { echo "get.sh: $*" >&2; }

gs_arch() {
  case "$(uname -m)" in
    x86_64|amd64) echo x86_64 ;;
    aarch64|arm64) echo aarch64 ;;
    *) gs_err "unsupported architecture: $(uname -m) (x86_64/aarch64 only)"; return 1 ;;
  esac
}

# gs_fetch URL OUTFILE — download via curl or wget.
gs_fetch() {
  local url="$1" out="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" -o "$out"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$out" "$url"
  else
    gs_err "need curl or wget"; return 1
  fi
}

gs_sha256() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@";
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$@";
  else gs_err "need sha256sum or shasum"; return 1; fi
}

# gs_verify DIR FILE — verify FILE in DIR against DIR/checksums.txt.
gs_verify() {
  local dir="$1" file="$2" line
  line="$(grep -E "  ${file}\$" "${dir}/checksums.txt")" || {
    gs_err "no checksum entry for ${file}"; return 1
  }
  printf '%s\n' "$line" | ( cd "$dir" && gs_sha256 -c - ) >/dev/null
}

gs_main() {
  local arch tmp profiles
  arch="$(gs_arch)" || return 1
  command -v tar >/dev/null 2>&1 || { gs_err "need tar"; return 1; }
  profiles=("$@"); [ "${#profiles[@]}" -eq 0 ] && profiles=(terminal)

  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN

  gs_err "downloading devboost-${arch} + data from the latest release…"
  gs_fetch "${GS_BASE}/checksums.txt" "${tmp}/checksums.txt" \
    || { gs_err "no published release yet (or network error). See README for releasing."; return 1; }
  gs_fetch "${GS_BASE}/devboost-${arch}" "${tmp}/devboost-${arch}" || return 1
  gs_fetch "${GS_BASE}/devboost-data.tar.gz" "${tmp}/devboost-data.tar.gz" || return 1

  gs_verify "$tmp" "devboost-${arch}"     || { gs_err "checksum mismatch: devboost-${arch}"; return 1; }
  gs_verify "$tmp" "devboost-data.tar.gz" || { gs_err "checksum mismatch: data tarball"; return 1; }

  mkdir -p "${GS_PREFIX}/bin"
  tar -xzf "${tmp}/devboost-data.tar.gz" -C "${GS_PREFIX}"
  install -m 0755 "${tmp}/devboost-${arch}" "${GS_PREFIX}/bin/devboost"

  gs_err "installed to ${GS_PREFIX}; running: devboost install ${profiles[*]}"
  export DEVBOOST_ROOT="${GS_PREFIX}"
  rm -rf "$tmp"
  exec "${GS_PREFIX}/bin/devboost" install "${profiles[@]}"
}

# Run only when executed (incl. via `curl | bash`), not when sourced for tests.
if ! (return 0 2>/dev/null); then
  gs_main "$@"
fi
