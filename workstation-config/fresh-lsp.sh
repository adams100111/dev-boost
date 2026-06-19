```bash
#!/usr/bin/env bash
set -Eeuo pipefail

###############################################################################
# Fresh LSP installer
#
# - Detects package manager
# - Installs missing prerequisites (jq, node/npm, cargo, go)
# - Installs language servers only if missing
# - Uses BasedPyright instead of Pyright
# - Creates backups of ~/.config/fresh/config.json
# - Merges LSP settings without overwriting unrelated settings
# - Safe to rerun
###############################################################################

FRESH_CONFIG="$HOME/.config/fresh/config.json"

###############################################################################
# Detect package manager
###############################################################################

if command -v dnf >/dev/null; then
    PKG_MANAGER=dnf
elif command -v apt >/dev/null; then
    PKG_MANAGER=apt
elif command -v pacman >/dev/null; then
    PKG_MANAGER=pacman
else
    echo "Unsupported package manager."
    exit 1
fi

install_system_package() {
    local pkg="$1"

    case "$PKG_MANAGER" in
        dnf)
            sudo dnf install -y "$pkg"
            ;;
        apt)
            sudo apt update
            sudo apt install -y "$pkg"
            ;;
        pacman)
            sudo pacman -S --noconfirm "$pkg"
            ;;
    esac
}

###############################################################################
# Prerequisites
###############################################################################

if ! command -v jq >/dev/null; then
    echo "Installing jq..."
    install_system_package jq
fi

if ! command -v node >/dev/null; then
    echo "Installing Node.js..."
    install_system_package nodejs
    install_system_package npm
fi

if ! command -v cargo >/dev/null; then
    echo "Installing Rust..."
    curl https://sh.rustup.rs -sSf | sh -s -- -y
    source "$HOME/.cargo/env"
fi

if ! command -v go >/dev/null; then
    echo "Installing Go..."
    install_system_package golang
fi

###############################################################################
# npm packages
###############################################################################

install_npm_package() {
    local package="$1"
    local executable="$2"

    if ! command -v "$executable" >/dev/null; then
        echo "Installing $package..."
        npm install -g "$package"
    else
        echo "$package already installed."
    fi
}

install_npm_package typescript typescript
install_npm_package typescript-language-server typescript-language-server

install_npm_package vscode-langservers-extracted vscode-json-language-server

install_npm_package tailwindcss-language-server tailwindcss-language-server

install_npm_package yaml-language-server yaml-language-server

install_npm_package basedpyright basedpyright-langserver

install_npm_package intelephense intelephense

install_npm_package bash-language-server bash-language-server

install_npm_package dockerfile-language-server-nodejs docker-langserver

install_npm_package graphql-language-service-cli graphql-lsp

install_npm_package @prisma/language-server prisma-language-server

install_npm_package @vue/language-server vue-language-server

install_npm_package vscode-eslint-language-server vscode-eslint-language-server

###############################################################################
# Rust language servers
###############################################################################

if ! command -v marksman >/dev/null; then
    cargo install marksman
fi

if ! command -v taplo >/dev/null; then
    cargo install taplo-cli --features lsp
fi

###############################################################################
# Go language servers
###############################################################################

if ! command -v sqls >/dev/null; then
    go install github.com/sqls-server/sqls@latest
fi

###############################################################################
# Create config
###############################################################################

mkdir -p "$(dirname "$FRESH_CONFIG")"

if [ ! -f "$FRESH_CONFIG" ]; then
    echo '{}' > "$FRESH_CONFIG"
fi

cp "$FRESH_CONFIG" "${FRESH_CONFIG}.bak"

###############################################################################
# Merge LSP configuration
###############################################################################

jq '
.lsp = (.lsp // {}) + {

  "typescript": {
    "command": "typescript-language-server",
    "args": ["--stdio"],
    "enabled": true
  },

  "javascript": {
    "command": "typescript-language-server",
    "args": ["--stdio"],
    "enabled": true
  },

  "php": {
    "command": "intelephense",
    "args": ["--stdio"],
    "enabled": true
  },

  "python": {
    "command": "basedpyright-langserver",
    "args": ["--stdio"],
    "enabled": true
  },

  "json": {
    "command": "vscode-json-language-server",
    "args": ["--stdio"],
    "enabled": true
  },

  "html": {
    "command": "vscode-html-language-server",
    "args": ["--stdio"],
    "enabled": true
  },

  "css": {
    "command": "vscode-css-language-server",
    "args": ["--stdio"],
    "enabled": true
  },

  "yaml": {
    "command": "yaml-language-server",
    "args": ["--stdio"],
    "enabled": true
  },

  "tailwind": {
    "command": "tailwindcss-language-server",
    "args": ["--stdio"],
    "enabled": true
  },

  "dockerfile": {
    "command": "docker-langserver",
    "args": ["--stdio"],
    "enabled": true
  },

  "bash": {
    "command": "bash-language-server",
    "args": ["start"],
    "enabled": true
  },

  "graphql": {
    "command": "graphql-lsp",
    "args": ["server"],
    "enabled": true
  },

  "prisma": {
    "command": "prisma-language-server",
    "args": ["--stdio"],
    "enabled": true
  },

  "markdown": {
    "command": "marksman",
    "args": ["server"],
    "enabled": true
  },

  "toml": {
    "command": "taplo",
    "args": ["lsp", "stdio"],
    "enabled": true
  },

  "sql": {
    "command": "sqls",
    "args": [],
    "enabled": true
  },

  "vue": {
    "command": "vue-language-server",
    "args": ["--stdio"],
    "enabled": true
  },

  "eslint": {
    "command": "vscode-eslint-language-server",
    "args": ["--stdio"],
    "enabled": true
  }

}
' "$FRESH_CONFIG" > /tmp/fresh-config.json

mv /tmp/fresh-config.json "$FRESH_CONFIG"

echo
echo "Fresh LSP setup complete."
echo
echo "Backup saved to:"
echo "  ${FRESH_CONFIG}.bak"
```