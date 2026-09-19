"""Hermetic tests for ``scripts/get.sh`` — the public ``curl … | bash`` bootstrap.

Every external command the script reaches (``uname``, ``sw_vers``, ``sysctl``, ``id``,
``curl``, ``sudo``) is a stub on a PATH that shadows the real tools, ``HOME`` is a tmp dir,
``GS_BREW_PREFIX`` and ``GS_TTY`` point into tmp, and the "binary" the script installs is a
shell script that logs how it was invoked. No test touches the network, the real Homebrew,
the real ``sudo`` or the real home.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import signal
import subprocess
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.scripts.conftest import StubPath

GET_SH = Path(__file__).resolve().parents[3] / "scripts" / "get.sh"

#: Asset keys that ``checksums.txt`` covers in the canned release.
ASSETS = ("devboost-x86_64", "devboost-aarch64", "devboost-darwin-arm64")

DEFAULT_BASE = "https://github.com/adams100111/dev-boost/releases/latest/download"
BREW_INSTALLER = "https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"


@dataclass(frozen=True)
class Harness:
    """A fully stubbed world for one ``get.sh`` run."""

    env: dict[str, str]
    home: Path
    canned: Path
    curl_log: Path
    exec_log: Path
    order_log: Path
    curl_args_log: Path
    brew_prefix: Path
    tty: Path
    tmpdir: Path

    def urls(self) -> list[str]:
        if not self.curl_log.exists():
            return []
        return self.curl_log.read_text(encoding="utf-8").split()

    def order(self) -> list[str]:
        if not self.order_log.exists():
            return []
        return self.order_log.read_text(encoding="utf-8").splitlines()

    def exec_lines(self) -> list[str]:
        if not self.exec_log.exists():
            return []
        return self.exec_log.read_text(encoding="utf-8").splitlines()

    def curl_argvs(self) -> list[str]:
        """One line per curl invocation, holding that call's whole argv."""
        if not self.curl_args_log.exists():
            return []
        return self.curl_args_log.read_text(encoding="utf-8").splitlines()

    def leaked_temp_dirs(self) -> list[str]:
        """What ``mktemp -d`` left behind. ``mktemp`` is stubbed to hand out dirs under
        ``tmpdir``, so anything still in there after the run is a leak. (Pinning
        ``TMPDIR`` alone would not do: macOS ``mktemp -d`` with no template ignores it
        and uses the per-user ``/var/folders/…`` dir.)"""
        return sorted(q.name for q in self.tmpdir.iterdir())

    @property
    def installed(self) -> Path:
        return self.home / ".local" / "share" / "devboost" / "bin" / "devboost"

    @property
    def link(self) -> Path:
        return self.home / ".local" / "bin" / "devboost"


def _canned_binary(exec_log: Path) -> str:
    """The stand-in for the released ``devboost`` binary: it records its argv, whether its
    stdin is a tty, and (on request) what it read from stdin."""
    return (
        "#!/bin/sh\n"
        "{\n"
        '  echo "args=$*"\n'
        '  if [ -t 0 ]; then echo "tty=yes"; else echo "tty=no"; fi\n'
        '  if [ "${GS_TEST_READ_STDIN:-0}" = 1 ]; then echo "stdin=$(cat)"; fi\n'
        f'}} >> "{exec_log}"\n'
    )


def _brew_stub(brew_prefix: Path) -> str:
    return (
        "#!/bin/sh\n"
        'if [ "$1" = shellenv ]; then\n'
        f"  echo 'export HOMEBREW_PREFIX=\"{brew_prefix}\"'\n"
        "fi\n"
        "exit 0\n"
    )


