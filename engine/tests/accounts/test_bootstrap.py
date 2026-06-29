from __future__ import annotations

from pathlib import Path

import pytest

from devboost.accounts import bootstrap
from devboost.accounts.config import ManagedUser
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx


def _user(**over: object) -> ManagedUser:
    base = dict(
        name="dev", enabled=True, shell="/bin/bash", lock_shell=False, linger=False,
        privilege="none", sudo_commands=(), ram=None, cpu=None, tasks=None, disk=None,
        ssh_authorized_keys=(), bootstrap_profiles=("terminal",),
    )
    base.update(over)
    return ManagedUser(**base)  # type: ignore[arg-type]


def test_bootstrap_demotes_unprivileged_commands_to_user(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Stub the heavy pipeline so the test asserts only the executor wiring.
    seen: dict[str, object] = {}

    def fake_run_profiles(c: Ctx, tokens: list[str], root: Path) -> None:
        seen["executor"] = type(c.ex).__name__
        seen["tokens"] = tokens
        c.ex.run(["chezmoi", "apply"])  # an unprivileged user-scoped command

    monkeypatch.setattr(bootstrap, "_run_profiles", fake_run_profiles)
    inner = FakeExecutor()
    ctx = Ctx(os=OsInfo("fedora", "fedora", "x86_64"), ex=inner)
    bootstrap.bootstrap_user(ctx, _user(), root=tmp_path)
    assert seen["executor"] == "DemotingExecutor"
    assert seen["tokens"] == ["terminal"]
    assert ["sudo", "-u", "dev", "-H", "chezmoi", "apply"] in inner.calls
