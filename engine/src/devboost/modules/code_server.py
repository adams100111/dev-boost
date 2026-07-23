"""code-server — VS Code in the browser, for editing the brain from any device.

Runs on the brain bound to localhost with code-server's own password auth; front it with
`tailscale serve` to get a full VS Code UI from an iPad / phone / any browser over the
tailnet, executing on the brain. Closes the "edit from a browser-only device" gap.
"""

from __future__ import annotations

import os

from devboost.core.registry import register
from devboost.exec.primitives import systemd
from devboost.model import Ctx, Module


def _invoking_user() -> str:
    return os.environ.get("SUDO_USER") or os.environ.get("USER") or ""


@register
class CodeServer(Module):
    name = "code-server"
    category = "brain-host"
    description = "code-server — VS Code in the browser (front with tailscale serve; any device)."
    profiles = ("brain-host",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("code-server")

    def install(self, ctx: Ctx) -> None:
        # Official cross-distro installer (same curl|sh escape hatch as tailscale/fresh). It
        # drops a `code-server@.service` template and defaults to 127.0.0.1:8080 + password
        # auth — a random password lands in ~/.config/code-server/config.yaml (read it once).
        if not ctx.ex.which("code-server"):
            ctx.ex.run(["sh", "-c", "curl -fsSL https://code-server.dev/install.sh | sh"])
        # Enable the per-user service so it's up on boot; tailscale serve fronts localhost:8080.
        user = _invoking_user()
        if user:
            systemd.enable_system_unit(ctx, f"code-server@{user}", now=True)
