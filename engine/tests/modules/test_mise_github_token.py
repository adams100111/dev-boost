"""mise points itself at `gh` for GitHub tokens, so tool installs are not rate-limited.

Unauthenticated, GitHub allows 60 API requests per hour **per IP**. A `base` install
resolves seven GitHub-backed tools, and anything else on the same IP shares that budget:
a second machine, CI, an office NAT. Past the limit GitHub answers 403 and the tools fail
to install — which is what happened on a clean-VM rehearsal.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.mise import _GH_CREDENTIAL_CMD, _GH_CREDENTIAL_KEY, Mise

MAC = OsInfo("macos", "macos", "aarch64")
LINUX = OsInfo("fedora", "fedora", "x86_64")

GET = ["mise", "settings", "get", _GH_CREDENTIAL_KEY]


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))  # no nvm/sdkman to migrate


def _sets(ex: FakeExecutor) -> list[list[str]]:
    return [c for c in ex.calls if c[:3] == ["mise", "settings", "set"]]


def test_install_points_mise_at_gh_for_github_tokens() -> None:
    """`gh` is already in the `cli` profile and authenticated per user, which lifts the
    limit to 5000/hour. mise runs the command on demand, so no token is written to disk
    or exported into the environment."""
    ex = FakeExecutor(scripts={"mise": Result(1)})  # setting unset
    Mise().install(Ctx(os=MAC, ex=ex))
    assert _sets(ex) == [["mise", "settings", "set", _GH_CREDENTIAL_KEY, _GH_CREDENTIAL_CMD]]


def test_install_is_idempotent_once_the_command_is_set() -> None:
    ex = FakeExecutor(scripts={"mise": Result(0, stdout=f"{_GH_CREDENTIAL_CMD}\n")})
    Mise().install(Ctx(os=MAC, ex=ex))
    assert _sets(ex) == []


def test_a_credential_command_the_user_chose_is_kept() -> None:
    """A work PAT or a GitHub Enterprise host is the user's call, not ours."""
    theirs = "cat /run/secrets/gh-token"
    ex = FakeExecutor(scripts={"mise": Result(0, stdout=f"{theirs}\n")})
    Mise().install(Ctx(os=MAC, ex=ex))
    assert _sets(ex) == []


def test_linux_gets_the_same_treatment() -> None:
    """The rate limit is per IP, not per OS."""
    ex = FakeExecutor(scripts={"mise": Result(1)}, present={"mise"})
    Mise().install(Ctx(os=LINUX, ex=ex))
    assert _sets(ex) == [["mise", "settings", "set", _GH_CREDENTIAL_KEY, _GH_CREDENTIAL_CMD]]


def test_the_command_reads_the_host_mise_asks_about() -> None:
    """`$MISE_CREDENTIAL_HOST` is expanded by mise per host, so a GitHub Enterprise host
    gets that host's token rather than github.com's. Single-quoted so the shell running
    devboost never expands it."""
    assert "$MISE_CREDENTIAL_HOST" in _GH_CREDENTIAL_CMD
    assert _GH_CREDENTIAL_CMD.startswith("gh auth token ")


def test_verify_stays_with_the_strategy() -> None:
    """The os-strategy contract: verify must match the declared strategy, so the setting
    is ensured by install() (idempotent) rather than reported as 'not installed'."""
    ex = FakeExecutor(present={"mise"})
    Mise().verify(Ctx(os=LINUX, ex=ex))
    assert GET not in ex.calls
