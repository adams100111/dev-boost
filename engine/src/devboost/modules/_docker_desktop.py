"""Docker Desktop — opt-in Docker runtime on macOS (paid above 250 staff / $10M; D3, D14)."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from devboost.core.errors import InstallError, NeedsUser
from devboost.core.userconfig import DockerRuntimeName
from devboost.exec.primitives import config, pkg
from devboost.model import Ctx
from devboost.modules._docker_runtime import (
    engine_up,
    engine_verified,
    json_has,
    read_json,
    vm_size,
    wait_for_engine,
)

CASK = "docker-desktop"


def settings_path() -> Path:
    """Docker Desktop's settings file (4.35+). Created by the app's first launch."""
    return (
        Path(os.environ["HOME"]) / "Library" / "Group Containers" / "group.com.docker"
        / "settings-store.json"
    )


def _atomic_write_json(path: Path, data: Mapping[str, Any]) -> None:
    """Durably replace *path* with *data* as JSON: a sibling temp file (``mkstemp``,
    same directory — same filesystem, so the swap is atomic), fsynced before the swap,
    then ``os.replace`` into place. Docker Desktop's own restart (``configure``) reads this
    file back right after devboost writes it, which is exactly the moment a plain
    truncate-then-write is riskiest: a crash or a lock held mid-write would otherwise leave
    a truncated/malformed ``settings-store.json`` and silently drop every setting the app
    or the user ever put there. The original file's permission bits are kept, and the temp
    file never survives a failed write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2) + "\n")
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            tmp.chmod(mode)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def update_settings(path: Path, values: Mapping[str, object]) -> bool:
    """Set settings keys, keeping the spelling the file already uses (plan D14).

    Docker does not document these keys (docker/docs#23706), so an existing key is matched
    case-insensitively and the given name is used only when the file has none. A file that
    exists but is unreadable (corrupt JSON, not an object) is never overwritten:
    ``read_json`` raises ``InstallError`` before any write is attempted.
    """
    data = read_json(path)
    changed = False
    for preferred, value in values.items():
        key = next((k for k in data if k.lower() == preferred.lower()), preferred)
        if data.get(key) != value:
            data[key] = value
            changed = True
    if changed:
        _atomic_write_json(path, data)
    return changed


def _first_launch() -> NeedsUser:
    return NeedsUser(
        "Docker Desktop has not finished its first launch",
        "open -a Docker, accept the Docker Subscription Service Agreement (free only under "
        "250 employees and US$10M revenue), then run: devboost docker use docker-desktop",
    )


class DockerDesktop:
    name: DockerRuntimeName = "docker-desktop"
    context_name = "desktop-linux"

    def daemon_config_path(self) -> Path:
        return Path(os.environ["HOME"]) / ".docker" / "daemon.json"

    def installed(self, ctx: Ctx) -> bool:
        return pkg.cask_installed(ctx, CASK)

    def install(self, ctx: Ctx) -> None:
        if pkg.installed(ctx, "docker"):
            # The cask links its own docker + docker-compose into the brew prefix, and brew
            # will not overwrite the Colima formulae's links (plan D14).
            pkg.brew_unlink(ctx, "docker", "docker-compose")
        pkg.install_cask(ctx, CASK)

    def _desktop(self, ctx: Ctx, verb: str) -> None:
        res = ctx.ex.run(["docker", "desktop", verb])
        if not res.ok:
            raise InstallError("docker-desktop", f"docker desktop {verb}", res.code)

    def configure(self, ctx: Ctx) -> None:
        path = settings_path()
        if not path.exists():
            raise _first_launch()
        size = vm_size(ctx)
        changed = update_settings(
            path, {"Cpus": size.cpu, "MemoryMiB": size.memory_gib * 1024, "AutoStart": True}
        )
        if changed and engine_up(ctx, self.context_name):
            self._desktop(ctx, "restart")

    def start(self, ctx: Ctx) -> None:
        if not ctx.ex.run(["docker", "desktop", "start"]).ok:
            raise _first_launch()
        wait_for_engine(ctx, self.context_name)

    def stop(self, ctx: Ctx) -> None:
        ctx.ex.run(["docker", "desktop", "stop"])

    def disable_autostart(self, ctx: Ctx) -> None:
        path = settings_path()
        if path.exists():
            update_settings(path, {"AutoStart": False})

    def release_socket(self, ctx: Ctx) -> None:
        return None  # Docker Desktop manages /var/run/docker.sock itself

    def merge_daemon_config(self, ctx: Ctx, patch: Mapping[str, Any]) -> bool:
        return config.json_merge(ctx, str(self.daemon_config_path()), patch)

    def daemon_config_has(self, patch: Mapping[str, Any]) -> bool:
        return json_has(self.daemon_config_path(), patch)

    def restart_engine(self, ctx: Ctx) -> None:
        self._desktop(ctx, "restart")
        wait_for_engine(ctx, self.context_name)

    def verify(self, ctx: Ctx) -> bool:
        return self.installed(ctx) and engine_verified(ctx, self.context_name)
