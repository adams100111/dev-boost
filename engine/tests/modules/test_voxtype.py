from __future__ import annotations

import hashlib
import plistlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from devboost.core.errors import InstallError
from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules import voxtype as vox
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
FEDORA_ARM = OsInfo("fedora", "fedora", "aarch64")
UBUNTU = OsInfo("ubuntu", "debian", "x86_64")
ARCH = OsInfo("arch", "arch", "x86_64")
OMARCHY = OsInfo("omarchy", "arch", "x86_64", id_like=("arch",))

RPM_SHA = "be103de733f376030180ac734bb845779bf6ee963419a8e72518b5df150525bf"
#: Read at import, before the autouse fixture swaps in digests of the fakes' files.
REAL_MODEL_PINS = dict(vox.MODEL_SHA256)


def _fake_model(name: str) -> bytes:
    return f"lmgg fake {name}".encode()


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("USER", "dev")
    monkeypatch.delenv("SUDO_USER", raising=False)
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")
    # M5-D7: never the real /Applications (the conftest HOST_APP_PATHS entry is I-M5's).
    monkeypatch.setattr(vox, "APP_BUNDLE", tmp_path / "Applications" / "Voxtype.app")
    # The pinned model digests are the real Hugging Face ones; the fakes write tiny files.
    monkeypatch.setattr(vox, "MODEL_SHA256", {
        n: hashlib.sha256(_fake_model(n)).hexdigest() for n in (vox.MODEL, vox.ARABIC_MODEL)
    })


def _write_bundle(version: str) -> None:
    contents = vox.APP_BUNDLE / "Contents"
    contents.mkdir(parents=True, exist_ok=True)
    (contents / "Info.plist").write_bytes(
        plistlib.dumps({"CFBundleShortVersionString": version})
    )


@dataclass
class VoxEx(RuleExecutor):
    """What the real `voxtype` leaves behind: the model file, the app bundle, a version.

    ``installed`` models the pinned binary at ~/.local/bin/voxtype (macOS): `--version`
    fails until an `install … <bin_path>` call has put it there.
    """

    version: str = "1.0.1"
    installed: bool = False

    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        interactive: bool = False,
    ) -> Result:
        res = super().run(argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd,
                          interactive=interactive)
        args = list(argv)
        if args and args[0] == "install" and args[-1] == str(vox.bin_path()) and res.ok:
            self.installed = True
        if not args or args[0] not in {"voxtype", str(vox.bin_path())}:
            return res
        rest = args[1:]
        if rest[:2] == ["setup", "--download"] and res.ok:
            name = rest[rest.index("--model") + 1]
            _download_to(env, name)
        elif rest == ["setup", "app-bundle"]:
            _write_bundle(self.version)
        elif rest == ["--version"]:
            if args[0] == "voxtype" or self.installed:
                return Result(0, f"voxtype {self.version}\n")
            return Result(127, "", "no such file")
        return res


def _download_to(env: Mapping[str, str] | None, name: str) -> None:
    """Where voxtype writes a model: $XDG_DATA_HOME/voxtype/models (the env it was given)."""
    base = Path(env["XDG_DATA_HOME"]) if env and "XDG_DATA_HOME" in env else None
    target = (base / "voxtype" / "models" / f"ggml-{name}.bin") if base else vox.model_file(name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_fake_model(name))


def _scripts(ex: FakeExecutor) -> list[str]:
    return [c[2] for c in ex.calls if c[:2] == ["sh", "-c"]]


# --- models --------------------------------------------------------------------------------


def test_model_paths_follow_xdg_data_home(tmp_path: Path) -> None:
    assert vox.model_file("small.en") == (
        tmp_path / ".local" / "share" / "voxtype" / "models" / "ggml-small.en.bin"
    )


def test_model_download_is_skipped_when_present_and_verified() -> None:
    vox.model_file("small.en").parent.mkdir(parents=True)
    vox.model_file("small.en").write_bytes(_fake_model("small.en"))
    ex = FakeExecutor()
    vox.download_model(Ctx(os=MAC, ex=ex), "small.en")
    assert ex.calls == []


def test_a_model_on_disk_that_fails_its_hash_is_downloaded_again() -> None:
    vox.model_file("small.en").parent.mkdir(parents=True)
    vox.model_file("small.en").write_bytes(b"truncated by a Ctrl-C")
    ex = VoxEx()
    vox.download_model(Ctx(os=MAC, ex=ex), "small.en")
    assert sum(c[1:3] == ["setup", "--download"] for c in ex.calls) == 1
    assert vox.model_file("small.en").read_bytes() == _fake_model("small.en")


