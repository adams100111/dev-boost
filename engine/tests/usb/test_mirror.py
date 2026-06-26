from __future__ import annotations

from devboost.core.settings import settings
from devboost.usb.mirror import package_set


def test_package_set_collects_dnf_and_flatpak_for_cli_and_apps() -> None:
    dnf, flat = package_set(("cli", "apps"), settings.root)
    assert "bat" in dnf                         # a cli package (from a PackageModule)
    assert "md.obsidian.Obsidian" in flat      # an apps flatpak id


def test_mirror_dnf_downloads_and_creates_repo(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from devboost.core.osinfo import OsInfo
    from devboost.exec.executor import FakeExecutor
    from devboost.model import Ctx
    from devboost.usb.mirror import mirror_dnf

    ctx = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor())
    mirror_dnf(ctx, {"ripgrep", "git"}, tmp_path)
    calls = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert any("dnf download --resolve" in c and "ripgrep" in c for c in calls)
    assert any("createrepo_c" in c for c in calls)


def test_mirror_flatpak_creates_bundles(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from devboost.core.osinfo import OsInfo
    from devboost.exec.executor import FakeExecutor
    from devboost.model import Ctx
    from devboost.usb.mirror import mirror_flatpak

    ctx = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=FakeExecutor())
    mirror_flatpak(ctx, {"org.gnome.Foo", "md.obsidian.Obsidian"}, tmp_path)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["flatpak", "create-usb", str(tmp_path), "md.obsidian.Obsidian"] in calls
    assert ["flatpak", "create-usb", str(tmp_path), "org.gnome.Foo"] in calls
