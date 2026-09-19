"""macOS system modules: open-files limit, application firewall, Time Machine exclusions.

Default apps are not here: they go through ``exec/primitives/default_apps`` and the
``utiluti`` module (ruling M5-D2).
"""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from typing import ClassVar

from devboost.core import log
from devboost.core.errors import InstallError
from devboost.core.registry import register
from devboost.exec.primitives import launchd
from devboost.model import Ctx, Module

_MACOS: tuple[str, ...] = ("macos",)
_PROFILES: tuple[str, ...] = ("macos-desktop",)

# --- macos-limits -------------------------------------------------------------------------

MAXFILES = 524288
_LIMITS_LABEL = launchd.label("maxfiles")
#: sysctl lifts the kernel clamp (`ulimit -n` can never exceed kern.maxfilesperproc);
#: `launchctl limit` raises launchd's own limit for GUI apps — best-effort, because Apple
#: returns EPERM for it under SIP on some releases (spec D11). The script runs as root
#: from a root-owned plist, so it names only system binaries — no user-writable path.
_LIMITS_SCRIPT = (
    f"sysctl -w kern.maxfiles={MAXFILES} kern.maxfilesperproc={MAXFILES} && "
    f"{{ launchctl limit maxfiles {MAXFILES} {MAXFILES} || true; }}"
)


def _sysctl_ints(ctx: Ctx, *names: str) -> list[int]:
    res = ctx.ex.run(["sysctl", "-n", *names])
    if not res.ok:
        return []
    try:
        return [int(tok) for tok in res.stdout.split()]
    except ValueError:
        return []


@register
class MacosLimits(Module):
    name = "macos-limits"
    category = "macos-desktop"
    description = "Open-files limit 524288 (LaunchDaemon: sysctl + launchctl limit)."
    profiles = _PROFILES
    families: ClassVar[tuple[str, ...]] = _MACOS
    portable: ClassVar[bool] = True
    needs_sudo_on_macos: ClassVar[bool] = True  # root LaunchDaemon + `sudo sh` (M5-D5)

    def verify(self, ctx: Ctx) -> bool:
        vals = _sysctl_ints(ctx, "kern.maxfiles", "kern.maxfilesperproc")
        return (
            len(vals) == 2
            and min(vals) >= MAXFILES
            and launchd.daemon_loaded(ctx, _LIMITS_LABEL)
        )

    def install(self, ctx: Ctx) -> None:
        launchd.system_daemon(ctx, _LIMITS_LABEL, ["/bin/sh", "-c", _LIMITS_SCRIPT])
        # Apply now as well: an unchanged plist is not re-bootstrapped, and the user
        # should not need a reboot.
        res = ctx.ex.run(["sh", "-c", _LIMITS_SCRIPT], sudo=True)
        if not res.ok:
            raise InstallError(self.name, f"sudo sh -c '{_LIMITS_SCRIPT}'", res.code)
        log.info(f"{self.name}: new terminals get `ulimit -n {MAXFILES}` (shell.zsh)")


# --- macos-firewall -----------------------------------------------------------------------

SOCKETFILTERFW = "/usr/libexec/ApplicationFirewall/socketfilterfw"
_FW_STATE = re.compile(r"\(State = (\d+)\)")


def firewall_enabled(ctx: Ctx) -> bool:
    """True when the application firewall is on.

    macOS prints ``Firewall is enabled. (State = 1)``, ``… disabled. (State = 0)``, or
    State = 2 when it blocks all incoming connections (which is on, too). Checked on
    macOS 27.0 (26A428): no root is needed to read it.
    """
    res = ctx.ex.run([SOCKETFILTERFW, "--getglobalstate"])
    if not res.ok:
        return False
    m = _FW_STATE.search(res.stdout)
    if m is not None:
        return int(m.group(1)) >= 1
    return "is enabled" in res.stdout


