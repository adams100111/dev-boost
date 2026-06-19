# lib/os.sh — OS detection. Source-only.
os_family_of() {
  case "$1" in
    fedora|rhel|centos|rocky|almalinux) echo fedora;;
    ubuntu|debian|linuxmint|pop)        echo debian;;
    arch|manjaro|endeavouros)           echo arch;;
    macos|darwin)                       echo macos;;
    *)                                  echo "$1";;
  esac
}

os_detect() {
  local f="${OS_RELEASE_FILE:-/etc/os-release}"
  if [[ "$(uname -s)" == "Darwin" ]]; then
    OS_DISTRO=macos
  elif [[ -r "$f" ]]; then
    OS_DISTRO="$(. "$f" 2>/dev/null; echo "${ID:-unknown}")"
  else
    OS_DISTRO=unknown
  fi
  OS_FAMILY="$(os_family_of "$OS_DISTRO")"
  OS_ARCH="$(uname -m)"
  export OS_DISTRO OS_FAMILY OS_ARCH
}
