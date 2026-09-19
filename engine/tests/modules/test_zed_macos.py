"""Z2: Zed on macOS — the cask, the same seeded config, and Zed as the default app."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from devboost.core import log
from devboost.core.errors import NeedsUser, PresentUnmanaged
from devboost.core.osinfo import OsInfo
from devboost.core.plan import PlannedModule, build_plan
from devboost.core.registry import load
from devboost.core.runner import run_plan
from devboost.exec.executor import Result
from devboost.exec.primitives import default_apps
from devboost.model import Ctx
from devboost.modules import _zed, editors
from devboost.modules._brew import BrewCask
from devboost.modules.cli_tools import Utiluti
from devboost.modules.editors import Zed
from devboost.modules.macos import Homebrew
from tests.scripted import Scripted

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
MAC_26_3 = OsInfo("macos", "macos", "aarch64", version_id="26.3")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
_CASK_INSTALL = ["brew", "install", "--cask", "-y", "--adopt", "zed"]


def _mac(cask_installed: bool = False) -> Scripted:
    """brew + utiluti: every extension has its own UTI; nothing opens in Zed yet."""
    answers: dict[tuple[str, ...], Result] = {
        ("brew", "list"): Result(0 if cask_installed else 1),
    }
    for row in _zed.default_app_rows():
        uti = f"test.{row.ext}"
        answers[("utiluti", "get-uti", row.ext)] = Result(0, stdout=f"{uti}\n")
        answers[("utiluti", "type", uti, "--bundle-id")] = Result(1)
    return Scripted(present={"utiluti"}, answers=answers)


def _sets(ex: Scripted) -> list[int]:
    return [i for i, c in enumerate(ex.calls) if c[:3] == ["utiluti", "type", "set"]]


def test_zed_is_managed_on_macos(tmp_path: Path) -> None:
    assert "macos" in Zed.families
    assert Zed.per_os.macos == BrewCask("zed")
    assert Homebrew in Zed.requires and Utiluti in Zed.requires
    assert build_plan(["zed"], load(), MAC, gpu_marker=tmp_path / "x") == [PlannedModule("zed")]


def test_mac_install_uses_the_cask_seeds_the_config_and_sets_default_apps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_zed, "is_interactive", lambda: True)
    ex = _mac()
    Zed().install(Ctx(os=MAC, ex=ex))
    assert _CASK_INSTALL in ex.calls
    assert _zed.settings_path().is_file() and _zed.keymap_path().is_file()
    sets = _sets(ex)
    assert len(sets) == len(_zed.default_app_rows())  # one UTI per extension here
    assert all(ex.interactives[i] for i in sets)  # the dialog needs the terminal
    assert ex.calls[sets[0]][-1] == _zed.ZED_BUNDLE_ID
    assert Zed().verify(Ctx(os=MAC, ex=Scripted())) is True


def test_unattended_run_on_27_configures_zed_and_leaves_default_apps_to_the_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")  # nobody at the terminal
    ex = _mac(cask_installed=True)
    with pytest.raises(NeedsUser, match="devboost install zed"):
        Zed().install(Ctx(os=MAC, ex=ex))
    assert _zed.settings_path().is_file()  # the config was done first
    assert _sets(ex) == []
    assert Zed().verify(Ctx(os=MAC, ex=Scripted())) is False


def test_before_26_4_no_dialog_so_no_person_is_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")
    ex = _mac(cask_installed=True)
    Zed().install(Ctx(os=MAC_26_3, ex=ex))
    assert _sets(ex)


def test_linux_zed_never_touches_brew_or_default_apps() -> None:
    ex = Scripted(answers={("mktemp", "-d"): Result(0, stdout="/tmp/z\n")})
    Zed().install(Ctx(os=FEDORA, ex=ex))
    assert not any(c[0] in ("brew", "utiluti") for c in ex.calls)


# --- R6: a hand-installed Zed.app brew cannot adopt is configured anyway ------------------


def _unadoptable(ex: Scripted) -> Scripted:
    ex.answers[tuple(_CASK_INSTALL)] = Result(
        1, stderr="Error: It seems there is already an App at '/Applications/Zed.app'."
    )
    return ex


def test_present_unmanaged_app_still_gets_config_and_default_apps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = tmp_path / "Applications" / "Zed.app"
    app.mkdir(parents=True)
    monkeypatch.setattr(editors, "_ZED_APP", app)
    monkeypatch.setattr(_zed, "is_interactive", lambda: True)
    ex = _unadoptable(_mac())
    Zed().install(Ctx(os=MAC, ex=ex))  # no PresentUnmanaged
    assert _CASK_INSTALL in ex.calls
    assert _zed.settings_path().is_file() and _zed.keymap_path().is_file()
    assert len(_sets(ex)) == len(_zed.default_app_rows())
    # brew does not list the cask, but the app bundle is there.
    assert Zed().verify(Ctx(os=MAC, ex=Scripted(scripts={"brew": Result(1)}))) is True


def test_present_unmanaged_without_the_app_bundle_is_still_reported() -> None:
    with pytest.raises(PresentUnmanaged):
        Zed().install(Ctx(os=MAC, ex=_unadoptable(_mac())))
    assert Zed().verify(Ctx(os=MAC, ex=Scripted(scripts={"brew": Result(1)}))) is False


# --- C-R17 / C-R13: --update (force) keeps Zed and repeats nothing ------------------------


def test_install_twice_with_force_repeats_no_side_effects_and_never_prompts_unattended(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")
    auto = Result(0, stdout='{"casks": [{"auto_updates": true}]}')

    def run() -> Scripted:
        ex = _mac(cask_installed=True)
        ex.answers[("brew", "info", "--json=v2", "--cask", "zed")] = auto
        with pytest.raises(NeedsUser):  # C-R13: default apps are left to a person
            Zed().install(Ctx(os=MAC, ex=ex, force=True))
        return ex

    first = run()
    settings = _zed.settings_path().read_text(encoding="utf-8")
    keymap = _zed.keymap_path().read_text(encoding="utf-8")
    second = run()
    for ex in (first, second):
        assert not any(c[:2] in (["brew", "install"], ["brew", "upgrade"]) for c in ex.calls)
        assert _sets(ex) == [] and not any(ex.interactives)  # no dialog, no prompt
    assert _zed.settings_path().read_text(encoding="utf-8") == settings
    assert _zed.keymap_path().read_text(encoding="utf-8") == keymap
    backups = [p.name for p in _zed.settings_path().parent.iterdir()]
    assert sorted(backups) == ["keymap.json", "settings.json"]
    assert not default_apps.state_path().exists()  # nothing was recorded as answered


def test_update_after_the_user_answered_asks_nothing_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_zed, "is_interactive", lambda: True)
    Zed().install(Ctx(os=MAC, ex=_mac()))
    monkeypatch.setattr(_zed, "is_interactive", lambda: False)
    ex = _mac(cask_installed=True)
    ex.answers[("brew", "info")] = Result(0, stdout='{"casks": [{"auto_updates": true}]}')
    Zed().install(Ctx(os=MAC, ex=ex, force=True))  # no NeedsUser: every type is handled
    assert not any(c[0] == "utiluti" for c in ex.calls)


# --- utiluti failures warn; a refusal names extensions ----------------------------------


def test_a_utiluti_set_failure_only_warns_and_zed_finishes_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Core review: a failed `type set` used to leave default_apps_done() False, so the
    # runner marked zed `fail` (verify-failed-after-install) and the run exited 1.
    warned: list[str] = []
    monkeypatch.setattr(log, "warn", warned.append)
    monkeypatch.setattr(_zed, "is_interactive", lambda: True)
    ex = _mac(cask_installed=True)
    ex.answers[("utiluti", "type", "set", "test.py")] = Result(1, stderr="boom")
    [result] = run_plan([PlannedModule("zed")], load(), Ctx(os=MAC, ex=ex))
    assert result.status == "ok", result
    assert any("test.py" in w and "try again" in w for w in warned)
    # The next run (a new process) retries only the failed type.
    monkeypatch.setattr(default_apps, "_deferred", {})
    assert Zed().verify(Ctx(os=MAC, ex=Scripted())) is False
    again = _mac(cask_installed=True)
    Zed().install(Ctx(os=MAC, ex=again))
    assert [again.calls[i][3] for i in _sets(again)] == ["test.py"]


def test_the_refusal_warning_names_extensions_not_utis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warned: list[str] = []
    monkeypatch.setattr(log, "warn", warned.append)
    monkeypatch.setattr(_zed, "is_interactive", lambda: True)
    Zed().install(Ctx(os=MAC, ex=_mac()))  # every read-back misses: all declined
    [msg] = [w for w in warned if "not the default app" in w]
    assert ".py" in msg and ".md" in msg
    assert "test." not in msg  # no UTI strings


def test_unattended_no_sudo_hand_installed_zed_is_kept_and_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # M3 AF2: `brew install --cask --adopt zed` needed sudo to chmod the hand-installed
    # bundle. Without sudo the adopt is skipped, and Zed still gets its config.
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")
    app = tmp_path / "Applications" / "Zed.app"
    app.mkdir(parents=True)
    monkeypatch.setattr(editors, "_ZED_APP", app)
    monkeypatch.setattr(_zed, "is_interactive", lambda: True)
    ex = _mac()
    art = [{"app": ["Zed.app"], "target": str(app)}]
    ex.answers[("brew", "info", "--json=v2", "--cask", "zed")] = Result(
        0, stdout=json.dumps({"casks": [{"artifacts": art}]})
    )
    Zed().install(Ctx(os=MAC, ex=ex, no_sudo=True))
    assert _CASK_INSTALL not in ex.calls
    assert _zed.settings_path().is_file() and _zed.keymap_path().is_file()
    assert len(_sets(ex)) == len(_zed.default_app_rows())
