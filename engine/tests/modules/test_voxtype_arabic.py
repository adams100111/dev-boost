from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from devboost.core.errors import InstallError, NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load
from devboost.core.settings import settings
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.modules import voxtype as vox
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
FAKE_MODEL = b"lmgg fake large-v3-turbo"


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")
    monkeypatch.setattr(vox, "APP_BUNDLE", tmp_path / "Applications" / "Voxtype.app")  # M5-D7
    monkeypatch.setattr(vox, "MODEL_SHA256",
                        {vox.ARABIC_MODEL: hashlib.sha256(FAKE_MODEL).hexdigest()})


@dataclass
class ModelEx(RuleExecutor):
    """`voxtype setup --download` leaves the model file where voxtype keeps it."""

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
        if list(argv[:3]) == ["voxtype", "setup", "--download"] and res.ok:
            path = vox.model_file(argv[argv.index("--model") + 1])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(FAKE_MODEL)
        return res


def test_needs_voxtype_first() -> None:
    ex = ModelEx()
    with pytest.raises(NeedsUser):
        vox.VoxtypeArabic().install(Ctx(os=FEDORA, ex=ex))
    assert ex.calls == []
    assert not vox.arabic_marker().exists()


def test_macos_install_downloads_marks_reapplies_and_restarts(tmp_path: Path) -> None:
    ex = ModelEx(present={"voxtype", "aerospace"})
    vox.VoxtypeArabic().install(Ctx(os=MAC, ex=ex))
    assert vox.arabic_marker().is_file()
    assert ex.calls == [
        ["voxtype", "setup", "--download", "--model", "large-v3-turbo", "--quiet"],
        ["chezmoi", "apply", "--force", "--parent-dirs",
         "--source", str(settings.root / "dotfiles"),
         "--destination", str(tmp_path),
         str(tmp_path / ".config" / "voxtype" / "config.toml"),
         str(tmp_path / ".config" / "aerospace" / "aerospace.toml")],
        ["osascript", "-e", 'tell application id "io.voxtype.daemon" to quit'],
        ["open", "-g", "-b", "io.voxtype.daemon"],
        ["aerospace", "reload-config"],
    ]


def test_macos_without_aerospace_skips_its_reload() -> None:
    ex = ModelEx(present={"voxtype"})
    vox.VoxtypeArabic().install(Ctx(os=MAC, ex=ex))
    assert ex.calls[-1] == ["open", "-g", "-b", "io.voxtype.daemon"]


def test_linux_install_reapplies_only_the_voxtype_config(tmp_path: Path) -> None:
    ex = ModelEx(present={"voxtype"})
    vox.VoxtypeArabic().install(Ctx(os=FEDORA, ex=ex))
    apply = next(c for c in ex.calls if c[:2] == ["chezmoi", "apply"])
    assert apply[-1] == str(tmp_path / ".config" / "voxtype" / "config.toml")
    assert not any("aerospace" in part for part in apply)
    assert ex.calls[-1] == ["systemctl", "--user", "restart", "voxtype.service"]


def test_a_bad_model_download_leaves_no_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    # The marker switches the rendered config to the Arabic model: never before it is on
    # disk and verified, or the daemon would point at a model that is not there.
    monkeypatch.setattr(vox, "MODEL_SHA256", {vox.ARABIC_MODEL: "0" * 64})
    ex = ModelEx(present={"voxtype"})
    with pytest.raises(InstallError, match="sha256"):
        vox.VoxtypeArabic().install(Ctx(os=FEDORA, ex=ex))
    assert not vox.arabic_marker().exists()
    assert not [c for c in ex.calls if c[0] in {"chezmoi", "systemctl"}]


def test_a_failed_apply_is_an_install_error() -> None:
    ex = ModelEx(present={"voxtype"}, rules=[(("chezmoi", "apply"), Result(1))])
    with pytest.raises(InstallError, match="chezmoi"):
        vox.VoxtypeArabic().install(Ctx(os=FEDORA, ex=ex))
    assert not [c for c in ex.calls if c[0] == "systemctl"]


def test_verify_reads_marker_model_and_rendered_config(tmp_path: Path) -> None:
    ctx = Ctx(os=MAC, ex=ModelEx())
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
