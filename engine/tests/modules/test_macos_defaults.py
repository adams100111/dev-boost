from __future__ import annotations

import json

import pytest

from devboost.core.errors import InstallError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.exec.primitives.macdefaults import Value
from devboost.model import Ctx
from devboost.modules import macos_defaults as md
from tests.modules.macos_fakes import PrefsExecutor

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
DOCK = "com.apple.dock"


def _ctx(ex: PrefsExecutor) -> Ctx:
    return Ctx(os=MAC, ex=ex)


def _writes(ex: PrefsExecutor) -> list[list[str]]:
    return [c for c in ex.calls if c[:2] == ["defaults", "write"]]


def _kills(ex: PrefsExecutor) -> list[list[str]]:
    return [c for c in ex.calls if c[0] == "killall"]


def test_table_matches_the_spec_with_typed_values() -> None:
    by_id = {s.id: s.value for s in md.SETTINGS}
    assert by_id["NSGlobalDomain:KeyRepeat"] == Value("int", 2)
    assert by_id["NSGlobalDomain:InitialKeyRepeat"] == Value("int", 15)
    assert by_id["NSGlobalDomain:ApplePressAndHoldEnabled"] == Value("bool", False)
    assert by_id["com.apple.finder:FXPreferredViewStyle"] == Value("string", "Nlsv")
    assert by_id["com.apple.dock:tilesize"] == Value("int", 48)
    assert by_id["com.apple.screencapture:target"] == Value("string", "clipboard")
    assert by_id["com.apple.screencapture:type"] == Value("string", "png")
    assert by_id["com.apple.AppleMultitouchTrackpad:Clicking"] == Value("bool", True)
    bt = "com.apple.driver.AppleBluetoothMultitouch.trackpad:Clicking"
    assert by_id[bt] == Value("bool", True)
    assert len(by_id) == len(md.SETTINGS) == 20  # ids are unique


def test_apply_writes_typed_values_and_restarts_each_process_once() -> None:
    ex = PrefsExecutor()
    changed = md.apply(_ctx(ex))
    assert len(changed) == len(md.SETTINGS)
    assert ["defaults", "write", DOCK, "tilesize", "-int", "48"] in ex.calls
    assert ["defaults", "write", "NSGlobalDomain", "ApplePressAndHoldEnabled",
            "-bool", "false"] in ex.calls
    assert ["defaults", "write", "com.apple.screencapture", "target",
            "-string", "clipboard"] in ex.calls
    assert _kills(ex) == [["killall", "Dock"], ["killall", "Finder"],
                          ["killall", "SystemUIServer"]]


def test_nothing_changes_and_nothing_restarts_when_already_applied() -> None:
    ex = PrefsExecutor()
    md.apply(_ctx(ex))
    ex.calls.clear()
    assert md.apply(_ctx(ex)) == []
    assert _writes(ex) == []
    assert _kills(ex) == []


def test_only_changed_processes_restart() -> None:
    ex = PrefsExecutor()
    md.apply(_ctx(ex))
    ex.prefs[(DOCK, "tilesize")] = ("integer", "64")  # the user moved the slider
    ex.calls.clear()
    assert md.apply(_ctx(ex)) == ["com.apple.dock:tilesize"]
    assert _kills(ex) == [["killall", "Dock"]]


def test_snapshot_records_prior_values_and_absence() -> None:
    ex = PrefsExecutor(prefs={(DOCK, "tilesize"): ("integer", "64")})
    md.apply(_ctx(ex))
    raw = json.loads(md.snapshot_path().read_text(encoding="utf-8"))
    assert raw["version"] == 1
    assert raw["prior"]["com.apple.dock:tilesize"] == {"kind": "int", "value": 64}
    assert raw["prior"]["com.apple.dock:autohide"] is None


def test_snapshot_keeps_the_first_prior_across_runs() -> None:
    ex = PrefsExecutor(prefs={(DOCK, "tilesize"): ("integer", "64")})
    md.apply(_ctx(ex))
    ex.prefs[(DOCK, "tilesize")] = ("integer", "30")
    md.apply(_ctx(ex))
    assert md.load_snapshot()["com.apple.dock:tilesize"] == Value("int", 64)


def test_verify_is_true_only_when_every_key_matches() -> None:
    ex = PrefsExecutor()
    assert md.verify_all(_ctx(ex)) is False
    md.apply(_ctx(ex))
    assert md.verify_all(_ctx(ex)) is True
    ex.prefs[(DOCK, "autohide")] = ("boolean", "0")
    assert md.verify_all(_ctx(ex)) is False


