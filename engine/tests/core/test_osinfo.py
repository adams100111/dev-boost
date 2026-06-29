from __future__ import annotations

import os
from pathlib import Path

from devboost.core.osinfo import OsInfo, OsMap, detect, family_of, is_headless


def test_family_mapping() -> None:
    assert family_of("ubuntu") == "debian"
    assert family_of("fedora") == "fedora"
    assert family_of("weird-distro") == "weird-distro"


def test_detect_reads_os_release(tmp_path: Path) -> None:
    p = tmp_path / "os-release"
    p.write_text('ID=fedora\nVERSION_ID=41\n', encoding="utf-8")
    # No DISPLAY and no readable default target → headless.
    info = detect(
        os_release_path=str(p), machine="x86_64", env={},
        default_target_link=str(tmp_path / "no-such-target"),
    )
    assert info.distro == "fedora"
    assert info.family == "fedora"
    assert info.arch == "x86_64"
    assert info.headless is True


def test_is_headless_false_when_display_set(tmp_path: Path) -> None:
    assert is_headless({"DISPLAY": ":0"}, str(tmp_path / "missing")) is False


def test_is_headless_false_when_default_target_graphical(tmp_path: Path) -> None:
    link = tmp_path / "default.target"
    os.symlink("/usr/lib/systemd/system/graphical.target", link)
    assert is_headless({}, str(link)) is False


def test_is_headless_true_when_default_target_multi_user(tmp_path: Path) -> None:
    link = tmp_path / "default.target"
    os.symlink("/usr/lib/systemd/system/multi-user.target", link)
    assert is_headless({}, str(link)) is True


def test_is_headless_true_when_target_unreadable(tmp_path: Path) -> None:
    assert is_headless({}, str(tmp_path / "missing")) is True


def test_osmap_precedence_distro_then_family_then_default() -> None:
    fedora = OsInfo("fedora", "fedora", "x86_64")
    ubuntu = OsInfo("ubuntu", "debian", "x86_64")
    arch = OsInfo("arch", "arch", "x86_64")

    m: OsMap[str] = OsMap(fedora="fd-find", debian="fd-find", default="fd")
    assert m.get(fedora) == "fd-find"   # distro hit
    assert m.get(ubuntu) == "fd-find"   # family hit
    assert m.get(arch) == "fd"          # default fallback

    empty: OsMap[str] = OsMap()
    assert empty.get(fedora) is None
