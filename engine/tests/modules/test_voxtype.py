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
    """What the real `voxtype` leaves behind: the model file, the app bundle, a version."""

    version: str = "1.0.1"

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
        if args[:3] == ["voxtype", "setup", "--download"] and res.ok:
            name = args[args.index("--model") + 1]
            vox.model_file(name).parent.mkdir(parents=True, exist_ok=True)
            vox.model_file(name).write_bytes(_fake_model(name))
        elif args == ["voxtype", "setup", "app-bundle"]:
            _write_bundle(self.version)
        elif args == ["voxtype", "--version"]:
            return Result(0, f"voxtype {self.version}\n")
        return res


def _scripts(ex: FakeExecutor) -> list[str]:
    return [c[2] for c in ex.calls if c[:2] == ["sh", "-c"]]


# --- models --------------------------------------------------------------------------------


def test_model_paths_follow_xdg_data_home(tmp_path: Path) -> None:
    assert vox.model_file("small.en") == (
        tmp_path / ".local" / "share" / "voxtype" / "models" / "ggml-small.en.bin"
    )


def test_model_download_is_skipped_when_present() -> None:
    vox.model_file("small.en").parent.mkdir(parents=True)
    vox.model_file("small.en").touch()
    ex = FakeExecutor()
    vox.download_model(Ctx(os=MAC, ex=ex), "small.en")
    assert ex.calls == []


def test_a_downloaded_model_must_match_its_pinned_sha256(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vox, "MODEL_SHA256", {"small.en": "0" * 64})
    with pytest.raises(InstallError, match="sha256"):
        vox.download_model(Ctx(os=MAC, ex=VoxEx()), "small.en")
    assert not vox.model_file("small.en").exists()  # the bad file is not left to "verify"


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


def test_macos_install_cask_model_then_app_bundle() -> None:
    ex = VoxEx()
    vox.Voxtype().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [
        ["brew", "install", "--cask", "-y", "--adopt", "peteonrails/voxtype/voxtype"],
        ["voxtype", "setup", "--download", "--model", "small.en", "--quiet"],
        ["voxtype", "setup", "app-bundle"],
    ]


def test_macos_verify_needs_cask_model_and_a_current_bundle() -> None:
    ctx = Ctx(os=MAC, ex=VoxEx())
    assert vox.Voxtype().verify(ctx) is False
    vox.model_file("small.en").parent.mkdir(parents=True)
    vox.model_file("small.en").touch()
    _write_bundle("0.9.0")  # a copy of the binary from before `brew upgrade`
    assert vox.Voxtype().verify(ctx) is False
    _write_bundle("1.0.1")
    assert vox.Voxtype().verify(ctx) is True


def test_macos_verify_is_false_without_the_cask() -> None:
    _write_bundle("1.0.1")
    vox.model_file("small.en").parent.mkdir(parents=True)
    vox.model_file("small.en").touch()
    ex = VoxEx(rules=[(("list", "--cask"), Result(1))])
    assert vox.Voxtype().verify(Ctx(os=MAC, ex=ex)) is False


def test_macos_force_twice_has_no_duplicate_side_effects() -> None:
    """M5-D6: `setup app-bundle` copies the binary, resets the TCC grants, adds the Login
    Item and launches the app, so a forced re-run must not repeat it for a current bundle."""
    ex = VoxEx()
    vox.Voxtype().install(Ctx(os=MAC, ex=ex))
    for _ in range(2):
        vox.Voxtype().install(Ctx(os=MAC, ex=ex, force=True))
    assert ex.calls.count(["voxtype", "setup", "app-bundle"]) == 1
    assert sum(c[:3] == ["voxtype", "setup", "--download"] for c in ex.calls) == 1
    assert ex.calls.count(["brew", "upgrade", "--cask", vox.CASK]) == 2
    assert sum(c[:3] == ["brew", "install", "--cask"] for c in ex.calls) == 1
    assert not [c for c in ex.calls if c[0] in {"open", "osascript", "sudo"}]


def test_macos_force_rebuilds_a_stale_bundle() -> None:
    _write_bundle("0.9.0")
    vox.model_file("small.en").parent.mkdir(parents=True)
    vox.model_file("small.en").touch()
    ex = VoxEx()
    vox.Voxtype().install(Ctx(os=MAC, ex=ex, force=True))
    assert ex.calls[-1] == ["voxtype", "setup", "app-bundle"]


def test_macos_app_bundle_failure_is_an_install_error() -> None:
    ex = VoxEx(rules=[(("app-bundle",), Result(1))])
    with pytest.raises(InstallError, match="app-bundle"):
        vox.Voxtype().install(Ctx(os=MAC, ex=ex))


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
    binary = next(c for c in ex.calls if c[:2] == ["install", "-Dm755"])
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
    assert vox.MacosVoxtype.uses_brew is True
    assert vox.Voxtype.needs_sudo_on_macos is False  # M5-D5