def test_full_revert_restores_values_deletes_absent_keys_and_clears_snapshot() -> None:
    ex = PrefsExecutor(prefs={(DOCK, "tilesize"): ("integer", "64")})
    md.apply(_ctx(ex))
    ex.calls.clear()
    restored = md.revert(_ctx(ex))
    assert len(restored) == len(md.SETTINGS)
    assert ex.prefs == {(DOCK, "tilesize"): ("integer", "64")}  # everything else deleted
    assert ["defaults", "delete", DOCK, "autohide"] in ex.calls
    assert not md.snapshot_path().exists()
    assert ["killall", "Dock"] in ex.calls


def test_partial_revert_restores_only_the_named_keys() -> None:
    ex = PrefsExecutor(prefs={(DOCK, "tilesize"): ("integer", "64")})
    md.apply(_ctx(ex))
    assert md.revert(_ctx(ex), ["com.apple.dock:tilesize"]) == ["com.apple.dock:tilesize"]
    assert ex.prefs[(DOCK, "tilesize")] == ("integer", "64")
    assert ex.prefs[(DOCK, "autohide")] == ("boolean", "1")
    snap = md.load_snapshot()
    assert "com.apple.dock:tilesize" not in snap
    assert "com.apple.dock:autohide" in snap


def test_revert_leaves_an_unrestorable_prior_alone() -> None:
    ex = PrefsExecutor(prefs={(DOCK, "tilesize"): ("array", "(\n)")})
    md.apply(_ctx(ex))
    assert md.revert(_ctx(ex), ["com.apple.dock:tilesize"]) == []
    assert ex.prefs[(DOCK, "tilesize")] == ("integer", "48")
    assert "com.apple.dock:tilesize" in md.load_snapshot()


def test_revert_of_unrecorded_key_is_a_noop() -> None:
    ex = PrefsExecutor()
    assert md.revert(_ctx(ex), ["com.apple.dock:tilesize"]) == []
    touched = [c for c in ex.calls if c[:2] in (["defaults", "write"], ["defaults", "delete"])]
    assert touched == []


def test_resolve_ids_accepts_full_or_unique_bare_keys() -> None:
    assert md.resolve_ids(["tilesize", "NSGlobalDomain:KeyRepeat"]) == [
        "com.apple.dock:tilesize",
        "NSGlobalDomain:KeyRepeat",
    ]
    with pytest.raises(ValueError, match="ambiguous"):
        md.resolve_ids(["Clicking"])
    with pytest.raises(ValueError, match="unknown"):
        md.resolve_ids(["nope"])


def test_version_gated_rows() -> None:
    row = md.Setting(DOCK, "x", Value("bool", True), min_macos=(28, 0))
    assert row.applies(MAC) is False
    assert row.applies(OsInfo("macos", "macos", "aarch64", version_id="28.1")) is True
    old_only = md.Setting(DOCK, "y", Value("bool", True), max_macos=(26, 99))
    assert old_only.applies(MAC) is False


def test_module_is_macos_only_and_in_macos_desktop() -> None:
    assert md.MacosDefaults.families == ("macos",)
    assert md.MacosDefaults.profiles == ("macos-desktop",)
    ex = PrefsExecutor()
    md.MacosDefaults().install(_ctx(ex))
    assert md.MacosDefaults().verify(_ctx(ex)) is True


# --- lane M5-A additions: backup and revert must survive failures and repeats ------------


def test_a_second_full_revert_is_a_noop() -> None:
    ex = PrefsExecutor(prefs={(DOCK, "tilesize"): ("integer", "64")})
    md.apply(_ctx(ex))
    md.revert(_ctx(ex))
    ex.calls.clear()
    assert md.revert(_ctx(ex)) == []
    assert ex.prefs == {(DOCK, "tilesize"): ("integer", "64")}
    assert _writes(ex) == [] and _kills(ex) == []


def test_apply_after_a_full_revert_snapshots_afresh() -> None:
    ex = PrefsExecutor(prefs={(DOCK, "tilesize"): ("integer", "64")})
    md.apply(_ctx(ex))
    md.revert(_ctx(ex))
    md.apply(_ctx(ex))
    assert md.load_snapshot()["com.apple.dock:tilesize"] == Value("int", 64)
    md.revert(_ctx(ex))
    assert ex.prefs == {(DOCK, "tilesize"): ("integer", "64")}


def test_a_corrupt_snapshot_stops_apply_before_any_write() -> None:
    path = md.snapshot_path()
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    ex = PrefsExecutor()
    with pytest.raises(md.SnapshotError, match="macos-defaults.prev.json"):
        md.apply(_ctx(ex))
    assert _writes(ex) == []
    assert path.read_text(encoding="utf-8") == "{not json"  # the evidence is kept


def test_a_corrupt_snapshot_stops_revert() -> None:
    path = md.snapshot_path()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"version": 99, "prior": {}}), encoding="utf-8")
    with pytest.raises(md.SnapshotError, match="version"):
        md.revert(_ctx(PrefsExecutor()))