def test_a_model_without_a_pinned_hash_is_refused() -> None:
    ex = VoxEx()
    with pytest.raises(InstallError, match="no pinned sha256"):
        vox.download_model(Ctx(os=MAC, ex=ex), "medium.en")
    assert ex.calls == []


def test_the_model_is_renamed_into_place_only_after_its_hash_matches() -> None:
    ex = VoxEx()
    vox.download_model(Ctx(os=MAC, ex=ex), "small.en")
    staging = Path(ex.envs[-1]["XDG_DATA_HOME"])
    assert staging.parent == vox.models_dir()  # same filesystem: the rename is atomic
    assert not staging.exists()  # the private download dir is gone
    assert vox.model_file("small.en").read_bytes() == _fake_model("small.en")


def test_a_downloaded_model_must_match_its_pinned_sha256(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vox, "MODEL_SHA256", {"small.en": "0" * 64})
    with pytest.raises(InstallError, match="sha256"):
        vox.download_model(Ctx(os=MAC, ex=VoxEx()), "small.en")
    assert not vox.model_file("small.en").exists()  # never moved into place
    assert list(vox.models_dir().iterdir()) == []  # and the download dir is removed


def test_a_model_missing_after_download_fails() -> None:
    # e.g. a Voxtype that keeps its models under ~/Library/Application Support (0.7.x).
    with pytest.raises(InstallError, match="not found"):
        vox.download_model(Ctx(os=MAC, ex=FakeExecutor()), "small.en")


def test_the_real_pins_are_the_hugging_face_digests() -> None:
    assert REAL_MODEL_PINS == {
        "small.en": "c6138d6d58ecc8322097e0f987c32f1be8bb0a18532a3f88f734d1bbf9c41e5d",
        "large-v3-turbo": "1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69",
    }


# --- macOS ---------------------------------------------------------------------------------

MAC_SHA = "275df56b1e9463d8c8888d208bcfae4ed2ab4cb5aa0177dbfc6044d4b8d3ae78"


def _vt(*args: str) -> list[str]:
    return [str(vox.bin_path()), *args]


def test_macos_installs_the_verified_binary_model_then_app_bundle(tmp_path: Path) -> None:
    ex = VoxEx()
    vox.Voxtype().install(Ctx(os=MAC, ex=ex))
    script = _scripts(ex)[0]
    assert "releases/download/v1.0.1/voxtype-1.0.1-macos-universal" in script
    assert MAC_SHA in script
    assert "shasum -a 256 -c -" in script
    assert "--proto '=https'" in script
    # the quarantine flag comes off only after the checksum line has passed
    assert script.index("shasum") < script.index("xattr -d com.apple.quarantine")
    install = next(c for c in ex.calls if c[0] == "install")
    assert install[:3] == ["install", "-m", "0755"]
    assert install[-1] == str(tmp_path / ".local" / "bin" / "voxtype")
    assert not Path(install[-2]).parent.exists()  # the private download dir is gone
    assert ex.calls[-2:] == [
        _vt("setup", "--download", "--model", "small.en", "--quiet"),
        _vt("setup", "app-bundle"),
    ]
    assert vox.models_dir().is_dir()  # made first, so voxtype never falls back to ~/Library


def test_the_macos_path_never_touches_homebrew() -> None:
    ex = VoxEx()
    vox.Voxtype().install(Ctx(os=MAC, ex=ex))
    vox.Voxtype().verify(Ctx(os=MAC, ex=ex))
    assert not [c for c in ex.calls if c[0] == "brew" or "peteonrails/voxtype/voxtype" in c]
    assert not [c for c in ex.calls if c[0] == "sudo"]
    assert vox.Voxtype.requires == ()
    assert not getattr(vox.MacosVoxtype, "uses_brew", False)


def test_macos_skips_the_download_when_the_pinned_version_is_installed() -> None:
    ex = VoxEx(installed=True)
    vox.Voxtype().install(Ctx(os=MAC, ex=ex))
    assert _scripts(ex) == []


def test_macos_verify_needs_binary_model_and_a_current_bundle() -> None:
    ctx = Ctx(os=MAC, ex=VoxEx(installed=True))
    assert vox.Voxtype().verify(ctx) is False
    vox.model_file("small.en").parent.mkdir(parents=True)
    vox.model_file("small.en").touch()
    _write_bundle("0.9.0")  # a copy of an older binary
    assert vox.Voxtype().verify(ctx) is False
    _write_bundle("1.0.1")
    assert vox.Voxtype().verify(ctx) is True
    assert vox.Voxtype().verify(Ctx(os=MAC, ex=VoxEx(installed=True, version="0.7.5"))) \
        is False


