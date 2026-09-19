#!/usr/bin/env bash
# scripts/get.sh — dev-boost public bootstrap (one of two bash files in the shipped tree).
# Usage: curl -fsSL https://raw.githubusercontent.com/adams100111/dev-boost/main/scripts/get.sh | bash -s -- terminal
# Downloads the (os, arch)-matched frozen devboost binary from the latest GitHub Release,
# verifies SHA256, installs it (onto PATH via a symlink in the user bin dir), and runs
# `devboost install`. On Linux it also fetches the Ventoy injection archive; macOS has none.
# No data tarball for the engine — profiles + templates are bundled inside the binary
# (resolved via devboost.exec.resources). Zero logic beyond fetch/verify/link/exec.
#
# macOS notes: only Apple Silicon (a Rosetta-translated shell still counts), macOS 15+,
# never as root, and Homebrew (which brings the command-line tools) is bootstrapped first
# after a single `sudo -v` read from the tty — so the whole thing works under `curl | bash`.
#
# Only bash 3.2 features: a fresh Mac runs this under /bin/bash 3.2.
set -Eeuo pipefail

GS_REPO="adams100111/dev-boost"
GS_DEFAULT_BASE="https://github.com/${GS_REPO}/releases/latest/download"
# DEVBOOST_RELEASE_BASE lets a pre-release rehearsal point at a local dir (file://…).
GS_BASE="${DEVBOOST_RELEASE_BASE:-$GS_DEFAULT_BASE}"
GS_PREFIX="${HOME}/.local/share/devboost"
# Test seams: the Homebrew prefix to probe, and the tty prompts/stdin are read from.
GS_BREW_PREFIX="${GS_BREW_PREFIX:-/opt/homebrew}"
GS_TTY="${GS_TTY:-/dev/tty}"
GS_BREW_INSTALLER="https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"
GS_MACOS_MIN=15
GS_MACOS_TESTED=27
# The download dir, as a global so the EXIT/signal traps can still see it.
GS_TMP=""

gs_err() { echo "get.sh: $*" >&2; }

gs_os() {
  case "$(uname -s)" in
    Linux) echo linux ;;
    Darwin) echo darwin ;;
    *) gs_err "unsupported OS: $(uname -s) (Linux and macOS only)"; return 1 ;;
  esac
}

# gs_arch — the release asset key for this host: x86_64 | aarch64 | darwin-arm64.
gs_arch() {
  local os
  os="$(gs_os)" || return 1
  if [ "$os" = darwin ]; then
    case "$(uname -m)" in
      arm64|aarch64) echo darwin-arm64 ;;
      x86_64|amd64)
        # A Rosetta-translated shell on Apple Silicon reports x86_64; the host is still
        # arm64 and gets the arm64 binary. Only a real Intel Mac is refused.
        if [ "$(sysctl -n hw.optional.arm64 2>/dev/null || echo 0)" = 1 ]; then
          echo darwin-arm64
        else
          gs_err "Intel Macs are not supported — dev-boost needs Apple Silicon (arm64)"
          return 1
        fi ;;
      *) gs_err "unsupported architecture: $(uname -m) (arm64 only on macOS)"; return 1 ;;
    esac
    return 0
  fi
  case "$(uname -m)" in
    x86_64|amd64) echo x86_64 ;;
    aarch64|arm64) echo aarch64 ;;
    *) gs_err "unsupported architecture: $(uname -m) (x86_64/aarch64 only)"; return 1 ;;
  esac
}

# gs_macos_check_version — refuse below 15, warn on 15 and on anything past the tested 27.
gs_macos_check_version() {
  local version major
  version="$(sw_vers -productVersion 2>/dev/null || echo '')"
  major="${version%%.*}"
  case "$major" in
    ''|*[!0-9]*)
      # Fail closed: an unreadable probe is not evidence of a supported macOS.
      gs_err "the macOS version could not be read — dev-boost needs macOS 15 or newer" \
        "(27 recommended)"
      return 1 ;;
  esac
  if [ "$major" -lt "$GS_MACOS_MIN" ]; then
    gs_err "macOS ${version} is not supported — dev-boost needs macOS 15 or newer" \
      "(27 recommended)"
    return 1
  fi
  if [ "$major" -eq "$GS_MACOS_MIN" ]; then
    gs_err "macOS 15 is best-effort (untested); 27 and 26 are supported"
  elif [ "$major" -gt "$GS_MACOS_TESTED" ]; then
    gs_err "macOS ${version} is newer than tested (27) — continuing"
  fi
}