def _make_harness(
    stub: StubPath,
    tmp_path: Path,
    *,
    system: str = "Darwin",
    machine: str = "arm64",
    arm64: str = "1",
    translated: str = "0",
    mac_version: str = "27.0",
    uid: str = "1000",
    brew: bool = True,
    corrupt: str | None = None,
    no_tty: bool = False,
    fail_install: bool = False,
    kill_int_on: str | None = None,
    real_curl: bool = False,
    canned_name: str = "canned",
    **extra_env: str,
) -> Harness:
    canned = tmp_path / canned_name
    canned.mkdir(parents=True)
    logs = tmp_path / "logs"
    logs.mkdir()
    curl_log = logs / "curl.log"
    exec_log = logs / "exec.log"
    order_log = logs / "order.log"
    curl_args_log = logs / "curl-args.log"
    brew_prefix = tmp_path / "brewprefix"
    tty = tmp_path / "tty-file"
    tty.write_text("", encoding="utf-8")
    tmpdir = tmp_path / "tmpdir"
    tmpdir.mkdir()

    for asset in ASSETS:
        (canned / asset).write_text(_canned_binary(exec_log), encoding="utf-8")
    for asset in ("devboost-x86_64", "devboost-aarch64"):
        (canned / f"{asset}.tar.gz").write_bytes(b"ventoy-archive-" + asset.encode())

    lines = [
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}"
        for p in sorted(canned.iterdir())
    ]
    (canned / "checksums.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if corrupt is not None:
        (canned / corrupt).write_text("tampered\n", encoding="utf-8")

    # Not part of the release: the brew the Homebrew installer "installs", and the canned
    # Homebrew installer itself.
    (canned / "brew-stub").write_text(_brew_stub(brew_prefix), encoding="utf-8")
    (canned / "install.sh").write_text(
        f'printf "brew-installer NONINTERACTIVE=%s\\n" "${{NONINTERACTIVE-unset}}" '
        f'>> "{order_log}"\n'
        f'mkdir -p "{brew_prefix}/bin"\n'
        f'cp "{canned}/brew-stub" "{brew_prefix}/bin/brew"\n'
        f'chmod 0755 "{brew_prefix}/bin/brew"\n',
        encoding="utf-8",
    )

    if brew:
        (brew_prefix / "bin").mkdir(parents=True)
        brew_bin = brew_prefix / "bin" / "brew"
        brew_bin.write_text(_brew_stub(brew_prefix), encoding="utf-8")
        brew_bin.chmod(0o755)

    stub.add(
        "uname",
        f'case "${{1:-}}" in\n  -m) echo "{machine}" ;;\n  *) echo "{system}" ;;\nesac',
    )
    stub.add("sw_vers", f'echo "{mac_version}"')
    # `sysctl -n <key>`: proc_translated is 1 only in a Rosetta-translated shell.
    stub.add(
        "sysctl",
        f'case "${{2:-}}" in\n'
        f'  sysctl.proc_translated) echo "{translated}" ;;\n'
        f'  *) echo "{arm64}" ;;\n'
        "esac",
    )
    stub.add("id", f'echo "{uid}"')
    # A mktemp whose output we control, so "was the download dir cleaned up?" is
    # observable — and so no test ever litters the host's real temp dir.
    stub.add(
        "mktemp",
        f'd="{tmpdir}/dl.$$"\nmkdir -p "$d"\nchmod 700 "$d"\nprintf "%s\\n" "$d"',
    )
    stub.add("sudo", f'printf "sudo %s\\n" "$*" >> "{order_log}"\nexit 0')
    kill_clause = ""
    if kill_int_on is not None:
        # Hang here so the test can signal the whole process group mid-download, the way
        # a real Ctrl-C arrives while curl is still streaming.
        kill_clause = (
            f'if [ "${{url##*/}}" = "{kill_int_on}" ]; then\n'
            f'  : > "{curl_log}.hanging"\n'
            "  sleep 30\n"
            "fi\n"
        )
    # `-w FORMAT` is the release-tag probe: it prints $GS_TEST_TAG_URL as the effective
    # URL of the latest-release redirect (or fails, like an offline curl, when unset).
    curl_stub = (
        f'printf "%s\\n" "$*" >> "{curl_args_log}"\n'
        'url=""\nout=""\nfmt=""\n'
        'while [ $# -gt 0 ]; do\n'
        '  case "$1" in\n'
        '    -o) out="$2"; shift 2 ;;\n'
        '    -w) fmt="$2"; shift 2 ;;\n'
        '    --proto|--proto-redir) shift 2 ;;\n'
        '    -*) shift ;;\n'
        '    *) url="$1"; shift ;;\n'
        "  esac\n"
        "done\n"
        f'printf "%s\\n" "$url" >> "{curl_log}"\n'
        'if [ -n "$fmt" ]; then\n'
        '  [ -n "${GS_TEST_TAG_URL:-}" ] || exit 6\n'
        '  printf "%s" "$GS_TEST_TAG_URL"; exit 0\n'
        "fi\n"
        + kill_clause
        + f'src="{canned}/${{url##*/}}"\n'
        '[ -f "$src" ] || exit 22\n'
        'if [ -n "$out" ]; then cp "$src" "$out"; else cat "$src"; fi\n'
    )
    if not real_curl:
        stub.add("curl", curl_stub)
    if fail_install:
        # Force a `set -e` abort mid-gs_main, after the download dir exists.
        stub.add("install", 'echo "install: refused" >&2\nexit 1')

    env = stub.env(
        GS_BREW_PREFIX=str(brew_prefix),
        GS_TTY=str(tmp_path / "absent-tty") if no_tty else str(tty),
        TMPDIR=str(tmpdir),
        **extra_env,
    )
    return Harness(
        env=env,
        home=tmp_path / "home",
        canned=canned,
        curl_log=curl_log,
        exec_log=exec_log,
        order_log=order_log,
        curl_args_log=curl_args_log,
        brew_prefix=brew_prefix,
        tty=tty,
        tmpdir=tmpdir,
    )


def _run_get_sh(
    harness: Harness, *args: str, stdin: bytes = b""
) -> subprocess.CompletedProcess[bytes]:
    """Run ``get.sh`` itself (its shebang resolves bash off the stubbed PATH) with an
    explicit stdin, so ``[ -t 0 ]`` inside the script is deterministic."""
    return subprocess.run(
        [str(GET_SH), *args],
        env=harness.env,
        input=stdin,
        capture_output=True,
        check=False,
    )


def _stderr(proc: subprocess.CompletedProcess[bytes]) -> str:
    return proc.stderr.decode("utf-8", "replace")


# --------------------------------------------------------------------------- Linux


def test_linux_x86_64_flow_unchanged(stub_path: StubPath, tmp_path: Path) -> None:
    h = _make_harness(stub_path, tmp_path, system="Linux", machine="x86_64")
    proc = _run_get_sh(h)
    assert proc.returncode == 0, _stderr(proc)
    assert h.urls() == [
        f"{DEFAULT_BASE}/checksums.txt",
        f"{DEFAULT_BASE}/devboost-x86_64",
        f"{DEFAULT_BASE}/devboost-x86_64.tar.gz",
    ]
    assert h.exec_lines()[0] == "args=install terminal"
    assert h.installed.is_file()
    assert (h.installed.parent / "devboost-x86_64.tar.gz").is_file()
    assert h.link.is_symlink()


def test_linux_never_reads_tty_or_bootstraps_brew(stub_path: StubPath, tmp_path: Path) -> None:
    h = _make_harness(stub_path, tmp_path, system="Linux", machine="aarch64", brew=False)
    proc = _run_get_sh(h)
    assert proc.returncode == 0, _stderr(proc)
    assert BREW_INSTALLER not in h.urls()
    assert not (h.brew_prefix / "bin" / "brew").exists()
    assert "tty=no" in h.exec_lines()


# --------------------------------------------------------------------------- Darwin happy path


def test_darwin_arm64_fetches_binary_only(stub_path: StubPath, tmp_path: Path) -> None:
    h = _make_harness(stub_path, tmp_path)
    proc = _run_get_sh(h)
    assert proc.returncode == 0, _stderr(proc)
    assert h.urls() == [
        f"{DEFAULT_BASE}/checksums.txt",
        f"{DEFAULT_BASE}/devboost-darwin-arm64",
    ]
    assert not any(u.endswith(".tar.gz") for u in h.urls())
    assert h.installed.is_file()
    assert h.link.is_symlink()
    assert list(h.installed.parent.iterdir()) == [h.installed]
    assert h.exec_lines()[0] == "args=install terminal"


ROSETTA_MSG = (
    "get.sh: this shell runs under Rosetta (x86_64) — open a native (arm64) terminal "
    "and re-run"
)


def test_darwin_rosetta_shell_refused(stub_path: StubPath, tmp_path: Path) -> None:
    """`sysctl.proc_translated` = 1: Homebrew's installer aborts under Rosetta, so get.sh
    refuses first — before any download, sudo or Homebrew."""
    h = _make_harness(stub_path, tmp_path, machine="x86_64", translated="1", brew=False)
    proc = _run_get_sh(h)
    assert proc.returncode == 1
    assert ROSETTA_MSG in _stderr(proc)
    assert h.urls() == []
    assert h.order() == []
    assert not h.installed.exists()


def test_darwin_x86_64_shell_on_arm64_host_refused_as_rosetta(
    stub_path: StubPath, tmp_path: Path
) -> None:
    """Belt and braces: even if proc_translated reads 0, an x86_64 shell on an arm64 host
    is translated — the same refusal, not the Intel one."""
    h = _make_harness(stub_path, tmp_path, machine="x86_64", arm64="1", translated="0")
    proc = _run_get_sh(h)
    assert proc.returncode == 1
    assert ROSETTA_MSG in _stderr(proc)
    assert "Intel" not in _stderr(proc)
    assert h.urls() == []


def test_darwin_intel_refused(stub_path: StubPath, tmp_path: Path) -> None:
    h = _make_harness(stub_path, tmp_path, machine="x86_64", arm64="0")
    proc = _run_get_sh(h)
    assert proc.returncode == 1
    assert (
        "get.sh: Intel Macs are not supported — dev-boost needs Apple Silicon (arm64)"
        in _stderr(proc)
    )
    assert h.urls() == []


def test_darwin_never_sudo_links_into_usr_local(stub_path: StubPath, tmp_path: Path) -> None:
    h = _make_harness(stub_path, tmp_path)
    proc = _run_get_sh(h)
    assert proc.returncode == 0, _stderr(proc)
    assert h.order() == []


# --------------------------------------------------------------------------- version gate


def test_darwin_macos_14_refused(stub_path: StubPath, tmp_path: Path) -> None:
    h = _make_harness(stub_path, tmp_path, mac_version="14.7")
    proc = _run_get_sh(h)
    assert proc.returncode == 1
    assert (
        "get.sh: macOS 14.7 is not supported — dev-boost needs macOS 15 or newer "
        "(27 recommended)" in _stderr(proc)
    )
    assert h.urls() == []


def test_darwin_macos_15_warns(stub_path: StubPath, tmp_path: Path) -> None:
    h = _make_harness(stub_path, tmp_path, mac_version="15.6")
    proc = _run_get_sh(h)
    assert proc.returncode == 0, _stderr(proc)
    assert (
        "get.sh: macOS 15 is best-effort (untested); 27 and 26 are supported" in _stderr(proc)
    )
    assert h.installed.is_file()


@pytest.mark.parametrize("version", ["26.3", "27.0"])
def test_darwin_macos_26_and_27_quiet(
    stub_path: StubPath, tmp_path: Path, version: str
) -> None:
    h = _make_harness(stub_path, tmp_path, mac_version=version)
    proc = _run_get_sh(h)
    assert proc.returncode == 0, _stderr(proc)
    err = _stderr(proc)
    assert "best-effort" not in err
    assert "newer than tested" not in err
    assert "is not supported" not in err


def test_darwin_macos_28_warns_newer(stub_path: StubPath, tmp_path: Path) -> None:
    h = _make_harness(stub_path, tmp_path, mac_version="28.0")
    proc = _run_get_sh(h)
    assert proc.returncode == 0, _stderr(proc)
    assert "get.sh: macOS 28.0 is newer than tested (27) — continuing" in _stderr(proc)
    assert h.installed.is_file()


@pytest.mark.parametrize("reported", ["", "beta"])
def test_darwin_unreadable_version_refused(
    stub_path: StubPath, tmp_path: Path, reported: str
) -> None:
    """The version gate fails CLOSED: an unreadable or unparseable sw_vers is not
    evidence of a supported macOS."""
    h = _make_harness(stub_path, tmp_path, mac_version=reported)
    proc = _run_get_sh(h)
    assert proc.returncode == 1
    assert (
        "get.sh: the macOS version could not be read — dev-boost needs macOS 15 or newer "
        "(27 recommended)" in _stderr(proc)
    )
    assert h.urls() == []
    assert not h.installed.exists()


# --------------------------------------------------------------------------- root


def test_darwin_root_refused(stub_path: StubPath, tmp_path: Path) -> None:
    h = _make_harness(stub_path, tmp_path, uid="0")
    proc = _run_get_sh(h)
    assert proc.returncode == 1
    assert (
        "get.sh: don't run this as root on macOS — Homebrew refuses root. "
        "Run it as your user." in _stderr(proc)
    )
    assert h.urls() == []


# --------------------------------------------------------------------------- Homebrew


def test_darwin_bootstraps_homebrew_when_missing(stub_path: StubPath, tmp_path: Path) -> None:
    h = _make_harness(stub_path, tmp_path, brew=False)
    proc = _run_get_sh(h)
    assert proc.returncode == 0, _stderr(proc)
    assert h.order() == ["sudo -v", "brew-installer NONINTERACTIVE=1"]
    assert (h.brew_prefix / "bin" / "brew").is_file()
    assert h.installed.is_file()


def test_darwin_fetches_and_verifies_before_homebrew(stub_path: StubPath, tmp_path: Path) -> None:
    """Ruling C-M6-R2: the release binary is downloaded and verified BEFORE Homebrew and
    the CLT are installed, so a bad release never leaves a half-provisioned Mac."""
    h = _make_harness(stub_path, tmp_path, brew=False)
    proc = _run_get_sh(h)
    assert proc.returncode == 0, _stderr(proc)
    assert h.urls() == [
        f"{DEFAULT_BASE}/checksums.txt",
        f"{DEFAULT_BASE}/devboost-darwin-arm64",
        BREW_INSTALLER,
    ]
    err = _stderr(proc)
    assert err.index("downloading devboost-") < err.index("Homebrew is missing")
    assert err.index("Homebrew is missing") < err.index("installed ")


def test_darwin_homebrew_installer_without_brew_fails(
    stub_path: StubPath, tmp_path: Path
) -> None:
    """An installer that "succeeds" but leaves no brew behind is a failure, not a shrug."""
    h = _make_harness(stub_path, tmp_path, brew=False)
    (h.canned / "install.sh").write_text("exit 0\n", encoding="utf-8")
    proc = _run_get_sh(h)
    assert proc.returncode == 1
    assert "the Homebrew installer finished, but" in _stderr(proc)
    assert not h.installed.exists()


def test_darwin_skips_homebrew_when_present(stub_path: StubPath, tmp_path: Path) -> None:
    h = _make_harness(stub_path, tmp_path, brew=True)
    proc = _run_get_sh(h)
    assert proc.returncode == 0, _stderr(proc)
    assert BREW_INSTALLER not in h.urls()
    assert h.order() == []


# --------------------------------------------------------------------------- tty


def test_darwin_exec_reads_tty_under_pipe(stub_path: StubPath, tmp_path: Path) -> None:
    h = _make_harness(stub_path, tmp_path, GS_TEST_READ_STDIN="1")
    h.tty.write_text("FROM-TTY\n", encoding="utf-8")
    proc = _run_get_sh(h, stdin=b"FROM-PIPE\n")
    assert proc.returncode == 0, _stderr(proc)
    assert "stdin=FROM-TTY" in h.exec_lines()
    assert "stdin=FROM-PIPE" not in h.exec_lines()


# --------------------------------------------------------------------------- profiles


def test_darwin_usb_profile_refused(stub_path: StubPath, tmp_path: Path) -> None:
    h = _make_harness(stub_path, tmp_path)
    proc = _run_get_sh(h, "usb")
    assert proc.returncode == 1
    assert "get.sh: the USB builder is Linux-only" in _stderr(proc)
    assert h.exec_lines() == []
    # The refusal fires before anything is fetched, installed or linked.
    assert h.urls() == []
    assert not h.installed.exists()
    assert not h.link.exists()
    assert not (h.home / ".local" / "share" / "devboost").exists()


def test_darwin_none_installs_only(stub_path: StubPath, tmp_path: Path) -> None:
    h = _make_harness(stub_path, tmp_path)
    proc = _run_get_sh(h, "none")
    assert proc.returncode == 0, _stderr(proc)
    assert h.installed.is_file()
    assert h.link.is_symlink()
    assert h.exec_lines() == []


# --------------------------------------------------------------------------- base override


def test_release_base_override(stub_path: StubPath, tmp_path: Path) -> None:
    h = _make_harness(stub_path, tmp_path, DEVBOOST_RELEASE_BASE="file:///x")
    proc = _run_get_sh(h)
    assert proc.returncode == 0, _stderr(proc)
    assert h.urls() == ["file:///x/checksums.txt", "file:///x/devboost-darwin-arm64"]


def test_file_base_with_a_space_works_with_real_curl(stub_path: StubPath, tmp_path: Path) -> None:
    """The D9 rehearsal serves the release from `/Volumes/My Shared Files/dist`. With the
    REAL curl (unstubbed), a percent-encoded file:// base with a space fetches, verifies
    and installs."""
    if shutil.which("curl") is None:
        pytest.skip("curl is not installed")
    h = _make_harness(stub_path, tmp_path, real_curl=True, canned_name="My Shared Files")
    base = "file://" + urllib.parse.quote(str(h.canned))
    assert "%20" in base
    h.env["DEVBOOST_RELEASE_BASE"] = base
    proc = _run_get_sh(h)
    assert proc.returncode == 0, _stderr(proc)
    assert h.installed.is_file()
    assert h.exec_lines()[0] == "args=install terminal"


def test_release_base_must_not_be_plain_http(stub_path: StubPath, tmp_path: Path) -> None:
    h = _make_harness(stub_path, tmp_path, DEVBOOST_RELEASE_BASE="http://evil.example/dl")
    proc = _run_get_sh(h)
    assert proc.returncode == 1
    assert "get.sh: refusing a non-HTTPS release base" in _stderr(proc)
    assert h.urls() == []


# --------------------------------------------------------------------------- integrity


def test_checksum_mismatch_darwin(stub_path: StubPath, tmp_path: Path) -> None:
    h = _make_harness(stub_path, tmp_path, corrupt="devboost-darwin-arm64")
    proc = _run_get_sh(h)
    assert proc.returncode == 1
    assert "get.sh: checksum mismatch: devboost-darwin-arm64" in _stderr(proc)
    assert not h.installed.exists()
    assert not h.link.exists()
    assert h.exec_lines() == []


def test_checksum_mismatch_leaves_the_mac_untouched(stub_path: StubPath, tmp_path: Path) -> None:
    """Homebrew missing + a tampered binary: no sudo, no Homebrew, no CLT, no devboost."""
    h = _make_harness(stub_path, tmp_path, brew=False, corrupt="devboost-darwin-arm64")
    proc = _run_get_sh(h)
    assert proc.returncode == 1
    assert "get.sh: checksum mismatch: devboost-darwin-arm64" in _stderr(proc)
    assert h.order() == []
    assert BREW_INSTALLER not in h.urls()
    assert not (h.brew_prefix / "bin" / "brew").exists()
    assert not (h.home / ".local").exists()


MISSING_MAC_ASSET = (
    "get.sh: no devboost-darwin-arm64 in release v0.1.80 yet — macOS support ships in v0.2.0"
)
TAG_URL = "https://github.com/adams100111/dev-boost/releases/tag/v0.1.80"


@pytest.mark.parametrize("shape", ["no-checksum-entry", "asset-404"])
def test_release_without_a_mac_asset_says_so_and_touches_nothing(
    stub_path: StubPath, tmp_path: Path, shape: str
) -> None:
    """A-I4: the latest release (today's v0.1.80) ships no Mac binary. Say exactly that,
    exit non-zero, and leave the machine untouched — no sudo, no Homebrew, no devboost."""
    h = _make_harness(stub_path, tmp_path, brew=False, GS_TEST_TAG_URL=TAG_URL)
    (h.canned / "devboost-darwin-arm64").unlink()
    if shape == "no-checksum-entry":
        lines = (h.canned / "checksums.txt").read_text(encoding="utf-8").splitlines()
        kept = [ln for ln in lines if not ln.endswith("  devboost-darwin-arm64")]
        (h.canned / "checksums.txt").write_text("\n".join(kept) + "\n", encoding="utf-8")
    proc = _run_get_sh(h)
    assert proc.returncode == 1
    err = _stderr(proc)
    assert MISSING_MAC_ASSET in err
    assert "get.sh: nothing was installed." in err
    assert "curl:" not in err
    assert h.order() == []
    assert BREW_INSTALLER not in h.urls()
    assert not (h.brew_prefix / "bin" / "brew").exists()
    assert not (h.home / ".local").exists()
    assert h.exec_lines() == []
    assert h.leaked_temp_dirs() == []
    # The tag probe is pinned to https like every other fetch.
    probe = [a for a in h.curl_argvs() if "-w" in a.split()]
    assert probe and all("--proto-redir =https" in a for a in probe)


def test_missing_asset_without_a_resolvable_tag(stub_path: StubPath, tmp_path: Path) -> None:
    """Offline tag probe: still a clear message, naming the latest release generically."""
    h = _make_harness(stub_path, tmp_path)
    (h.canned / "devboost-darwin-arm64").unlink()
    proc = _run_get_sh(h)
    assert proc.returncode == 1
    assert (
        "get.sh: no devboost-darwin-arm64 in release (latest) yet — macOS support ships in "
        "v0.2.0" in _stderr(proc)
    )


def test_missing_linux_asset_names_the_release(stub_path: StubPath, tmp_path: Path) -> None:
    h = _make_harness(
        stub_path, tmp_path, system="Linux", machine="aarch64", GS_TEST_TAG_URL=TAG_URL
    )
    (h.canned / "devboost-aarch64").unlink()
    proc = _run_get_sh(h)
    assert proc.returncode == 1
    err = _stderr(proc)
    assert "get.sh: no devboost-aarch64 in release v0.1.80 yet" in err
    assert "macOS" not in err
    assert not h.installed.exists()


def test_missing_asset_under_an_overridden_base_names_the_base(
    stub_path: StubPath, tmp_path: Path
) -> None:
    h = _make_harness(stub_path, tmp_path, DEVBOOST_RELEASE_BASE="https://mirror.example/dl")
    (h.canned / "devboost-darwin-arm64").unlink()
    proc = _run_get_sh(h)
    assert proc.returncode == 1
    assert (
        "get.sh: no devboost-darwin-arm64 in release at https://mirror.example/dl yet"
        in _stderr(proc)
    )
    # No tag probe against github.com for a non-default base.
    assert not [a for a in h.curl_argvs() if "-w" in a.split()]


def test_checksum_entry_is_an_exact_name_match(stub_path: StubPath, tmp_path: Path) -> None:
    """A regex lookup would let `devboost-darwin-arm64` match a look-alike entry; the
    lookup is an exact comparison of the name field."""
    h = _make_harness(stub_path, tmp_path)
    lines = (h.canned / "checksums.txt").read_text(encoding="utf-8").splitlines()
    kept = [
        ln.replace("  devboost-darwin-arm64", "  xdevboost-darwin-arm64")
        for ln in lines
    ]
    (h.canned / "checksums.txt").write_text("\n".join(kept) + "\n", encoding="utf-8")
    proc = _run_get_sh(h)
    assert proc.returncode == 1
    assert "no devboost-darwin-arm64 in release" in _stderr(proc)
    assert not h.installed.exists()


def test_missing_release_reports_cleanly(stub_path: StubPath, tmp_path: Path) -> None:
    h = _make_harness(stub_path, tmp_path)
    (h.canned / "checksums.txt").unlink()
    proc = _run_get_sh(h)
    assert proc.returncode == 1
    assert "no published release yet" in _stderr(proc)
    assert not h.installed.exists()


# --------------------------------------------------------------------------- temp dir


def test_temp_dir_cleaned_after_success(stub_path: StubPath, tmp_path: Path) -> None:
    h = _make_harness(stub_path, tmp_path)
    proc = _run_get_sh(h)
    assert proc.returncode == 0, _stderr(proc)
    assert h.leaked_temp_dirs() == []


def test_temp_dir_cleaned_after_checksum_mismatch(stub_path: StubPath, tmp_path: Path) -> None:
    h = _make_harness(stub_path, tmp_path, corrupt="devboost-darwin-arm64")
    proc = _run_get_sh(h)
    assert proc.returncode == 1
    assert h.leaked_temp_dirs() == []


def test_temp_dir_cleaned_on_sigint(stub_path: StubPath, tmp_path: Path) -> None:
    """Ctrl-C mid-download must not leave a partial, unverified binary behind. The
    RETURN trap alone does not cover this: a default-disposition SIGINT kills the shell
    outright, running no trap at all."""
    h = _make_harness(stub_path, tmp_path, kill_int_on="devboost-darwin-arm64")
    hanging = Path(f"{h.curl_log}.hanging")
    with subprocess.Popen(
        [str(GET_SH)],
        env=h.env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    ) as proc:
        deadline = time.monotonic() + 30
        while not hanging.exists() and time.monotonic() < deadline:
            if proc.poll() is not None:
                raise AssertionError("get.sh exited before the download started")
            time.sleep(0.05)
        assert hanging.exists(), "the stubbed download never started"
        assert h.leaked_temp_dirs(), "the download dir should exist while downloading"
        os.killpg(os.getpgid(proc.pid), signal.SIGINT)
        proc.wait(timeout=30)
    assert proc.returncode != 0
    assert h.leaked_temp_dirs() == []
    assert not h.installed.exists()


def test_temp_dir_cleaned_on_errexit_abort(stub_path: StubPath, tmp_path: Path) -> None:
    """A `set -e` abort mid-gs_main (here: a failing `install`) fires no RETURN trap."""
    h = _make_harness(stub_path, tmp_path, fail_install=True)
    proc = _run_get_sh(h)
    assert proc.returncode != 0
    assert h.leaked_temp_dirs() == []
    assert not h.link.exists()


# --------------------------------------------------------------------------- transport


def test_curl_pins_https_on_the_first_hop_and_on_redirects(
    stub_path: StubPath, tmp_path: Path
) -> None:
    h = _make_harness(stub_path, tmp_path, brew=False)
    proc = _run_get_sh(h)
    assert proc.returncode == 0, _stderr(proc)
    argvs = h.curl_argvs()
    # The release fetches plus the Homebrew installer fetch — every single one.
    assert len(argvs) == 3
    for argv in argvs:
        assert "--proto =https,file" in argv, argv
        assert "--proto-redir =https" in argv, argv


def test_non_default_base_warns_and_names_the_host(stub_path: StubPath, tmp_path: Path) -> None:
    h = _make_harness(
        stub_path, tmp_path, DEVBOOST_RELEASE_BASE="https://mirror.example/dl"
    )
    proc = _run_get_sh(h)
    assert proc.returncode == 0, _stderr(proc)
    err = _stderr(proc)
    assert "get.sh: WARNING: DEVBOOST_RELEASE_BASE overrides the official release." in err
    assert (
        "get.sh: WARNING: devboost AND its checksums will be fetched from: mirror.example"
        in err
    )
    # The warning precedes the first fetch.
    assert err.index("WARNING") < err.index("downloading devboost-")


def test_default_base_does_not_warn(stub_path: StubPath, tmp_path: Path) -> None:
    h = _make_harness(stub_path, tmp_path)
    proc = _run_get_sh(h)
    assert proc.returncode == 0, _stderr(proc)
    assert "WARNING" not in _stderr(proc)


# --------------------------------------------------------------------------- no tty


def test_darwin_no_tty_refuses_before_sudo(stub_path: StubPath, tmp_path: Path) -> None:
    """With no usable tty the Homebrew bootstrap cannot prompt: say so, and never let a
    raw shell redirection error reach the user."""
    h = _make_harness(stub_path, tmp_path, brew=False, no_tty=True)
    proc = _run_get_sh(h)
    assert proc.returncode == 1
    err = _stderr(proc)
    assert (
        "get.sh: no terminal available for the sudo prompt — install Homebrew first, "
        "then re-run this script" in err
    )
    assert "No such file or directory" not in err
    assert "sudo failed" not in err
    assert h.order() == []
    assert h.urls() == []


def test_darwin_exec_without_tty_falls_through(stub_path: StubPath, tmp_path: Path) -> None:
    """Brew is present, so no prompt is needed; an unopenable tty must not break the
    install — the exec just keeps the piped stdin."""
    h = _make_harness(stub_path, tmp_path, no_tty=True, GS_TEST_READ_STDIN="1")
    proc = _run_get_sh(h, stdin=b"FROM-PIPE\n")
    assert proc.returncode == 0, _stderr(proc)
    assert "stdin=FROM-PIPE" in h.exec_lines()
    assert "No such file or directory" not in _stderr(proc)


# --------------------------------------------------------------------------- lint


def test_get_sh_shellcheck_clean() -> None:
    if shutil.which("shellcheck") is None:
        pytest.skip("shellcheck is not installed")
    proc = subprocess.run(
        ["shellcheck", "-x", str(GET_SH)], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
