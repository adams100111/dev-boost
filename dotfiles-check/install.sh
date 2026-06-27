#!/usr/bin/env bash
# dotfiles installer
# Usage:
#   ./install.sh              — interactive
#   ./install.sh --yes        — install everything without prompts
#   ./install.sh --no-pkgs    — symlinks only, skip package installs
#   ./install.sh --dry-run    — preview all actions, make no changes
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Flags ─────────────────────────────────────────────────────────────────────
DRY_RUN=false
YES=false
NO_PKGS=false
for arg in "$@"; do
  case "$arg" in
    --dry-run)  DRY_RUN=true ;;
    --yes|-y)   YES=true ;;
    --no-pkgs)  NO_PKGS=true ;;
  esac
done

# ── Colours ───────────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'
  CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
else
  GREEN=''; YELLOW=''; RED=''; CYAN=''; BOLD=''; NC=''
fi

info()    { echo -e "${GREEN}[+]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
error()   { echo -e "${RED}[✘]${NC} $*" >&2; }
skip()    { echo -e "${CYAN}[=]${NC} $* (already installed)"; }
section() { echo -e "\n${BOLD}── $* ──${NC}"; }
dryrun()  { echo -e "${YELLOW}[dry]${NC} $*"; }

# ── Track results for summary ─────────────────────────────────────────────────
INSTALLED=()
SKIPPED=()
FAILED=()

mark_installed() { INSTALLED+=("$1"); }
mark_skipped()   { SKIPPED+=("$1"); }
mark_failed()    { FAILED+=("$1"); }

# ── OS / arch detection ───────────────────────────────────────────────────────
OS="$(uname -s)"        # Linux | Darwin
RAW_ARCH="$(uname -m)"  # x86_64 | aarch64 | armv7l | i686

# Normalise to common names
case "$RAW_ARCH" in
  x86_64)         ARCH_GENERIC="amd64";  ARCH_ALT="x86_64" ;;
  aarch64|arm64)  ARCH_GENERIC="arm64";  ARCH_ALT="arm64"  ;;
  armv7l|armhf)   ARCH_GENERIC="armhf";  ARCH_ALT="armv7"  ;;
  *)              ARCH_GENERIC="$RAW_ARCH"; ARCH_ALT="$RAW_ARCH" ;;
esac

IS_DEBIAN=false
IS_MACOS=false
[[ "$OS" == "Linux" ]] && command -v apt-get &>/dev/null && IS_DEBIAN=true
[[ "$OS" == "Darwin" ]] && IS_MACOS=true

# ── Helpers ───────────────────────────────────────────────────────────────────
is_installed() { command -v "$1" &>/dev/null; }

# confirm <question> — returns 0 for yes, 1 for no
confirm() {
  $YES && return 0
  local ans
  read -rp "$1 [y/N] " ans || true
  [[ "$ans" =~ ^[Yy]$ ]]
}

run() {
  if $DRY_RUN; then
    dryrun "$*"
  else
    "$@"
  fi
}

# apt_install <pkg> [pkg...] — install if not already present, with OS guard
apt_install() {
  $IS_DEBIAN || { warn "apt not available on $OS — skipping: $*"; return; }
  DEBIAN_FRONTEND=noninteractive sudo apt-get install -y -qq "$@"
}

# github_latest <owner/repo> — returns latest tag name
github_latest() {
  curl -fsSL "https://api.github.com/repos/$1/releases/latest" \
    | grep '"tag_name"' | head -1 | sed 's/.*"tag_name": *"//;s/".*//'
}

# ── ~/.local/bin/env — PATH bootstrap file ────────────────────────────────────
ensure_local_bin_env() {
  local env_file="$HOME/.local/bin/env"
  mkdir -p "$HOME/.local/bin"
  if [[ ! -f "$env_file" ]]; then
    if $DRY_RUN; then
      dryrun "create $env_file (PATH bootstrap)"
    else
      cat > "$env_file" <<'EOF'
#!/bin/sh
case ":${PATH}:" in
  *:"$HOME/.local/bin":*) ;;
  *) export PATH="$HOME/.local/bin:$PATH" ;;
