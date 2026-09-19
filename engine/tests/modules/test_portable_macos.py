"""Modules verified to run unchanged on macOS, and the chezmoi-repo / credential fixes."""

from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.errors import ConfigError, NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx, Module
from devboost.modules.base import ChezmoiRepo
from devboost.modules.claude_code import ClaudeCode
from devboost.modules.claude_mcp import ClaudeMcp
from devboost.modules.claude_plugins import ClaudePlugins
from devboost.modules.claude_skills import ClaudeSkills
from devboost.modules.codex_code import CodexCode
from devboost.modules.codex_config import CodexConfig
from devboost.modules.codex_mcp import CodexMcp
from devboost.modules.codex_plugins import CodexPlugins
from devboost.modules.codex_skills import CodexSkills
from devboost.modules.dev_stacks import (
    Aspire,
    DataServices,
    DevopsLsp,
    DevopsTools,
    DotnetLsp,
    Expo,
    LaravelLsp,
    PythonLsp,
    WebLsp,
    WebRuntimes,
)
from devboost.modules.editors import FreshLsp
from devboost.modules.pi_harness import PiHarness
from devboost.modules.shell import ClaudeNotify
from devboost.modules.tpm import TmuxPersist, Tpm
from tests.core.test_macos_contract import resolvable_on_macos

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
PORTABLE: list[type[Module]] = [
    ClaudeCode, ClaudeMcp, ClaudePlugins, ClaudeSkills, ClaudeNotify,
    CodexCode, CodexConfig, CodexMcp, CodexPlugins, CodexSkills, PiHarness,
    Tpm, TmuxPersist, WebRuntimes, DevopsTools, Expo, DataServices, Aspire, DotnetLsp,
    FreshLsp, PythonLsp, WebLsp, LaravelLsp, DevopsLsp, ChezmoiRepo,
]


@pytest.mark.parametrize("cls", PORTABLE)
def test_verified_portable(cls: type[Module]) -> None:
    assert cls.portable is True
    assert resolvable_on_macos(cls)


def test_chezmoi_repo_never_waits_on_a_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVBOOST_DOTFILES_REPO", "https://github.com/user/dotfiles")
    ex = FakeExecutor()
    ChezmoiRepo().install(Ctx(os=MAC, ex=ex))
    assert ["chezmoi", "init", "--apply", "--force", "https://github.com/user/dotfiles"] in ex.calls


def test_chezmoi_repo_without_a_repo_needs_the_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEVBOOST_DOTFILES_REPO", raising=False)
    monkeypatch.setenv("DEVBOOST_BOOTSTRAP_DIR", str(tmp_path))  # no secrets bundle here
    with pytest.raises(NeedsUser, match="DEVBOOST_DOTFILES_REPO"):
        ChezmoiRepo().install(Ctx(os=FEDORA, ex=FakeExecutor(scripts={"age": Result(1)})))


def test_pi_harness_failure_points_at_the_real_github_auth() -> None:
    ex = FakeExecutor(scripts={"sh": Result(1)})
    with pytest.raises(ConfigError) as exc:
        PiHarness().install(Ctx(os=MAC, ex=ex))
    assert "gh auth status" in str(exc.value)
    assert "PAT from the secrets bundle" not in str(exc.value)
