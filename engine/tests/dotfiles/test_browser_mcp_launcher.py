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


# --- security: pinned server (never @latest), one version everywhere -------------------------

REPO = Path(__file__).resolve().parents[3]
ALIASES = REPO / "dotfiles" / "dot_config" / "devboost" / "aliases.sh"


def _run_env(tmp_path: Path, **extra: str) -> subprocess.CompletedProcess[str]:
    bash = shutil.which("bash")
    assert bash is not None
    env = {"HOME": str(tmp_path), "PATH": str(_fake_bin(tmp_path)),
           "CHROME_APP": str(tmp_path / "absent.app"), **extra}
    return subprocess.run([bash, str(LAUNCHER)], env=env, capture_output=True, text=True)


def test_launcher_runs_the_pinned_server(tmp_path: Path) -> None:
    from devboost.modules._playwright_mcp import PLAYWRIGHT_MCP_PKG

    out = _run(tmp_path, tmp_path / "absent.app")
    assert out.startswith(f"-y {PLAYWRIGHT_MCP_PKG} ")
    assert PLAYWRIGHT_MCP_PKG == "@playwright/mcp@0.0.82"


def test_launcher_takes_the_version_the_launchagent_passes(tmp_path: Path) -> None:
    res = _run_env(tmp_path, PLAYWRIGHT_MCP_VERSION="0.0.83")
    assert res.returncode == 0 and res.stdout.startswith("-y @playwright/mcp@0.0.83 ")


@pytest.mark.parametrize("bad", ["latest", "next", "^0.0.82", "0.0.82 --host 0.0.0.0", ".1"])
def test_launcher_rejects_a_non_exact_version(tmp_path: Path, bad: str) -> None:
    res = _run_env(tmp_path, PLAYWRIGHT_MCP_VERSION=bad)
    assert res.returncode == 1
    assert "exact x.y.z" in res.stderr and res.stdout == ""


def test_bash_defaults_match_the_engine_pin() -> None:
    """The launcher (Linux systemd + macOS) and `pw-mcp` default to the engine's one pin."""
    from devboost.modules._playwright_mcp import PLAYWRIGHT_MCP_VERSION

    want = f"${{PLAYWRIGHT_MCP_VERSION:-{PLAYWRIGHT_MCP_VERSION}}}"
    assert want in LAUNCHER.read_text(encoding="utf-8")
    assert want in ALIASES.read_text(encoding="utf-8")


def test_nothing_starts_playwright_mcp_at_latest() -> None:
    roots = [REPO / "dotfiles", REPO / "engine" / "src", REPO / "docs"]
    skip = {"superpowers"}  # dated plans/specs record history, not what runs
    hits = [
        str(f.relative_to(REPO))
        for root in roots
        for f in root.rglob("*")
        if f.is_file() and not skip & set(f.relative_to(REPO).parts)
        and "@playwright/mcp@latest" in f.read_text(encoding="utf-8", errors="ignore")
    ]
    assert hits == []


def test_pw_mcp_never_binds_every_interface() -> None:
    text = ALIASES.read_text(encoding="utf-8")
    assert "bind=0.0.0.0" not in text
    assert "refusing to bind 0.0.0.0" in text
