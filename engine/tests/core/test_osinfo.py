from __future__ import annotations

from pathlib import Path

from devboost.core.osinfo import OsInfo, OsMap, detect, family_of


def test_family_mapping() -> None:
    assert family_of("ubuntu") == "debian"
    assert family_of("fedora") == "fedora"
    assert family_of("weird-distro") == "weird-distro"


def test_detect_reads_os_release(tmp_path: Path) -> None:
    p = tmp_path / "os-release"
    p.write_text('ID=fedora\nVERSION_ID=41\n', encoding="utf-8")
    info = detect(os_release_path=str(p), machine="x86_64", env={})
    assert info.distro == "fedora"
    assert info.family == "fedora"
    assert info.arch == "x86_64"
    assert info.headless is True


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
