"""system profile — resilience services + GPU detection."""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar

from devboost.core import log
from devboost.core.errors import UnsupportedOS
from devboost.core.registry import register
from devboost.exec.primitives import config, gpu, pkg, systemd
from devboost.model import Ctx, Module


class SystemService(Module):
    """Install a package and enable its system service (verify = is-enabled)."""

    svc_pkg: ClassVar[str]
    service: ClassVar[str]
    category = "system"
    profiles = ("system",)

    def verify(self, ctx: Ctx) -> bool:
        return systemd.is_enabled(ctx, self.service)

    def install(self, ctx: Ctx) -> None:
        pkg.install(ctx, self.svc_pkg)
        systemd.enable_system_unit(ctx, self.service, now=True)


@register
class GrubBtrfs(SystemService):
    name = "grub-btrfs"
    description = "Boot into BTRFS snapshots from GRUB."
    svc_pkg = "grub-btrfs"
    service = "grub-btrfsd"
    families: ClassVar[tuple[str, ...]] = ("fedora",)

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family != "fedora":
            raise UnsupportedOS(
                f"grub-btrfs is Fedora/btrfs-only; detected {ctx.os.distro!r}"
            )
        super().install(ctx)


@register
class Fwupd(SystemService):
    name = "fwupd"
    description = "Firmware updates."
    svc_pkg = "fwupd"
    service = "fwupd.service"


@register
class PowerProfilesDaemon(SystemService):
    name = "power-profiles-daemon"
    description = "Power profile switching."
    svc_pkg = "power-profiles-daemon"
    service = "power-profiles-daemon"


@register
class Thermald(SystemService):
    name = "thermald"
    description = "Thermal management."
    svc_pkg = "thermald"
    service = "thermald"


@register
class Smartmontools(SystemService):
    name = "smartmontools"
    description = "Disk SMART monitoring."
    svc_pkg = "smartmontools"
    service = "smartd"


@register
class Snapper(Module):
    name = "snapper"
    category = "system"
    description = "BTRFS snapshots for /."
    profiles = ("system",)
    families: ClassVar[tuple[str, ...]] = ("fedora",)

    def verify(self, ctx: Ctx) -> bool:
        if ctx.os.family != "fedora":
            return False
        return "root" in ctx.ex.run(["snapper", "list-configs"]).stdout.split()

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family != "fedora":
            raise UnsupportedOS(
                f"snapper/btrfs is Fedora-only; detected {ctx.os.distro!r}"
            )
        pkg.install(ctx, "snapper", "python3-dnf-plugin-snapper")
        ctx.ex.run(["snapper", "-c", "root", "create-config", "/"], sudo=True)


@register
class SnapperDnfHook(Module):
    name = "snapper-dnf-hook"
    category = "system"
    description = "dnf plugin: snapshot before/after transactions."
    profiles = ("system",)
    families: ClassVar[tuple[str, ...]] = ("fedora",)

    def verify(self, ctx: Ctx) -> bool:
        if ctx.os.family != "fedora":
            return False
        return ctx.ex.run(["rpm", "-q", "python3-dnf-plugin-snapper"]).ok

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family != "fedora":
            raise UnsupportedOS(
                f"snapper-dnf-hook is Fedora-only; detected {ctx.os.distro!r}"
            )
        pkg.install(ctx, "python3-dnf-plugin-snapper")


@register
class BtrfsAssistant(Module):
    name = "btrfs-assistant"
    category = "system"
    description = "GUI for snapshots/subvolumes."
    gui = True
    profiles = ("system",)
    families: ClassVar[tuple[str, ...]] = ("fedora",)

    def verify(self, ctx: Ctx) -> bool:
        if ctx.os.family != "fedora":
            return False
        return ctx.ex.which("btrfs-assistant") or ctx.ex.run(["rpm", "-q", "btrfs-assistant"]).ok

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family != "fedora":
            raise UnsupportedOS(
                f"btrfs-assistant is Fedora/btrfs-only; detected {ctx.os.distro!r}"
            )
        pkg.install(ctx, "btrfs-assistant")


@register
class Btrfsmaintenance(Module):
    name = "btrfsmaintenance"
    category = "system"
    description = "Scheduled BTRFS balance/scrub/trim."
    profiles = ("system",)
    families: ClassVar[tuple[str, ...]] = ("fedora",)

    def verify(self, ctx: Ctx) -> bool:
        if ctx.os.family != "fedora":
            return False
        return ctx.ex.run(["rpm", "-q", "btrfsmaintenance"]).ok

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family != "fedora":
            raise UnsupportedOS(
                f"btrfsmaintenance is Fedora/btrfs-only; detected {ctx.os.distro!r}"
            )
        pkg.install(ctx, "btrfsmaintenance")


