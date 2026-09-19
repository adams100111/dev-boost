"""Where things live: the store repo, the local clone, sync state, device name."""

from __future__ import annotations

import os
import re
import shutil
import socket
import sys
from pathlib import Path

from devboost.core.selfupdate import is_frozen
from devboost.core.userconfig import UserConfig, load_user_config


def pass_repo(cfg: UserConfig | None = None) -> str:
    """Repo name (owner/repo) or URL; env DEVBOOST_PASS_REPO wins."""
    env = os.environ.get("DEVBOOST_PASS_REPO")
    if env:
        return env
    return (cfg if cfg is not None else load_user_config()).pass_repo


def clone_url(repo: str) -> str:
    """`owner/repo` → GitHub HTTPS; URLs and paths pass through."""
    if "://" in repo or repo.startswith(("git@", "/")):
        return repo
    return f"https://github.com/{repo.removesuffix('.git')}.git"


def store_dir() -> Path:
    """$PASSWORD_STORE_DIR › ~/.password-store."""
    override = os.environ.get("PASSWORD_STORE_DIR")
    if override:
        return Path(override)
    return Path(os.environ["HOME"]) / ".password-store"


def state_dir() -> Path:
    """$XDG_STATE_HOME/devboost › ~/.local/state/devboost."""
    base = os.environ.get("XDG_STATE_HOME")
    root = Path(base) if base else Path(os.environ["HOME"]) / ".local" / "state"
    return root / "devboost"


def sanitize_name(raw: str) -> str:
    """Lower-case, [a-z0-9-] only; device names are file names in the store."""
    name = re.sub(r"[^a-z0-9-]+", "-", raw.strip().lower()).strip("-")
    if not name:
        raise ValueError(f"not a usable device name: {raw!r}")
    return name[:63]


def device_name(
    cfg: UserConfig | None = None, hostname: str | None = None
) -> str:
    """Config device_name › hostname (or socket.gethostname()), sanitized."""
    c = cfg if cfg is not None else load_user_config()
    if c.device_name:
        return sanitize_name(c.device_name)
    host = hostname if hostname is not None else socket.gethostname()
    return sanitize_name(host.split(".", 1)[0])


def devboost_bin() -> str:
    """Absolute path for units/hooks: frozen binary or devboost on PATH."""
    if is_frozen():
        return sys.executable
    return shutil.which("devboost") or "devboost"
