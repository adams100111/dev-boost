"""Where things live: the store repo, the local clone, sync state, device name."""

from __future__ import annotations

import os
import re
import shutil
import socket
import sys
from pathlib import Path

from devboost.core.errors import ConfigError
from devboost.core.selfupdate import is_frozen
from devboost.core.userconfig import UserConfig, load_user_config


def origin_url(root: Path) -> str | None:
    """The `origin` remote of the clone at *root*, read from .git/config, or None.

    Parsed rather than shelled out to: this runs during config resolution, where there is
    no executor, and a missing/odd file must degrade to None rather than raise.
    """
    config = root / ".git" / "config"
    try:
        text = config.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    in_origin = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("["):
            in_origin = line.replace(" ", "").lower() in ('[remote"origin"]',)
            continue
        if in_origin and line.lower().startswith("url"):
            _, _, value = line.partition("=")
            return value.strip() or None
    return None


def pass_repo(cfg: UserConfig | None = None) -> str | None:
    """Where the pass store lives, or None when nothing says.

    In order: `DEVBOOST_PASS_REPO`, `pass_repo` in the user config, then the `origin` of an
    existing clone — a machine that already has the store needs no configuration at all.
    There is deliberately no built-in default: a pass store is personal, and one person's
    repo as the fallback makes every other install try to clone a repo it cannot read.
    """
    env = os.environ.get("DEVBOOST_PASS_REPO")
    if env:
        return env
    configured = (cfg if cfg is not None else load_user_config()).pass_repo
    if configured:
        return configured
    return origin_url(store_dir())


#: What to tell someone who has no pass repo configured.
NO_PASS_REPO_FIX = (
    "set it once, either way:\n"
    "  - `pass_repo = \"<owner>/<repo>\"` in ~/.config/devboost/config.toml\n"
    "  - or export DEVBOOST_PASS_REPO=<owner/repo or git url>\n"
    "A private GitHub repo holding your `pass` store; `gh auth login` covers access."
)


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
        raise ConfigError(
            f"pass: {raw!r} is not a usable device name — fix `device_name` in "
            "~/.config/devboost/config.toml, or pass a valid --name"
        )
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
