#!/usr/bin/env bash
# modules/ghostty/install.sh — install Ghostty terminal.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent; non-interactive.
#
# Fedora: installed via the scottames/ghostty COPR repository.
# Ubuntu/Debian: installed via the mkasberg/ghostty-ubuntu community .deb releases.
# Ptyxis is intentionally left available as the GNOME default terminal fallback.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

if [[ "${OS_FAMILY}" == "debian" ]]; then
  # ---------------------------------------------------------------------------
  # Ubuntu/Debian: download and install the matching .deb from
  # mkasberg/ghostty-ubuntu community releases.
  # Asset naming: ghostty_<version>_<arch>_<codename>.deb
  # e.g.: ghostty_1.3.1-0.ppa2_amd64_24.04.deb
  # ---------------------------------------------------------------------------
  if command -v ghostty >/dev/null 2>&1; then
    log_skip "ghostty: already installed"
  else
    log_info "ghostty: installing .deb from ghostty-ubuntu releases"
    _arch="$(dpkg --print-architecture)"
    _codename="$(. "${OS_RELEASE_FILE:-/etc/os-release}"; echo "${VERSION_CODENAME}")"
    _url="$(curl -fsSL https://api.github.com/repos/mkasberg/ghostty-ubuntu/releases/latest \
            | grep -oE 'https://[^"]+_'"${_arch}"'_'"${_codename}"'\.deb' | head -1)"
    if [[ -n "${_url}" ]]; then
      _tmp="$(mktemp --suffix=.deb)"
      curl -fsSL "${_url}" -o "${_tmp}"
      sudo apt-get install -y "${_tmp}"
      rm -f "${_tmp}"
      log_ok "ghostty: installed from ${_url}"
    else
      log_warn "ghostty: no matching .deb for ${_arch}/${_codename} (non-blocking)"
    fi
  fi
else
  # ---------------------------------------------------------------------------
  # Fedora: enable the scottames/ghostty COPR repository if not already present.
  # Check first; only run `copr enable` when the COPR is absent so the operation
  # is strictly add-if-absent (mirrors rpmfusion/docker module pattern).
  # ---------------------------------------------------------------------------
  if dnf copr list 2>/dev/null | grep -q 'scottames/ghostty'; then
    log_info "ghostty: scottames/ghostty COPR already enabled — skipping"
  else
    log_info "ghostty: enabling scottames/ghostty COPR"
    sudo dnf copr enable -y scottames/ghostty
  fi

  # Install ghostty from the COPR repository.
  log_info "ghostty: installing ghostty package"
  sudo dnf install -y ghostty

  # Note: Ptyxis is NOT removed — it remains available as the GNOME fallback
  # terminal emulator. Users who prefer Ghostty can set it as their default
  # without losing Ptyxis.

  log_ok "ghostty: installed via scottames/ghostty COPR"
fi