@register
class DnfAutomaticSecurity(Module):
    name = "dnf-automatic-security"
    category = "system"
    description = "Automatic security-only dnf updates."
    profiles = ("system",)
    families: ClassVar[tuple[str, ...]] = ("fedora",)

    def _conf(self) -> str:
        return os.environ.get("DEVBOOST_DNF_AUTOMATIC_CONF", "/etc/dnf/automatic.conf")

    def verify(self, ctx: Ctx) -> bool:
        p = Path(self._conf())
        return p.exists() and "upgrade_type=security" in p.read_text(encoding="utf-8")

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family != "fedora":
            raise UnsupportedOS(
                f"dnf-automatic-security is Fedora-only; detected {ctx.os.distro!r}"
            )
        pkg.install(ctx, "dnf-automatic")
        config.write_kv(ctx, self._conf(), "upgrade_type", "security")
        systemd.enable_system_unit(ctx, "dnf-automatic.timer", now=True)


@register
class Earlyoom(Module):
    name = "earlyoom"
    category = "system"
    description = "Userspace OOM killer (dev-protecting)."
    profiles = ("system",)

    def _conf(self, ctx: Ctx | None = None) -> str:
        """Return the earlyoom config path.

        Respects DEVBOOST_EARLYOOM_CONF override; otherwise selects the
        distro-conventional path: /etc/default/earlyoom on Debian/Ubuntu,
        /etc/sysconfig/earlyoom on Fedora.
        """
        override = os.environ.get("DEVBOOST_EARLYOOM_CONF")
        if override:
            return override
        if ctx is not None and ctx.os.family == "debian":
            return "/etc/default/earlyoom"
        return "/etc/sysconfig/earlyoom"

    def verify(self, ctx: Ctx) -> bool:
        p = Path(self._conf(ctx))
        if not p.exists():
            return False
        text = p.read_text(encoding="utf-8")
        return "--avoid" in text and "--prefer" in text

    def install(self, ctx: Ctx) -> None:
        pkg.install(ctx, "earlyoom")
        args = (
            "\"-r 60 --avoid '(^|/)(init|systemd|Xorg|sshd)$' "
            "--prefer '(^|/)(chrome|firefox|node|java)$'\""
        )
        config.write_kv(ctx, self._conf(ctx), "EARLYOOM_ARGS", args)
        systemd.enable_system_unit(ctx, "earlyoom", now=True)


@register
class ResticBackup(Module):
    name = "restic-backup"
    category = "system"
    description = "Restic backup user service + timer."
    profiles = ("system",)

    def verify(self, ctx: Ctx) -> bool:
        d = systemd._user_unit_dir()
        if not ((d / "restic-backup.service").exists() and (d / "restic-backup.timer").exists()):
            return False
        return systemd.is_enabled(ctx, "restic-backup.timer", user=True)

    def install(self, ctx: Ctx) -> None:
        if not ctx.ex.which("restic"):
            pkg.install(ctx, "restic")
        service = (
            "[Unit]\nDescription=devboost restic backup\n\n[Service]\nType=oneshot\n"
            "ExecStart=/usr/bin/restic backup --files-from %h/.config/devboost/restic-include\n"
        )
        timer = (
            "[Unit]\nDescription=daily restic backup\n\n[Timer]\nOnCalendar=daily\n"
            "Persistent=true\n\n[Install]\nWantedBy=timers.target\n"
        )
        systemd.write_user_unit(ctx, "restic-backup.service", service)
        systemd.write_user_unit(ctx, "restic-backup.timer", timer)
        systemd.enable_user_unit(ctx, "restic-backup.timer", now=True)


@register
class GpuDetect(Module):
    name = "gpu-detect"
    category = "system"
    description = "Auto-detect the GPU vendor and record it for driver selection."
    profiles = ("system",)

    def _marker(self) -> Path:
        state = os.environ.get("XDG_STATE_HOME") or str(
            Path(os.environ["HOME"]) / ".local" / "state"
        )
        return Path(state) / "devboost" / "gpu-vendor"

    def verify(self, ctx: Ctx) -> bool:
        return self._marker().exists()

    def install(self, ctx: Ctx) -> None:
        gpus = gpu.detect(ctx)
        vendors = [n for n, on in
                   (("intel", gpus.intel), ("amd", gpus.amd), ("nvidia", gpus.nvidia)) if on]
        marker = self._marker()
        marker.parent.mkdir(parents=True, exist_ok=True)
        # One vendor token per line (intel / amd / nvidia).  The core agent reads this
        # file and checks for the token "nvidia" to decide whether to inject hardware-nvidia.
        marker.write_text("\n".join(vendors) + "\n" if vendors else "", encoding="utf-8")
        log.ok(f"gpu-detect: {', '.join(vendors) or 'no recognized GPU'}")
