"""The one pin for Microsoft's Playwright MCP server (`@playwright/mcp`).

Every place dev-boost starts the server uses this version, never `@latest`: the macOS
browser-mcp LaunchAgent passes it to the launcher, the `playwright` module wires it into
Claude Code, and the bash launchers (dotfiles/dot_local/bin/executable_browser-mcp and
`pw-mcp` in dotfiles/dot_config/devboost/aliases.sh) default to the same string — a test
keeps them equal. Bump it here and in those two defaults together.

Why pinned: the server exposes `browser_run_code_unsafe` and `browser_evaluate` (both in the
always-on `core` capability; `--caps` can only ADD capabilities), so an unreviewed upstream
release changes what a tailnet peer on port 8931 can do. See docs/remote-dev.md.
"""

from __future__ import annotations

PLAYWRIGHT_MCP_VERSION = "0.0.82"
PLAYWRIGHT_MCP_PKG = f"@playwright/mcp@{PLAYWRIGHT_MCP_VERSION}"
