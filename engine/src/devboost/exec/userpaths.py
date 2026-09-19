"""Where per-user tool directories live — one answer for the executor and config writers.

Lives in the exec layer so ``executor.py`` can use it; modules (e.g. ``_zed``) import it
from here rather than keeping their own copy.
"""

from __future__ import annotations

import os
from pathlib import Path


def mise_shims(home: Path) -> Path:
    """mise's shim dir, resolved the way mise resolves its data dir: ``$MISE_DATA_DIR``,
    then ``$XDG_DATA_HOME/mise``, then ``~/.local/share/mise`` (an empty variable counts as
    unset)."""
    data = os.environ.get("MISE_DATA_DIR")
    if data:
        return Path(data) / "shims"
    xdg = os.environ.get("XDG_DATA_HOME")
    return (Path(xdg) if xdg else home / ".local" / "share") / "mise" / "shims"


def dotnet_root(home: Path) -> Path:
    """The per-user .NET SDK that ``dotnet-install.sh`` writes on macOS (dotnet-sdk module)."""
    return home / ".dotnet"
