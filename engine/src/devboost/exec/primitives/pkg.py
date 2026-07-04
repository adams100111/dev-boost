"""Package primitive with OS dispatch.

The package manager is selected from ctx.os; no module ever names dnf/apt directly.
Dnf (Fedora) and Apt (Debian/Ubuntu) are implemented; Pacman is a seam for a later spec.
"""

from __future__ import annotations

import re
import shlex
from typing import Protocol, runtime_checkable

from devboost.core import log
from devboost.core.errors import InstallError, UnsupportedOS
from devboost.core.osinfo import OsInfo, OsMap
from devboost.model import AptRepo, Ctx, DnfRepo

# A package name: a plain string, or per-OS names resolved distro->family->default.
Pkg = str | OsMap[str]
# A third-party install source per OS (DnfRepo for Fedora, AptRepo for Debian/Ubuntu).
Source = OsMap[DnfRepo | AptRepo]


@runtime_checkable
class PackageManager(Protocol):
    def install(self, ctx: Ctx, *pkgs: str) -> None: ...
    def installed(self, ctx: Ctx, pkg: str) -> bool: ...
    def add_repo(self, ctx: Ctx, repo: DnfRepo | AptRepo) -> None: ...


class Dnf:
    def install(self, ctx: Ctx, *pkgs: str) -> None:
        if pkgs:
            result = ctx.ex.run(["dnf", "install", "-y", *pkgs], sudo=True)
            if not result.ok:
                raise InstallError("dnf", f"dnf install -y {' '.join(pkgs)}", result.code)

    def installed(self, ctx: Ctx, pkg: str) -> bool:
        return ctx.ex.run(["rpm", "-q", pkg]).ok

    def add_repo(self, ctx: Ctx, repo: DnfRepo | AptRepo) -> None:
        if not isinstance(repo, DnfRepo):
            raise TypeError(f"Dnf.add_repo expects DnfRepo, got {type(repo).__name__}")
        body = (
            f"[{repo.name}]\nname={repo.name}\nbaseurl={repo.baseurl}\n"
            f"gpgcheck={1 if repo.gpgcheck else 0}\nenabled=1\n"
        )
        if repo.gpgkey is not None:
            body += f"gpgkey={repo.gpgkey}\n"
        dest = f"/etc/yum.repos.d/{repo.name}.repo"
        result = ctx.ex.run(["tee", dest], sudo=True, stdin=body)
        if not result.ok:
            raise InstallError("dnf", f"tee {dest}", result.code)


def _apt_slug(list_line: str) -> str:
    """Derive a stable filename slug from the first URL in an apt list_line."""
    m = re.search(r"https?://([^/\s]+)", list_line)
    return m.group(1).replace(".", "-") if m else "custom-repo"


# Ubuntu 24.04's apt post-hook runs needrestart, which pops whiptail prompts that hang a
# non-interactive (agent / curl|bash) install: a "restart which services?" prompt AND a
# "pending kernel upgrade" msgbox. NEEDRESTART_MODE=a silences the first, but the kernel
# hint is only disabled via config — so drop in a conf that turns both off.
_NEEDRESTART_CONF = "/etc/needrestart/conf.d/99-devboost.conf"
_NEEDRESTART_BODY = (
    "# devboost — keep apt's needrestart hook from hanging non-interactive installs.\n"
    "$nrconf{restart} = 'a';\n"       # auto-restart services, don't ask
    "$nrconf{kernelhints} = -1;\n"    # no 'pending kernel upgrade' msgbox
    "$nrconf{ucodehints} = 0;\n"      # no microcode msgbox
)


