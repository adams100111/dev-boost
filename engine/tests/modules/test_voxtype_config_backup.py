"""The dotfiles apply keeps a user's own Voxtype config (spec: never clobber silently)."""

from __future__ import annotations

from pathlib import Path

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules.shell import Dotfiles
from tests.modules.voxtype_fakes import VoxtypeExecutor

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
OMARCHY = OsInfo("omarchy", "arch", "x86_64", id_like=("arch",))
CFG = ".config/voxtype/config.toml"
RENDERED = "# devboost — managed by chezmoi (dotfiles/dot_config/voxtype/config.toml.tmpl)\n"


def _apply_ex() -> VoxtypeExecutor:
    """`chezmoi apply` writes dev-boost's rendering of the config into HOME."""
    return VoxtypeExecutor(rendered=RENDERED)


def test_the_config_is_taken_over_everywhere_but_omarchy() -> None:
    for os_info in (MAC, FEDORA):
        taken = Dotfiles._taken_over_for(Ctx(os=os_info, ex=FakeExecutor()))
        assert taken is not None and CFG in taken
    assert Dotfiles._taken_over_for(Ctx(os=OMARCHY, ex=FakeExecutor())) is None


def test_a_users_own_config_is_backed_up_once_then_tracked(tmp_path: Path) -> None:
    cfg = tmp_path / CFG
    cfg.parent.mkdir(parents=True)
    cfg.write_text('[hotkey]\nkey = "F13"\n', encoding="utf-8")
    ex = _apply_ex()
    for _ in range(3):  # later runs see what dev-boost last wrote: no new copy
        Dotfiles().install(Ctx(os=FEDORA, ex=ex, force=True))
    assert sorted(p.name for p in cfg.parent.glob("config.toml.pre-devboost*")) == [
        "config.toml.pre-devboost"
    ]
    assert (cfg.parent / "config.toml.pre-devboost").read_text(encoding="utf-8") == (
        '[hotkey]\nkey = "F13"\n'
    )


def test_an_edit_after_devboost_wrote_it_is_backed_up_again(tmp_path: Path) -> None:
    ex = _apply_ex()
    Dotfiles().install(Ctx(os=MAC, ex=ex, force=True))  # dev-boost's own, recorded
    cfg = tmp_path / CFG
    assert not list(cfg.parent.glob("*.pre-devboost*"))
    cfg.write_text(RENDERED + 'model = "medium.en"\n', encoding="utf-8")  # user drift
    Dotfiles().install(Ctx(os=MAC, ex=ex, force=True))
    assert [p.name for p in cfg.parent.glob("*.pre-devboost*")] == ["config.toml.pre-devboost"]
