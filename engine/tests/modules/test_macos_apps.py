from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx, TccGrant
from devboost.modules import macos_apps as apps
from devboost.modules._cask import CaskApp, CaskInstall

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
MAC15 = OsInfo("macos", "macos", "aarch64", version_id="15.6")
FEDORA = OsInfo("fedora", "fedora", "x86_64")

DESKTOP = {
    # module: (cask, launch, TCC services)
    "stats": ("stats", "Stats", ()),
    "raycast": ("raycast", "Raycast", ("Accessibility",)),
    "aerospace": ("nikitabobko/tap/aerospace", "AeroSpace", ("Accessibility",)),
    "alt-tab": ("alt-tab", "AltTab", ("Accessibility", "ScreenCapture")),
    "thaw": ("thaw", "Thaw", ("Accessibility", "ScreenCapture")),
    "monitorcontrol": ("monitorcontrol", "MonitorControl", ("Accessibility",)),
    "keka": ("keka", None, ()),
}


class _Brew(FakeExecutor):
    """Models real `brew`: `list`/`info` answer from tracked install state, and
    `install --cask` (and `upgrade --cask`) update it — so a strategy's verify() before
    and after install() behaves like the real tool, not FakeExecutor's blanket Result(0).
    """

    def __init__(
        self, present: set[str] | None = None, auto_updates: set[str] | None = None
    ) -> None:
        super().__init__()
        self.present: set[str] = set(present) if present else set()
        self.auto_updates: set[str] = set(auto_updates) if auto_updates else set()

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
        super().run(argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive)
        a = list(argv)
        if a[:2] == ["brew", "list"] and "--cask" in a:
            return Result(0) if a[-1] in self.present else Result(1)
        if a[:3] == ["brew", "install", "--cask"]:
            self.present.add(a[-1])
            return Result(0)
        if a[:2] == ["brew", "info"]:
            cask = a[-1]
            body = {"casks": [{"token": cask, "auto_updates": cask in self.auto_updates}]}
            return Result(0, stdout=json.dumps(body))
        return Result(0)


def test_desktop_cask_table() -> None:
    mods = load()
    for name, (cask, launch, services) in DESKTOP.items():
        cls = mods[name]
        assert issubclass(cls, CaskApp), name
        assert cls.per_os.macos == CaskInstall(cask, launch), name
        assert tuple(g.service for g in cls.tcc) == services, name
        assert cls.profiles == ("macos-desktop",), name


def test_betterdisplay_is_not_shipped() -> None:
    assert "betterdisplay" not in load()  # paid for business use (D3)


def test_tapped_cask_installs_and_verifies_fully_qualified() -> None:
    """`nikitabobko/tap/aerospace` auto-taps on install; brew resolves the same
    tap-qualified name for `list`/`info`/`upgrade` once the tap exists locally, so
    CaskInstall uses one consistent name throughout (M5-D6: wraps `_brew.BrewCask`)."""
    ex = _Brew()
    ctx = Ctx(os=MAC, ex=ex)
    apps.Aerospace().install(ctx)
    assert ex.calls == [
        ["brew", "list", "--cask", "--versions", "nikitabobko/tap/aerospace"],
        ["brew", "trust", "--cask", "nikitabobko/tap/aerospace"],
        ["brew", "install", "--cask", "-y", "--adopt", "nikitabobko/tap/aerospace"],
        ["open", "-g", "-a", "AeroSpace"],
    ]
    ex.calls.clear()
    apps.Aerospace().verify(ctx)
    assert ex.calls == [["brew", "list", "--cask", "--versions", "nikitabobko/tap/aerospace"]]


def test_app_without_launch_is_not_opened() -> None:
    ex = _Brew()
    apps.Keka().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [
        ["brew", "list", "--cask", "--versions", "keka"],
        ["brew", "install", "--cask", "-y", "--adopt", "keka"],
    ]


