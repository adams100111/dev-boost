"""The browser-mcp launcher picks Chrome on macOS (CHROME_APP) without a PATH binary."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

LAUNCHER = (
    Path(__file__).resolve().parents[3] / "dotfiles" / "dot_local" / "bin"
    / "executable_browser-mcp"
)

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not installed")


def _fake_bin(tmp_path: Path) -> Path:
    """PATH holds only fakes + `head`, so a google-chrome on the host (CI images ship one)
    cannot leak into the channel choice."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "tailscale").write_text("#!/bin/sh\necho 100.64.0.7\n", encoding="utf-8")
    (bin_ / "npx").write_text('#!/bin/sh\necho "$@"\n', encoding="utf-8")
    for f in bin_.iterdir():
        f.chmod(0o755)
    head = shutil.which("head")
    assert head is not None
    (bin_ / "head").symlink_to(head)
    return bin_


def _run(tmp_path: Path, chrome_app: Path) -> str:
    bash = shutil.which("bash")
    assert bash is not None
    env = {"HOME": str(tmp_path), "PATH": str(_fake_bin(tmp_path)), "CHROME_APP": str(chrome_app)}
    out = subprocess.run(
        [bash, str(LAUNCHER)], env=env, capture_output=True, text=True, check=True
    )
    return out.stdout


def test_chrome_app_bundle_selects_the_chrome_channel(tmp_path: Path) -> None:
    app = tmp_path / "Google Chrome.app"
    app.mkdir()
    assert "--browser chrome" in _run(tmp_path, app)


def test_no_chrome_falls_back_to_chromium(tmp_path: Path) -> None:
    out = _run(tmp_path, tmp_path / "absent.app")
    assert "--browser chromium" in out
    assert "--host 100.64.0.7" in out and "--allowed-hosts 100.64.0.7:8931" in out


def test_launcher_is_valid_bash() -> None:
    subprocess.run(["bash", "-n", str(LAUNCHER)], check=True, env=dict(os.environ))