def test_macos_verify_is_false_without_the_binary() -> None:
    _write_bundle("1.0.1")
    vox.model_file("small.en").parent.mkdir(parents=True)
    vox.model_file("small.en").touch()
    assert vox.Voxtype().verify(Ctx(os=MAC, ex=VoxEx())) is False


def test_macos_force_twice_has_no_duplicate_side_effects() -> None:
    """M5-D6: `setup app-bundle` copies the binary, resets the TCC grants, adds the Login
    Item and launches the app, so a forced re-run must not repeat it for a current bundle."""
    ex = VoxEx()
    vox.Voxtype().install(Ctx(os=MAC, ex=ex))
    for _ in range(2):
        vox.Voxtype().install(Ctx(os=MAC, ex=ex, force=True))
    assert ex.calls.count(_vt("setup", "app-bundle")) == 1
    assert sum(c[1:3] == ["setup", "--download"] for c in ex.calls) == 1
    assert len(_scripts(ex)) == 3  # --force re-fetches (and re-verifies) the binary
    assert not [c for c in ex.calls if c[0] in {"open", "osascript", "sudo", "brew"}]


def test_macos_force_rebuilds_a_stale_bundle() -> None:
    _write_bundle("0.9.0")
    vox.model_file("small.en").parent.mkdir(parents=True)
    vox.model_file("small.en").touch()
    ex = VoxEx(installed=True)
    vox.Voxtype().install(Ctx(os=MAC, ex=ex, force=True))
    assert ex.calls[-1] == _vt("setup", "app-bundle")


def test_macos_app_bundle_failure_is_an_install_error() -> None:
    ex = VoxEx(rules=[(("app-bundle",), Result(1))])
    with pytest.raises(InstallError, match="app-bundle"):
        vox.Voxtype().install(Ctx(os=MAC, ex=ex))


def test_macos_checksum_failure_installs_nothing() -> None:
    ex = VoxEx(rules=[(("sh", "-c"), Result(1))])
    with pytest.raises(InstallError, match="checksum"):
        vox.Voxtype().install(Ctx(os=MAC, ex=ex))
    assert not [c for c in ex.calls if c[0] == "install" or c[-1:] == ["app-bundle"]]


# --- Linux ---------------------------------------------------------------------------------


def test_fedora_installs_the_verified_rpm_deps_group_model_and_service() -> None:
    ex = VoxEx()
    vox.Voxtype().install(Ctx(os=FEDORA, ex=ex))
    script = _scripts(ex)[0]
    assert "voxtype-1.0.1-1.x86_64.rpm" in script
    assert RPM_SHA in script
    assert "sha256sum -c -" in script
    assert "--proto '=https'" in script
    assert "sudo" not in script  # root only for the package manager, never for curl
    rpm = next(c for c in ex.calls if c[:4] == ["sudo", "dnf", "install", "-y"]
               and c[-1].endswith("voxtype.rpm"))
    assert ex.calls.index(rpm) > ex.calls.index(["sh", "-c", script])
    assert ["sudo", "dnf", "install", "-y", "wtype", "wl-clipboard", "libnotify",
            "pipewire-alsa"] in ex.calls
    assert ["sudo", "usermod", "-aG", "input", "dev"] in ex.calls
    assert ex.calls[-2:] == [
        ["voxtype", "setup", "--download", "--model", "small.en", "--quiet"],
        ["voxtype", "setup", "systemd"],
    ]
    assert not Path(rpm[-1]).parent.exists()  # the download dir is cleaned up


def test_a_checksum_mismatch_installs_nothing() -> None:
    ex = VoxEx(rules=[(("sh", "-c"), Result(1))])
    with pytest.raises(InstallError, match="checksum"):
        vox.Voxtype().install(Ctx(os=FEDORA, ex=ex))
    assert ex.calls == [["sh", "-c", _scripts(ex)[0]]]


def test_ubuntu_installs_the_verified_deb() -> None:
    ex = VoxEx()
    vox.Voxtype().install(Ctx(os=UBUNTU, ex=ex))
    script = _scripts(ex)[0]
    assert "voxtype_1.0.1-1_amd64.deb" in script
    assert "2308e762f9fd2986a2052c931388b13e7e1c74f067b6be25cacbe710546c4a0e" in script
    assert any(c[:4] == ["sudo", "apt-get", "install", "-y"] and c[-1].endswith("voxtype.deb")
               for c in ex.calls)
    assert any("libnotify-bin" in c for c in ex.calls)


