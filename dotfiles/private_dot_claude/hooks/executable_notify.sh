#!/usr/bin/env bash
# Claude Code notification hook. Wired by the claude-notify module into
# ~/.claude/settings.json as the Stop hook (task finished) and Notification hook (Claude
# needs input).
#   - macOS: a native notification, always (no setup).
#   - ntfy (phone push): set DEVBOOST_NTFY_URL to a topic — e.g. https://ntfy.sh/<your-
#     private-topic> or your self-hosted ntfy behind Tailscale. Unset → skipped.
# Never blocks Claude: every step is best-effort and time-limited.

case "${1:-event}" in
  done)  title="✅ Claude finished";     prio="default" ;;
  input) title="⌨️ Claude needs input";  prio="high" ;;
  *)     title="Claude";                 prio="default" ;;
esac

# macOS: title and cwd reach AppleScript as arguments (`on run argv`), never spliced into
# the script text, so a quote in a path cannot break it.
if [ "$(uname -s)" = "Darwin" ] && command -v osascript >/dev/null 2>&1; then
  osascript - "${title}" "cwd: ${PWD}" >/dev/null 2>&1 <<'OSA' || true
on run argv
  display notification (item 2 of argv) with title (item 1 of argv)
end run
OSA
fi

url="${DEVBOOST_NTFY_URL:-}"
[ -z "$url" ] && exit 0
command -v curl >/dev/null 2>&1 || exit 0

# --max-time keeps a slow/unreachable ntfy from ever stalling the shell; errors ignored.
curl -fsS --max-time 5 \
  -H "Title: ${title} — $(hostname)" \
  -H "Priority: ${prio}" \
  -H "Tags: robot" \
  -d "cwd: ${PWD}" \
  "$url" >/dev/null 2>&1 || true
exit 0
