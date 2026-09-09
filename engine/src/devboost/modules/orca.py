"""orca — install the Orca agent development environment (stablyai/orca)."""

from __future__ import annotations

import os

from devboost.core.errors import ConfigError
from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import Ctx, Module

_REPO = "stablyai/orca"
#: Linux command differs by distro: .rpm/.deb install `orca-ide`; the AUR `stably-orca-bin`
#: installs `stably-orca` (a pass-through wrapper over the same release binary).
_ORCA_CMD: OsMap[str] = OsMap(fedora="orca-ide", debian="orca-ide", arch="stably-orca")
_RARCH = {"x86_64": "x86_64", "aarch64": "aarch64"}
_DARCH = {"x86_64": "amd64", "aarch64": "arm64"}


def orca_cmd(ctx: Ctx) -> str:
    cmd = _ORCA_CMD.get(ctx.os)
    if cmd is None:
        raise ConfigError(f"orca: unsupported OS {ctx.os.distro!r}")
    return cmd


def _release_ref() -> str:
    ver = os.environ.get("DEVBOOST_ORCA_VERSION", "")
    return f"tags/v{ver}" if ver else "latest"


def _fetch_script(pattern: str, install_cmd: str, suffix: str) -> str:
    api = f"https://api.github.com/repos/{_REPO}/releases/{_release_ref()}"
    return (
        f"set -e; "
        f"url=$(curl -fsSL \"{api}\" | grep -oE 'https://[^\"]*{pattern}' | head -1); "
        f"[ -n \"$url\" ] || {{ echo 'orca-ide: no asset for {pattern}' >&2; exit 1; }}; "
        f"f=$(mktemp --suffix={suffix}); curl -fsSL \"$url\" -o \"$f\"; "
        f"{install_cmd} \"$f\"; rm -f \"$f\""
    )


@register
class OrcaIde(Module):
    name = "orca-ide"
    category = "orca"
    description = "Orca — multi-agent development environment (stablyai/orca)."
    profiles = ("orca",)
    families = ("fedora", "debian", "arch")

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which(orca_cmd(ctx))

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "arch":
            # Upstream-recommended AUR build of the release binary (command: `stably-orca`).
            pkg.install_aur(ctx, "stably-orca-bin")
            return
        if ctx.os.family == "fedora":
            rarch = _RARCH.get(ctx.os.arch)
            if rarch is None:
                raise ConfigError(f"orca-ide: no rpm for arch {ctx.os.arch!r}")
            pattern = rf"orca-ide-[^\"/]*\.{rarch}\.rpm"
            script = _fetch_script(pattern, "sudo dnf install -y", ".rpm")
        elif ctx.os.family == "debian":
            darch = _DARCH.get(ctx.os.arch)
            if darch is None:
                raise ConfigError(f"orca-ide: no deb for arch {ctx.os.arch!r}")
            script = _fetch_script(rf"orca-ide_[^\"/]*_{darch}\.deb", "sudo apt install -y", ".deb")
        else:
            raise ConfigError(f"orca-ide: unsupported OS family {ctx.os.family!r}")
        res = ctx.ex.run(["sh", "-c", script])
        if not res.ok:
            raise ConfigError(f"orca-ide: install failed (exit {res.code})")