esac
EOF
      info "created $env_file"
    fi
  fi
}

# ── Symlink helper ────────────────────────────────────────────────────────────
symlink() {
  local src="$1" dst="$2" label="${3:-}"
  [[ -z "$label" ]] && label="$(basename "$dst")"

  if $DRY_RUN; then
    dryrun "symlink $src → $dst"
    return
  fi

  mkdir -p "$(dirname "$dst")"

  if [[ -L "$dst" ]]; then
    # Already a symlink — re-point it silently
    ln -sf "$src" "$dst"
    info "linked $label"
  elif [[ -e "$dst" ]]; then
    warn "Backing up existing $dst → $dst.bak"
    mv "$dst" "$dst.bak"
    ln -sf "$src" "$dst"
    info "linked $label (old file backed up)"
  else
    ln -sf "$src" "$dst"
    info "linked $label"
  fi
}

# ═════════════════════════════════════════════════════════════════════════════
# PACKAGE INSTALLERS
# ═════════════════════════════════════════════════════════════════════════════

install_apt_bundle() {
  section "apt packages"

  local pkgs=(tmux ripgrep git-delta direnv tealdeer jq btop bat fd-find openssh-client rsync)

  # eza is in Ubuntu 24.04+ (noble) apt; older releases need a workaround
  local ubuntu_ver
  ubuntu_ver=$(lsb_release -rs 2>/dev/null || echo "0")
  if awk "BEGIN{exit !($ubuntu_ver >= 24.04)}"; then
    pkgs+=(eza)
  else
    warn "Ubuntu < 24.04 detected — eza will be installed from GitHub"
  fi

  if $DRY_RUN; then
    dryrun "apt-get install -y ${pkgs[*]}"
  else
    info "Running apt update..."
    DEBIAN_FRONTEND=noninteractive sudo apt-get update -qq
    DEBIAN_FRONTEND=noninteractive sudo apt-get install -y -qq "${pkgs[@]}"
  fi

  # Ubuntu installs bat as 'batcat' and fd as 'fdfind' — create shims
  if ! $DRY_RUN; then
    if [[ -f /usr/bin/batcat && ! -f "$HOME/.local/bin/bat" ]]; then
      ln -sf /usr/bin/batcat "$HOME/.local/bin/bat"
      info "shimmed: bat → batcat"
    fi
    if [[ -f /usr/bin/fdfind && ! -f "$HOME/.local/bin/fd" ]]; then
      ln -sf /usr/bin/fdfind "$HOME/.local/bin/fd"
      info "shimmed: fd → fdfind"
    fi
  fi
}

install_starship() {
  if is_installed starship; then
    skip "starship $(starship --version 2>/dev/null | head -1)"
    mark_skipped "starship"; return
  fi
  info "Installing starship..."
  if $DRY_RUN; then dryrun "curl starship installer | sh"; return; fi
  curl -fsSL https://starship.rs/install.sh | sh -s -- --yes
  mark_installed "starship"
}

install_eza_github() {
  if is_installed eza; then
    skip "eza $(eza --version 2>/dev/null | head -1)"
    mark_skipped "eza"; return
  fi
  info "Installing eza from GitHub..."
  local ver
  ver=$(github_latest "eza-community/eza" | tr -d 'v')
  local url="https://github.com/eza-community/eza/releases/download/v${ver}/eza_${ARCH_ALT}-unknown-linux-musl.tar.gz"
  if $DRY_RUN; then dryrun "download eza $ver ($ARCH_ALT)"; return; fi
  curl -fsSL "$url" | tar -xz -C "$HOME/.local/bin" eza 2>/dev/null \
    && mark_installed "eza" \
    || { error "eza install failed"; mark_failed "eza"; }
}