class Apt:
    def _quiet_needrestart(self, ctx: Ctx) -> None:
        ctx.ex.run(["mkdir", "-p", "/etc/needrestart/conf.d"], sudo=True)
        ctx.ex.run(["tee", _NEEDRESTART_CONF], sudo=True, stdin=_NEEDRESTART_BODY)

    def install(self, ctx: Ctx, *pkgs: str) -> None:
        if pkgs:
            self._quiet_needrestart(ctx)
            result = ctx.ex.run(
                ["apt-get", "install", "-y", *pkgs],
                sudo=True,
                env={"DEBIAN_FRONTEND": "noninteractive", "NEEDRESTART_MODE": "a"},
            )
            if not result.ok:
                raise InstallError("apt", f"apt-get install -y {' '.join(pkgs)}", result.code)

    def installed(self, ctx: Ctx, pkg: str) -> bool:
        return ctx.ex.run(["dpkg", "-s", pkg]).ok

    def add_repo(self, ctx: Ctx, repo: DnfRepo | AptRepo) -> None:
        if not isinstance(repo, AptRepo):
            raise TypeError(f"Apt.add_repo expects AptRepo, got {type(repo).__name__}")
        slug = _apt_slug(repo.list_line)
        # Fetch the signing key and normalize it to a BINARY keyring. Vendors serve
        # either ASCII-armored keys (ddev, Microsoft, Docker) or binary keyrings;
        # `gpg --dearmor` accepts both and always emits binary, matching the `.gpg`
        # name used in signed-by. Writing an armored key straight to `.gpg` (the old
        # behavior) trips NO_PUBKEY. Pipe curl→gpg in one shell run so a binary key is
        # never corrupted by round-tripping through captured stdout.
        if repo.key_url:
            key_path = f"/etc/apt/keyrings/{slug}.gpg"
            script = (
                "mkdir -p /etc/apt/keyrings && "
                f"curl -fsSL {shlex.quote(repo.key_url)} "
                f"| gpg --dearmor --yes -o {shlex.quote(key_path)}"
            )
            put = ctx.ex.run(["sh", "-c", script], sudo=True)
            if not put.ok:
                raise InstallError("apt", f"import key {repo.key_url}", put.code)
        # Write the sources list entry.
        list_path = f"/etc/apt/sources.list.d/{slug}.list"
        put = ctx.ex.run(["tee", list_path], sudo=True, stdin=repo.list_line + "\n")
        if not put.ok:
            raise InstallError("apt", f"tee {list_path}", put.code)
        # Refresh the package index.
        upd = ctx.ex.run(
            ["apt-get", "update"],
            sudo=True,
            env={"DEBIAN_FRONTEND": "noninteractive"},
        )
        if not upd.ok:
            raise InstallError("apt", "apt-get update", upd.code)


def manager_for(os_info: OsInfo) -> PackageManager:
    if os_info.family == "fedora":
        return Dnf()
    if os_info.family == "debian":
        return Apt()
    raise UnsupportedOS(f"no package manager implemented for {os_info.distro!r}")


def _resolve_names(ctx: Ctx, pkgs: tuple[Pkg, ...]) -> list[str]:
    names: list[str] = []
    for p in pkgs:
        if isinstance(p, str):
            names.append(p)
        else:
            name = p.get(ctx.os)
            if name is None:
                raise UnsupportedOS(f"no package name for {ctx.os.distro!r}")
            names.append(name)
    return names


def install(
    ctx: Ctx,
    *pkgs: Pkg,
    source: Source | None = None,
    refresh: bool = False,
) -> None:
    mgr = manager_for(ctx.os)
    if source is not None:
        repo = source.get(ctx.os)
        if repo is None:
            raise UnsupportedOS(f"no install source for {ctx.os.distro!r}")
        mgr.add_repo(ctx, repo)
    names = _resolve_names(ctx, pkgs)
    if refresh and isinstance(mgr, Dnf) and names:
        result = ctx.ex.run(["dnf", "install", "--refresh", "-y", *names], sudo=True)
        if not result.ok:
            raise InstallError("dnf", f"dnf install --refresh -y {' '.join(names)}", result.code)
        return
    mgr.install(ctx, *names)


def installed(ctx: Ctx, pkg: str) -> bool:
    return manager_for(ctx.os).installed(ctx, pkg)


#: Seconds apt waits for a held dpkg/apt lock before giving up (drop-in below).
_APT_LOCK_TIMEOUT = 300
_APT_LOCK_CONF = "/etc/apt/apt.conf.d/99-devboost-lock-timeout"


def refresh_index(ctx: Ctx) -> None:
    """Refresh the package index once before the install loop (best-effort).

    On Debian/Ubuntu a fresh or minimal system can carry a stale/incomplete apt index,
    so installing an otherwise-available package (e.g. ``du-dust`` from universe) fails
    with apt exit 100.  A single ``apt-get update`` up front makes installs robust without
    per-package overhead.  No-op on Fedora (dnf refreshes metadata on demand) and on any
    OS without a package manager.  Failures are logged, never raised: a transient mirror
    error must not abort the run, and a usable cached index may still satisfy installs.
    """
    if ctx.os.family != "debian":
        return
    # Make every apt call WAIT up to _APT_LOCK_TIMEOUT for a held dpkg/apt lock (e.g.
    # cloud-init / unattended-upgrades on a fresh VM) instead of failing with exit 100.
    # A drop-in applies globally — including the user's own later `apt`. Best-effort.
    ctx.ex.run(
        ["tee", _APT_LOCK_CONF],
        sudo=True,
        stdin=f'DPkg::Lock::Timeout "{_APT_LOCK_TIMEOUT}";\n',
    )
    result = ctx.ex.run(
        ["apt-get", "update"],
        sudo=True,
        env={"DEBIAN_FRONTEND": "noninteractive"},
    )
    if not result.ok:
        log.warn(f"apt-get update failed (code {result.code}); using the existing index")
