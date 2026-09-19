"""Default apps via utiluti: one dialog per UTI, asked once, only when someone can answer."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

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
    """utiluti over a fake LaunchServices: extension → UTI, UTI → default app."""

    def __init__(self, utis: dict[str, str], handlers: dict[str, str] | None = None,
                 refuse: set[str] | None = None) -> None:
        super().__init__(present={"utiluti"})
        self.utis = utis
        self.handlers = dict(handlers or {})
        self.refuse = refuse or set()
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
    ) -> Result:
        super().run(argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive)
        a = list(argv)
        if a[:2] == ["utiluti", "get-uti"]:
            uti = self.utis.get(a[2])
            return Result(0, stdout=f"{uti}\n") if uti else Result(1)
        if a[:3] == ["utiluti", "type", "set"]:
            self.sets.append((a[3], a[4], interactive))
            if a[3] in self.refuse:
                return Result(1, stderr="declined")
            self.handlers[a[3]] = a[4]
            return Result(0)
        if a[:2] == ["utiluti", "type"]:
            app = self.handlers.get(a[2])
            return Result(0, stdout=f"{app}\n") if app else Result(1)
        return Result(0)


UTIS = {"yaml": "public.yaml", "yml": "public.yaml", "py": "public.python-script"}
ROWS = [Association(e, ZED) for e in ("yaml", "yml", "py")]


def test_the_bundled_table_has_the_zed_rows() -> None:
    rows = default_apps.table("data", "macos", "default-apps.tsv")
    zed = [r.ext for r in rows if r.bundle_id == ZED]
    assert {"md", "json", "py", "ts", "tsx", "php", "cs"} <= set(zed)
    assert len(zed) == len(set(zed))  # no duplicate extensions


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
    ex = _LaunchServices(UTIS, refuse={"public.python-script"})
    out = default_apps.apply(Ctx(os=MAC, ex=ex), ROWS, can_prompt=True)
    assert out.refused == ["public.python-script"]
    again = _LaunchServices(UTIS)
    default_apps.apply(Ctx(os=MAC, ex=again), ROWS, can_prompt=True)
    assert again.sets == []


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


def test_utiluti_is_a_macos_brew_formula() -> None:
    assert Utiluti.families == ("macos",)
    ex = FakeExecutor()
    Utiluti().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [["brew", "install", "--formula", "-y", "utiluti"]]
