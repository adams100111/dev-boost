"""Default apps via utiluti: one dialog per UTI, asked once, only when someone can answer."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from devboost.core import log
from devboost.core.errors import InstallError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import default_apps
from devboost.exec.primitives.default_apps import Association
from devboost.model import Ctx
from devboost.modules.cli_tools import Utiluti

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
ZED = "dev.zed.Zed"


class _LaunchServices(FakeExecutor):
    """utiluti over a fake LaunchServices: extension → UTI, UTI → default app.

    ``refuse``: the user declines the dialog — utiluti still exits 0, nothing changes.
    ``broken``: ``type set`` fails (exit 1). ``crash``: ``type set`` raises (an
    interrupted run). ``lower``: LaunchServices reports bundle ids lower-cased."""

    def __init__(self, utis: dict[str, str], handlers: dict[str, str] | None = None,
                 refuse: set[str] | None = None, *, broken: set[str] | None = None,
                 crash: set[str] | None = None, lower: bool = False) -> None:
        super().__init__(present={"utiluti"})
        self.utis = utis
        self.handlers = dict(handlers or {})
        self.refuse = refuse or set()
        self.broken = broken or set()
        self.crash = crash or set()
        self.lower = lower
        self.sets: list[tuple[str, str, bool]] = []

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
            argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive,
            timeout=timeout,
        )
        a = list(argv)
        if a[:2] == ["utiluti", "get-uti"]:
            uti = self.utis.get(a[2])
            if uti is None:
                return Result(1)
            # Real utiluti: a dyn.* UTI (no app declares the type) prints nothing unless
            # --show-dynamic is passed — still exit 0, which without the flag is
            # indistinguishable from "nothing to report" and used to be logged as a
            # lookup failure instead of the dynamic-UTI skip path.
            if uti.startswith("dyn.") and "--show-dynamic" not in a:
                return Result(0, stdout="")
            return Result(0, stdout=f"{uti}\n")
        if a[:3] == ["utiluti", "type", "set"]:
            self.sets.append((a[3], a[4], interactive))
            if a[3] in self.crash:
                raise KeyboardInterrupt
            if a[3] in self.broken:
                return Result(1, stderr="error setting default app")
            if a[3] not in self.refuse:
                self.handlers[a[3]] = a[4]
            return Result(0)
        if a[:2] == ["utiluti", "type"]:
            app = self.handlers.get(a[2])
            if app and self.lower:
                app = app.lower()
            return Result(0, stdout=f"{app}\n") if app else Result(1)
        return Result(0)


UTIS = {"yaml": "public.yaml", "yml": "public.yaml", "py": "public.python-script"}
ROWS = [Association(e, ZED) for e in ("yaml", "yml", "py")]


def test_the_bundled_table_has_the_zed_rows() -> None:
    rows = default_apps.table("data", "macos", "default-apps.tsv")
    zed = [r.ext for r in rows if r.bundle_id == ZED]
    assert {"md", "json", "py", "tsx", "php", "cs"} <= set(zed)
    # .ts (and .mts) is MPEG-2 transport-stream video on macOS: claiming it would open
    # camera/Blu-ray video in Zed (modules review M5).
    assert not {"ts", "mts", "m2ts"} & set(zed)
    assert len(zed) == len(set(zed))  # no duplicate extensions


def _table_from(monkeypatch: pytest.MonkeyPatch, text: str) -> list[Association]:
    rows = [line.split("\t") for line in text.splitlines()
            if line.strip() and not line.startswith("#")]
    monkeypatch.setattr(default_apps, "tsv_rows", lambda *parts, min_cols: [
        r for r in rows if len(r) >= min_cols
    ])
    return default_apps.table("data", "macos", "default-apps.tsv")


def test_table_rows_are_normalised(monkeypatch: pytest.MonkeyPatch) -> None:
    text = "# header\n\n  .MD \t dev.zed.Zed \n   # indented comment\t x\nPy\tdev.zed.Zed\n"
    assert _table_from(monkeypatch, text) == [Association("md", ZED), Association("py", ZED)]


def test_a_duplicate_extension_is_an_error_at_load(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match=r"\.md is listed twice"):
        _table_from(monkeypatch, "md\tdev.zed.Zed\n.MD\tcom.example.Other\n")


@pytest.mark.parametrize(
    ("version", "asks"),
    [("27.0", True), ("26.4", True), ("26.3", False), ("15.6", False), ("", True)],
)
def test_confirmation_required_from_26_4(version: str, asks: bool) -> None:
    os_info = OsInfo("macos", "macos", "aarch64", version_id=version)
    assert default_apps.confirmation_required(os_info) is asks


def test_one_dialog_per_uti_and_every_extension_recorded() -> None:
    ex = _LaunchServices(UTIS)
    out = default_apps.apply(Ctx(os=MAC, ex=ex), ROWS, can_prompt=True)
    assert sorted(ex.sets) == [("public.python-script", ZED, True), ("public.yaml", ZED, True)]
    assert sorted(out.changed) == ["public.python-script", "public.yaml"]
    assert default_apps.handled(ROWS)
    saved = json.loads(default_apps.state_path().read_text(encoding="utf-8"))
    assert saved == {ZED: ["py", "yaml", "yml"]}


def test_a_type_already_on_the_app_needs_no_dialog() -> None:
    ex = _LaunchServices(UTIS, handlers={"public.yaml": ZED, "public.python-script": ZED})
    out = default_apps.apply(Ctx(os=MAC, ex=ex), ROWS, can_prompt=False)
    assert ex.sets == [] and out.pending == []
    assert sorted(out.already) == ["public.python-script", "public.yaml"]
    assert default_apps.handled(ROWS)


def test_a_declined_type_is_never_asked_again() -> None:
    # utiluti exits 0 on a declined dialog; the read-back shows the old handler.
    ex = _LaunchServices(UTIS, refuse={"public.python-script"})
    out = default_apps.apply(Ctx(os=MAC, ex=ex), ROWS, can_prompt=True)
    assert out.refused == ["py"]  # extensions, as the user knows them
    assert out.changed == ["public.yaml"]
    assert default_apps.handled(ROWS)
    again = _LaunchServices(UTIS)
    default_apps.apply(Ctx(os=MAC, ex=again), ROWS, can_prompt=True)
    assert again.sets == []


def _next_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """A new process: nothing deferred by the previous run survives."""
    monkeypatch.setattr(default_apps, "_deferred", {})


def test_a_failed_set_is_not_recorded_and_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    warned: list[str] = []
    monkeypatch.setattr(log, "warn", warned.append)
    ex = _LaunchServices(UTIS, broken={"public.python-script"})
    out = default_apps.apply(Ctx(os=MAC, ex=ex), ROWS, can_prompt=True)
    assert out.failed == ["py"]
    assert out.changed == ["public.yaml"] and out.refused == []
    assert len(warned) == 1 and "public.python-script" in warned[0]
    saved = json.loads(default_apps.state_path().read_text(encoding="utf-8"))
    assert saved == {ZED: ["yaml", "yml"]}  # py is not recorded
    assert default_apps.handled(ROWS)  # deferred: this run can finish
    _next_run(monkeypatch)
    assert not default_apps.handled(ROWS)
    again = _LaunchServices(UTIS)
    out = default_apps.apply(Ctx(os=MAC, ex=again), ROWS, can_prompt=True)
    assert again.sets == [("public.python-script", ZED, True)]
    assert out.changed == ["public.python-script"]
    assert default_apps.handled(ROWS)


def test_a_failed_uti_lookup_is_warned_not_recorded_and_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # C-R26: a get-uti that exits non-zero is a tool failure, not a declined type.
    warned: list[str] = []
    monkeypatch.setattr(log, "warn", warned.append)
    utis = {k: v for k, v in UTIS.items() if k != "py"}
    out = default_apps.apply(Ctx(os=MAC, ex=_LaunchServices(utis)), ROWS, can_prompt=True)
    assert out.failed == ["py"] and out.refused == []
    assert len(warned) == 1 and ".py" in warned[0]
    saved = json.loads(default_apps.state_path().read_text(encoding="utf-8"))
    assert saved == {ZED: ["yaml", "yml"]}
    assert default_apps.handled(ROWS)  # deferred for this run only
    _next_run(monkeypatch)
    assert not default_apps.handled(ROWS)
    again = _LaunchServices(UTIS)
    out = default_apps.apply(Ctx(os=MAC, ex=again), ROWS, can_prompt=True)
    assert again.sets == [("public.python-script", ZED, True)]
    assert default_apps.handled(ROWS)


def test_a_dynamic_uti_is_skipped_not_declined(monkeypatch: pytest.MonkeyPatch) -> None:
    # Core review M4: no installed app declares the type, so there is nothing to set.
    skipped: list[str] = []
    warned: list[str] = []
    monkeypatch.setattr(log, "skip", skipped.append)
    monkeypatch.setattr(log, "warn", warned.append)
    utis = {**UTIS, "py": "dyn.ah62d4rv4ge81e5pe"}
    ex = _LaunchServices(utis)
    out = default_apps.apply(Ctx(os=MAC, ex=ex), ROWS, can_prompt=True)
    assert out.dynamic == ["py"] and out.refused == [] and out.failed == []
    assert ex.sets == [("public.yaml", ZED, True)]  # no dialog for the dyn.* type
    assert len(skipped) == 1 and ".py" in skipped[0] and warned == []
    _next_run(monkeypatch)
    assert default_apps.handled(ROWS)  # settled: not asked again


def test_get_uti_passes_show_dynamic_so_a_dyn_type_is_not_mistaken_for_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Regression: `utiluti get-uti <ext>` alone prints nothing (exit 0) for a dyn.* type
    # (e.g. .jsx/.cs/.scss when no installed app declares them); only --show-dynamic
    # reveals it. Without the flag this looked like a tool failure, not the dyn.* skip.
    warned: list[str] = []
    monkeypatch.setattr(log, "warn", warned.append)
    utis = {**UTIS, "py": "dyn.ah62d4rv4ge81e5pe"}
    ex = _LaunchServices(utis)
    out = default_apps.apply(Ctx(os=MAC, ex=ex), ROWS, can_prompt=True)
    assert out.dynamic == ["py"] and out.failed == [] and warned == []
    calls = [c for c in ex.calls if c[:2] == ["utiluti", "get-uti"] and c[2] == "py"]
    assert calls and "--show-dynamic" in calls[0]


def test_an_interrupted_run_keeps_the_answers_already_given() -> None:
    ex = _LaunchServices(UTIS, crash={"public.python-script"})
    with pytest.raises(KeyboardInterrupt):
        default_apps.apply(Ctx(os=MAC, ex=ex), ROWS, can_prompt=True)
    saved = json.loads(default_apps.state_path().read_text(encoding="utf-8"))
    assert saved == {ZED: ["yaml", "yml"]}
    again = _LaunchServices(UTIS, handlers=ex.handlers)
    default_apps.apply(Ctx(os=MAC, ex=again), ROWS, can_prompt=True)
    assert again.sets == [("public.python-script", ZED, True)]


@pytest.mark.parametrize("body", ["{not json", "[1, 2]", ""])
def test_a_corrupt_state_file_counts_as_empty(
    body: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    warned: list[str] = []
    monkeypatch.setattr(log, "warn", warned.append)
    path = default_apps.state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    assert not default_apps.handled(ROWS)
    assert warned and str(path) in warned[0]
    ex = _LaunchServices(UTIS)
    out = default_apps.apply(Ctx(os=MAC, ex=ex), ROWS, can_prompt=True)
    assert sorted(out.changed) == ["public.python-script", "public.yaml"]
    assert json.loads(path.read_text(encoding="utf-8")) == {ZED: ["py", "yaml", "yml"]}


def test_bundle_ids_match_case_insensitively() -> None:
    # Already the default, reported lower-cased: no dialog.
    ex = _LaunchServices(UTIS, handlers={"public.yaml": "dev.zed.zed"})
    out = default_apps.apply(Ctx(os=MAC, ex=ex), ROWS[:2], can_prompt=True)
    assert out.already == ["public.yaml"] and ex.sets == []
    # A successful set whose read-back comes back lower-cased is still a change.
    ex = _LaunchServices(UTIS, lower=True)
    out = default_apps.apply(Ctx(os=MAC, ex=ex), ROWS[2:], can_prompt=True)
    assert out.changed == ["public.python-script"] and out.refused == []


def test_nobody_to_answer_leaves_the_types_pending() -> None:
    ex = _LaunchServices(UTIS)
    out = default_apps.apply(Ctx(os=MAC, ex=ex), ROWS, can_prompt=False)
    assert ex.sets == []
    assert sorted(out.pending) == ["py", "yaml", "yml"]
    assert not default_apps.handled(ROWS)


def test_missing_utiluti_is_an_install_error() -> None:
    with pytest.raises(InstallError, match="utiluti"):
        default_apps.apply(Ctx(os=MAC, ex=FakeExecutor()), ROWS, can_prompt=True)


def test_state_lives_under_xdg_state_home(tmp_path: Path) -> None:
    assert default_apps.state_path() == (
        tmp_path / ".local" / "state" / "devboost" / "default-apps.json"
    )


def test_a_relative_xdg_state_home_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", "relative/state")  # invalid per the XDG spec
    assert default_apps.state_path() == (
        tmp_path / ".local" / "state" / "devboost" / "default-apps.json"
    )


def test_an_unset_home_falls_back_to_path_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("XDG_STATE_HOME")
    monkeypatch.delenv("HOME")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "pw"))
    assert default_apps.state_path() == (
        tmp_path / "pw" / ".local" / "state" / "devboost" / "default-apps.json"
    )


def test_utiluti_is_a_macos_brew_formula() -> None:
    assert Utiluti.families == ("macos",)
    ex = FakeExecutor()
    Utiluti().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [["brew", "install", "--formula", "-y", "utiluti"]]