# gs_macos_prereqs — make sure Homebrew is there (it installs the command-line tools too),
# then put it on PATH. A present Homebrew is left completely alone.
gs_macos_prereqs() {
  if [ ! -x "${GS_BREW_PREFIX}/bin/brew" ]; then
    gs_err "Homebrew is missing — installing it (this also installs the Xcode CLT)."
    if ! ( : <"$GS_TTY" ) 2>/dev/null; then
      gs_err "no terminal available for the sudo prompt — install Homebrew first," \
        "then re-run this script"
      return 1
    fi
    gs_err "macOS needs your password once; nothing after this prompt is interactive."
    # The redirect is this (user) shell's, on purpose: sudo must read the password from
    # the tty, not from the script `curl` is piping into bash. SC2024 is about the
    # opposite case (redirecting *output* into a root-owned path).
    # shellcheck disable=SC2024
    sudo -v <"$GS_TTY" || { gs_err "sudo failed — cannot install Homebrew"; return 1; }
    NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL "${GS_CURL_PROTO[@]}" "$GS_BREW_INSTALLER")" \
      || { gs_err "the Homebrew installer failed"; return 1; }
  fi
  if [ -x "${GS_BREW_PREFIX}/bin/brew" ]; then
    eval "$("${GS_BREW_PREFIX}/bin/brew" shellenv)"
  fi
}

# --proto/--proto-redir: an https:// release must stay https:// even across a 302, so a
# redirect cannot silently downgrade the fetch to plaintext. file:// is the D9 local
# rehearsal hatch, allowed on the first hop only.
GS_CURL_PROTO=(--proto '=https,file' --proto-redir '=https')

gs_fetch() {
  local url="$1" out="$2"
  if command -v curl >/dev/null 2>&1
  then curl -fsSL "${GS_CURL_PROTO[@]}" "$url" -o "$out"
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

# gs_check_base — never fetch the release over plaintext. file:// is the local-rehearsal
# escape hatch (DEVBOOST_RELEASE_BASE), everything else must be HTTPS.
gs_check_base() {
  case "$GS_BASE" in
    https://*|file://*) : ;;
    *) gs_err "refusing a non-HTTPS release base: ${GS_BASE}"; return 1 ;;
  esac
}

# gs_warn_base — an overridden base is where BOTH the binary and its checksums come from,
# so the checksum chain cannot vouch for it. Say so, loudly, and name the host.
gs_warn_base() {
  local host
  if [ "$GS_BASE" = "$GS_DEFAULT_BASE" ]; then
    return 0
  fi
  host="${GS_BASE#*://}"
  host="${host%%/*}"
  if [ -z "$host" ]; then host="(this machine)"; fi
  gs_err "WARNING: DEVBOOST_RELEASE_BASE overrides the official release."
  gs_err "WARNING: devboost AND its checksums will be fetched from: ${host}"
  gs_err "WARNING: full base: ${GS_BASE}"
}

# gs_cleanup — remove the download dir, from any exit path. Safe to call twice.
gs_cleanup() {
  if [ -n "$GS_TMP" ]; then
    rm -rf "$GS_TMP"
    GS_TMP=""
  fi
  return 0
}

# gs_on_signal RC — clean up, then really die (a bare trap would resume the script).
gs_on_signal() {
  gs_cleanup
  exit "$1"
}

