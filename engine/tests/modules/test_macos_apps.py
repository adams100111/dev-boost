from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from devboost.core.errors import NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.registry import load
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx, TccGrant
from devboost.modules import _cask
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
        self,
        present: set[str] | None = None,
        auto_updates: set[str] | None = None,
        defaults: dict[str, bool] | None = None,
    ) -> None:
        super().__init__()
        self.present: set[str] = set(present) if present else set()
        self.auto_updates: set[str] = set(auto_updates) if auto_updates else set()
        #: Keys already in the defaults domain, as `defaults read-type` would see them.
        self.defaults: dict[str, bool] = dict(defaults) if defaults else {}

    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        interactive: bool = False,
        timeout: float | None = None,
    ) -> Result:
        super().run(
            argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive, timeout=timeout
        )
        a = list(argv)
        if a[:2] == ["brew", "list"] and "--cask" in a:
            # Real brew 7.0.4 (cmd/list.rb): a named cask is listed only when
            # Caskroom/<name> exists, and that dir is the bare token — so a tap-qualified
            # name is never "installed", whatever is on disk.
            return Result(0) if a[-1] in self.present else Result(1)
        if a[:3] == ["brew", "install", "--cask"]:
            self.present.add(a[-1].rsplit("/", 1)[-1])  # Caskroom/<token>
            return Result(0)
        if a[:2] == ["brew", "info"]:
            cask = a[-1]
            body = {"casks": [{"token": cask, "auto_updates": cask in self.auto_updates}]}
            return Result(0, stdout=json.dumps(body))
        # `defaults` against a domain: absent keys must FAIL read-type, the way the real
        # tool does — a blanket Result(0) would make every key look already-set.
        if a[:2] == ["defaults", "read-type"]:
            return Result(0, stdout="Type is boolean\n") if a[3] in self.defaults else Result(1)
        if a[:2] == ["defaults", "read"]:
            if a[2] not in ("eu.exelban.Stats",) or a[3] not in self.defaults:
                return Result(1)
            return Result(0, stdout="1\n" if self.defaults[a[3]] else "0\n")
        if a[:2] == ["defaults", "write"]:
            self.defaults[a[3]] = a[-1] in ("1", "true", "YES", "-bool")
            return Result(0)
        return Result(0)


@pytest.fixture
def interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    """A human is at the terminal: `open`/`qlmanage -r` may run (ddev/ios/server precedent)."""
    monkeypatch.setattr(_cask, "is_interactive", lambda: True)
    monkeypatch.setattr(apps, "is_interactive", lambda: True)


