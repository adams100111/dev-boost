"""ssh-setup seeds GitHub's SSH host keys.

A fresh Mac has no `~/.ssh/known_hosts` entry for github.com, so the first
`git clone git@github.com:…` dies with "Host key verification failed" — which reads like
a credentials problem and is not one. Found on a real machine: two keys were loaded in the
agent and `gh` was authenticated, yet every SSH clone failed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.exec.primitives import github
from devboost.exec.primitives.github import HttpResponse, host_keys
from devboost.model import Ctx
from devboost.modules import ssh_setup

MAC = OsInfo("macos", "macos", "aarch64")

ED = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl"
RSA = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQCj7ndNxQowgcQnjshcLrqPEiiphnt+VTTvDP6mHBL9j1a"


def _meta(keys: list[str]) -> object:
    def http(method: str, url: str, headers: object, body: object) -> HttpResponse:
        assert url == "https://api.github.com/meta"
        import json as _json

        return HttpResponse(200, _json.dumps({"ssh_keys": keys}))

    return http


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


def test_keys_come_from_githubs_published_metadata_over_tls() -> None:
    """Not `ssh-keyscan`, which asks the server it is trying to authenticate."""
    assert host_keys(_meta([ED, RSA])) == [ED, RSA]  # type: ignore[arg-type]


def test_a_failed_fetch_yields_no_keys_rather_than_raising() -> None:
    def http(method: str, url: str, headers: object, body: object) -> HttpResponse:
        return HttpResponse(503, "nope")

    assert host_keys(http) == []


def test_seeding_writes_github_entries_and_tightens_the_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(github, "host_keys", lambda: [ED, RSA])
    ssh_setup.seed_github_host_keys(Ctx(os=MAC, ex=FakeExecutor()))

    kh = tmp_path / ".ssh" / "known_hosts"
    lines = kh.read_text(encoding="utf-8").splitlines()
    assert lines == [f"github.com {ED}", f"github.com {RSA}"]
    assert kh.stat().st_mode & 0o777 == 0o600


def test_an_entry_the_user_already_trusts_is_never_touched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pinned or hashed github.com entry stays exactly as it is."""
    kh = tmp_path / ".ssh" / "known_hosts"
    kh.parent.mkdir(mode=0o700, parents=True)
    kh.write_text("|1|hashed|entry= ssh-ed25519 AAAAmine github.com\n", encoding="utf-8")
    called: list[bool] = []

    def _fetch() -> list[str]:
        called.append(True)
        return [ED]

    monkeypatch.setattr(github, "host_keys", _fetch)

    ssh_setup.seed_github_host_keys(Ctx(os=MAC, ex=FakeExecutor()))
    assert called == []  # not even fetched
    assert kh.read_text(encoding="utf-8").count("ssh-ed25519") == 1


def test_no_network_warns_and_leaves_the_file_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Seeding is best-effort: it must never fail an install."""
    monkeypatch.setattr(github, "host_keys", lambda: [])
    ssh_setup.seed_github_host_keys(Ctx(os=MAC, ex=FakeExecutor()))  # must not raise
    assert not (tmp_path / ".ssh" / "known_hosts").exists()


def test_existing_file_without_github_keeps_its_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kh = tmp_path / ".ssh" / "known_hosts"
    kh.parent.mkdir(mode=0o700, parents=True)
    kh.write_text("gitlab.com ssh-ed25519 AAAAother", encoding="utf-8")  # no trailing newline
    monkeypatch.setattr(github, "host_keys", lambda: [ED])

    ssh_setup.seed_github_host_keys(Ctx(os=MAC, ex=FakeExecutor()))
    text = kh.read_text(encoding="utf-8")
    assert text.startswith("gitlab.com ssh-ed25519 AAAAother\n")
    assert text.endswith(f"github.com {ED}\n")
