"""system profile — resilience services + GPU detection."""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar

from devboost.core import log
from devboost.core.errors import UnsupportedOS
from devboost.core.registry import register
from devboost.exec.primitives import config, copr, gpu, pkg, systemd
from devboost.model import Ctx, Module


def _snapper_config_value(get_config_stdout: str, key: str) -> str | None:
    """Return the value for `key` in `snapper get-config` table output, or None.

    snapper prints a two-column ``Key │ Value`` table using a box-drawing separator;
    normalise the separator to whitespace and match the row whose first token is `key`
    (exact-token match, so ``NUMBER_LIMIT`` never matches ``NUMBER_LIMIT_IMPORTANT``).
    """
    for line in get_config_stdout.splitlines():
        parts = line.replace("│", " ").replace("|", " ").split()
        if parts and parts[0] == key:
            return parts[-1] if len(parts) > 1 else ""
    return None


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
        # grub-btrfs is NOT in Fedora's own repos — `dnf install grub-btrfs` fails with
        # "No match for argument: grub-btrfs". Its canonical source is the kylegospo/grub-btrfs
        # COPR (verified to build for fedora-44). Enable it first (idempotent).
        copr.enable(ctx, "kylegospo/grub-btrfs")
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
    description = "Power profile switching (D-Bus)."
    svc_pkg = "power-profiles-daemon"
    service = "power-profiles-daemon"

    def _ppd_already_provided(self, ctx: Ctx) -> bool:
        # power-profiles-daemon and tuned-ppd both Provide AND Conflict on `ppd-service`, so
        # exactly one may be installed. Fedora 44 ships tuned-ppd by default, which already
        # gives GNOME the power-profiles D-Bus API — so `dnf install power-profiles-daemon`
        # FAILS on the conflict (exit 1). rpm-only probe; non-Fedora falls through to install.
        return ctx.os.family == "fedora" and ctx.ex.run(
            ["rpm", "-q", "--whatprovides", "ppd-service"]
        ).ok

    def verify(self, ctx: Ctx) -> bool:
        # Satisfied if either implementation provides it: tuned-ppd on modern Fedora, or the
        # power-profiles-daemon service where we installed it ourselves.
        return self._ppd_already_provided(ctx) or systemd.is_enabled(ctx, self.service)

    def install(self, ctx: Ctx) -> None:
        if self._ppd_already_provided(ctx):
            return  # tuned-ppd already provides the ppd D-Bus API; forcing the pkg conflicts
        pkg.install(ctx, self.svc_pkg)
        systemd.enable_system_unit(ctx, self.service, now=True)


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
    description = "BTRFS snapshots for / (retention-capped)."
    profiles = ("system",)
    families: ClassVar[tuple[str, ...]] = ("fedora",)

    #: Retention policy applied after create-config. Without this, the stock config keeps
    #: hourly timeline snapshots plus up to 50 number snapshots; paired with the dnf
    #: pre/post hook (snapper-dnf-hook) that piles up and quietly consumes the disk. The
    #: useful rollback points on a dev box are the per-transaction number snapshots, so we
    #: drop the timeline entirely and keep the last 10.
    _POLICY: ClassVar[tuple[str, ...]] = (
        "TIMELINE_CREATE=no",
        "NUMBER_CLEANUP=yes",
        "NUMBER_LIMIT=10",
        "NUMBER_LIMIT_IMPORTANT=5",
    )
    #: Subset of _POLICY that verify() re-checks (proves the config exists AND is capped).
    _EXPECTED: ClassVar[dict[str, str]] = {"TIMELINE_CREATE": "no", "NUMBER_LIMIT": "10"}

    def verify(self, ctx: Ctx) -> bool:
        if ctx.os.family != "fedora":
            return False
        # sudo=True is REQUIRED: `snapper get-config` is root-only, so without it snapper
        # prints "No permissions." and exits non-zero — making verify ALWAYS fail for the
        # unprivileged install user, even when the config exists and is correct ("snapper:
        # verify failed after install"). install() already runs create-config with sudo.
        res = ctx.ex.run(["snapper", "-c", "root", "get-config"], sudo=True)
        if not res.ok:
            # get-config also fails when the root config genuinely does not exist yet.
            return False
        return all(
            _snapper_config_value(res.stdout, key) == val
            for key, val in self._EXPECTED.items()
        )

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family != "fedora":
            raise UnsupportedOS(
                f"snapper/btrfs is Fedora-only; detected {ctx.os.distro!r}"
            )
        pkg.install(ctx, "snapper", "python3-dnf-plugin-snapper")
        ctx.ex.run(["snapper", "-c", "root", "create-config", "/"], sudo=True)
        ctx.ex.run(["snapper", "-c", "root", "set-config", *self._POLICY], sudo=True)


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
class Swapfile(Module):
    name = "swapfile"
    category = "system"
    description = "Disk swapfile sized to RAM for OOM headroom (page-out overflow above zram)."
    profiles = ("system",)
    families: ClassVar[tuple[str, ...]] = ("fedora",)

    #: swapfile size = this fraction of total RAM, bounded above by ``cap_gib``.
    percent_of_ram: ClassVar[float] = 1.0
    cap_gib: ClassVar[int] = 32

    def _path(self) -> str:
        return os.environ.get("DEVBOOST_SWAPFILE_PATH", "/swapfile")

    def _fstab(self) -> str:
        return os.environ.get("DEVBOOST_FSTAB", "/etc/fstab")

    def _total_ram_bytes(self, ctx: Ctx) -> int:
        for line in ctx.ex.run(["free", "-b"]).stdout.splitlines():
            parts = line.split()
            if parts and parts[0] == "Mem:" and len(parts) > 1:
                try:
                    return int(parts[1])
                except ValueError:
                    break
        try:  # fallback when `free` is unavailable/unparsable
            return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
        except (ValueError, OSError):
            return 0

    def _size_gib(self, ctx: Ctx) -> int:
        gib = round(self._total_ram_bytes(ctx) * self.percent_of_ram / 1024**3)
        return max(1, min(self.cap_gib, gib))

    def _is_btrfs(self, ctx: Ctx) -> bool:
        return ctx.ex.run(["findmnt", "-no", "FSTYPE", "/"]).stdout.strip() == "btrfs"

    def _fstab_has(self, path: str) -> bool:
        p = Path(self._fstab())
        if not p.exists():
            return False
        return any(
            ln.split()[:1] == [path]
            for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.split()
        )

    def verify(self, ctx: Ctx) -> bool:
        if ctx.os.family != "fedora":
            return False
        path = self._path()
        active = path in ctx.ex.run(
            ["swapon", "--show=NAME", "--noheadings"]
        ).stdout.split()
        return active and self._fstab_has(path)

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family != "fedora":
            raise UnsupportedOS(
                f"swapfile module is Fedora-only; detected {ctx.os.distro!r}"
            )
        path = self._path()
        size = self._size_gib(ctx)
        if not Path(path).exists():
            if self._is_btrfs(ctx):
                # mkswapfile makes it NOCOW + uncompressed — the only correct way on btrfs;
                # a fallocate'd swapfile is rejected/corrupt on btrfs.
                ctx.ex.run(
                    ["btrfs", "filesystem", "mkswapfile",
                     "--size", f"{size}g", "--uuid", "clear", path],
                    sudo=True,
                )
            else:
                ctx.ex.run(["fallocate", "-l", f"{size}G", path], sudo=True)
                ctx.ex.run(["chmod", "600", path], sudo=True)
                ctx.ex.run(["mkswap", path], sudo=True)
        ctx.ex.run(["swapon", path], sudo=True)
        self._ensure_fstab(ctx, path)

    def _ensure_fstab(self, ctx: Ctx, path: str) -> None:
        if self._fstab_has(path):
            return
        fstab = self._fstab()
        p = Path(fstab)
        lines = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
        body = "\n".join([*lines, f"{path} none swap defaults 0 0"]) + "\n"
        writable = os.access(fstab, os.W_OK) if p.exists() else os.access(p.parent, os.W_OK)
        if writable:
            p.write_text(body, encoding="utf-8")
        else:
            ctx.ex.run(["tee", fstab], sudo=True, stdin=body)


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
