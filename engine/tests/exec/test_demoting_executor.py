from __future__ import annotations

from devboost.exec.executor import DemotingExecutor, FakeExecutor, NoPromptSudoExecutor, Result


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


# --- NoPromptSudoExecutor (ruling C-R18) -------------------------------------------


def test_no_prompt_sudo_runs_root_steps_as_sudo_n() -> None:
    inner = FakeExecutor(present={"brew"})
    ex = NoPromptSudoExecutor(inner)
    ex.run(["softwareupdate", "--install-rosetta"], sudo=True)
    ex.run(["brew", "list"])
    assert inner.calls == [
        ["sudo", "-n", "softwareupdate", "--install-rosetta"],
        ["brew", "list"],
    ]
    assert ex.which("brew") is True and ex.which("nope") is False


def test_no_prompt_sudo_passes_the_failure_through() -> None:
    # `sudo -n` without a cached timestamp exits 1 "a password is required": the step
    # fails at once instead of waiting on a prompt nobody can see.
    denied = Result(1, stderr="sudo: a password is required")
    ex = NoPromptSudoExecutor(FakeExecutor(scripts={"sudo": denied}))
    assert ex.run(["touch", "/x"], sudo=True) == denied
