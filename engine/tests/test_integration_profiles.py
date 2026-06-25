import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_real_terminal_profile_lists_core_tools() -> None:
    out = subprocess.run(
        ["devboost", "list", "terminal", "--root", str(ROOT)],
        capture_output=True, text=True, check=True,
    ).stdout
    for tool in ("zoxide", "fzf", "starship", "bat", "eza"):
        assert tool in out


def test_real_devtools_profile_nonempty() -> None:
    out = subprocess.run(
        ["devboost", "list", "devtools", "--root", str(ROOT)],
        capture_output=True, text=True, check=True,
    ).stdout
    assert out.strip() != ""
