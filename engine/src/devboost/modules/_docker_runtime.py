"""Docker runtimes on macOS — the ``DockerRuntime`` protocol and what every runtime shares.

Three runtimes (spec §4): Colima (the default; MIT), OrbStack and Docker Desktop (both need
a paid plan for most work use — docs/docker-runtimes.md). Each lives in its own module
(``_docker_colima``, ``_docker_orbstack``, ``_docker_desktop``); ``runtime_for`` picks one.
Linux never reaches this file: it runs docker-ce (modules/docker.py).
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from devboost.core.errors import InstallError
from devboost.core.userconfig import DockerRuntimeName
from devboost.model import Ctx

# M4-D8: one Rosetta probe for the whole engine — M3's, re-exported (explicit `as` form).
from devboost.modules.macos import rosetta_present as rosetta_present
from devboost.modules.macos import rosetta_supported as rosetta_supported

_GIB = 1024**3
#: Seconds to wait for a freshly started engine (a first Colima boot takes ~1 min).
ENGINE_TIMEOUT = 180.0
#: Seconds one ``docker info`` probe may take. A socket that accepts but never answers
#: (Docker Desktop's backend starting, a stale forward) must not hang the install.
PROBE_TIMEOUT = 10.0

#: Test seams — a unit test never sleeps.
_sleep: Callable[[float], None] = time.sleep
_clock: Callable[[], float] = time.monotonic


class DockerRuntime(Protocol):
    """One way to run the Docker engine on a Mac. ``configure`` runs after ``install``
    and before ``start``; ``release_socket`` undoes what the runtime did to
    ``/var/run/docker.sock`` (a no-op for runtimes that manage it themselves)."""

    @property
    def name(self) -> DockerRuntimeName: ...
    @property
    def context_name(self) -> str: ...
    def daemon_config_path(self) -> Path: ...
    def installed(self, ctx: Ctx) -> bool: ...
    def install(self, ctx: Ctx) -> None: ...
    def configure(self, ctx: Ctx) -> None: ...
    def start(self, ctx: Ctx) -> None: ...
    def stop(self, ctx: Ctx) -> None: ...
    def disable_autostart(self, ctx: Ctx) -> None: ...
    def release_socket(self, ctx: Ctx) -> None: ...
    def merge_daemon_config(self, ctx: Ctx, patch: Mapping[str, Any]) -> bool: ...
    def daemon_config_has(self, patch: Mapping[str, Any]) -> bool: ...
    def restart_engine(self, ctx: Ctx) -> None: ...
    def verify(self, ctx: Ctx) -> bool: ...


@dataclass(frozen=True)
class VmSize:
    cpu: int
    memory_gib: int


def _sysctl_int(ctx: Ctx, key: str) -> int | None:
    res = ctx.ex.run(["sysctl", "-n", key])
    if not res.ok:
        return None
    try:
        return int(res.stdout.strip())
    except ValueError:
        return None


def vm_size(ctx: Ctx) -> VmSize:
    """Half the CPUs (at least 2) and a quarter of the RAM (at least 4 GiB) — spec §4."""
    ncpu = _sysctl_int(ctx, "hw.ncpu") or 4
    ram_gib = (_sysctl_int(ctx, "hw.memsize") or 16 * _GIB) // _GIB
    return VmSize(cpu=max(2, ncpu // 2), memory_gib=max(4, ram_gib // 4))


def rosetta_usable(ctx: Ctx) -> bool:
    """Colima may pass ``--vz-rosetta``: this macOS still ships full Rosetta 2 and it is
    installed (M4-D8 — the probes are M3's, re-exported above)."""
    return rosetta_supported(ctx.os) and rosetta_present(ctx)


def current_context(ctx: Ctx) -> str:
    res = ctx.ex.run(["docker", "context", "show"])
    return res.stdout.strip() if res.ok else ""


def use_context(ctx: Ctx, name: str) -> None:
    res = ctx.ex.run(["docker", "context", "use", name])
    if not res.ok:
        raise InstallError("docker", f"docker context use {name}", res.code)


def engine_up(ctx: Ctx, context: str, *, timeout: float = PROBE_TIMEOUT) -> bool:
    """The engine behind ``context`` answers within ``timeout`` seconds."""
    return ctx.ex.run(
        ["docker", "--context", context, "info", "--format", "{{.ServerVersion}}"],
        timeout=timeout,
    ).ok


def engine_verified(ctx: Ctx, context: str) -> bool:
    """The docker CLI points at ``context`` and the engine behind it answers (spec §4)."""
    return current_context(ctx) == context and engine_up(ctx, context)


def wait_for_engine(
    ctx: Ctx, context: str, *, timeout: float = ENGINE_TIMEOUT, interval: float = 3.0
) -> None:
    """Poll ``docker info`` until the engine answers, or raise after ``timeout`` s.

    Each probe is bounded by the time left (at most ``PROBE_TIMEOUT``, at least 1 s), so
    a hung ``docker info`` cannot outlive the deadline by more than a second.
    """
    deadline = _clock() + timeout
    while not engine_up(
        ctx, context, timeout=max(1.0, min(PROBE_TIMEOUT, deadline - _clock()))
    ):
        if _clock() >= deadline:
            raise InstallError("docker", f"docker --context {context} info", 1)
        _sleep(interval)


def docker_config_path() -> Path:
    """The docker CLI's config.json (``$DOCKER_CONFIG`` or ``~/.docker``)."""
    base = os.environ.get("DOCKER_CONFIG")
    root = Path(base) if base else Path(os.environ["HOME"]) / ".docker"
    return root / "config.json"


def read_json(path: Path) -> dict[str, Any]:
    """A JSON object from ``path``; ``{}`` only when the file is missing.

    A file that *exists* but cannot be read as a JSON object — corrupt JSON, undecodable
    bytes, or valid JSON that isn't an object — raises ``InstallError`` naming the file,
    instead of silently answering ``{}``. A caller that merges a patch into "the current
    contents, or {}" (``json_has``, ``_docker_desktop.update_settings``,
    ``_docker_colima._cli_plugins``) would otherwise treat an unreadable settings file as
    empty and overwrite it with only the few keys it's trying to set — discarding every
    other setting the user or the app itself put there. Let it fail loudly instead: the
    file needs a human to fix or delete it.
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InstallError("docker", f"parse JSON at {path}", 1) from exc
    if not isinstance(data, dict):
        raise InstallError("docker", f"parse JSON at {path}", 1)
    return data


def json_has(path: Path, patch: Mapping[str, Any]) -> bool:
    data = read_json(path)
    return all(data.get(k) == v for k, v in patch.items())


_LICENSE_NOTES: dict[DockerRuntimeName, str] = {
    "orbstack": (
        "OrbStack's Free plan is for personal, non-commercial use only; work for an "
        "employer or clients needs OrbStack Pro ($8/user/month)."
    ),
    "docker-desktop": (
        "Docker Desktop is free only when the organisation the work is for has fewer than "
        "250 employees AND less than US$10M annual revenue; otherwise it needs a paid "
        "Docker subscription."
    ),
}


def license_note(name: DockerRuntimeName) -> str | None:
    """The commercial-use caveat for a non-default runtime (spec *Licensing*)."""
    return _LICENSE_NOTES.get(name)
