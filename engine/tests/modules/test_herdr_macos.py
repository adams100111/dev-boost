"""herdr on every OS: one pin keyed by (os, arch), BSD-safe install, image paste kept."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from devboost.core.errors import InstallError, MediaError
from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.profiles import load_profiles
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor, Result
from devboost.media.catalog import asset_key, herdr_pin
from devboost.model import Ctx
from devboost.modules.herdr import _PLUGINS, Herdr, HerdrPlugins
from tests.scripted import Scripted

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
OMARCHY = OsInfo("omarchy", "arch", "aarch64", id_like=("arch",))
REPO_ROOT = Path(__file__).resolve().parents[3]


def test_asset_key_names_the_os_and_the_arch() -> None:
    assert asset_key(MAC) == "macos-aarch64"
    assert asset_key(FEDORA) == "linux-x86_64"
    assert asset_key(OMARCHY) == "linux-aarch64"


def test_live_pin_is_keyed_by_os_and_arch() -> None:
    pin = herdr_pin()
    assert pin.version == "0.9.1"
    assert set(pin.assets) == {"linux-x86_64", "linux-aarch64", "macos-aarch64"}
    for key, asset in pin.assets.items():
        assert asset.url == (
            f"https://github.com/herdrdev/herdr/releases/download/v0.9.1/herdr-{key}"
        )


def test_catalog_rejects_arch_only_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "catalog.toml"
    p.write_text(
        '[herdr]\nversion = "0.9.1"\n[herdr.assets.aarch64]\n'
        f'url = "https://x/herdr"\nsha256 = "{"a" * 64}"\n',
        encoding="utf-8",
    )

    class _FakeSettings:
        catalog_path = p

    monkeypatch.setattr("devboost.media.catalog.settings", _FakeSettings())
    herdr_pin.cache_clear()
    try:
        with pytest.raises(MediaError, match="asset keys must be"):
            herdr_pin()
    finally:
        herdr_pin.cache_clear()


def test_mac_installs_the_macos_binary_bsd_safely(tmp_path: Path) -> None:
    ex = FakeExecutor()
    Herdr().install(Ctx(os=MAC, ex=ex))
    script = ex.calls[0][2]
    assert "herdr-macos-aarch64" in script and "herdr-linux" not in script
    assert "shasum -a 256 -c -" in script and "sha256sum" not in script
    assert f'mkdir -p "{tmp_path}/.local/bin"' in script
    assert f'install -m 755 "$tmp/herdr" "{tmp_path}/.local/bin/herdr"' in script
    assert "install -D" not in script


def test_linux_keeps_sha256sum() -> None:
    ex = FakeExecutor()
    Herdr().install(Ctx(os=FEDORA, ex=ex))
    script = ex.calls[0][2]
    assert "herdr-linux-x86_64" in script and "sha256sum -c -" in script


def test_an_intel_mac_never_gets_a_linux_binary() -> None:
    with pytest.raises(InstallError, match="macos-x86_64"):
        Herdr().install(Ctx(os=OsInfo("macos", "macos", "x86_64"), ex=FakeExecutor()))


@pytest.mark.parametrize(
    ("installed", "ok"), [("herdr 0.7.5", False), ("herdr 0.9.1", True), ("herdr 0.10.0", True)]
)
def test_verify_upgrades_an_older_herdr_and_keeps_a_newer_one(installed: str, ok: bool) -> None:
    ex = Scripted(present={"herdr"},
                  answers={("herdr", "--version"): Result(0, stdout=installed + "\n")})
    assert Herdr().verify(Ctx(os=FEDORA, ex=ex)) is ok


def test_herdr_config_keeps_ctrl_v_for_remote_image_paste() -> None:
    cfg = REPO_ROOT / "dotfiles" / "dot_config" / "herdr" / "config.toml"
    data = tomllib.loads(cfg.read_text(encoding="utf-8"))
    assert data["keys"]["remote_image_paste"] == "ctrl+v"


def test_plugins_and_glow_are_in_cli_on_every_os() -> None:
    cli = load_profiles(REPO_ROOT / "profiles.toml")["cli"]
    assert "herdr-plugins" in cli and "glow" in cli
    assert "cli" in HerdrPlugins.profiles
    assert Herdr.portable and HerdrPlugins.portable


# --- herdr-plugins is a default now: prove its argv on every OS (ruling R11) -------------

UBUNTU = OsInfo("ubuntu", "debian", "x86_64", version_id="24.04")
ARCH = OsInfo("arch", "arch", "x86_64")


@pytest.mark.parametrize("os_info", [FEDORA, UBUNTU, ARCH, OMARCHY, MAC], ids=lambda o: o.distro)
def test_plugins_install_is_the_same_herdr_argv_on_every_os(os_info: OsInfo) -> None:
    ex = Scripted(answers={("herdr", "plugin", "config-dir"): Result(0, stdout="")})
    HerdrPlugins().install(Ctx(os=os_info, ex=ex))
    installs = [c for c in ex.calls if c[:3] == ["herdr", "plugin", "install"]]
    assert installs == [
        ["herdr", "plugin", "install", source, "--ref", ref, "--yes"]
        for _pid, source, ref in _PLUGINS
    ]
    # Only the herdr CLI (and pass for the notify secret): no package manager, no sudo.
    assert {c[0] for c in ex.calls} <= {"herdr", "pass"}


def _cli_plan(os_info: OsInfo) -> dict[str, str | None]:
    modules = load()
    order = toposort(["herdr", "herdr-plugins"], modules)
    plan = build_plan(order, modules, os_info, gpu_marker=Path("/nonexistent/gpu-vendor"))
    return {p.name: p.skip_reason for p in plan}


def test_omarchy_plugins_use_omarchys_own_herdr() -> None:
    plan = _cli_plan(OMARCHY)
    assert plan["herdr"] == "provided-by-omarchy"
    assert plan["herdr-plugins"] is None


@pytest.mark.parametrize("os_info", [FEDORA, UBUNTU, ARCH, MAC], ids=lambda o: o.distro)
def test_plugins_and_their_herdr_are_planned_everywhere_else(os_info: OsInfo) -> None:
    plan = _cli_plan(os_info)
    assert plan["herdr"] is None
    assert plan["herdr-plugins"] is None
    if os_info.family == "macos":
        # herdr-plugins requires xcode-clt (I1): `herdr plugin install` runs `git`
        # internally, which would otherwise hit the CLT stub dialog on a fresh Mac.
        assert plan["xcode-clt"] is None
    else:
        assert set(plan) == {"herdr", "herdr-plugins"}  # xcode-clt is macOS-only
