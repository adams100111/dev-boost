from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.errors import InstallError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.passstore import git, notify
from tests.passstore.fakes import RuleExecutor

FEDORA = OsInfo("fedora", "fedora", "x86_64")
MAC = OsInfo("macos", "macos", "aarch64")
S = Path("/s")


def _ctx(ex: RuleExecutor, os_: OsInfo = FEDORA) -> Ctx:
    return Ctx(os=os_, ex=ex)


#: Every store git call: hook off, and git's own config never signs a commit — including
#: the commits `pull --rebase` replays (I3), which `-c` on `commit` alone would not cover.
LOCAL = {"DEVBOOST_PASS_HOOK": "off", "GIT_CONFIG_COUNT": "1",
         "GIT_CONFIG_KEY_0": "commit.gpgsign", "GIT_CONFIG_VALUE_0": "false"}
NET = {**LOCAL, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "", "SSH_ASKPASS": "",
       "GIT_SSH_COMMAND": "ssh -o BatchMode=yes"}


def test_network_git_calls_disable_the_hook_and_never_prompt() -> None:
    ex = RuleExecutor()
    git.clone(_ctx(ex), "https://github.com/me/s.git", S)
    git.pull(_ctx(ex), S)
    git.push(_ctx(ex), S)
    assert ex.calls == [
        ["git", "clone", "--quiet", "https://github.com/me/s.git", "/s"],
        ["git", "-C", "/s", "pull", "--rebase", "--autostash", "--quiet"],
        ["git", "-C", "/s", "push", "--quiet", "--set-upstream", "origin", "HEAD"],
    ]
    assert ex.envs == [NET, NET, NET]


def test_local_git_calls_disable_the_hook() -> None:
    ex = RuleExecutor(rules=[(("diff", "--cached"), Result(1))])
    git.commit(_ctx(ex), S, "m")
    assert ex.envs and all(e == LOCAL for e in ex.envs)


def test_pull_rebase_never_signs_replayed_commits() -> None:
    ex = RuleExecutor()
    git.pull(_ctx(ex), S)
    env = ex.envs[0]
    assert (env["GIT_CONFIG_COUNT"], env["GIT_CONFIG_KEY_0"], env["GIT_CONFIG_VALUE_0"]) == (
        "1", "commit.gpgsign", "false")


def test_pin_hooks_path_pins_the_store_hooks_dir() -> None:
    ex = RuleExecutor()
    git.pin_hooks_path(_ctx(ex), S)
    assert ex.calls == [["git", "-C", "/s", "config", "--local", "core.hooksPath",
                         ".git/hooks"]]


def test_commit_only_when_staged() -> None:
    ex = RuleExecutor()  # `diff --cached --quiet` exits 0 → nothing staged
    assert git.commit(_ctx(ex), S, "m") is False
    assert not any("commit" in c for c in ex.calls)
    ex2 = RuleExecutor(rules=[(("diff", "--cached"), Result(1))])
    assert git.commit(_ctx(ex2), S, "devboost: x") is True
    assert ex2.calls[-1] == ["git", "-C", "/s", "-c", "commit.gpgsign=false",  # D6: no pinentry
                             "commit", "--quiet", "-m", "devboost: x"]


def test_commit_failure_raises() -> None:
    ex = RuleExecutor(rules=[(("diff", "--cached"), Result(1)), (("commit",), Result(1))])
    with pytest.raises(InstallError):
        git.commit(_ctx(ex), S, "m")


def test_ahead_and_conflicted_parse_output() -> None:
    ex = RuleExecutor(rules=[
        (("rev-list",), Result(0, "3\n")),
        (("--diff-filter=U",), Result(0, ".gpg-id\nweb/x.gpg\n")),
    ])
    assert git.ahead(_ctx(ex), S) == 3
    assert git.conflicted(_ctx(ex), S) == [".gpg-id", "web/x.gpg"]
    assert git.ahead(_ctx(RuleExecutor(rules=[(("rev-list",), Result(128))])), S) == 0


def test_ahead_without_upstream_counts_commits_on_no_remote() -> None:
    ex = RuleExecutor(rules=[
        (("rev-list", "@{u}..HEAD"), Result(128)),
        (("rev-list", "--remotes=origin"), Result(0, "2\n")),
    ])
    assert git.ahead(_ctx(ex), S) == 2
    assert ex.calls[-1] == ["git", "-C", str(S), "rev-list", "--count", "HEAD", "--not",
                            "--remotes=origin"]


def test_history_queries() -> None:
    ex = RuleExecutor(rules=[
        (("-SAAAA",), Result(0, "c1\nc2\n")),
        (("ls-tree",), Result(0, ".gpg-id\nweb/a.gpg\n")),
        (("--diff-filter=A",), Result(0, "\nweb/b.gpg\n\n")),
    ])
    assert git.first_commit_with(_ctx(ex), S, "AAAA") == "c1"
    assert git.files_at(_ctx(ex), S, "c1") == [".gpg-id", "web/a.gpg"]
    assert git.added_since(_ctx(ex), S, "c1") == ["web/b.gpg"]
    assert git.first_commit_with(_ctx(RuleExecutor()), S, "ZZZZ") is None


def test_ntfy_only_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEVBOOST_NTFY_URL", raising=False)
    ex = RuleExecutor()
    assert notify.ntfy(_ctx(ex), "t", "b") is False and ex.calls == []
    monkeypatch.setenv("DEVBOOST_NTFY_URL", "https://ntfy.sh/topic")
    assert notify.ntfy(_ctx(ex), "t", "b", priority="high") is True
    assert ex.calls[0][0] == "curl" and ex.calls[0][-1] == "https://ntfy.sh/topic"
    assert "Priority: high" in ex.calls[0]


def test_native_linux_uses_notify_send_when_present() -> None:
    ex = RuleExecutor(present={"notify-send"})
    assert notify.native(_ctx(ex), "t", "b") is True
    assert ex.calls == [["notify-send", "--app-name=devboost", "t", "b"]]
    assert notify.native(_ctx(RuleExecutor()), "t", "b") is False  # not installed


def test_native_macos_is_a_p2_seam() -> None:
    assert notify._native_argv(MAC, "t", "b") is None


def test_clean_strips_control_chars_and_leading_dashes_and_caps() -> None:
    """Minor (c): record names/os come from the remote — never let them steer notify-send."""
    assert notify.clean("--urgency=critical") == "urgency=critical"
    assert notify.clean(" -lap\x1b[31m\nx\u202e ") == "lap[31mx"
    assert notify.clean("a" * 500) == "a" * 64
    assert notify.clean("b" * 500, limit=10) == "b" * 10