install_lazygit() {
  if is_installed lazygit; then
    skip "lazygit $(lazygit --version 2>/dev/null | grep -o 'version=[^,]*')"
    mark_skipped "lazygit"; return
  fi
  info "Installing lazygit..."
  local ver arch_str
  ver=$(github_latest "jesseduffield/lazygit" | tr -d 'v')
  # lazygit uses x86_64 for amd64, arm64 for arm64
  case "$ARCH_GENERIC" in
    amd64)  arch_str="x86_64" ;;
    arm64)  arch_str="arm64"  ;;
    armhf)  arch_str="armv6"  ;;
    *)      arch_str="$RAW_ARCH" ;;
  esac
  local url="https://github.com/jesseduffield/lazygit/releases/download/v${ver}/lazygit_${ver}_Linux_${arch_str}.tar.gz"
  if $DRY_RUN; then dryrun "download lazygit $ver ($arch_str)"; return; fi
  curl -fsSL "$url" | tar -xz -C /tmp lazygit \
    && sudo mv /tmp/lazygit /usr/local/bin/ \
    && mark_installed "lazygit" \
    || { error "lazygit install failed"; mark_failed "lazygit"; }
}

install_yq() {
  if is_installed yq; then
    skip "yq $(yq --version 2>/dev/null | head -1)"
    mark_skipped "yq"; return
  fi
  info "Installing yq..."
  local ver arch_str
  ver=$(github_latest "mikefarah/yq")
  # yq uses amd64/arm64 (dpkg-style)
  case "$ARCH_GENERIC" in
    amd64)  arch_str="amd64" ;;
    arm64)  arch_str="arm64" ;;
    armhf)  arch_str="arm"   ;;
    *)      arch_str="$ARCH_GENERIC" ;;
  esac
  local url="https://github.com/mikefarah/yq/releases/download/${ver}/yq_linux_${arch_str}"
  if $DRY_RUN; then dryrun "download yq $ver ($arch_str)"; return; fi
  sudo curl -fsSL "$url" -o /usr/local/bin/yq \
    && sudo chmod +x /usr/local/bin/yq \
    && mark_installed "yq" \
    || { error "yq install failed"; mark_failed "yq"; }
}

install_atuin() {
  if is_installed atuin || [[ -f "$HOME/.atuin/bin/atuin" ]]; then
    local ver
    ver=$({ atuin --version 2>/dev/null || "$HOME/.atuin/bin/atuin" --version 2>/dev/null; } | head -1)
    skip "atuin $ver"
    mark_skipped "atuin"; return
  fi
  info "Installing atuin..."
  if $DRY_RUN; then dryrun "curl https://setup.atuin.sh | bash"; return; fi
  curl -fsSL https://setup.atuin.sh | bash \
    && mark_installed "atuin" \
    || { error "atuin install failed"; mark_failed "atuin"; }
}

install_zoxide() {
  if is_installed zoxide; then
    skip "zoxide $(zoxide --version 2>/dev/null)"
    mark_skipped "zoxide"; return
  fi
  info "Installing zoxide..."
  if $DRY_RUN; then dryrun "curl zoxide installer | sh"; return; fi
  curl -fsSL https://raw.githubusercontent.com/ajeetdsouza/zoxide/main/install.sh | sh \
    && mark_installed "zoxide" \
    || { error "zoxide install failed"; mark_failed "zoxide"; }
}

install_fzf() {
  if is_installed fzf || [[ -f "$HOME/.fzf/bin/fzf" ]]; then
    local ver
    ver=$({ fzf --version 2>/dev/null || "$HOME/.fzf/bin/fzf" --version 2>/dev/null; } | head -1)
    skip "fzf $ver"
    mark_skipped "fzf"; return
  fi
  info "Installing fzf..."
  if $DRY_RUN; then dryrun "git clone fzf && install"; return; fi
  git clone --depth 1 https://github.com/junegunn/fzf.git "$HOME/.fzf" \
    && "$HOME/.fzf/install" --all --no-update-rc \
    && mark_installed "fzf" \
    || { error "fzf install failed"; mark_failed "fzf"; }
}

