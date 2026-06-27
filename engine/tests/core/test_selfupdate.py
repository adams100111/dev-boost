"""Tests for devboost.core.selfupdate."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from devboost import __version__
from devboost.core import selfupdate
from devboost.core.selfupdate import (
    cached_latest,
    latest_version,
    update_available,
    update_frozen,
    version_tuple,
)

# ---------------------------------------------------------------------------
# version_tuple — comparison helper
# ---------------------------------------------------------------------------


def test_version_tuple_parses_dotted_ints() -> None:
    assert version_tuple("1.2.3") == (1, 2, 3)
    assert version_tuple("0.10.0") == (0, 10, 0)


def test_version_tuple_ordering() -> None:
    assert version_tuple("0.2.0") > version_tuple("0.1.9")
    assert version_tuple("1.0.0") > version_tuple("0.99.99")


def test_version_tuple_bad_input_returns_empty() -> None:
    assert version_tuple("not-a-version") == ()
    assert version_tuple("") == ()


# ---------------------------------------------------------------------------
# latest_version — redirect-URL parsing
# ---------------------------------------------------------------------------


def test_latest_version_parses_tag_url() -> None:
    def fake_fetch(url: str) -> str:
        return "https://github.com/adams100111/dev-boost/releases/tag/v1.5.0"

    result = latest_version(fetch_url=fake_fetch)
    assert result == "1.5.0"


def test_latest_version_handles_trailing_slash() -> None:
    def fake_fetch(url: str) -> str:
        return "https://github.com/adams100111/dev-boost/releases/tag/v2.0.1/"

    result = latest_version(fetch_url=fake_fetch)
    assert result == "2.0.1"


def test_latest_version_returns_none_on_bad_url() -> None:
    def fake_fetch(url: str) -> str:
        return "https://github.com/adams100111/dev-boost/releases/latest"

    # URL doesn't end in a version tag → None
    result = latest_version(fetch_url=fake_fetch)
    assert result is None


def test_latest_version_returns_none_on_exception() -> None:
    def bad_fetch(url: str) -> str:
        raise OSError("network down")

    result = latest_version(fetch_url=bad_fetch)
    assert result is None


# ---------------------------------------------------------------------------
# update_available — version comparison + opt-out
# ---------------------------------------------------------------------------


def test_update_available_returns_newer_version(tmp_path: Path) -> None:
    # Plant a fresh cache with a version higher than the current one.
    cache_path = tmp_path / "update-check.json"
    cache_path.write_text(
        json.dumps({"checked_at": datetime.now(UTC).isoformat(), "latest": "99.0.0"}),
        encoding="utf-8",
    )
    result = update_available(state_dir=tmp_path)
    assert result == "99.0.0"


def test_update_available_returns_none_when_already_latest(tmp_path: Path) -> None:
    # Cache holds the same version as the running binary.
    cache_path = tmp_path / "update-check.json"
    cache_path.write_text(
        json.dumps({"checked_at": datetime.now(UTC).isoformat(), "latest": __version__}),
        encoding="utf-8",
    )
    result = update_available(state_dir=tmp_path)
    assert result is None


def test_update_available_env_opt_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVBOOST_NO_UPDATE_CHECK", "1")
    cache_path = tmp_path / "update-check.json"
    cache_path.write_text(
        json.dumps({"checked_at": datetime.now(UTC).isoformat(), "latest": "99.0.0"}),
        encoding="utf-8",
    )
    result = update_available(state_dir=tmp_path)
    assert result is None


def test_update_available_never_raises(tmp_path: Path) -> None:
    # Point at a corrupt cache file — must silently return None.
    cache_path = tmp_path / "update-check.json"
    cache_path.write_text("this is not json", encoding="utf-8")
    result = update_available(state_dir=tmp_path)
    assert result is None


# ---------------------------------------------------------------------------
# cached_latest — TTL logic
# ---------------------------------------------------------------------------


def test_cached_latest_returns_cache_within_ttl(tmp_path: Path) -> None:
    cache_path = tmp_path / "update-check.json"
    cache_path.write_text(
        json.dumps({"checked_at": datetime.now(UTC).isoformat(), "latest": "3.0.0"}),
        encoding="utf-8",
    )
    calls: list[str] = []

    def spy_fetch(url: str) -> str:
        calls.append(url)
        return "https://github.com/adams100111/dev-boost/releases/tag/v9.9.9/"

    result = cached_latest(state_dir=tmp_path, fetch_url=spy_fetch)
    assert result == "3.0.0"
    assert calls == [], "network should not be hit when cache is fresh"


def test_cached_latest_refreshes_when_stale(tmp_path: Path) -> None:
    old_ts = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
    cache_path = tmp_path / "update-check.json"
    cache_path.write_text(
        json.dumps({"checked_at": old_ts, "latest": "0.0.1"}),
        encoding="utf-8",
    )

    def fresh_fetch(url: str) -> str:
        return "https://github.com/adams100111/dev-boost/releases/tag/v5.0.0"

    result = cached_latest(state_dir=tmp_path, fetch_url=fresh_fetch)
    assert result == "5.0.0"
    # Cache file must be updated
    data = json.loads(cache_path.read_text(encoding="utf-8"))
    assert data["latest"] == "5.0.0"


# ---------------------------------------------------------------------------
# update_frozen — checksum verification
# ---------------------------------------------------------------------------


def _make_fetch_file(
    files: dict[str, bytes],
    checksums_override: str | None = None,
) -> selfupdate.FetchFileFn:
    """Return a FetchFileFn that writes canned bytes from *files* keyed by URL basename."""

    def fetch(url: str, dest: Path) -> None:
        name = url.rsplit("/", 1)[-1]
        if checksums_override is not None and name == "checksums.txt":
            dest.write_bytes(checksums_override.encode())
            return
        if name not in files:
            raise FileNotFoundError(f"unexpected download: {url}")
        dest.write_bytes(files[name])

    return fetch


def test_update_frozen_checksum_mismatch_raises(tmp_path: Path) -> None:
    arch = selfupdate._arch()
    bin_name = f"devboost-{arch}"
    tar_name = f"devboost-{arch}.tar.gz"

    real_bin_content = b"fake binary content"
    real_tar_content = b"fake tarball content"

    # checksums.txt with wrong hashes
    bad_checksums = (
        f"deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef  {bin_name}\n"
        f"cafecafecafecafecafecafecafecafecafecafecafecafecafecafecafecafe00  {tar_name}\n"
    )

    def fake_fetch_url(url: str) -> str:
        return "https://github.com/adams100111/dev-boost/releases/tag/v9.9.9"

    fetch_file = _make_fetch_file(
        {bin_name: real_bin_content, tar_name: real_tar_content},
        checksums_override=bad_checksums,
    )

    with pytest.raises(RuntimeError, match="checksum mismatch"):
        update_frozen(fetch_url=fake_fetch_url, fetch_file=fetch_file)


def test_update_frozen_missing_checksum_entry_raises(tmp_path: Path) -> None:
    arch = selfupdate._arch()
    bin_name = f"devboost-{arch}"
    tar_name = f"devboost-{arch}.tar.gz"

    # checksums.txt only has the binary, not the tarball
    bin_hash = hashlib.sha256(b"bin").hexdigest()
    partial_checksums = f"{bin_hash}  {bin_name}\n"

    def fake_fetch_url(url: str) -> str:
        return "https://github.com/adams100111/dev-boost/releases/tag/v9.9.9"

    fetch_file = _make_fetch_file(
        {bin_name: b"bin", tar_name: b"tar"},
        checksums_override=partial_checksums,
    )

    with pytest.raises(RuntimeError, match="no checksum entry"):
        update_frozen(fetch_url=fake_fetch_url, fetch_file=fetch_file)


def test_update_frozen_download_failure_raises() -> None:
    def fake_fetch_url(url: str) -> str:
        return "https://github.com/adams100111/dev-boost/releases/tag/v9.9.9"

    def bad_fetch_file(url: str, dest: Path) -> None:
        raise OSError("network timeout")

    with pytest.raises(RuntimeError, match="download failed"):
        update_frozen(fetch_url=fake_fetch_url, fetch_file=bad_fetch_file)


def test_update_frozen_success(tmp_path: Path) -> None:
    """Full happy-path: correct checksums → files replaced atomically."""
    arch = selfupdate._arch()
    bin_name = f"devboost-{arch}"
    tar_name = f"devboost-{arch}.tar.gz"

    bin_content = b"new binary content"
    tar_content = b"new tarball content"
    bin_hash = hashlib.sha256(bin_content).hexdigest()
    tar_hash = hashlib.sha256(tar_content).hexdigest()
    good_checksums = f"{bin_hash}  {bin_name}\n{tar_hash}  {tar_name}\n"

    fake_binary = tmp_path / "devboost"
    fake_binary.write_bytes(b"old binary")
    fake_archive = tmp_path / tar_name
    fake_archive.write_bytes(b"old archive")

    def fake_fetch_url(url: str) -> str:
        return "https://github.com/adams100111/dev-boost/releases/tag/v9.9.9"

    fetch_file = _make_fetch_file(
        {bin_name: bin_content, tar_name: tar_content},
        checksums_override=good_checksums,
    )

    with (
        patch("sys.executable", str(fake_binary)),
        patch(
            "devboost.core.selfupdate.injection_archive_path",
            return_value=fake_archive,
        ),
    ):
        old, new = update_frozen(fetch_url=fake_fetch_url, fetch_file=fetch_file)

    assert old == __version__
    assert new == "9.9.9"
    assert fake_binary.read_bytes() == bin_content
    assert fake_archive.read_bytes() == tar_content


# ---------------------------------------------------------------------------
# CLI integration — --check output, warning suppression
# ---------------------------------------------------------------------------


def test_self_update_check_shows_update_available(monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from devboost.cli.app import app

    monkeypatch.setattr(
        "devboost.core.selfupdate.latest_version",
        lambda fetch_url=None: "99.0.0",
    )
    runner = CliRunner()
    result = runner.invoke(app, ["self-update", "--check"])
    assert result.exit_code == 0
    assert "update available" in result.output
    assert __version__ in result.output
    assert "99.0.0" in result.output


def test_self_update_check_shows_up_to_date(monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from devboost.cli.app import app

    monkeypatch.setattr(
        "devboost.core.selfupdate.latest_version",
        lambda fetch_url=None: __version__,
    )
    runner = CliRunner()
    result = runner.invoke(app, ["self-update", "--check"])
    assert result.exit_code == 0
    assert "up to date" in result.output


def test_update_warning_appears_on_non_self_update_command(
    profiles_file: Path,
    tmp_path: Path,
) -> None:
    """Warning printed to stderr for normal commands when a newer version is cached."""
    from typer.testing import CliRunner

    from devboost.cli.app import app

    # Plant a cache that says 99.0.0 is available
    cache_path = tmp_path / "update-check.json"
    cache_path.write_text(
        json.dumps({"checked_at": datetime.now(UTC).isoformat(), "latest": "99.0.0"}),
        encoding="utf-8",
    )

    with patch(
        "devboost.core.selfupdate.cached_latest",
        return_value="99.0.0",
    ):
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["list", "cli", "--root", str(profiles_file.parent)],
        )

    assert "99.0.0" in result.stderr
    assert "devboost self-update" in result.stderr


def test_update_warning_suppressed_for_self_update_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The warning must NOT appear when the invoked command is self-update."""
    from typer.testing import CliRunner

    from devboost.cli.app import app

    warned: list[str] = []

    def spy_update_available(state_dir: Path | None = None) -> str | None:
        warned.append("called")
        return "99.0.0"

    monkeypatch.setattr("devboost.core.selfupdate.update_available", spy_update_available)
    monkeypatch.setattr(
        "devboost.core.selfupdate.latest_version",
        lambda fetch_url=None: __version__,
    )

    runner = CliRunner()
    result = runner.invoke(app, ["self-update", "--check"])
    assert "99.0.0" not in result.stderr
    assert warned == [], "update_available must not be called for the self-update command"


def test_update_warning_suppressed_by_env_opt_out(
    profiles_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When DEVBOOST_NO_UPDATE_CHECK is set, the warning must not appear."""
    from typer.testing import CliRunner

    from devboost.cli.app import app

    monkeypatch.setenv("DEVBOOST_NO_UPDATE_CHECK", "1")

    with patch(
        "devboost.core.selfupdate.cached_latest",
        return_value="99.0.0",
    ):
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["list", "cli", "--root", str(profiles_file.parent)],
        )

    assert "99.0.0" not in result.stderr