@pytest.fixture
def unattended(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nobody is watching: no dialog-popping `open`/`qlmanage -r` may run."""
    monkeypatch.setattr(_cask, "is_interactive", lambda: False)
    monkeypatch.setattr(apps, "is_interactive", lambda: False)


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


@pytest.mark.usefixtures("interactive")
def test_tapped_cask_installs_qualified_and_verifies_by_token() -> None:
    """C2: `nikitabobko/tap/aerospace` installs (and trusts) by its qualified name, but
    `brew list --cask --versions nikitabobko/tap/aerospace` always exits 1 on Homebrew
    7.0.4, so presence is probed with the bare token `aerospace`."""
    ex = _Brew()
    ctx = Ctx(os=MAC, ex=ex)
    apps.Aerospace().install(ctx)
    assert ex.calls == [
        ["brew", "list", "--cask", "--versions", "aerospace"],
        ["brew", "trust", "--cask", "nikitabobko/tap/aerospace"],
        ["brew", "install", "--cask", "-y", "--adopt", "nikitabobko/tap/aerospace"],
        ["open", "-g", "-a", "AeroSpace"],
    ]
    ex.calls.clear()
    assert apps.Aerospace().verify(ctx) is True
    assert ex.calls == [["brew", "list", "--cask", "--versions", "aerospace"]]


@pytest.mark.usefixtures("interactive")
def test_installed_tapped_cask_is_not_reinstalled_or_reopened() -> None:
    """C2 regression: once installed, a re-run (plain or --update) neither re-trusts nor
    re-opens AeroSpace, and its post-install verify passes. (A plain re-run's `brew
    install --cask` of an installed cask is brew's own no-op, BrewCask's design.)"""
    ex = _Brew(present={"aerospace"}, auto_updates={"nikitabobko/tap/aerospace"})
    for force in (False, True):
        apps.Aerospace().install(Ctx(os=MAC, ex=ex, force=force))
    assert not [c for c in ex.calls if c[:2] == ["brew", "trust"]]
    assert not [c for c in ex.calls if c[:2] == ["brew", "upgrade"]]  # auto_updates
    assert not [c for c in ex.calls if c[0] == "open"]
    assert apps.Aerospace().verify(Ctx(os=MAC, ex=ex)) is True


def test_app_without_launch_is_not_opened() -> None:
    ex = _Brew()
    apps.Keka().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [
        ["brew", "list", "--cask", "--versions", "keka"],
        ["brew", "install", "--cask", "-y", "--adopt", "keka"],
    ]


@pytest.mark.usefixtures("interactive")
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


@pytest.mark.usefixtures("interactive")
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


@pytest.mark.usefixtures("interactive")
def test_quicklook_install_twice_with_force_registers_extensions_only_once() -> None:
    ex = _Brew()
    ctx = Ctx(os=MAC, ex=ex, force=True)
    apps.Quicklook().install(ctx)
    ex.calls.clear()
    apps.Quicklook().install(ctx)  # already present -> upgrade path, no reopen/re-register
    assert [c for c in ex.calls if c[:1] == ["open"]] == []
    assert [c for c in ex.calls if c == ["qlmanage", "-r"]] == []


@pytest.mark.usefixtures("unattended")
def test_unattended_fresh_install_of_a_tcc_app_raises_needs_user_and_never_opens() -> None:
    """Raycast needs Accessibility. Unattended, opening it would pop a TCC dialog nobody
    can answer — global constraint — so the install is reported `blocked` instead."""
    ex = _Brew()
    with pytest.raises(NeedsUser) as exc_info:
        apps.Raycast().install(Ctx(os=MAC, ex=ex))
    assert [c for c in ex.calls if c[:1] == ["open"]] == []
    assert ["brew", "install", "--cask", "-y", "--adopt", "raycast"] in ex.calls  # still installed
    assert "Raycast once" in exc_info.value.how_to_fix
    assert "devboost permissions --confirm raycast" in exc_info.value.how_to_fix


class _Quiet(CaskApp):
    """A cask with `launch` but no `tcc` and no `launch_unattended` — the default shape."""

    name = "quiet-app"
    cask = "quiet-app"
    launch = "QuietApp"


@pytest.mark.usefixtures("unattended")
def test_unattended_fresh_install_without_tcc_just_skips_the_launch() -> None:
    """No `tcc` means nothing only a human can unblock, so the install is clean — but the
    app is still not opened on an unattended run unless it asks to be."""
    ex = _Brew()
    _Quiet().install(Ctx(os=MAC, ex=ex))  # must not raise
    assert [c for c in ex.calls if c[:1] == ["open"]] == []
    assert ["brew", "install", "--cask", "-y", "--adopt", "quiet-app"] in ex.calls


@pytest.mark.usefixtures("unattended")
def test_stats_starts_unattended_so_the_menu_bar_is_not_empty() -> None:
    """A monitor nobody started monitors nothing: Stats opts into `launch_unattended`, so
    a `curl | bash` Mac gets its readouts without a second, manual step."""
    ex = _Brew()
    apps.Stats().install(Ctx(os=MAC, ex=ex))  # must not raise
    assert [c for c in ex.calls if c[:1] == ["open"]] == [["open", "-g", "-a", "Stats"]]


@pytest.mark.usefixtures("unattended")
def test_stats_seeds_disk_ram_cpu_gpu_before_it_launches() -> None:
    """The requested menu bar: disk, RAM, CPU, GPU and nothing else. Every readout is
    written explicitly, and all of them before the app starts — Stats caches its domain at
    startup, so a write to a running Stats is ignored and then overwritten."""
    ex = _Brew()
    apps.Stats().install(Ctx(os=MAC, ex=ex))

    wrote = {c[3]: c[-1] for c in ex.calls if c[:2] == ["defaults", "write"]}
    assert wrote == {
        "CPU_state": "true",
        "RAM_state": "true",
        "Disk_state": "true",
        "GPU_state": "true",
        "Network_state": "false",
        "Battery_state": "false",
        "Sensors_state": "false",
        "Bluetooth_state": "false",
        "Clock_state": "false",
        "Remote_state": "false",
    }
    last_write = max(i for i, c in enumerate(ex.calls) if c[:2] == ["defaults", "write"])
    opened = next(i for i, c in enumerate(ex.calls) if c[:1] == ["open"])
    assert last_write < opened, "every readout must be seeded before Stats starts"


@pytest.mark.usefixtures("unattended")
def test_stats_never_overwrites_a_readout_the_user_already_chose() -> None:
    """Once someone toggles a readout in Stats' own UI the key exists. dev-boost seeds
    only absent keys, so a later run never undoes that choice."""
    ex = _Brew(defaults={"Network_state": True, "GPU_state": False})
    apps.Stats().install(Ctx(os=MAC, ex=ex))

    wrote = {c[3] for c in ex.calls if c[:2] == ["defaults", "write"]}
    assert "Network_state" not in wrote
    assert "GPU_state" not in wrote
    assert "CPU_state" in wrote  # the untouched ones are still seeded


@pytest.mark.usefixtures("interactive")
def test_interactive_fresh_install_of_a_tcc_app_opens_once() -> None:
    ex = _Brew()
    apps.Raycast().install(Ctx(os=MAC, ex=ex))  # must not raise
    assert [c for c in ex.calls if c[:1] == ["open"]] == [["open", "-g", "-a", "Raycast"]]


@pytest.mark.usefixtures("unattended")
def test_quicklook_unattended_skips_open_and_qlmanage() -> None:
    ex = _Brew()
    apps.Quicklook().install(Ctx(os=MAC, ex=ex))
    assert [c for c in ex.calls if c[:1] == ["open"]] == []
    assert ["qlmanage", "-r"] not in ex.calls
    assert ["brew", "install", "--cask", "-y", "--adopt", "qlmarkdown"] in ex.calls


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
