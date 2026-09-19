from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from devboost.core.errors import InstallError, NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load
from devboost.core.settings import settings
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.modules import _credentials
from devboost.modules import voxtype as vox
from tests.modules.voxtype_fakes import VoxtypeExecutor, fake_model

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")
    monkeypatch.setattr(vox, "MODEL_SHA256", {
        vox.ARABIC_MODEL: hashlib.sha256(fake_model(vox.ARABIC_MODEL)).hexdigest()
    })
    # The pinned macOS binary is in place unless a test says otherwise.
    vox.bin_path().parent.mkdir(parents=True, exist_ok=True)
    vox.bin_path().touch()


@pytest.fixture
def attended(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_credentials, "is_interactive", lambda: True)


def test_needs_voxtype_first() -> None:
    ex = VoxtypeExecutor()
    with pytest.raises(NeedsUser):
        vox.VoxtypeArabic().install(Ctx(os=FEDORA, ex=ex))
    assert ex.calls == []
    assert not vox.arabic_marker().exists()


@pytest.mark.usefixtures("attended")
def test_macos_install_downloads_marks_reapplies_and_restarts(tmp_path: Path) -> None:
    ex = VoxtypeExecutor(present={"voxtype", "aerospace"})
    vox.VoxtypeArabic().install(Ctx(os=MAC, ex=ex))
    assert vox.arabic_marker().is_file()
    assert ex.calls == [
        [str(vox.bin_path()), "setup", "--download", "--model", "large-v3-turbo", "--quiet"],
        ["chezmoi", "apply", "--force", "--parent-dirs",
         "--source", str(settings.root / "dotfiles"),
         "--destination", str(tmp_path),
         str(tmp_path / ".config" / "voxtype" / "config.toml"),
         str(tmp_path / ".config" / "aerospace" / "aerospace.toml")],
        ["aerospace", "reload-config"],
        ["osascript", "-e", 'tell application id "io.voxtype.daemon" to quit'],
        ["open", "-g", "-b", "io.voxtype.daemon"],
    ]
    assert vox.VoxtypeArabic().verify(Ctx(os=MAC, ex=ex)) is True


@pytest.mark.usefixtures("attended")
def test_macos_without_aerospace_skips_its_reload() -> None:
    ex = VoxtypeExecutor(present={"voxtype"})
    vox.VoxtypeArabic().install(Ctx(os=MAC, ex=ex))
    assert not [c for c in ex.calls if c[0] == "aerospace"]
    assert ex.calls[-1] == ["open", "-g", "-b", "io.voxtype.daemon"]


def test_macos_needs_the_pinned_binary_not_any_voxtype_on_path() -> None:
    vox.bin_path().unlink()  # only a leftover brew 0.7.5 answers `which`
    ex = VoxtypeExecutor(present={"voxtype"})
    with pytest.raises(NeedsUser, match="not installed"):
        vox.VoxtypeArabic().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == []


def test_unattended_macos_never_relaunches_and_leaves_verify_drifted() -> None:
    ex = VoxtypeExecutor(present={"voxtype", "aerospace"})
    ctx = Ctx(os=MAC, ex=ex)
    with pytest.raises(NeedsUser, match="restart"):
        vox.VoxtypeArabic().install(ctx)
    assert not [c for c in ex.calls if c[0] in {"osascript", "open"}]
    assert ["aerospace", "reload-config"] in ex.calls  # a config reload opens nothing
    assert vox.VoxtypeArabic().verify(ctx) is False  # the next run applies the restart


def test_the_next_attended_run_restarts_and_clears_the_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ex = VoxtypeExecutor(present={"voxtype"})
    ctx = Ctx(os=MAC, ex=ex)
    with pytest.raises(NeedsUser):
        vox.VoxtypeArabic().install(ctx)
    monkeypatch.setattr(_credentials, "is_interactive", lambda: True)
    vox.VoxtypeArabic().install(ctx)
    assert ex.calls[-1] == ["open", "-g", "-b", "io.voxtype.daemon"]
    assert vox.VoxtypeArabic().verify(ctx) is True


@pytest.mark.usefixtures("attended")
@pytest.mark.parametrize("fails", ["osascript", "open"])
def test_a_failed_macos_restart_warns_and_needs_the_user(fails: str) -> None:
    ex = VoxtypeExecutor(present={"voxtype"}, rules=[((fails,), Result(1, "", "boom"))])
    ctx = Ctx(os=MAC, ex=ex)
    with pytest.raises(NeedsUser, match="did not restart"):
        vox.VoxtypeArabic().install(ctx)
    assert ["open", "-g", "-b", "io.voxtype.daemon"] in ex.calls  # both steps were tried
    assert vox.VoxtypeArabic().verify(ctx) is False


def test_linux_install_reapplies_only_the_voxtype_config(tmp_path: Path) -> None:
    ex = VoxtypeExecutor(present={"voxtype"})
    vox.VoxtypeArabic().install(Ctx(os=FEDORA, ex=ex))
    apply = next(c for c in ex.calls if c[:2] == ["chezmoi", "apply"])
    assert apply[-1] == str(tmp_path / ".config" / "voxtype" / "config.toml")
    assert not any("aerospace" in part for part in apply)
    assert ex.calls[-1] == ["systemctl", "--user", "restart", "voxtype.service"]
    assert vox.VoxtypeArabic().verify(Ctx(os=FEDORA, ex=ex)) is True