gs_main() {
  local os arch tmp profiles bindir link
  gs_check_base || return 1
  os="$(gs_os)" || return 1

  if [ "$#" -eq 0 ]; then profiles=(terminal); else profiles=("$@"); fi

  # Every macOS refusal fires before any network call or any change to HOME.
  if [ "$os" = darwin ]; then
    if [ "$(id -u)" = 0 ]; then
      gs_err "don't run this as root on macOS — Homebrew refuses root. Run it as your user."
      return 1
    fi
    if [ "${profiles[0]}" = "usb" ]; then
      gs_err "the USB builder is Linux-only"
      return 1
    fi
  fi

  arch="$(gs_arch)" || return 1

  if [ "$os" = darwin ]; then
    gs_macos_check_version || return 1
    gs_macos_prereqs || return 1
  fi

  gs_warn_base

  # Clean the download dir on EVERY exit path: a plain return, a `set -e` abort, and
  # Ctrl-C / SIGHUP / SIGTERM. (`exec` fires no trap, so that path removes it by hand.)
  trap 'gs_cleanup' EXIT RETURN
  trap 'gs_on_signal 130' INT
  trap 'gs_on_signal 129' HUP
  trap 'gs_on_signal 143' TERM
  GS_TMP="$(mktemp -d)"
  chmod 700 "$GS_TMP"
  tmp="$GS_TMP"

  gs_err "downloading devboost-${arch} from the latest release…"
  gs_fetch "${GS_BASE}/checksums.txt" "${tmp}/checksums.txt" \
    || { gs_err "no published release yet (or network error). See README for releasing."
         return 1; }
  gs_fetch "${GS_BASE}/devboost-${arch}" "${tmp}/devboost-${arch}" || return 1
  gs_verify "$tmp" "devboost-${arch}" || { gs_err "checksum mismatch: devboost-${arch}"; return 1; }
  if [ "$os" = linux ]; then
    # The Ventoy injection archive is shipped alongside the binary so the online-installed
    # `devboost installer` can build a USB with no clone/build. The builder is Linux-only.
    gs_fetch "${GS_BASE}/devboost-${arch}.tar.gz" "${tmp}/devboost-${arch}.tar.gz" || return 1
    gs_verify "$tmp" "devboost-${arch}.tar.gz" \
      || { gs_err "checksum mismatch: devboost-${arch}.tar.gz"; return 1; }
  fi

  mkdir -p "${GS_PREFIX}/bin"
  install -m 0755 "${tmp}/devboost-${arch}" "${GS_PREFIX}/bin/devboost"
  if [ "$os" = linux ]; then
    install -m 0644 "${tmp}/devboost-${arch}.tar.gz" "${GS_PREFIX}/bin/devboost-${arch}.tar.gz"
  fi
  gs_cleanup

  # Put `devboost` on PATH: keep the payload in the data dir, link it into the user bin dir.
  bindir="${XDG_BIN_HOME:-${HOME}/.local/bin}"
  mkdir -p "$bindir"
  link="${bindir}/devboost"
  ln -sf "${GS_PREFIX}/bin/devboost" "$link"
  gs_err "installed ${GS_PREFIX}/bin/devboost → linked ${link}"
  case ":${PATH}:" in
    *":${bindir}:"*) : ;;
    *) gs_err "note: ${bindir} is not on PATH — add it for future shells:"
       if [ "$os" = darwin ]; then
         gs_err "      echo 'export PATH=\"${bindir}:\$PATH\"' >> ~/.zshrc"
         gs_err "      (dev-boost's shell config adds it for you once installed)"
       else
         gs_err "      echo 'export PATH=\"${bindir}:\$PATH\"' >> ~/.bashrc"
       fi ;;
  esac

  if [ "$os" = linux ]; then
    # Also link into a root-PATH dir (when sudo permits) so `sudo devboost …` resolves
    # — Fedora's sudo secure_path excludes ~/.local/bin. Best-effort; never fatal.
    if sudo -n true 2>/dev/null; then
      sudo -n ln -sf "${GS_PREFIX}/bin/devboost" /usr/local/bin/devboost 2>/dev/null || true
    fi
  fi

  # `usb`/`none` => install the builder only; do NOT configure this machine.
  # (On Darwin `usb` was already refused, before any download.)
  if [ "${profiles[0]}" = "usb" ] || [ "${profiles[0]}" = "none" ]; then
    if [ "$os" = darwin ]; then
      gs_err "devboost installed. Configure this machine with:  devboost install terminal"
      return 0
    fi
    gs_err "devboost installed (with the USB injection archive)."
    gs_err "build a bootable USB on this machine:  sudo devboost installer"
    return 0
  fi
  gs_err "running: devboost install ${profiles[*]}"
  # Under `curl … | bash` stdin is the script itself, so any prompt would read the script.
  # On macOS, read the install's stdin from the tty instead (when there is one).
  if [ "$os" = darwin ] && [ ! -t 0 ] && ( : <"$GS_TTY" ) 2>/dev/null; then
    exec "${GS_PREFIX}/bin/devboost" install "${profiles[@]}" <"$GS_TTY"
  fi
  exec "${GS_PREFIX}/bin/devboost" install "${profiles[@]}"
}

# Run only when executed (incl. via `curl | bash`), not when sourced for tests.
if ! (return 0 2>/dev/null); then
  gs_main "$@"
fi
