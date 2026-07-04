#!/usr/bin/env bash
# Claude Code notification hook → ntfy (phone push). Wired by the claude-notify module
# into ~/.claude/settings.json as the Stop hook (task finished) and Notification hook
# (Claude needs input). Set DEVBOOST_NTFY_URL to a topic — e.g. https://ntfy.sh/<your-
# private-topic> or your self-hosted ntfy behind Tailscale. Unset → clean no-op, so it
# never blocks Claude. (Claude Code's built-in push is the zero-infra alternative.)
url="${DEVBOOST_NTFY_URL:-}"
[ -z "$url" ] && exit 0
command -v curl >/dev/null 2>&1 || exit 0

case "${1:-event}" in
  done)  title="✅ Claude finished";     prio="default" ;;
  input) title="⌨️ Claude needs input";  prio="high" ;;
  *)     title="Claude";                 prio="default" ;;
esac

# --max-time keeps a slow/unreachable ntfy from ever stalling the shell; errors ignored.
curl -fsS --max-time 5 \
  -H "Title: ${title} — $(hostname)" \
  -H "Priority: ${prio}" \
  -H "Tags: robot" \
  -d "cwd: ${PWD}" \
  "$url" >/dev/null 2>&1 || true
exit 0
