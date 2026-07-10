#!/usr/bin/env bash
# pw-autoregister — invoked by the tmux `client-attached` hook.
#
# Auto-wires the Playwright MCP so switching workstations is zero-touch: on every tmux attach,
# if you're SSH'd in AND the machine you attached FROM is actually serving its MCP (you ran
# `pw-mcp` there), (re)register it with Claude on this server as `playwright-workstation`.
# Otherwise it does nothing. Silent, idempotent, non-blocking. The manual equivalent is
# `pw-workstation`.
set -u

command -v claude >/dev/null 2>&1 || exit 0
command -v tmux   >/dev/null 2>&1 || exit 0

# The attaching client's address — tmux refreshes SSH_CONNECTION from that client on attach
# (update-environment). Format: "<client-ip> <client-port> <server-ip> <server-port>".
conn=$(tmux show-environment SSH_CONNECTION 2>/dev/null) || exit 0
conn=${conn#SSH_CONNECTION=}
host=${conn%% *}
# Not in an ssh session (local attach), or tmux prints "-SSH_CONNECTION" when unset → no-op.
case $host in ''|-*) exit 0 ;; esac

port=${DEVBOOST_PW_MCP_PORT:-8931}

# Reachability probe (no curl dependency): is the MCP port open on the attaching machine?
# If pw-mcp isn't running there, do nothing — never register a dead endpoint.
timeout 1 bash -c "exec 3<>/dev/tcp/${host}/${port}" 2>/dev/null || exit 0

# Remove-then-add so a switch (same name, new address) updates cleanly.
claude mcp remove --scope user playwright-workstation >/dev/null 2>&1
claude mcp add --transport http --scope user playwright-workstation "http://${host}:${port}/mcp" >/dev/null 2>&1 || exit 0
