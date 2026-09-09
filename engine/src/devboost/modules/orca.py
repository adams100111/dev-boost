"""orca — install the Orca agent development environment (stablyai/orca)."""

from __future__ import annotations

import os

from devboost.core import log
from devboost.core.errors import ConfigError
from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.exec.primitives import pkg, systemd
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
        f"f=$(mktemp --suffix={suffix}); trap 'rm -f \"$f\"' EXIT; "
        f"curl -fsSL \"$url\" -o \"$f\"; {install_cmd} \"$f\""
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


_ORCA_UNIT = """\
[Unit]
Description=Orca headless serve

[Service]
Type=simple
Environment=LIBGL_ALWAYS_SOFTWARE=1
ExecStart=/usr/bin/xvfb-run -a {cmd} serve --port {port} --pairing-address {addr}
Restart=on-failure
RestartPreventExitStatus=3

[Install]
WantedBy=default.target
"""


def _invoking_user() -> str:
    return os.environ.get("SUDO_USER") or os.environ.get("USER") or ""


@register
class OrcaServe(Module):
    name = "orca-serve"
    category = "orca"
    description = "Run Orca headless (orca-ide serve) as a systemd --user service."
    requires = (OrcaIde,)
    profiles = ("orca-box",)
    families = ("fedora", "debian")

    def verify(self, ctx: Ctx) -> bool:
        return systemd.is_enabled(ctx, "orca-serve.service", user=True)

    def _pairing_address(self, ctx: Ctx) -> str:
        env = os.environ.get("DEVBOOST_ORCA_PAIRING_ADDRESS")
        if env:
            return env
        if ctx.ex.which("tailscale"):
            res = ctx.ex.run(["tailscale", "ip", "-4"])
            lines = res.stdout.strip().splitlines()
            if res.ok and lines:
                return lines[0].strip()
        return ""

    def install(self, ctx: Ctx) -> None:
        # Resolve the pairing address first so a misconfigured box fails before doing work.
        addr = self._pairing_address(ctx)
        if not addr:
            raise ConfigError(
                "orca-serve: no pairing address — set DEVBOOST_ORCA_PAIRING_ADDRESS or bring up "
                "Tailscale (`tailscale up`) on this box"
            )
        pkg.install(ctx, OsMap(fedora="xorg-x11-server-Xvfb", debian="xvfb"))
        port = os.environ.get("DEVBOOST_ORCA_PORT", "6768")
        unit = _ORCA_UNIT.format(cmd=orca_cmd(ctx), port=port, addr=addr)
        systemd.write_user_unit(ctx, "orca-serve.service", unit)
        user = _invoking_user()
        if user:
            ctx.ex.run(["loginctl", "enable-linger", user], sudo=True)
        systemd.enable_user_unit(ctx, "orca-serve.service", now=True)
        log.info("orca-serve enabled; first pairing prints an orca://pair code in its journal")
