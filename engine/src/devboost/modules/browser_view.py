"""browser-view — watch an agent's browser live from any device.

The brain is headless, so when an agent drives a headful browser you normally can't see it.
This installs a virtual-display + web-VNC stack (Xvfb + x11vnc + noVNC) and drops a
`browser-view` helper on the brain that wires them together: start a virtual display, point a
headful browser at it, and serve it as a web page. Front with `tailscale serve` to watch/click
it from an iPad / phone / any browser. Closes the live-agent-browser gap.

The helper is written by this module (not shipped as a laptop dotfile) because it runs on the
brain SERVER, which doesn't apply the dotfiles — same reason caddy writes its own Caddyfile.
"""

from __future__ import annotations

import os
from pathlib import Path

from devboost.core.errors import UnsupportedOS
from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import Ctx, Module

# The runtime helper. `browser-view start` brings up Xvfb :99 + x11vnc + a noVNC web page on
# :6080; run headful browsers with DISPLAY=:99, then `fleet expose 6080` to watch them.
_HELPER = r"""#!/usr/bin/env bash
# browser-view — virtual display + web VNC to WATCH a headful browser (e.g. an agent's
# Playwright Chromium) from any device over the tailnet. Managed by dev-boost.
#   browser-view start   # Xvfb :99 + x11vnc + noVNC web on :6080
#   browser-view stop
# Run browsers to be watched with  DISPLAY=:99 . Then:  fleet expose 6080  (tailscale serve)
# and open  https://<brain>.<tailnet>.ts.net/vnc.html  in any browser.
set -euo pipefail
DPY=":99"; VNC_PORT=5900; WEB_PORT=6080
RUN="${XDG_RUNTIME_DIR:-/tmp}/browser-view"; mkdir -p "$RUN"
novnc_web() { for d in /usr/share/novnc /usr/share/webapps/novnc /usr/share/novnc-common; do
  [ -d "$d" ] && { echo "$d"; return; }; done; echo /usr/share/novnc; }
start() {
  command -v Xvfb >/dev/null || { echo "browser-view: Xvfb missing" >&2; exit 1; }
  Xvfb "$DPY" -screen 0 1920x1080x24 >/dev/null 2>&1 & echo $! > "$RUN/xvfb.pid"
  sleep 1
  x11vnc -display "$DPY" -localhost -nopw -forever -shared -rfbport "$VNC_PORT" \
    -bg -o "$RUN/x11vnc.log" >/dev/null 2>&1 || true
  websockify --web="$(novnc_web)" "$WEB_PORT" "localhost:${VNC_PORT}" >/dev/null 2>&1 &
  echo $! > "$RUN/websockify.pid"
  echo "browser-view: up. Run headful browsers with  DISPLAY=$DPY"
  echo "  watch:  fleet expose $WEB_PORT   then open  .../vnc.html"
}
stop() {
  for p in websockify xvfb; do
    [ -f "$RUN/$p.pid" ] && kill "$(cat "$RUN/$p.pid")" 2>/dev/null || true; rm -f "$RUN/$p.pid"
  done
  pkill -f "x11vnc -display $DPY" 2>/dev/null || true
  echo "browser-view: stopped"
}
case "${1:-}" in
  start) start ;;
  stop) stop ;;
  *) echo "usage: browser-view {start|stop}" >&2; exit 2 ;;
esac
"""


def _helper_path() -> Path:
    return Path(os.environ["HOME"]) / ".local" / "bin" / "browser-view"


@register
class BrowserView(Module):
    name = "browser-view"
    category = "brain-host"
    description = "Xvfb + x11vnc + noVNC to watch a headful (agent) browser from any device."
    profiles = ("brain-host",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("Xvfb") and ctx.ex.which("x11vnc") and _helper_path().exists()

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "debian":
            pkg.install(ctx, "xvfb", "x11vnc", "novnc", "websockify")
        elif ctx.os.family == "fedora":
            pkg.install(ctx, "xorg-x11-server-Xvfb", "x11vnc", "novnc", "python3-websockify")
        else:
            raise UnsupportedOS(f"browser-view not implemented for {ctx.os.distro!r}")
        # Drop the runtime helper onto the brain (dotfiles don't reach a server) + make it exec.
        dest = _helper_path()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_HELPER, encoding="utf-8")
        dest.chmod(0o755)