def test_a_failed_write_keeps_the_snapshot_of_every_key() -> None:
    ex = PrefsExecutor(rules=[(("defaults", "write", "tilesize"), Result(1))])
    with pytest.raises(InstallError):
        md.apply(_ctx(ex))
    assert len(md.load_snapshot()) == len(md.SETTINGS)


def test_a_failed_restore_keeps_its_prior_and_saves_the_progress() -> None:
    ex = PrefsExecutor(prefs={(DOCK, "tilesize"): ("integer", "64")})
    md.apply(_ctx(ex))
    ex.rules.append((("defaults", "write", "tilesize"), Result(1)))
    with pytest.raises(InstallError):
        md.revert(_ctx(ex))
    snap = md.load_snapshot()
    assert "com.apple.dock:tilesize" in snap
    assert "com.apple.dock:autohide" not in snap  # restored before the failure
    ex.rules.clear()
    again = md.revert(_ctx(ex))  # finishes the job: tilesize and the ids sorted after it
    assert "com.apple.dock:tilesize" in again
    assert "com.apple.dock:autohide" not in again
    assert ex.prefs == {(DOCK, "tilesize"): ("integer", "64")}
    assert not md.snapshot_path().exists()


def test_the_snapshot_is_written_atomically() -> None:
    md.apply(_ctx(PrefsExecutor()))
    leftovers = [p.name for p in md.snapshot_path().parent.iterdir()]
    assert leftovers == ["macos-defaults.prev.json"]


def test_float_and_string_priors_round_trip() -> None:
    ex = PrefsExecutor(prefs={
        (DOCK, "tilesize"): ("float", "36.5"),
        ("com.apple.screencapture", "target"): ("string", "file"),
    })
    md.apply(_ctx(ex))
    md.revert(_ctx(ex))
    assert ex.prefs == {
        (DOCK, "tilesize"): ("float", "36.5"),
        ("com.apple.screencapture", "target"): ("string", "file"),
    }


def test_rows_outside_the_running_macos_are_neither_applied_nor_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gated = md.Setting(DOCK, "future-key", Value("bool", True), "Dock", min_macos=(99, 0))
    monkeypatch.setattr(md, "SETTINGS", (*md.SETTINGS, gated))
    ex = PrefsExecutor()
    md.apply(_ctx(ex))
    assert (DOCK, "future-key") not in ex.prefs
    assert "com.apple.dock:future-key" not in md.load_snapshot()
    assert md.verify_all(_ctx(ex)) is True


@pytest.mark.parametrize("entry", [{"kind": "int", "value": "2"}, {"kind": "blob"}, [1]])
def test_a_mistyped_snapshot_entry_is_refused(entry: object) -> None:
    path = md.snapshot_path()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"version": 1, "prior": {"a:b": entry}}), encoding="utf-8")
    with pytest.raises(md.SnapshotError, match="not a valid"):
        md.load_snapshot()


def test_a_missing_domain_counts_as_absent() -> None:
    ex = PrefsExecutor(rules=[(
        ("read-type", "com.apple.desktopservices"),
        Result(1, "", "Domain 'com.apple.desktopservices' not found.\n"),
    )])
    md.apply(_ctx(ex))
    assert md.load_snapshot()["com.apple.desktopservices:DSDontWriteUSBStores"] is None


def test_a_failed_read_is_never_recorded_as_absent() -> None:
    # A transient failure must not become "absent": revert would then delete the user's value.
    ex = PrefsExecutor(
        prefs={(DOCK, "tilesize"): ("integer", "64")},
        rules=[(("read-type", DOCK, "tilesize"), Result(2, "", "cfprefsd not responding\n"))],
    )
    changed = md.apply(_ctx(ex))
    assert "com.apple.dock:tilesize" not in changed
    assert "com.apple.dock:tilesize" not in md.load_snapshot()
    assert ex.prefs[(DOCK, "tilesize")] == ("integer", "64")  # not written either
    assert "com.apple.dock:autohide" in changed  # the other keys still go ahead
    assert md.verify_all(_ctx(ex)) is False
    ex.rules.clear()  # the next run records the real prior
    md.apply(_ctx(ex))
    assert md.load_snapshot()["com.apple.dock:tilesize"] == Value("int", 64)
    md.revert(_ctx(ex))
    assert ex.prefs == {(DOCK, "tilesize"): ("integer", "64")}


def test_a_failed_value_read_after_a_good_type_read_is_unreadable() -> None:
    ex = PrefsExecutor(
        prefs={(DOCK, "tilesize"): ("integer", "64")},
        rules=[(("defaults", "read", DOCK, "tilesize"), Result(1))],
    )
    md.apply(_ctx(ex))
    assert "com.apple.dock:tilesize" not in md.load_snapshot()
    assert ex.prefs[(DOCK, "tilesize")] == ("integer", "64")
