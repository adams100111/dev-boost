from __future__ import annotations

from devboost.exec.executor import DemotingExecutor, FakeExecutor


def test_privileged_command_runs_as_root_directly() -> None:
    inner = FakeExecutor()
    DemotingExecutor(inner, "dev").run(["dnf", "install", "-y", "ripgrep"], sudo=True)
    # sudo=False passed to inner -> no 'sudo' prefix recorded
    assert inner.calls == [["dnf", "install", "-y", "ripgrep"]]


def test_unprivileged_command_demoted_to_target_user() -> None:
    inner = FakeExecutor()
    DemotingExecutor(inner, "dev").run(["chezmoi", "apply"])
    assert inner.calls == [["sudo", "-u", "dev", "-H", "chezmoi", "apply"]]


def test_which_delegates() -> None:
    inner = FakeExecutor(present={"git"})
    ex = DemotingExecutor(inner, "dev")
    assert ex.which("git") is True
    assert ex.which("nope") is False
