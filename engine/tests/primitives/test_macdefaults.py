from __future__ import annotations

import pytest

from devboost.core.errors import InstallError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import macdefaults
from devboost.exec.primitives.macdefaults import Value
from devboost.model import Ctx
from tests.modules.macos_fakes import PrefsExecutor

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
DOCK = "com.apple.dock"


def _ctx(ex: FakeExecutor) -> Ctx:
    return Ctx(os=MAC, ex=ex)


def test_read_absent_is_none() -> None:
    assert macdefaults.read(_ctx(PrefsExecutor()), DOCK, "tilesize") is None


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        (("boolean", "1"), Value("bool", True)),
        (("boolean", "0"), Value("bool", False)),
        (("integer", "48"), Value("int", 48)),
        (("float", "0.5"), Value("float", 0.5)),
        (("string", "Nlsv"), Value("string", "Nlsv")),
        (("array", "(\n)"), Value("other", "array")),
    ],
)
def test_read_is_typed(stored: tuple[str, str], expected: Value) -> None:
    ex = PrefsExecutor(prefs={(DOCK, "k"): stored})
    assert macdefaults.read(_ctx(ex), DOCK, "k") == expected


@pytest.mark.parametrize(
    ("value", "flag"),
    [
        (Value("bool", True), ["-bool", "true"]),
        (Value("bool", False), ["-bool", "false"]),
        (Value("int", 48), ["-int", "48"]),
        (Value("float", 0.5), ["-float", "0.5"]),
        (Value("string", "clipboard"), ["-string", "clipboard"]),
    ],
)
def test_write_argv_is_typed(value: Value, flag: list[str]) -> None:
    ex = FakeExecutor()
    macdefaults.write(_ctx(ex), DOCK, "k", value)
    assert ex.calls == [["defaults", "write", DOCK, "k", *flag]]


def test_write_round_trips_through_read() -> None:
    ex = PrefsExecutor()
    macdefaults.write(_ctx(ex), DOCK, "autohide", Value("bool", True))
    assert macdefaults.read(_ctx(ex), DOCK, "autohide") == Value("bool", True)


def test_write_failure_raises() -> None:
    ex = FakeExecutor(scripts={"defaults": Result(1)})
    with pytest.raises(InstallError):
        macdefaults.write(_ctx(ex), DOCK, "k", Value("int", 1))


def test_write_other_kind_is_refused() -> None:
    with pytest.raises(ValueError, match="other"):
        macdefaults.write(_ctx(FakeExecutor()), DOCK, "k", Value("other", "array"))


def test_delete_absent_is_not_an_error() -> None:
    ex = PrefsExecutor()
    macdefaults.delete(_ctx(ex), DOCK, "tilesize")
    assert ex.calls == [["defaults", "delete", DOCK, "tilesize"]]


# --- the stateful fake itself (Wave 1 lanes lean on it) ---


def test_delete_restores_absence_in_the_fake() -> None:
    ex = PrefsExecutor(prefs={(DOCK, "tilesize"): ("integer", "48")})
    macdefaults.delete(_ctx(ex), DOCK, "tilesize")
    assert ex.prefs == {}
    assert macdefaults.read(_ctx(ex), DOCK, "tilesize") is None


def test_a_matching_rule_overrides_the_store() -> None:
    ex = PrefsExecutor(rules=[(("defaults", "write"), Result(1))])
    with pytest.raises(InstallError):
        macdefaults.write(_ctx(ex), DOCK, "k", Value("int", 1))
    assert ex.prefs == {}


def test_other_argv_behaves_like_fake_executor() -> None:
    ex = PrefsExecutor(scripts={"killall": Result(1)})
    assert ex.run(["killall", "Dock"]).code == 1
    assert ex.run(["open", "-a", "Dock"]).ok
    assert ex.calls == [["killall", "Dock"], ["open", "-a", "Dock"]]
