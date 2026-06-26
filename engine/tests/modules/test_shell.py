from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.base import Chezmoi
from devboost.modules.cli_tools import Atuin, Direnv, Zoxide
from devboost.modules.shell import BashConfig, Dotfiles, Ghostty, NerdFonts, Starship

FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_starship_installs() -> None:
    ctx = _ctx()
    Starship().install(ctx)
    assert ["sudo", "dnf", "install", "-y", "starship"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_ghostty_is_gui_and_uses_copr() -> None:
    assert Ghostty.gui is True
    ctx = _ctx()
    Ghostty().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "dnf", "copr", "enable", "-y", "scottames/ghostty"] in calls
    assert ["sudo", "dnf", "install", "-y", "ghostty"] in calls


def test_nerd_fonts_download_unzip_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = _ctx()
    NerdFonts().install(ctx)
    cmds = [c[0] for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert cmds == ["curl", "unzip", "fc-cache"]


def test_nerd_fonts_verify_reads_fc_list() -> None:
    ctx = _ctx(scripts={"fc-list": Result(0, stdout="JetBrainsMono Nerd Font:style=Regular")})
    assert NerdFonts().verify(ctx) is True


def test_dotfiles_requires_runtime_tools() -> None:
    assert {Chezmoi, Starship, Atuin, Zoxide, Direnv} <= set(Dotfiles.requires)


def test_bash_config_verify(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = _ctx()
    assert BashConfig().verify(ctx) is False
    (tmp_path / ".bashrc").write_text(
        "eval \"$(starship init bash)\"  # devboost\n", encoding="utf-8"
    )
    assert BashConfig().verify(ctx) is True
