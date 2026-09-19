"""I1: the AeroSpace config is taken over like the Voxtype one (backed up before the forced
apply overwrites it), and never next to a user's own ~/.aerospace.toml.

AeroSpace reads ~/.aerospace.toml or ${XDG_CONFIG_HOME}/aerospace/aerospace.toml and
reports an ambiguity when both exist (docs/guide.adoc, "Custom config location").
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from devboost.core import log
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules import _credentials
from devboost.modules import voxtype as vox
from devboost.modules.shell import Dotfiles
from tests.modules.voxtype_fakes import VoxtypeExecutor, fake_model

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
XDG = ".config/aerospace/aerospace.toml"
LEGACY = ".aerospace.toml"
RENDERED = "# devboost — managed by chezmoi (dotfiles/dot_config/aerospace/aerospace.toml.tmpl)\n"
OWN = "[mode.main.binding]\nalt-h = 'focus left'\n"


@dataclass
class ApplyEx(FakeExecutor):
    """`chezmoi apply` writes dev-boost's AeroSpace config unless HOME has the legacy one
    (the `.chezmoiignore` rule; the real template is covered in tests/dotfiles)."""

    home: Path = Path()

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
        if list(argv[:2]) == ["chezmoi", "apply"] and not (self.home / LEGACY).exists():
            (self.home / XDG).parent.mkdir(parents=True, exist_ok=True)
            (self.home / XDG).write_text(RENDERED, encoding="utf-8")
        return res


@pytest.fixture
def warns(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    got: list[str] = []
    monkeypatch.setattr(log, "warn", got.append)
    return got


def test_taken_over_on_macos_only() -> None:
    mac = Dotfiles._taken_over_for(Ctx(os=MAC, ex=FakeExecutor()))
    linux = Dotfiles._taken_over_for(Ctx(os=FEDORA, ex=FakeExecutor()))
    assert mac is not None and mac[XDG] == "dot_config/aerospace/aerospace.toml.tmpl"
    assert linux is not None and XDG not in linux  # Linux ignores it (.chezmoiignore)


def test_a_users_own_aerospace_config_is_backed_up_once(tmp_path: Path) -> None:
    cfg = tmp_path / XDG
    cfg.parent.mkdir(parents=True)
    cfg.write_text(OWN, encoding="utf-8")
    ex = ApplyEx(home=tmp_path)
    for _ in range(3):
        Dotfiles().install(Ctx(os=MAC, ex=ex, force=True))
    assert sorted(p.name for p in cfg.parent.glob("aerospace.toml.pre-devboost*")) == [
        "aerospace.toml.pre-devboost"
    ]
    assert (cfg.parent / "aerospace.toml.pre-devboost").read_text(encoding="utf-8") == OWN
    assert cfg.read_text(encoding="utf-8") == RENDERED


def test_a_legacy_config_is_left_alone_with_a_warning(
    tmp_path: Path, warns: list[str]
) -> None:
    (tmp_path / LEGACY).write_text(OWN, encoding="utf-8")
    Dotfiles().install(Ctx(os=MAC, ex=ApplyEx(home=tmp_path)))
    assert not (tmp_path / XDG).exists()
    assert (tmp_path / LEGACY).read_text(encoding="utf-8") == OWN
    assert any("~/.aerospace.toml" in w and "~/.config/aerospace/aerospace.toml" in w
               for w in warns), warns


def test_linux_never_warns_about_aerospace(tmp_path: Path, warns: list[str]) -> None:
    (tmp_path / LEGACY).write_text(OWN, encoding="utf-8")
    Dotfiles().install(Ctx(os=FEDORA, ex=ApplyEx(home=tmp_path)))
    assert not [w for w in warns if "aerospace" in w]


# --- voxtype-arabic's targeted apply --------------------------------------------------------


@pytest.fixture
def arabic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")
    monkeypatch.setattr(_credentials, "is_interactive", lambda: True)
    monkeypatch.setattr(vox, "MODEL_SHA256", {
        vox.ARABIC_MODEL: hashlib.sha256(fake_model(vox.ARABIC_MODEL)).hexdigest()
    })
    vox.bin_path().parent.mkdir(parents=True, exist_ok=True)
    vox.bin_path().touch()


def _apply(ex: VoxtypeExecutor) -> list[str]:
    return next(c for c in ex.calls if c[:2] == ["chezmoi", "apply"])


@pytest.mark.usefixtures("arabic")
def test_arabic_backs_up_a_users_own_aerospace_config(tmp_path: Path) -> None:
    cfg = tmp_path / XDG
    cfg.parent.mkdir(parents=True)
    cfg.write_text(OWN, encoding="utf-8")
    ex = VoxtypeExecutor(present={"voxtype"})
    vox.VoxtypeArabic().install(Ctx(os=MAC, ex=ex))
    assert str(cfg) in _apply(ex)
    assert (cfg.parent / "aerospace.toml.pre-devboost").read_text(encoding="utf-8") == OWN


@pytest.mark.usefixtures("arabic")
def test_arabic_never_targets_the_xdg_config_next_to_a_legacy_one(
    tmp_path: Path, warns: list[str]
) -> None:
    (tmp_path / LEGACY).write_text(OWN, encoding="utf-8")
    ex = VoxtypeExecutor(present={"voxtype"})
    vox.VoxtypeArabic().install(Ctx(os=MAC, ex=ex))
    assert not [part for part in _apply(ex) if "aerospace" in part]
    assert any("~/.aerospace.toml" in w and "~/.config/aerospace/aerospace.toml" in w
               for w in warns), warns
