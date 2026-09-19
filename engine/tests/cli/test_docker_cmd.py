from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from typer.testing import CliRunner

from devboost.cli import docker_cmd, host
from devboost.cli.app import app
from devboost.core import osinfo
from devboost.core.errors import InstallError, NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.core.userconfig import set_user_value
from devboost.exec.executor import FakeExecutor, NoPromptSudoExecutor
from devboost.modules._docker_switch import SwitchReport

MAC = OsInfo("macos", "macos", "aarch64")
runner = CliRunner()


class _Session:
    """Stands in for `host.mac_session`; records the `sudo=` it was asked for (M4-D6)."""

    def __init__(self) -> None:
        self.granted = True
        self.sudo: list[bool] = []

    @contextmanager
    def __call__(self, os_info: OsInfo, *, dry_run: bool, **kw: Any) -> Iterator[bool]:
        assert dry_run is False
        self.sudo.append(kw.get("sudo", True))
        yield self.granted


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> _Session:
    s = _Session()
    monkeypatch.setattr(host, "mac_session", s)
    return s


@pytest.fixture
def on_mac(monkeypatch: pytest.MonkeyPatch, session: _Session) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(osinfo, "detect", lambda *a, **k: MAC)
    monkeypatch.setattr(docker_cmd, "RealExecutor", lambda: FakeExecutor(present={"ddev"}))

    def fake_switch(ctx: Any, target: str, *, snapshot: bool) -> SwitchReport:
        seen.append({"target": target, "snapshot": snapshot, "ex": ctx.ex})
        return SwitchReport("colima", target,  # type: ignore[arg-type]
                            (("docker", True), ("docker-build-gc", True), ("ddev", False)))

    monkeypatch.setattr(docker_cmd, "switch_runtime", fake_switch)
    return seen


def _targets(seen: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"target": s["target"], "snapshot": s["snapshot"]} for s in seen]


def test_use_is_macos_only() -> None:
    res = runner.invoke(app, ["docker", "use", "orbstack"])
    assert res.exit_code == 2
    assert "macOS-only" in res.output


def test_use_rejects_an_unknown_runtime(on_mac: list[dict[str, Any]]) -> None:
    res = runner.invoke(app, ["docker", "use", "podman"])
    assert res.exit_code == 2
    assert "unknown docker runtime 'podman'" in res.output
    assert on_mac == []


def test_use_with_yes_snapshots(on_mac: list[dict[str, Any]]) -> None:
    res = runner.invoke(app, ["docker", "use", "orbstack", "--yes"])
    assert res.exit_code == 0, res.output
    assert _targets(on_mac) == [{"target": "orbstack", "snapshot": True}]
    assert "ddev" in res.output and "devboost install ddev" in res.output
    assert "ddev snapshot restore --latest" in res.output


def test_use_no_snapshot_flag(on_mac: list[dict[str, Any]]) -> None:
    runner.invoke(app, ["docker", "use", "orbstack", "--no-snapshot"])
    assert _targets(on_mac) == [{"target": "orbstack", "snapshot": False}]


def test_use_asks_when_not_told(on_mac: list[dict[str, Any]]) -> None:
    res = runner.invoke(app, ["docker", "use", "orbstack"], input="n\n")
    assert "ddev snapshot --all" in res.output
    assert _targets(on_mac) == [{"target": "orbstack", "snapshot": False}]


def test_noninteractive_snapshots_without_asking(
    on_mac: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")
    res = runner.invoke(app, ["docker", "use", "orbstack"])
    assert res.exit_code == 0, res.output
    assert _targets(on_mac) == [{"target": "orbstack", "snapshot": True}]


def test_without_ddev_nothing_is_asked(
    on_mac: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(docker_cmd, "RealExecutor", lambda: FakeExecutor(present=set()))
    res = runner.invoke(app, ["docker", "use", "orbstack"])
    assert res.exit_code == 0, res.output
    assert _targets(on_mac) == [{"target": "orbstack", "snapshot": False}]


def test_blocked_switch_prints_the_fix_and_the_way_back(
    on_mac: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def blocked(ctx: Any, target: str, *, snapshot: bool) -> SwitchReport:
        raise NeedsUser("OrbStack has not finished its first launch", "open -a OrbStack")

    monkeypatch.setattr(docker_cmd, "switch_runtime", blocked)
    res = runner.invoke(app, ["docker", "use", "orbstack", "-y"])
    assert res.exit_code == 1
    assert "open -a OrbStack" in res.output
    assert "devboost docker use colima" in res.output


def test_a_failed_step_prints_the_way_back(
    on_mac: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    def failed(ctx: Any, target: str, *, snapshot: bool) -> SwitchReport:
        raise InstallError("ddev", "ddev snapshot --all", 1)

    monkeypatch.setattr(docker_cmd, "switch_runtime", failed)
    res = runner.invoke(app, ["docker", "use", "orbstack", "-y"])
    assert res.exit_code == 1
    assert "ddev snapshot --all" in res.output
    assert "devboost docker use colima" in res.output


def test_failed_required_check_exits_1(
    on_mac: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        docker_cmd, "switch_runtime",
        lambda ctx, target, *, snapshot: SwitchReport("colima", target, (("docker", False),)),
    )
    res = runner.invoke(app, ["docker", "use", "orbstack", "-y"])
    assert res.exit_code == 1
    assert "FAIL  docker" in res.output


@pytest.mark.parametrize(
    ("previous", "target", "sudo"),
    [
        (None, "orbstack", True),  # nothing saved: colima is the previous runtime
        ("orbstack", "colima", True),
        ("orbstack", "docker-desktop", False),
        ("docker-desktop", "orbstack", False),
    ],
)
def test_sudo_is_asked_only_when_colima_is_involved(
    on_mac: list[dict[str, Any]], session: _Session,
    previous: str | None, target: str, sudo: bool,
) -> None:
    if previous is not None:
        set_user_value("docker_runtime", previous)
    res = runner.invoke(app, ["docker", "use", target, "-y"])
    assert res.exit_code == 0, res.output
    assert session.sudo == [sudo]
    # Without the sudo session a stray sudo step fails fast (C-R18), it never prompts.
    assert isinstance(on_mac[0]["ex"], NoPromptSudoExecutor) is not sudo


def test_refused_sudo_touches_nothing(
    on_mac: list[dict[str, Any]], session: _Session
) -> None:
    session.granted = False
    res = runner.invoke(app, ["docker", "use", "orbstack", "-y"])
    assert res.exit_code == 1
    assert "sudo" in res.output and "nothing was changed" in res.output
    assert on_mac == []


def test_a_conflicting_env_override_is_refused_before_anything_runs(
    on_mac: list[dict[str, Any]], session: _Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEVBOOST_DOCKER_RUNTIME", "colima")
    res = runner.invoke(app, ["docker", "use", "orbstack", "-y"])
    assert res.exit_code == 2
    assert "DEVBOOST_DOCKER_RUNTIME" in res.output
    assert on_mac == [] and session.sudo == []


def test_a_matching_env_override_is_fine(
    on_mac: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEVBOOST_DOCKER_RUNTIME", "orbstack")
    res = runner.invoke(app, ["docker", "use", "orbstack", "-y"])
    assert res.exit_code == 0, res.output
