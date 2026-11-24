from __future__ import annotations

import json

import pytest

from devboost.core import log
from devboost.core.errors import InstallError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.media.catalog import worktrunk_pin
from devboost.model import Ctx
from devboost.modules.worktrunk import Worktrunk, WorktrunkAgents

FEDORA_X86 = OsInfo(distro="fedora", family="fedora", arch="x86_64")
UBUNTU_ARM = OsInfo(distro="ubuntu", family="debian", arch="aarch64")
MAC_ARM = OsInfo(distro="macos", family="macos", arch="aarch64")

CLAUDE_HAS = json.dumps([{"id": "worktrunk@worktrunk", "enabled": True}])
CODEX_HAS = json.dumps(
    {
        "installed": [
            {"name": "worktrunk", "installed": True},
            {"name": "worktrunk-markers", "installed": True},
        ]
    }
)


def _ctx(os_: OsInfo = FEDORA_X86, **kw: object) -> Ctx:
    return Ctx(os=os_, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_profiles() -> None:
    assert Worktrunk.profiles == ("cli", "brain-tools")
    assert WorktrunkAgents.profiles == ("cli", "brain-tools")
    assert Worktrunk in WorktrunkAgents.requires


def test_pin_has_every_supported_asset() -> None:
    pin = worktrunk_pin()
    assert set(pin.assets) == {"linux-x86_64", "linux-aarch64", "macos-aarch64"}
    for a in pin.assets.values():
        assert a.url.startswith("https://github.com/max-sixty/worktrunk/releases/download/")
        assert f"v{pin.version}/" in a.url and a.url.endswith(".tar.xz")


def test_verify_needs_wt_at_or_above_the_pin() -> None:
    assert Worktrunk().verify(_ctx(present=set())) is False
    want = worktrunk_pin().version
    ok = _ctx(present={"wt"}, scripts={"wt": Result(0, stdout=f"wt v{want}")})
    assert Worktrunk().verify(ok) is True
    old = _ctx(present={"wt"}, scripts={"wt": Result(0, stdout="wt v0.1.0")})
    assert Worktrunk().verify(old) is False
    broken = _ctx(present={"wt"}, scripts={"wt": Result(1, stdout="")})
    assert Worktrunk().verify(broken) is False


@pytest.mark.parametrize(
    ("os_", "asset", "check"),
    [
        (FEDORA_X86, "x86_64-unknown-linux-musl", "sha256sum -c -"),
        (UBUNTU_ARM, "aarch64-unknown-linux-musl", "sha256sum -c -"),
        (MAC_ARM, "aarch64-apple-darwin", "shasum -a 256 -c -"),
    ],
)
def test_install_downloads_verifies_and_installs_both_binaries(
    monkeypatch: pytest.MonkeyPatch, os_: OsInfo, asset: str, check: str
) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    ctx = _ctx(os_)
    Worktrunk().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert len(calls) == 1 and calls[0][:2] == ["sh", "-c"]
    script = calls[0][2]
    assert f"worktrunk-{asset}.tar.xz" in script
    assert check in script
    assert script.index(check) < script.index("tar -xJf")  # verify before unpacking
    assert "trap" in script
    assert "for b in wt git-wt" in script and "/home/tester/.local/bin/$b" in script
    # Shell integration belongs to the chezmoi-managed rc files, never this module.
    assert "shell install" not in script


def test_install_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    ctx = _ctx(scripts={"sh": Result(1, stderr="FAILED")})
    with pytest.raises(InstallError):
        Worktrunk().install(ctx)


def _wt_calls(ctx: Ctx) -> list[list[str]]:
    return [c for c in ctx.ex.calls if c[:1] == ["wt"]]  # type: ignore[attr-defined]


def test_agents_install_both_harnesses_when_missing() -> None:
    ctx = _ctx(
        present={"wt", "claude", "codex"},
        scripts={"claude": Result(0, stdout="[]"), "codex": Result(0, stdout="{}")},
    )
    assert WorktrunkAgents().verify(ctx) is False
    WorktrunkAgents().install(ctx)
    assert _wt_calls(ctx) == [
        ["wt", "config", "plugins", "claude", "install", "--yes"],
        ["wt", "config", "plugins", "codex", "install", "--yes"],
    ]


def test_agents_skip_a_harness_that_already_has_them() -> None:
    ctx = _ctx(
        present={"wt", "claude", "codex"},
        scripts={"claude": Result(0, stdout=CLAUDE_HAS), "codex": Result(0, stdout="{}")},
    )
    WorktrunkAgents().install(ctx)
    assert _wt_calls(ctx) == [["wt", "config", "plugins", "codex", "install", "--yes"]]


def test_agents_codex_needs_the_markers_plugin_too() -> None:
    only_skill = json.dumps({"installed": [{"name": "worktrunk", "installed": True}]})
    ctx = _ctx(present={"wt", "codex"}, scripts={"codex": Result(0, stdout=only_skill)})
    assert WorktrunkAgents().verify(ctx) is False


def test_agents_verified_when_every_present_harness_has_them() -> None:
    ctx = _ctx(
        present={"wt", "claude", "codex"},
        scripts={"claude": Result(0, stdout=CLAUDE_HAS), "codex": Result(0, stdout=CODEX_HAS)},
    )
    assert WorktrunkAgents().verify(ctx) is True
    # Only claude on the box: codex is not required.
    ctx = _ctx(present={"wt", "claude"}, scripts={"claude": Result(0, stdout=CLAUDE_HAS)})
    assert WorktrunkAgents().verify(ctx) is True


def test_agents_no_harness_warns_and_does_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    warned: list[str] = []
    monkeypatch.setattr(log, "warn", warned.append)
    ctx = _ctx(present={"wt"})
    WorktrunkAgents().install(ctx)
    assert _wt_calls(ctx) == []
    assert warned and "neither claude nor codex" in warned[0]


def test_agents_failure_is_non_blocking(monkeypatch: pytest.MonkeyPatch) -> None:
    warned: list[str] = []
    monkeypatch.setattr(log, "warn", warned.append)
    ctx = _ctx(
        present={"wt", "claude"},
        scripts={"claude": Result(0, stdout="[]"), "wt": Result(1, stderr="boom")},
    )
    WorktrunkAgents().install(ctx)
    assert warned and "boom" in warned[0]
