from devboost.osinfo import OsInfo, detect, family_of, is_headless


def test_family_of_maps_distros() -> None:
    assert family_of("ubuntu") == "debian"
    assert family_of("fedora") == "fedora"
    assert family_of("rocky") == "fedora"
    assert family_of("unknown-os") == "unknown-os"


def test_detect_reads_os_release(tmp_path) -> None:
    f = tmp_path / "os-release"
    f.write_text('ID=ubuntu\nVERSION_ID="24.04"\n')
    info = detect(os_release_path=str(f), machine="x86_64")
    assert info == OsInfo(distro="ubuntu", family="debian", arch="x86_64")


def test_is_headless_true_without_display() -> None:
    assert is_headless(env={}) is True


def test_is_headless_false_with_wayland() -> None:
    assert is_headless(env={"WAYLAND_DISPLAY": "wayland-0"}) is False
