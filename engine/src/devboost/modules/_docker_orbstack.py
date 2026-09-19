"""OrbStack — opt-in Docker runtime on macOS (paid for commercial use; plan D3, D15)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from devboost.core.errors import InstallError, NeedsUser
from devboost.core.userconfig import DockerRuntimeName
from devboost.exec.primitives import config, pkg
from devboost.model import Ctx
from devboost.modules._docker_runtime import engine_verified, json_has, vm_size, wait_for_engine

CASK = "orbstack"


def _first_launch() -> NeedsUser:
    return NeedsUser(
        "OrbStack has not finished its first launch",
        "open -a OrbStack and finish setup (the Free plan is non-commercial — choose Pro "
        "for work), then run: devboost docker use orbstack",
    )


class OrbStack:
    name: DockerRuntimeName = "orbstack"
    context_name = "orbstack"

    def daemon_config_path(self) -> Path:
        return Path(os.environ["HOME"]) / ".orbstack" / "config" / "docker.json"

    def installed(self, ctx: Ctx) -> bool:
        return pkg.cask_installed(ctx, CASK)

    def install(self, ctx: Ctx) -> None:
        pkg.install_cask(ctx, CASK)

    def _set(self, ctx: Ctx, key: str, value: str) -> None:
        if not ctx.ex.run(["orb", "config", "set", key, value]).ok:
            raise _first_launch()

    def configure(self, ctx: Ctx) -> None:
        size = vm_size(ctx)
        self._set(ctx, "cpu", str(size.cpu))
        self._set(ctx, "memory_mib", str(size.memory_gib * 1024))
        self._set(ctx, "app.start_at_login", "true")

    def start(self, ctx: Ctx) -> None:
        if not ctx.ex.run(["orb", "start"]).ok:
            raise _first_launch()
        wait_for_engine(ctx, self.context_name)

    def stop(self, ctx: Ctx) -> None:
        ctx.ex.run(["orb", "stop"])

    def disable_autostart(self, ctx: Ctx) -> None:
        ctx.ex.run(["orb", "config", "set", "app.start_at_login", "false"])

    def release_socket(self, ctx: Ctx) -> None:
        return None  # OrbStack manages /var/run/docker.sock itself

    def merge_daemon_config(self, ctx: Ctx, patch: Mapping[str, Any]) -> bool:
        return config.json_merge(ctx, str(self.daemon_config_path()), patch)

    def daemon_config_has(self, patch: Mapping[str, Any]) -> bool:
        return json_has(self.daemon_config_path(), patch)

    def restart_engine(self, ctx: Ctx) -> None:
        res = ctx.ex.run(["orb", "restart", "docker"])
        if not res.ok:
            raise InstallError("orbstack", "orb restart docker", res.code)
        wait_for_engine(ctx, self.context_name)

    def verify(self, ctx: Ctx) -> bool:
        return self.installed(ctx) and engine_verified(ctx, self.context_name)