def test_install_twice_with_force_has_no_duplicate_side_effects() -> None:
    """M5-D6's required test: install a cask twice under `--update` (force=True). The
    second run must not re-open the app (a duplicate side effect, and a possible
    surprise TCC prompt on an unattended re-run) or re-run a plain fresh install."""
    ex = _Brew()
    ctx = Ctx(os=MAC, ex=ex, force=True)

    apps.Aerospace().install(ctx)
    opens = [c for c in ex.calls if c[:1] == ["open"]]
    assert opens == [["open", "-g", "-a", "AeroSpace"]]
    assert ["brew", "install", "--cask", "-y", "--adopt", "nikitabobko/tap/aerospace"] in ex.calls
    assert ["brew", "trust", "--cask", "nikitabobko/tap/aerospace"] in ex.calls

    ex.calls.clear()
    apps.Aerospace().install(ctx)  # second force run — cask already present
    assert [c for c in ex.calls if c[:1] == ["open"]] == []  # no re-open, no re-prompt
    assert not any(c[:3] == ["brew", "install", "--cask"] for c in ex.calls)
    assert not any(c[:2] == ["brew", "trust"] for c in ex.calls)  # already trusted
    # BrewCask's own force path: present + not auto_updates -> upgrade in place.
    assert ex.calls[-1] == ["brew", "upgrade", "--cask", "nikitabobko/tap/aerospace"]

    ex.calls.clear()
    apps.Aerospace().install(ctx)  # third run: still idempotent, still no open
    assert [c for c in ex.calls if c[:1] == ["open"]] == []


def test_aerospace_runs_after_the_dotfiles() -> None:
    assert "dotfiles" in {c.name for c in apps.Aerospace.after}


def test_thaw_is_gated_below_macos_26(tmp_path: Path) -> None:
    assert apps.Thaw.supported_on(MAC) is True
    assert apps.Thaw.supported_on(MAC15) is False
    plan = build_plan(["thaw"], load(), MAC15, gpu_marker=tmp_path / "none")
    assert plan[0].skip_reason == "unsupported-os"


def test_linux_drops_every_cask_app(tmp_path: Path) -> None:
    names = [*DESKTOP, "quicklook"]
    assert build_plan(names, load(), FEDORA, gpu_marker=tmp_path / "none") == []


def test_quicklook_installs_both_extensions_and_registers_them() -> None:
    ex = _Brew()
    apps.Quicklook().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [
        ["brew", "list", "--cask", "--versions", "qlmarkdown"],
        ["brew", "install", "--cask", "-y", "--adopt", "qlmarkdown"],
        ["open", "-g", "-a", "QLMarkdown"],
        ["brew", "list", "--cask", "--versions", "syntax-highlight"],
        ["brew", "install", "--cask", "-y", "--adopt", "syntax-highlight"],
        ["open", "-g", "-a", "Syntax Highlight"],
        ["qlmanage", "-r"],
    ]


def test_quicklook_install_twice_with_force_registers_extensions_only_once() -> None:
    ex = _Brew()
    ctx = Ctx(os=MAC, ex=ex, force=True)
    apps.Quicklook().install(ctx)
    ex.calls.clear()
    apps.Quicklook().install(ctx)  # already present -> upgrade path, no reopen/re-register
    assert [c for c in ex.calls if c[:1] == ["open"]] == []
    assert [c for c in ex.calls if c == ["qlmanage", "-r"]] == []


def test_tcc_grants_name_the_app_the_user_sees() -> None:
    assert apps.Raycast.tcc == (TccGrant("Accessibility", "Raycast"),)
    assert apps.AltTab.tcc == (
        TccGrant("Accessibility", "AltTab"),
        TccGrant("ScreenCapture", "AltTab"),
    )


@pytest.mark.parametrize("name", DESKTOP)
def test_every_desktop_app_uses_brew_and_requires_homebrew(name: str) -> None:
    mods = load()
    cls = mods[name]
    assert getattr(cls.per_os.macos, "uses_brew", False) is True
    assert cls.requires == (mods["homebrew"],)
