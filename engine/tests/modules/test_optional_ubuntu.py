"""Ubuntu/Debian path tests for optional-editors and security-cli modules."""

from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules.optional import JetbrainsToolbox, Neovim, Pass, PassStore

UBUNTU = OsInfo(distro="ubuntu", family="debian", arch="x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=UBUNTU, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Neovim
# ---------------------------------------------------------------------------


def test_neovim_installs_via_apt_on_ubuntu() -> None:
    ctx = _ctx()
    Neovim().install(ctx)
    assert ["sudo", "apt-get", "install", "-y", "neovim"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_neovim_verify_uses_nvim_binary() -> None:
    """Verify checks for 'nvim' binary — same on Ubuntu and Fedora."""
    ctx = _ctx(present={"nvim"})
    assert Neovim().verify(ctx) is True


def test_neovim_verify_false_when_absent() -> None:
    ctx = _ctx()
    assert Neovim().verify(ctx) is False


def test_neovim_no_dnf_calls_on_ubuntu() -> None:
    ctx = _ctx()
    Neovim().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert not any("dnf" in " ".join(c) for c in calls)


# ---------------------------------------------------------------------------
# JetbrainsToolbox — tarball, cross-distro
# ---------------------------------------------------------------------------


def test_jetbrains_toolbox_uses_tarball_on_ubuntu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = _ctx()
    JetbrainsToolbox().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    # Must use sh + curl, not any package manager
    assert calls[0][0] == "sh"
    assert any("jetbrains" in " ".join(c).lower() for c in calls)


def test_jetbrains_toolbox_no_dnf_or_apt_calls_on_ubuntu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = _ctx()
    JetbrainsToolbox().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    # Check executables only (first token or sudo+second) — not the path in arguments
    executables = {c[0] for c in calls} | {c[1] for c in calls if c[0] == "sudo"}
    assert "dnf" not in executables
    assert "apt-get" not in executables


def test_jetbrains_toolbox_verify_checks_bin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    tb_bin = tmp_path / ".local" / "bin" / "jetbrains-toolbox"
    tb_bin.parent.mkdir(parents=True)
    assert JetbrainsToolbox().verify(Ctx(os=UBUNTU, ex=FakeExecutor())) is False
    tb_bin.write_text("#!/bin/sh", encoding="utf-8")
    assert JetbrainsToolbox().verify(Ctx(os=UBUNTU, ex=FakeExecutor())) is True


# ---------------------------------------------------------------------------
# Pass
# ---------------------------------------------------------------------------


def test_pass_installs_via_apt_on_ubuntu() -> None:
    ctx = _ctx()
    Pass().install(ctx)
    assert ["sudo", "apt-get", "install", "-y", "pass"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_pass_verify_uses_pass_binary() -> None:
    ctx = _ctx(present={"pass"})
    assert Pass().verify(ctx) is True


def test_pass_no_dnf_calls_on_ubuntu() -> None:
    ctx = _ctx()
    Pass().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert not any("dnf" in " ".join(c) for c in calls)


# ---------------------------------------------------------------------------
# PassStore — cross-distro git clone / pass init
# ---------------------------------------------------------------------------


def test_pass_store_clones_repo_on_ubuntu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("DEVBOOST_PASS_REPO", "git@github.com:user/pass-store.git")
    ctx = _ctx()
    PassStore().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert any(c[:2] == ["git", "clone"] for c in calls)


def test_pass_store_inits_with_gpg_id_on_ubuntu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("DEVBOOST_PASS_REPO", raising=False)
    monkeypatch.setenv("DEVBOOST_PASS_GPG_ID", "ABCDEF12")
    ctx = _ctx()
    PassStore().install(ctx)
    assert ["pass", "init", "ABCDEF12"] in ctx.ex.calls  # type: ignore[attr-defined]