@register
class MacosFirewall(Module):
    name = "macos-firewall"
    category = "macos-desktop"
    description = "Turn on the macOS application firewall."
    profiles = _PROFILES
    families: ClassVar[tuple[str, ...]] = _MACOS
    portable: ClassVar[bool] = True
    needs_sudo_on_macos: ClassVar[bool] = True  # `sudo socketfilterfw` (M5-D5)

    def verify(self, ctx: Ctx) -> bool:
        return firewall_enabled(ctx)

    def install(self, ctx: Ctx) -> None:
        res = ctx.ex.run([SOCKETFILTERFW, "--setglobalstate", "on"], sudo=True)
        if not res.ok:
            raise InstallError(
                self.name, f"sudo {SOCKETFILTERFW} --setglobalstate on", res.code
            )


# --- timemachine-exclusions ---------------------------------------------------------------

#: Regenerable caches and VM disks (relative to HOME) — spec §2 plus ruling M5-D8: every
#: Colima home candidate (the legacy ``.colima`` and the fresh-Mac ``.config/colima``),
#: OrbStack, and Docker Desktop's container. launchd gives the agent no XDG variables, so
#: these are literal; ``$COLIMA_HOME`` is added by ``tm_candidates`` at install time.
TM_PATHS: tuple[str, ...] = (
    "Library/Caches",
    ".colima",
    ".config/colima",
    ".orbstack",
    "Library/Containers/com.docker.docker",
    ".gradle",
    ".npm",
    ".cache",
    ".nuget/packages",
    "Library/Developer/Xcode/DerivedData",
)
_TM_LABEL = launchd.label("tm-exclusions")
_TM_INTERVAL = 6 * 60 * 60


def _home() -> Path:
    return Path(os.environ["HOME"])


def tm_candidates() -> list[Path]:
    """Every fixed path (absolute), plus ``$COLIMA_HOME`` when it is set and not listed."""
    paths = [_home() / rel for rel in TM_PATHS]
    colima_home = os.environ.get("COLIMA_HOME")
    if colima_home and Path(colima_home) not in paths:
        paths.append(Path(colima_home))
    return paths


def tm_sweep_script() -> str:
    """Sticky-exclude the fixed paths that exist, plus node_modules/vendor under ~/repos.

    Sticky (`tmutil addexclusion` without -p) needs no sudo and follows the item if it
    moves; a path that does not exist yet is skipped and picked up by a later sweep.
    ``$COLIMA_HOME`` is baked in (shell-quoted) because launchd does not pass it.
    """
    fixed = [f'"$HOME/{p}"' for p in TM_PATHS]
    fixed += [shlex.quote(str(p)) for p in tm_candidates()[len(TM_PATHS):]]
    return (
        'ex() { [ -e "$1" ] || return 0; '
        "tmutil isexcluded \"$1\" | grep -q '^\\[Excluded\\]' || tmutil addexclusion \"$1\"; }\n"
        f"for p in {' '.join(fixed)}; do ex \"$p\"; done\n"
        'if [ -d "$HOME/repos" ]; then\n'
        '  find "$HOME/repos" -maxdepth 6 -type d \\( -name node_modules -o -name vendor \\) '
        '-prune -print | while IFS= read -r d; do ex "$d"; done\n'
        "fi\n"
        "exit 0\n"
    )


def _excluded(ctx: Ctx, path: Path) -> bool:
    res = ctx.ex.run(["tmutil", "isexcluded", str(path)])
    return res.ok and res.stdout.lstrip().startswith("[Excluded]")


def _sweep_argv() -> list[str]:
    return ["/bin/sh", "-c", tm_sweep_script()]


@register
class TimemachineExclusions(Module):
    name = "timemachine-exclusions"
    category = "macos-desktop"
    description = "Keep caches, VM disks, node_modules and vendor out of Time Machine."
    profiles = _PROFILES
    families: ClassVar[tuple[str, ...]] = _MACOS
    portable: ClassVar[bool] = True

    def verify(self, ctx: Ctx) -> bool:
        present = [p for p in tm_candidates() if p.exists()]
        return all(_excluded(ctx, p) for p in present) and launchd.agent_current(
            ctx, _TM_LABEL, _sweep_argv(), start_interval=_TM_INTERVAL, run_at_load=True
        )

    def install(self, ctx: Ctx) -> None:
        argv = _sweep_argv()
        launchd.user_agent(ctx, _TM_LABEL, argv, start_interval=_TM_INTERVAL, run_at_load=True)
        res = ctx.ex.run(argv)
        if not res.ok:
            raise InstallError(self.name, "tm-exclusions sweep", res.code)
