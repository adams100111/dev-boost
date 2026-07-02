from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.base import Chezmoi
from devboost.modules.cli_tools import Atuin, Direnv, Zoxide
from devboost.modules.shell import (
    BashConfig,
    ClaudeStatusline,
    Dotfiles,
    Ghostty,
    NerdFonts,
    Starship,
    Wezterm,
)

FEDORA = OsInfo("fedora", "fedora", "x86_64")
UBUNTU = OsInfo("ubuntu", "debian", "x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_starship_installs() -> None:
    ctx = _ctx()
    Starship().install(ctx)
    assert ["sudo", "dnf", "install", "-y", "starship"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_starship_installs_via_official_script_on_ubuntu() -> None:
    """Not in Ubuntu apt — use the official install.sh into ~/.local/bin, no apt."""
    ctx = Ctx(os=UBUNTU, ex=FakeExecutor())  # type: ignore[arg-type]
    Starship().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    joined = [" ".join(c) for c in calls]
    assert any("starship.rs/install.sh" in j and ".local/bin" in j for j in joined)
    assert not any("apt-get" in j for j in joined)


def test_ghostty_is_gui_and_uses_copr() -> None:
    assert Ghostty.gui is True
    ctx = _ctx()
    Ghostty().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "dnf", "copr", "enable", "-y", "scottames/ghostty"] in calls
    assert ["sudo", "dnf", "install", "-y", "ghostty"] in calls


def test_ghostty_is_now_optional() -> None:
    """WezTerm is the default terminal; Ghostty stays registered but off-profile."""
    assert Ghostty.profiles == ()


def test_wezterm_is_default_terminal_and_installs_nightly_appimage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert Wezterm.gui is True
    assert "shell" in Wezterm.profiles
    ctx = _ctx()
    Wezterm().install(ctx)
    joined = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert any("WezTerm-nightly" in j and "AppImage" in j for j in joined)


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


def test_dotfiles_verify_reflects_chezmoi_sync_state() -> None:
    """Dotfiles must re-apply when the source drifts from the destination (e.g. after a
    config update) rather than skip forever once run — so verify uses `chezmoi verify`
    (exit 0 = in sync → skip; non-zero = drift → re-apply)."""
    assert Dotfiles().verify(_ctx(scripts={"chezmoi": Result(0)})) is True
    assert Dotfiles().verify(_ctx(scripts={"chezmoi": Result(1)})) is False


def test_claude_statusline_merges_preserving_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    monkeypatch.setenv("HOME", str(tmp_path))
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"model": "opus", "permissions": {"x": 1}}), encoding="utf-8")

    ctx = _ctx()
    assert ClaudeStatusline().verify(ctx) is False
    ClaudeStatusline().install(ctx)

    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["model"] == "opus"  # existing settings preserved
    assert data["permissions"] == {"x": 1}
    assert data["statusLine"]["command"] == str(tmp_path / ".claude" / "statusline.sh")
    assert data["statusLine"]["type"] == "command"
    assert ClaudeStatusline().verify(ctx) is True


def test_claude_statusline_creates_settings_when_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = _ctx()
    ClaudeStatusline().install(ctx)
    data = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert data["statusLine"]["command"].endswith("/.claude/statusline.sh")


def test_claude_statusline_leaves_invalid_json_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{ not valid json ", encoding="utf-8")
    ctx = _ctx()
    ClaudeStatusline().install(ctx)
    assert settings.read_text(encoding="utf-8") == "{ not valid json "  # untouched


def test_bash_config_verify(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = _ctx()
    assert BashConfig().verify(ctx) is False
    (tmp_path / ".bashrc").write_text(
        "eval \"$(starship init bash)\"  # devboost\n", encoding="utf-8"
    )
    assert BashConfig().verify(ctx) is True
