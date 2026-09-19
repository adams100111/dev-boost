"""`scripts/release.sh` — BSD-portable version parsing and the Darwin upload list.

Hermetic: `release.sh` is copied into a tmp fixture repo and run with `--dry-run` under a
stubbed PATH (`gh`, `git`, `uname`). Nothing is built, nothing is uploaded, no real `gh`
or network is reached.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.scripts.conftest import StubPath, run_bash

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "scripts"
SCRIPT = SCRIPTS / "release.sh"

# `gh` stub: authenticated, and `release view` fails so the "create the release" branch runs.
GH_STUB = """
case "$1" in
  auth) exit 0 ;;
  release)
    case "$2" in
      view) exit 1 ;;
      *) exit 0 ;;
    esac ;;
esac
exit 0
"""


def _uname(system: str, machine: str) -> str:
    return (
        'case "$1" in\n'
        f"  -s) echo {system} ;;\n"
        f"  -m) echo {machine} ;;\n"
        f"  *) echo {system} ;;\n"
        "esac"
    )


def _fixture_repo(tmp_path: Path, pyproject_version: str, init_version: str) -> Path:
    """A minimal repo tree holding a copy of release.sh and the two version files."""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    pkg = root / "engine" / "src" / "devboost"
    pkg.mkdir(parents=True)
    (root / "engine" / "pyproject.toml").write_text(
        '[project]\nname = "devboost"\n'
        f'version = "{pyproject_version}"\n'
        'requires-python = ">=3.12"\n',
        encoding="utf-8",
    )
    (pkg / "__init__.py").write_text(
        f'"""devboost."""\n\n__version__ = "{init_version}"\n', encoding="utf-8"
    )
    copy = root / "scripts" / "release.sh"
    shutil.copy2(SCRIPT, copy)
    copy.chmod(0o755)
    return copy


def _dry_run(
    stub_path: StubPath,
    tmp_path: Path,
    *,
    system: str = "Darwin",
    machine: str = "arm64",
    pyproject_version: str = "1.2.3",
    init_version: str = "1.2.3",
) -> tuple[int, str, str]:
    stub_path.add("uname", _uname(system, machine))
    stub_path.add("gh", GH_STUB)
    stub_path.add("git", "echo abc1234")
    script = _fixture_repo(tmp_path, pyproject_version, init_version)
    res = run_bash(script, "--dry-run", env=stub_path.env())
    return res.returncode, res.stdout, res.stderr


def test_release_version_parse_without_grep_P(stub_path: StubPath, tmp_path: Path) -> None:
    rc, out, err = _dry_run(stub_path, tmp_path)
    assert rc == 0, err
    assert "release: v1.2.3 (host arch: darwin-arm64)" in out


def test_release_dry_run_darwin_uploads_binary_only(
    stub_path: StubPath, tmp_path: Path
) -> None:
    rc, out, err = _dry_run(stub_path, tmp_path)
    assert rc == 0, err
    assert "+ gh release upload v1.2.3 dist/devboost-darwin-arm64 --clobber" in out
    assert ".tar.gz" not in out


def test_release_dry_run_linux_still_uploads_the_tarball(
    stub_path: StubPath, tmp_path: Path
) -> None:
    """Linux unchanged: both the binary and the Ventoy archive are still uploaded."""
    rc, out, err = _dry_run(stub_path, tmp_path, system="Linux", machine="x86_64")
    assert rc == 0, err
    assert "release: v1.2.3 (host arch: x86_64)" in out
    assert (
        "+ gh release upload v1.2.3 dist/devboost-x86_64 dist/devboost-x86_64.tar.gz "
        "--clobber" in out
    )


def test_release_version_mismatch_exits_1(stub_path: StubPath, tmp_path: Path) -> None:
    rc, _out, err = _dry_run(stub_path, tmp_path, init_version="1.2.4")
    assert rc == 1
    assert "version mismatch" in err
    assert "pyproject='1.2.3'" in err
    assert "__version__='1.2.4'" in err


def test_release_intel_mac_refused(stub_path: StubPath, tmp_path: Path) -> None:
    rc, _out, err = _dry_run(stub_path, tmp_path, machine="x86_64")
    assert rc == 1
    assert "release: Intel Macs are not supported (Apple Silicon only)" in err


@pytest.mark.parametrize("script", sorted(SCRIPTS.glob("*.sh")), ids=lambda p: p.name)
def test_no_grep_P_in_scripts(script: Path) -> None:
    """BSD grep has no `-P`/`-oP`; every version parse must use `sed -nE` instead."""
    offenders = [
        line
        for line in script.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
        and re.search(r"grep[^|;]*\s-[a-zA-Z]*P\b", line)
    ]
    assert offenders == [], f"{script.name}: {offenders}"


def test_release_regenerates_checksums_with_a_shasum_fallback() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "rl_sha256" in text
    assert "shasum -a 256" in text


def test_release_is_shellcheck_clean() -> None:
    shellcheck = shutil.which("shellcheck")
    if shellcheck is None:
        pytest.skip("shellcheck not installed")
    res = subprocess.run(
        [shellcheck, "-x", str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    assert res.returncode == 0, res.stdout + res.stderr
