from __future__ import annotations

import pytest

from devboost.core.errors import ConfigError, NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.pi_harness import PiHarness

FEDORA = OsInfo("fedora", "fedora", "x86_64")


@pytest.fixture(autouse=True)
def _harness_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test but the unset one needs a repo: there is no built-in default any more."""
    monkeypatch.setenv("DEVBOOST_HARNESS_REPO", "adams100111/agent-harness")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def _joined(ctx: Ctx) -> list[str]:
    return [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]


def test_verify_uses_harness_binary() -> None:
    assert PiHarness().verify(_ctx(present={"harness"})) is True
    assert PiHarness().verify(_ctx()) is False


def test_bootstrap_clones_repo_and_runs_installer() -> None:
    ctx = _ctx(present={"node", "harness"})
    PiHarness().install(ctx)
    j = _joined(ctx)
    assert any("github.com/adams100111/agent-harness" in c for c in j)
    assert any("install.sh" in c for c in j)
    assert any("HARNESS_REF=main" in c for c in j)
    # install.sh must receive HARNESS_REPO as a full URL (it re-clones the repo itself).
    assert any("HARNESS_REPO=https://github.com/adams100111/agent-harness" in c for c in j)


def test_provisions_node_when_absent() -> None:
    ctx = _ctx(present={"harness"})  # node absent
    PiHarness().install(ctx)
    assert any("node@lts" in c for c in _joined(ctx))


def test_bootstrap_failure_raises_configerror() -> None:
    ctx = _ctx(present={"node"}, scripts={"sh": Result(1)})
    with pytest.raises(ConfigError):
        PiHarness().install(ctx)


def test_env_overrides_repo_and_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVBOOST_HARNESS_REPO", "me/fork")
    monkeypatch.setenv("DEVBOOST_HARNESS_REF", "v1.2.3")
    ctx = _ctx(present={"node", "harness"})
    PiHarness().install(ctx)
    j = _joined(ctx)
    assert any("github.com/me/fork" in c for c in j)
    assert any("HARNESS_REF=v1.2.3" in c for c in j)
    assert any("HARNESS_REPO=https://github.com/me/fork" in c for c in j)


def test_provisions_from_pass_when_store_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    monkeypatch.setenv("PASSWORD_STORE_DIR", str(tmp_path))  # tmp_path exists
    ctx = _ctx(present={"node", "harness", "pass"})
    PiHarness().install(ctx)
    j = _joined(ctx)
    assert any("harness secrets init --backend pass" in c for c in j)
    assert any(c == "harness provision" for c in j)


def test_skips_provision_without_pass_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PASSWORD_STORE_DIR", raising=False)
    ctx = _ctx(present={"node", "harness"})  # no pass
    PiHarness().install(ctx)
    assert not any("secrets init" in c for c in _joined(ctx))


def test_guarded_install_never_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    # bootstrap (`sh`) succeeds by default; every `harness ...` call fails.
    monkeypatch.setenv("PASSWORD_STORE_DIR", str(tmp_path))
    ctx = _ctx(present={"node", "harness", "pass"}, scripts={"harness": Result(1)})
    PiHarness().install(ctx)  # must NOT raise
    assert any("harness install --yes" in c for c in _joined(ctx))


def test_no_harness_repo_configured_is_blocked_not_a_clone_of_a_private_repo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """dev-boost used to default to its author's PRIVATE agent-harness repo, so every
    other install cloned something it could not read. With nothing configured there is
    simply no source to build from: that is a step for the user, reported blocked."""
    monkeypatch.delenv("DEVBOOST_HARNESS_REPO", raising=False)
    ctx = _ctx(present={"node", "harness"})
    with pytest.raises(NeedsUser, match="no harness repo is configured") as err:
        PiHarness().install(ctx)
    assert "DEVBOOST_HARNESS_REPO" in err.value.how_to_fix
    assert not [c for c in _joined(ctx) if "git clone" in c]


def test_a_full_git_url_is_used_as_given(monkeypatch: pytest.MonkeyPatch) -> None:
    """Not everyone's harness lives on github.com."""
    monkeypatch.setenv("DEVBOOST_HARNESS_REPO", "git@git.example.com:team/harness.git")
    ctx = _ctx(present={"node", "harness"})
    PiHarness().install(ctx)
    assert any("git@git.example.com:team/harness.git" in c for c in _joined(ctx))
    assert not [c for c in _joined(ctx) if "github.com/git@" in c]