def test_linux_aarch64_installs_the_raw_binary(tmp_path: Path) -> None:
    ex = VoxEx()
    vox.Voxtype().install(Ctx(os=FEDORA_ARM, ex=ex))
    script = _scripts(ex)[0]
    assert "voxtype-1.0.1-linux-aarch64-cpu" in script
    binary = next(c for c in ex.calls if c[:3] == ["install", "-m", "0755"])
    assert binary[-1] == str(tmp_path / ".local" / "bin" / "voxtype")
    assert not any(c[-1].endswith(("voxtype.rpm", "voxtype.deb")) for c in ex.calls)


def test_arch_uses_the_aur_package() -> None:
    ex = VoxEx(present={"yay"})
    vox.Voxtype().install(Ctx(os=ARCH, ex=ex))
    assert ["yay", "-S", "--needed", "--noconfirm", "voxtype-bin"] in ex.calls
    assert _scripts(ex) == []


def test_usermod_is_skipped_when_already_in_the_input_group() -> None:
    ex = VoxEx(rules=[(("id", "-nG", "dev"), Result(0, "dev wheel input\n"))])
    vox.Voxtype().install(Ctx(os=FEDORA, ex=ex))
    assert not [c for c in ex.calls if "usermod" in c]


def test_the_input_group_goes_to_the_sudo_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USER", "root")
    monkeypatch.setenv("SUDO_USER", "alice")
    ex = VoxEx()
    vox.Voxtype().install(Ctx(os=FEDORA, ex=ex))
    assert ["sudo", "usermod", "-aG", "input", "alice"] in ex.calls


@pytest.mark.parametrize("user", ["root", "-oops", "a b", ""])
def test_usermod_never_runs_for_root_or_an_odd_name(
    monkeypatch: pytest.MonkeyPatch, user: str
) -> None:
    monkeypatch.setenv("USER", user)
    monkeypatch.setattr("getpass.getuser", lambda: user)
    ex = VoxEx()
    vox.Voxtype().install(Ctx(os=FEDORA, ex=ex))
    assert not [c for c in ex.calls if "usermod" in c]
    assert ex.calls[-1] == ["voxtype", "setup", "systemd"]  # the rest still runs


def test_linux_verify_needs_binary_model_and_enabled_service() -> None:
    vox.model_file("small.en").parent.mkdir(parents=True)
    vox.model_file("small.en").touch()
    ok = RuleExecutor(present={"voxtype"})
    assert vox.Voxtype().verify(Ctx(os=FEDORA, ex=ok)) is True
    off = RuleExecutor(present={"voxtype"}, rules=[(("is-enabled",), Result(1))])
    assert vox.Voxtype().verify(Ctx(os=FEDORA, ex=off)) is False


# --- plan / metadata -----------------------------------------------------------------------


def test_linux_plans_run_it(tmp_path: Path) -> None:
    # Controller note (W0 minor 8): nothing gates voxtype off Linux as unsupported-os.
    mods = load()
    for os_info in (FEDORA, UBUNTU, ARCH, MAC):
        plan = build_plan(["voxtype"], mods, os_info, gpu_marker=tmp_path / "x")
        assert plan[-1].name == "voxtype"
        assert plan[-1].skip_reason is None, os_info


def test_linux_plans_carry_no_homebrew(tmp_path: Path) -> None:
    plan = build_plan(["voxtype"], load(), FEDORA, gpu_marker=tmp_path / "x")
    assert "homebrew" not in {p.name for p in plan}


def test_omarchy_provides_it_and_headless_skips_it(tmp_path: Path) -> None:
    mods = load()
    assert build_plan(["voxtype"], mods, OMARCHY, gpu_marker=tmp_path / "x")[-1].skip_reason \
        == "provided-by-omarchy"
    headless = OsInfo("fedora", "fedora", "x86_64", headless=True)
    assert build_plan(["voxtype"], mods, headless, gpu_marker=tmp_path / "x")[-1].skip_reason \
        == "headless"


def test_permissions_and_profile() -> None:
    assert {g.service for g in vox.Voxtype.tcc} == {"Microphone", "ListenEvent", "Accessibility"}
    assert {g.app for g in vox.Voxtype.tcc} == {"Voxtype"}
    assert vox.Voxtype.profiles == ("base",)
    assert vox.Voxtype.needs_sudo_on_macos is False  # M5-D5
