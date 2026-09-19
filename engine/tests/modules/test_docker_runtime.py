from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from devboost.core.errors import InstallError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.modules import _docker_runtime as rt
from devboost.modules import macos
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64")
GIB = 1024**3


def _ctx(*rules: tuple[tuple[str, ...], Result]) -> Ctx:
    return Ctx(os=MAC, ex=RuleExecutor(rules=list(rules)))


def test_vm_size_is_half_the_cpus_and_a_quarter_of_the_ram() -> None:
    ctx = _ctx(
        (("hw.ncpu",), Result(0, stdout="11\n")),
        (("hw.memsize",), Result(0, stdout=f"{24 * GIB}\n")),
    )
    assert rt.vm_size(ctx) == rt.VmSize(cpu=5, memory_gib=6)


def test_vm_size_floors() -> None:
    ctx = _ctx(
        (("hw.ncpu",), Result(0, stdout="2\n")),
        (("hw.memsize",), Result(0, stdout=f"{8 * GIB}\n")),
    )
    assert rt.vm_size(ctx) == rt.VmSize(cpu=2, memory_gib=4)


def test_vm_size_defaults_when_sysctl_fails() -> None:
    assert rt.vm_size(_ctx((("sysctl",), Result(1)))) == rt.VmSize(cpu=2, memory_gib=4)


def test_rosetta_probe_is_the_m3_probe() -> None:
    """M4-D8: one Rosetta probe, M3's (`arch -x86_64 /usr/bin/true`), re-exported here."""
    assert rt.rosetta_present is macos.rosetta_present
    assert rt.rosetta_supported is macos.rosetta_supported
    ctx = _ctx()
    assert rt.rosetta_present(ctx) is True
    assert ctx.ex.calls == [["arch", "-x86_64", "/usr/bin/true"]]  # type: ignore[attr-defined]
    assert rt.rosetta_present(_ctx((("-x86_64",), Result(1)))) is False


@pytest.mark.parametrize(
    ("version", "probe", "usable"),
    [("27.0", Result(0), True), ("27.0", Result(1), False), ("28.0", Result(0), False)],
)
def test_rosetta_usable_needs_support_and_presence(
    version: str, probe: Result, usable: bool
) -> None:
    ctx = Ctx(
        os=OsInfo("macos", "macos", "aarch64", version_id=version),
        ex=RuleExecutor(rules=[(("-x86_64",), probe)]),
    )
    assert rt.rosetta_usable(ctx) is usable


def test_use_context() -> None:
    ctx = _ctx()
    rt.use_context(ctx, "colima")
    assert ctx.ex.calls == [["docker", "context", "use", "colima"]]  # type: ignore[attr-defined]
    with pytest.raises(InstallError, match="docker context use colima"):
        rt.use_context(_ctx((("context", "use"), Result(1))), "colima")


def test_engine_verified_needs_the_context_and_a_live_engine() -> None:
    show = (("context", "show"), Result(0, stdout="colima\n"))
    assert rt.engine_verified(_ctx(show), "colima") is True
    assert rt.engine_verified(_ctx(show), "orbstack") is False
    assert rt.engine_verified(_ctx(show, (("info",), Result(1))), "colima") is False
    assert rt.current_context(_ctx((("context", "show"), Result(1)))) == ""


def test_engine_up_argv() -> None:
    ctx = _ctx()
    assert rt.engine_up(ctx, "colima") is True
    assert ctx.ex.calls == [  # type: ignore[attr-defined]
        ["docker", "--context", "colima", "info", "--format", "{{.ServerVersion}}"]
    ]


class _Flaky(RuleExecutor):
    """`docker … info` fails ``fails`` times, then succeeds."""

    def __init__(self, fails: int) -> None:
        super().__init__()
        self.fails = fails

    def run(self, argv: Sequence[str], **kw: Any) -> Result:
        res = super().run(argv, **kw)
        if "info" in argv and self.fails > 0:
            self.fails -= 1
            return Result(1)
        return res


def test_wait_for_engine_polls_until_up(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(rt, "_sleep", sleeps.append)
    monkeypatch.setattr(rt, "_clock", lambda: 0.0)
    rt.wait_for_engine(Ctx(os=MAC, ex=_Flaky(2)), "colima", interval=2.0)
    assert sleeps == [2.0, 2.0]


def test_wait_for_engine_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks: Iterator[float] = iter([0.0, 1.0, 999.0])
    monkeypatch.setattr(rt, "_sleep", lambda s: None)
    monkeypatch.setattr(rt, "_clock", lambda: next(ticks))
    with pytest.raises(InstallError, match="docker --context colima info"):
        rt.wait_for_engine(Ctx(os=MAC, ex=_Flaky(99)), "colima", timeout=180.0)


def test_docker_config_path_honours_docker_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert rt.docker_config_path() == tmp_path / ".docker" / "config.json"
    monkeypatch.setenv("DOCKER_CONFIG", str(tmp_path / "dc"))
    assert rt.docker_config_path() == tmp_path / "dc" / "config.json"


def test_read_json_and_json_has(tmp_path: Path) -> None:
    p = tmp_path / "d.json"
    assert rt.read_json(p) == {}
    p.write_text("[1]", encoding="utf-8")
    assert rt.read_json(p) == {}
    p.write_text("{nope", encoding="utf-8")
    assert rt.read_json(p) == {}
    p.write_text(json.dumps({"builder": {"gc": {"enabled": True}}, "x": 1}), encoding="utf-8")
    assert rt.json_has(p, {"builder": {"gc": {"enabled": True}}}) is True
    assert rt.json_has(p, {"x": 2}) is False


def test_license_notes() -> None:
    assert rt.license_note("colima") is None
    orb = rt.license_note("orbstack")
    assert orb is not None and "non-commercial" in orb and "$8/user/month" in orb
    dd = rt.license_note("docker-desktop")
    assert dd is not None and "250 employees" in dd and "US$10M" in dd
