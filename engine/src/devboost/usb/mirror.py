"""Offline mirror: describe a profile's dnf/flatpak package set, then materialize it."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx, Module

_FEDORA = OsInfo("fedora", "fedora", "x86_64")


class _Recorder(FakeExecutor):
    """Records dnf-install package args and flatpak-install app ids; never mutates anything."""

    def __init__(self) -> None:
        super().__init__()
        self.dnf: set[str] = set()
        self.flatpak: set[str] = set()

    def run(self, argv: Sequence[str], *, sudo: bool = False, stdin: str | None = None,
            env: Mapping[str, str] | None = None) -> Result:
        a = list(argv)
        if a[:2] == ["dnf", "install"]:
            self.dnf.update(x for x in a[2:] if not x.startswith("-"))
        elif a[:2] == ["flatpak", "install"]:
            self.flatpak.update(x for x in a[2:] if not x.startswith("-") and x != "flathub")
        return super().run(argv, sudo=sudo, stdin=stdin, env=env)


def package_set(profiles: tuple[str, ...], root: Path) -> tuple[set[str], set[str]]:
    modules = load()
    profs = load_profiles(root / "profiles.toml")
    order = toposort(expand(list(profiles), profs, modules), modules)
    rec = _Recorder()
    ctx = Ctx(os=_FEDORA, ex=rec, force=True)   # force=True so verify never short-circuits install
    for name in order:
        try:
            modules[name]().install(ctx)
        except Exception:  # noqa: BLE001 — describing only; ignore modules needing real state
            continue
    return rec.dnf, rec.flatpak


def mirror_dnf(ctx: Ctx, packages: set[str], dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    dnf_cmd = ["dnf", "download", "--resolve", "--destdir", str(dest), *sorted(packages)]
    ctx.ex.run(dnf_cmd, sudo=True)
    ctx.ex.run(["createrepo_c", str(dest)], sudo=True)


def mirror_flatpak(ctx: Ctx, app_ids: set[str], dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for app in sorted(app_ids):
        ctx.ex.run(["flatpak", "create-usb", str(dest), app])


def offline_installable(cls: type[Module]) -> bool:
    """Return True if a module class can be installed from the offline mirror."""
    from devboost.modules._pkgmodule import PackageModule
    from devboost.modules.apps import FlatpakApp

    return issubclass(cls, (PackageModule, FlatpakApp))