# ═════════════════════════════════════════════════════════════════════════════
# SYMLINKS
# ═════════════════════════════════════════════════════════════════════════════

link_configs() {
  section "config symlinks"

  symlink "$DOTFILES_DIR/bash/bashrc"                "$HOME/.bashrc"                          "~/.bashrc"
  symlink "$DOTFILES_DIR/bash/fzf.bash"              "$HOME/.fzf.bash"                        "~/.fzf.bash"
  symlink "$DOTFILES_DIR/starship/starship.toml"     "$HOME/.config/starship.toml"            "starship.toml"
  symlink "$DOTFILES_DIR/bat/config"                 "$HOME/.config/bat/config"               "bat/config"
  symlink "$DOTFILES_DIR/ripgrep/ripgreprc"          "$HOME/.config/ripgrep/ripgreprc"        "ripgrep/ripgreprc"
  symlink "$DOTFILES_DIR/tmux/tmux.conf"             "$HOME/.config/tmux/tmux.conf"           "tmux/tmux.conf"
  symlink "$DOTFILES_DIR/git/gitconfig"              "$HOME/.gitconfig"                       "~/.gitconfig"
  symlink "$DOTFILES_DIR/git/delta-themes.gitconfig" "$HOME/.config/delta/themes.gitconfig"   "delta-themes.gitconfig"
  symlink "$DOTFILES_DIR/lazygit/config.yml"         "$HOME/.config/lazygit/config.yml"       "lazygit/config.yml"
  symlink "$DOTFILES_DIR/atuin/config.toml"          "$HOME/.config/atuin/config.toml"        "atuin/config.toml"
  symlink "$DOTFILES_DIR/btop/btop.conf"             "$HOME/.config/btop/btop.conf"           "btop/btop.conf"
  symlink "$DOTFILES_DIR/tealdeer/config.toml"       "$HOME/.config/tealdeer/config.toml"     "tealdeer/config.toml"
}

# ═════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═════════════════════════════════════════════════════════════════════════════

print_summary() {
  echo ""
  echo -e "${BOLD}── Summary ──${NC}"
  if [[ ${#INSTALLED[@]} -gt 0 ]]; then
    echo -e "${GREEN}Installed:${NC} ${INSTALLED[*]}"
  fi
  if [[ ${#SKIPPED[@]} -gt 0 ]]; then
    echo -e "${CYAN}Skipped:${NC}   ${SKIPPED[*]}"
  fi
  if [[ ${#FAILED[@]} -gt 0 ]]; then
    echo -e "${RED}Failed:${NC}    ${FAILED[*]}"
    echo ""
    echo -e "${YELLOW}Tip:${NC} re-run with --yes to retry failed installs"
  fi
  echo ""
  echo -e "${GREEN}Done.${NC} Reload your shell: ${BOLD}source ~/.bashrc${NC}"
  echo ""
}

# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════

echo ""
echo -e "${BOLD}  dotfiles installer${NC}"
echo    "  dir:  $DOTFILES_DIR"
echo    "  os:   $OS ($RAW_ARCH → $ARCH_GENERIC)"
$DRY_RUN && echo -e "  mode: ${YELLOW}DRY RUN — no changes will be made${NC}"
echo ""

ensure_local_bin_env

if ! $NO_PKGS; then
  if confirm "Install / update all packages?"; then
    section "packages"

    # apt bundle first (provides jq which is needed by github_latest via curl fallback)
    $IS_DEBIAN && install_apt_bundle

    # Check if eza needs GitHub install (older ubuntu or non-debian)
    if ! is_installed eza; then
      install_eza_github
    else
      skip "eza $(eza --version 2>/dev/null | head -1)"
      mark_skipped "eza"
    fi

    install_starship
    install_lazygit
    install_yq
    install_atuin
    install_zoxide
    install_fzf
  fi
fi

link_configs
print_summary
