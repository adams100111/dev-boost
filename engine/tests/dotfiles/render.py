"""Render a chezmoi template from the in-repo source for a chosen OS and HOME.

Unlike conftest's ``chezmoi_render`` (which takes a distro and inherits HOME), this pins
``.chezmoi.homeDir`` and HOME to *home*, so templates that ``stat`` a marker file under
the home directory can be tested both with and without it. Callers mark their tests
``slow`` and skip when ``CHEZMOI`` is None (ruling M5-D12).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "dotfiles"
CHEZMOI = shutil.which("chezmoi")


def render_template(rel: str, os_name: str, home: Path) -> str:
    assert CHEZMOI is not None
    data = json.dumps({"chezmoi": {"os": os_name, "homeDir": str(home)}})
    res = subprocess.run(
        [CHEZMOI, "execute-template", "--source", str(SRC), "--override-data", data],
        input=(SRC / rel).read_text(encoding="utf-8"),
        text=True,
        capture_output=True,
        env={**os.environ, "HOME": str(home)},
        check=True,
    )
    return res.stdout
