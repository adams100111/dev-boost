"""lifecycle.diff_drift filters through build_plan, like `verify` does (ruling C-R19, I2)."""

from __future__ import annotations

from devboost.cli import lifecycle as lc
from devboost.core.osinfo import OsInfo
from devboost.core.settings import settings
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx

FEDORA = OsInfo("fedora", "fedora", "x86_64")


def test_diff_never_reports_macos_only_drift_on_linux() -> None:
    """`base` names xcode-clt/homebrew/rosetta directly AND pulls them in transitively
    (pass, pass-store, every brew-backed module's `requires`). None of that is drift on
    a Linux host: build_plan already drops macOS-only modules before diff_drift compares
    verify() against the plan, exactly like `verify` does.
    """
    ctx = Ctx(os=FEDORA, ex=FakeExecutor())
    drift = lc.diff_drift(ctx, ["base"], settings.root)
    assert not {"homebrew", "xcode-clt", "rosetta"} & set(drift)
