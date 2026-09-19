"""The verified-download script, run for real by `sh` against a fake `curl` (no network).

The fake executor tests pin the argv; these prove the shell logic itself: a checksum
mismatch deletes the file and fails, and the quarantine flag comes off only a verified file.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from devboost.core.errors import InstallError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.media.catalog import ReleaseAsset, VoxtypeSpec, voxtype_pin
from devboost.model import Ctx
from devboost.modules import voxtype as vox

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
PAYLOAD = b"#!/bin/sh\necho voxtype 1.0.1\n"
URL = "https://github.com/peteonrails/voxtype/releases/download/v1.0.1/voxtype"


@pytest.fixture
def fake_curl(tmp_path: Path) -> Path:
    """A `curl` that writes PAYLOAD to its -o path (and quarantines it, on a Mac)."""
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    src = tmp_path / "payload"
    src.write_bytes(PAYLOAD)
    quarantine = (
        'xattr -w com.apple.quarantine "0081;00000000;Safari;" "$out"\n'
        if sys.platform == "darwin" else ""
    )
    curl = bindir / "curl"
    curl.write_text(
        "#!/bin/sh\n"
        'while [ $# -gt 0 ]; do [ "$1" = "-o" ] && out="$2"; shift; done\n'
        f'cp "{src}" "$out"\n{quarantine}',
        encoding="utf-8",
    )
    curl.chmod(0o755)
    return bindir


@dataclass
class ShellEx(FakeExecutor):
    """Runs `sh -c` for real (fake curl first on PATH) and records every other call."""

    path: str = ""
    seen: list[tuple[Path, bool]] = field(default_factory=list)

    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        interactive: bool = False,
    ) -> Result:
        super().run(argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive)
        if list(argv[:2]) == ["sh", "-c"]:
            p = subprocess.run(list(argv), capture_output=True, text=True,
                               env={**os.environ, "PATH": self.path})
            return Result(p.returncode, p.stdout, p.stderr)
        if argv and argv[0] == "install":
            src = Path(argv[-2])
            q = subprocess.run(["xattr", "-p", "com.apple.quarantine", str(src)],
                               capture_output=True).returncode == 0 \
                if sys.platform == "darwin" else False
            self.seen.append((src, q))
        return Result(0)


def _asset(data: bytes) -> ReleaseAsset:
    return ReleaseAsset(url=URL, sha256=hashlib.sha256(data).hexdigest())


def _ex(fake_curl: Path) -> ShellEx:
    return ShellEx(path=f"{fake_curl}:/usr/bin:/bin:/usr/sbin")


@pytest.mark.parametrize("os_info", [MAC, FEDORA], ids=["macos", "linux"])
def test_a_checksum_mismatch_deletes_the_file_and_fails(
    fake_curl: Path, tmp_path: Path, os_info: OsInfo
) -> None:
    if os_info is MAC and sys.platform != "darwin":
        pytest.skip("shasum/xattr are macOS tools")
    if os_info is FEDORA and not subprocess.run(["sh", "-c", "command -v sha256sum"],
                                                capture_output=True).returncode == 0:
        pytest.skip("no sha256sum on this host")
    dest = tmp_path / "dl" / "voxtype"
    dest.parent.mkdir()
    ex = _ex(fake_curl)
    with pytest.raises(InstallError, match="checksum"):
        vox._fetch_verified(Ctx(os=os_info, ex=ex), _asset(b"something else"), dest)
    assert not dest.exists()


@pytest.mark.skipif(sys.platform != "darwin", reason="shasum/xattr are macOS tools")
def test_macos_installs_only_a_verified_unquarantined_file(
    fake_curl: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pin = voxtype_pin()
    assets = {**pin.assets, "bin-macos-universal": _asset(PAYLOAD)}
    monkeypatch.setattr(vox, "voxtype_pin", lambda: VoxtypeSpec(pin.version, assets))
    ex = _ex(fake_curl)
    vox._install_pinned_binary(Ctx(os=MAC, ex=ex), "bin-macos-universal")
    [(src, quarantined)] = ex.seen
    assert quarantined is False  # the flag came off the verified file before install
    assert not src.parent.exists()  # the private download dir is removed afterwards


@pytest.mark.skipif(sys.platform != "darwin", reason="shasum/xattr are macOS tools")
def test_macos_mismatch_never_reaches_install(
    fake_curl: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pin = voxtype_pin()
    assets = {**pin.assets, "bin-macos-universal": _asset(b"not the payload")}
    monkeypatch.setattr(vox, "voxtype_pin", lambda: VoxtypeSpec(pin.version, assets))
    ex = _ex(fake_curl)
    with pytest.raises(InstallError, match="checksum"):
        vox._install_pinned_binary(Ctx(os=MAC, ex=ex), "bin-macos-universal")
    assert ex.seen == []
