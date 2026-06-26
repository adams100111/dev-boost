"""Package primitive with OS dispatch. The package manager is selected from ctx.os;
no module ever names dnf/apt. Dnf is implemented; Apt/Pacman are seams for later specs.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from devboost.core.errors import UnsupportedOS
from devboost.core.osinfo import OsInfo, OsMap
from devboost.model import Ctx, DnfRepo

# A package name: a plain string, or per-OS names resolved distro->family->default.
Pkg = str | OsMap[str]
# A third-party install source per OS (only DnfRepo is applied for Fedora).
Source = OsMap[DnfRepo]


@runtime_checkable
class PackageManager(Protocol):
    def install(self, ctx: Ctx, *pkgs: str) -> None: ...
    def installed(self, ctx: Ctx, pkg: str) -> bool: ...
    def add_repo(self, ctx: Ctx, repo: DnfRepo) -> None: ...


class Dnf:
    def install(self, ctx: Ctx, *pkgs: str) -> None:
        if pkgs:
            ctx.ex.run(["dnf", "install", "-y", *pkgs], sudo=True)

    def installed(self, ctx: Ctx, pkg: str) -> bool:
        return ctx.ex.run(["rpm", "-q", pkg]).ok

    def add_repo(self, ctx: Ctx, repo: DnfRepo) -> None:
        body = (
            f"[{repo.name}]\nname={repo.name}\nbaseurl={repo.baseurl}\n"
            f"gpgcheck={1 if repo.gpgcheck else 0}\nenabled=1\n"
        )
        ctx.ex.run(
            ["tee", f"/etc/yum.repos.d/{repo.name}.repo"],
            sudo=True,
            stdin=body,
        )


def manager_for(os_info: OsInfo) -> PackageManager:
    if os_info.family == "fedora":
        return Dnf()
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
        ctx.ex.run(["dnf", "install", "--refresh", "-y", *names], sudo=True)
        return
    mgr.install(ctx, *names)


def installed(ctx: Ctx, pkg: str) -> bool:
    return manager_for(ctx.os).installed(ctx, pkg)
