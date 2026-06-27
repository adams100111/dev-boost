"""Self-update support for the frozen dev-boost binary."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import stat
import sys
import tempfile
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import devboost
from devboost.exec.resources import injection_archive_path

REPO = "adams100111/dev-boost"
LATEST = f"https://github.com/{REPO}/releases/latest/download"

# Injectable function types for hermetic testing.
type FetchUrlFn = Callable[[str], str]
type FetchFileFn = Callable[[str, Path], None]


# ---------------------------------------------------------------------------
# Network helpers (used as defaults; replace in tests)
# ---------------------------------------------------------------------------


def _default_fetch_url(url: str) -> str:
    """Follow redirects and return the final URL."""
    req = urllib.request.Request(url, headers={"User-Agent": "devboost-selfupdate/1"})
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        return str(resp.geturl())


def _default_fetch_file(url: str, dest: Path) -> None:
    """Stream *url* into *dest*."""
    req = urllib.request.Request(url, headers={"User-Agent": "devboost-selfupdate/1"})
    with urllib.request.urlopen(req, timeout=120) as resp, dest.open("wb") as fh:  # noqa: S310
        while True:
            chunk: bytes = resp.read(65536)
            if not chunk:
                break
            fh.write(chunk)


# ---------------------------------------------------------------------------
# Public API — version detection
# ---------------------------------------------------------------------------


def latest_version(fetch_url: FetchUrlFn | None = None) -> str | None:
    """Return the latest release version string (e.g. ``'1.2.3'``), or ``None`` on any error.

    Resolves by following the GitHub ``/releases/latest`` redirect to the tag URL
    ``…/releases/tag/vX.Y.Z`` and parsing the version from the final path component.
    """
    _fetch = fetch_url if fetch_url is not None else _default_fetch_url
    try:
        final_url = _fetch(f"https://github.com/{REPO}/releases/latest")
        tag = final_url.rstrip("/").rsplit("/", 1)[-1]
        if tag.startswith("v"):
            tag = tag[1:]
        parts = tag.split(".")
        if len(parts) >= 2 and all(p.isdigit() for p in parts):
            return tag
        return None
    except Exception:
        return None


def version_tuple(v: str) -> tuple[int, ...]:
    """Parse a dotted-integer version string into a comparable tuple."""
    try:
        return tuple(int(p) for p in v.split("."))
    except ValueError:
        return ()


def is_frozen() -> bool:
    """Return ``True`` when running inside a PyInstaller frozen binary."""
    return hasattr(sys, "_MEIPASS")


# ---------------------------------------------------------------------------
# Frozen-binary update
# ---------------------------------------------------------------------------


def _arch() -> str:
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x86_64"
    if machine in ("aarch64", "arm64"):
        return "aarch64"
    raise RuntimeError(f"unsupported architecture: {machine}")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _atomic_replace(src: Path, dst: Path, mode: int) -> None:
    """Copy *src* to a tempfile in *dst*'s parent directory, set *mode*, then rename.

    Using a tempfile in the same directory as *dst* ensures the rename is always
    on the same filesystem (i.e. atomic on Linux, no EXDEV across mount points).
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=dst.parent)
    tmp_path = Path(tmp_name)
    try:
        os.close(fd)
        shutil.copy2(src, tmp_path)
        tmp_path.chmod(mode)
        os.replace(tmp_path, dst)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def update_frozen(
    fetch_url: FetchUrlFn | None = None,
    fetch_file: FetchFileFn | None = None,
) -> tuple[str, str]:
    """Download, verify checksums, and atomically install the latest release.

    Returns ``(old_version, new_version)``.
    Raises ``RuntimeError`` on download failure or checksum mismatch.
    """
    _fetch_url = fetch_url if fetch_url is not None else _default_fetch_url
    _fetch_file = fetch_file if fetch_file is not None else _default_fetch_file

    new_ver = latest_version(_fetch_url)
    if new_ver is None:
        raise RuntimeError("could not determine latest version from the GitHub release redirect")

    arch = _arch()
    bin_name = f"devboost-{arch}"
    tar_name = f"devboost-{arch}.tar.gz"

    with tempfile.TemporaryDirectory(prefix="devboost-update-") as tmpdir:
        tmp = Path(tmpdir)

        try:
            _fetch_file(f"{LATEST}/checksums.txt", tmp / "checksums.txt")
            _fetch_file(f"{LATEST}/{bin_name}", tmp / bin_name)
            _fetch_file(f"{LATEST}/{tar_name}", tmp / tar_name)
        except Exception as exc:
            raise RuntimeError(f"download failed: {exc}") from exc

        # Parse "checksums.txt" — each line is "<sha256hash>  <filename>"
        expected: dict[str, str] = {}
        for line in (tmp / "checksums.txt").read_text(encoding="utf-8").splitlines():
            halves = line.split("  ", 1)
            if len(halves) == 2:
                expected[halves[1].strip()] = halves[0].strip()

        for fname in (bin_name, tar_name):
            if fname not in expected:
                raise RuntimeError(f"no checksum entry for {fname} in checksums.txt")
            actual = _sha256_file(tmp / fname)
            if actual != expected[fname]:
                raise RuntimeError(
                    f"checksum mismatch for {fname}: expected {expected[fname]}, got {actual}"
                )

        real_binary = Path(sys.executable).resolve()
        real_archive = injection_archive_path(arch)

        _mode_exe = (
            stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH
        )
        _mode_data = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH

        _atomic_replace(tmp / bin_name, real_binary, _mode_exe)
        _atomic_replace(tmp / tar_name, real_archive, _mode_data)

    return devboost.__version__, new_ver


# ---------------------------------------------------------------------------
# Update-available cache (cheap per-command check)
# ---------------------------------------------------------------------------


def _state_dir(state_dir: Path | None) -> Path:
    if state_dir is not None:
        return state_dir
    xdg_state = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg_state) if xdg_state else Path.home() / ".local" / "state"
    return base / "devboost"


def cached_latest(
    state_dir: Path | None = None,
    ttl_hours: int = 24,
    fetch_url: FetchUrlFn | None = None,
) -> str | None:
    """Return the latest version from a disk cache, refreshing when stale.

    Stores ``{checked_at, latest}`` in ``~/.local/state/devboost/update-check.json``
    (honours ``$XDG_STATE_HOME``).  Never raises.
    """
    try:
        cache_path = _state_dir(state_dir) / "update-check.json"
        now = datetime.now(UTC)

        if cache_path.exists():
            data: dict[str, object] = json.loads(cache_path.read_text(encoding="utf-8"))
            checked_at_raw = data.get("checked_at")
            if isinstance(checked_at_raw, str):
                checked_at = datetime.fromisoformat(checked_at_raw)
                if now - checked_at < timedelta(hours=ttl_hours):
                    cached = data.get("latest")
                    return str(cached) if cached is not None else None

        latest = latest_version(fetch_url)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"checked_at": now.isoformat(), "latest": latest}),
            encoding="utf-8",
        )
        return latest
    except Exception:
        return None


def update_available(state_dir: Path | None = None) -> str | None:
    """Return the newer version string if an update is available, else ``None``.

    Reads the disk cache (network only once per 24 h).  Never raises.
    Honours the ``DEVBOOST_NO_UPDATE_CHECK`` opt-out env var.
    """
    if os.environ.get("DEVBOOST_NO_UPDATE_CHECK"):
        return None
    try:
        latest = cached_latest(state_dir=state_dir)
        if latest is None:
            return None
        if version_tuple(latest) > version_tuple(devboost.__version__):
            return latest
        return None
    except Exception:
        return None
