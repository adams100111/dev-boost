"""lifecycle.diff_drift filters through build_plan, like `verify` does (ruling C-R19, I2)."""

from __future__ import annotations

from devboost.cli import lifecycle as lc
from devboost.core.osinfo import OsInfo
from devboost.core.settings import settings
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from tests.scripted import Scripted

FEDORA = OsInfo("fedora", "fedora", "x86_64")
MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")


def test_diff_never_reports_macos_only_drift_on_linux() -> None:
    """`base` names xcode-clt/homebrew/rosetta directly AND pulls them in transitively
    (pass, pass-store, every brew-backed module's `requires`). None of that is drift on
    a Linux host: build_plan already drops macOS-only modules before diff_drift compares
    verify() against the plan, exactly like `verify` does.
    """
    ctx = Ctx(os=FEDORA, ex=FakeExecutor())
    drift = lc.diff_drift(ctx, ["base"], settings.root)
    assert not {"homebrew", "xcode-clt", "rosetta"} & set(drift)


def test_diff_on_a_mac_reports_the_missing_foundation_but_not_linux_only_modules() -> None:
    """Core review M3: on a fresh Mac the foundation IS drift, while the Linux-only
    modules `base` names (rpmfusion, dnf-tune, fedora-third-party, flatpak) are dropped
    by build_plan and never reported."""
    ex = Scripted(answers={
        ("xcode-select", "-p"): Result(2),  # no CLT
        ("brew",): Result(127),             # no Homebrew
        ("arch",): Result(1, stderr="Bad CPU type in executable"),  # no Rosetta
    })
    drift = set(lc.diff_drift(Ctx(os=MAC, ex=ex), ["base"], settings.root))
    assert {"xcode-clt", "homebrew", "rosetta"} <= drift
    assert not {"rpmfusion", "dnf-tune", "fedora-third-party", "flatpak"} & drift
