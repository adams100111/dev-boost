#!/usr/bin/env bash
# scripts/get.sh — dev-boost public bootstrap (one of two bash files in the shipped tree).
# Usage: curl -fsSL https://raw.githubusercontent.com/adams100111/dev-boost/main/scripts/get.sh | bash -s -- terminal
# Downloads the arch-matched frozen devboost binary from the latest GitHub Release, verifies
# SHA256, installs it (onto PATH via a symlink in the user bin dir), and runs `devboost install`.
# No data tarball — profiles + templates are
# bundled inside the binary (resolved via devboost.exec.resources). Zero logic beyond fetch/verify/link/exec.
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

gs_fetch() {
  local url="$1" out="$2"
  if command -v curl >/dev/null 2>&1; then curl -fsSL "$url" -o "$out"
  elif command -v wget >/dev/null 2>&1; then wget -qO "$out" "$url"
  else gs_err "need curl or wget"; return 1; fi
}

gs_sha256() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$@"
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
  local arch tmp profiles bindir link
  arch="$(gs_arch)" || return 1
  profiles=("$@"); [ "${#profiles[@]}" -eq 0 ] && profiles=(terminal)

  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN

  gs_err "downloading devboost-${arch} from the latest release…"
  gs_fetch "${GS_BASE}/checksums.txt" "${tmp}/checksums.txt" \
    || { gs_err "no published release yet (or network error). See README for releasing."; return 1; }
  gs_fetch "${GS_BASE}/devboost-${arch}" "${tmp}/devboost-${arch}" || return 1
  gs_verify "$tmp" "devboost-${arch}" || { gs_err "checksum mismatch: devboost-${arch}"; return 1; }
  # The Ventoy injection archive is shipped alongside the binary so the online-installed
  # `devboost installer` can build a USB with no clone/build.
  gs_fetch "${GS_BASE}/devboost-${arch}.tar.gz" "${tmp}/devboost-${arch}.tar.gz" || return 1
  gs_verify "$tmp" "devboost-${arch}.tar.gz" \
    || { gs_err "checksum mismatch: devboost-${arch}.tar.gz"; return 1; }

  mkdir -p "${GS_PREFIX}/bin"
  install -m 0755 "${tmp}/devboost-${arch}" "${GS_PREFIX}/bin/devboost"
  install -m 0644 "${tmp}/devboost-${arch}.tar.gz" "${GS_PREFIX}/bin/devboost-${arch}.tar.gz"
  rm -rf "$tmp"

  # Put `devboost` on PATH: keep the payload in the data dir, link it into the user bin dir.
  bindir="${XDG_BIN_HOME:-${HOME}/.local/bin}"
  mkdir -p "$bindir"
  link="${bindir}/devboost"
  ln -sf "${GS_PREFIX}/bin/devboost" "$link"
  gs_err "installed ${GS_PREFIX}/bin/devboost → linked ${link}"
  case ":${PATH}:" in
    *":${bindir}:"*) : ;;
    *) gs_err "note: ${bindir} is not on PATH — add it for future shells:"
       gs_err "      echo 'export PATH=\"${bindir}:\$PATH\"' >> ~/.bashrc" ;;
  esac

  # `usb`/`none` => install the builder only; do NOT configure this machine.
  if [ "${profiles[0]}" = "usb" ] || [ "${profiles[0]}" = "none" ]; then
    gs_err "devboost installed (with the USB injection archive)."
    gs_err "build a bootable USB on this machine:  sudo \"${link}\" installer"
    return 0
  fi
  gs_err "running: devboost install ${profiles[*]}"
  exec "${GS_PREFIX}/bin/devboost" install "${profiles[@]}"
}

# Run only when executed (incl. via `curl | bash`), not when sourced for tests.
if ! (return 0 2>/dev/null); then
  gs_main "$@"
fi
