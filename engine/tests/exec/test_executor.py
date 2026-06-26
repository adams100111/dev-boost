from __future__ import annotations

from devboost.exec.executor import FakeExecutor, RealExecutor, Result


def test_fake_records_calls_and_sudo_prefix() -> None:
    ex = FakeExecutor()
    ex.run(["dnf", "install", "-y", "ripgrep"], sudo=True)
    ex.run(["rpm", "-q", "ripgrep"])
    assert ex.calls == [
        ["sudo", "dnf", "install", "-y", "ripgrep"],
        ["rpm", "-q", "ripgrep"],
    ]


def test_fake_scripts_and_present() -> None:
    ex = FakeExecutor(scripts={"rpm": Result(1)}, present={"rg"})
    assert ex.run(["rpm", "-q", "x"]).code == 1
    assert ex.run(["true"]).ok
    assert ex.which("rg") is True
    assert ex.which("nope") is False


def test_real_which_finds_python() -> None:
    assert RealExecutor().which("python3") is True
    assert RealExecutor().which("definitely-not-a-real-binary-xyz") is False