def test_a_failed_linux_restart_needs_the_user() -> None:
    ex = VoxtypeExecutor(present={"voxtype"}, rules=[(("systemctl",), Result(1))])
    with pytest.raises(NeedsUser, match="did not restart"):
        vox.VoxtypeArabic().install(Ctx(os=FEDORA, ex=ex))


def test_a_drifted_user_config_is_backed_up_once(tmp_path: Path) -> None:
    cfg = tmp_path / ".config" / "voxtype" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('[hotkey]\nkey = "F13"\n', encoding="utf-8")  # the user's own
    ex = VoxtypeExecutor(present={"voxtype"})
    for _ in range(2):
        vox.VoxtypeArabic().install(Ctx(os=FEDORA, ex=ex, force=True))
    backups = sorted(p.name for p in cfg.parent.iterdir() if "pre-devboost" in p.name)
    assert backups == ["config.toml.pre-devboost"]
    assert (cfg.parent / backups[0]).read_text(encoding="utf-8") == '[hotkey]\nkey = "F13"\n'


def test_omarchy_config_is_never_rewritten(tmp_path: Path) -> None:
    omarchy = OsInfo("omarchy", "arch", "x86_64", id_like=("arch",))
    cfg = tmp_path / ".config" / "voxtype" / "config.toml"
    cfg.parent.mkdir(parents=True)
    own = '[hotkey]\nenabled = false\n[whisper]\nmodel = "base.en"\n'
    cfg.write_text(own, encoding="utf-8")
    ex = VoxtypeExecutor(present={"voxtype"})
    with pytest.raises(NeedsUser, match="Omarchy manages"):
        vox.VoxtypeArabic().install(Ctx(os=omarchy, ex=ex))
    assert cfg.read_text(encoding="utf-8") == own
    assert not [c for c in ex.calls if c[0] in {"chezmoi", "systemctl"}]
    assert not list(cfg.parent.glob("*.pre-devboost*"))
    # Once the user has added the key, the install completes and verify passes.
    cfg.write_text(own + 'secondary_model = "large-v3-turbo"\n', encoding="utf-8")
    vox.VoxtypeArabic().install(Ctx(os=omarchy, ex=ex))
    assert vox.VoxtypeArabic().verify(Ctx(os=omarchy, ex=ex)) is True


def test_a_bad_model_download_leaves_no_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    # The marker switches the rendered config to the Arabic model: never before it is on
    # disk and verified, or the daemon would point at a model that is not there.
    monkeypatch.setattr(vox, "MODEL_SHA256", {vox.ARABIC_MODEL: "0" * 64})
    ex = VoxtypeExecutor(present={"voxtype"})
    with pytest.raises(InstallError, match="sha256"):
        vox.VoxtypeArabic().install(Ctx(os=FEDORA, ex=ex))
    assert not vox.arabic_marker().exists()
    assert not [c for c in ex.calls if c[0] in {"chezmoi", "systemctl"}]


def test_a_failed_apply_is_an_install_error() -> None:
    ex = VoxtypeExecutor(present={"voxtype"}, rules=[(("chezmoi", "apply"), Result(1))])
    with pytest.raises(InstallError, match="chezmoi"):
        vox.VoxtypeArabic().install(Ctx(os=FEDORA, ex=ex))
    assert not [c for c in ex.calls if c[0] == "systemctl"]


def test_verify_reads_marker_model_and_rendered_config(tmp_path: Path) -> None:
    ctx = Ctx(os=MAC, ex=VoxtypeExecutor())
    assert vox.VoxtypeArabic().verify(ctx) is False
    vox.arabic_marker().parent.mkdir(parents=True)
    vox.arabic_marker().touch()
    vox.model_file("large-v3-turbo").parent.mkdir(parents=True)
    vox.model_file("large-v3-turbo").touch()
    cfg = tmp_path / ".config" / "voxtype" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('[whisper]\nmodel = "small.en"\n', encoding="utf-8")
    assert vox.VoxtypeArabic().verify(ctx) is False  # config not re-rendered yet
    cfg.write_text('[whisper]\nsecondary_model = "large-v3-turbo"\n', encoding="utf-8")
    assert vox.VoxtypeArabic().verify(ctx) is True


def test_opt_in_only() -> None:
    assert vox.VoxtypeArabic.profiles == ()
    assert [c.name for c in vox.VoxtypeArabic.requires] == ["voxtype"]
    assert vox.VoxtypeArabic.portable is True
    assert vox.VoxtypeArabic.needs_sudo_on_macos is False


def test_linux_plans_run_it_after_voxtype(tmp_path: Path) -> None:
    plan = build_plan(["voxtype", "voxtype-arabic"], load(), FEDORA, gpu_marker=tmp_path / "x")
    names = [p.name for p in plan]
    assert names.index("voxtype") < names.index("voxtype-arabic")
    assert all(p.skip_reason is None for p in plan if p.name.startswith("voxtype"))
