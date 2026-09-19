"""`scripts/build-bundle.sh` — platform key, checksum tool fallback and shellcheck.

Hermetic: every test stubs `uname` on a PATH that shadows the real tool, and sources the
real script (its body lives in `bb_main`, so sourcing never builds anything). No test here
runs PyInstaller, reads the host OS, or touches the real `dist/`.
"""

from __future__ import annotations

import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

from tests.scripts.conftest import StubPath, run_bash

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "build-bundle.sh"


def _uname(system: str, machine: str) -> str:
    """A `uname` stub answering `-s` with *system* and `-m` with *machine*."""
    return (
        'case "$1" in\n'
        f"  -s) echo {system} ;;\n"
        f"  -m) echo {machine} ;;\n"
        f"  *) echo {system} ;;\n"
        "esac"
    )


def _sealed_env(
    stub_path: StubPath, stubdir: Path, tmp_path: Path, *real_tools: str
) -> dict[str, str]:
    """An env whose PATH is *stubdir* plus **only** the named real tools.

    Used where a test must prove a tool is *absent* (e.g. `sha256sum`): the default
    fixture PATH keeps `/usr/bin:/bin`, where a real `sha256sum` exists on Linux.
    """
    bindir = tmp_path / "realbin"
    bindir.mkdir(exist_ok=True)
    for tool in real_tools:
        found = shutil.which(tool)
        assert found is not None, f"host is missing {tool}"
        (bindir / tool).symlink_to(found)
    env = stub_path.env()
    env["PATH"] = f"{stubdir}:{bindir}"
    return env


def test_bb_arch_linux_x86_64(stub_path: StubPath) -> None:
    stub_path.add("uname", _uname("Linux", "x86_64"))
    res = run_bash(SCRIPT, env=stub_path.env(), source_fn="bb_arch")
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "x86_64"


@pytest.mark.parametrize("machine", ["aarch64", "arm64"])
def test_bb_arch_linux_aarch64_and_arm64(stub_path: StubPath, machine: str) -> None:
    stub_path.add("uname", _uname("Linux", machine))
    res = run_bash(SCRIPT, env=stub_path.env(), source_fn="bb_arch")
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "aarch64"


def test_bb_arch_darwin_arm64(stub_path: StubPath) -> None:
    stub_path.add("uname", _uname("Darwin", "arm64"))
    res = run_bash(SCRIPT, env=stub_path.env(), source_fn="bb_arch")
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "darwin-arm64"


def test_bb_arch_intel_mac_refused(stub_path: StubPath) -> None:
    stub_path.add("uname", _uname("Darwin", "x86_64"))
    res = run_bash(SCRIPT, env=stub_path.env(), source_fn="bb_arch")
    assert res.returncode == 1
    assert res.stdout.strip() == ""
    assert (
        res.stderr.strip()
        == "build-bundle: Intel Macs are not supported (Apple Silicon only)"
    )


def test_bb_arch_unknown_platform(stub_path: StubPath) -> None:
    stub_path.add("uname", _uname("Linux", "riscv64"))
    res = run_bash(SCRIPT, env=stub_path.env(), source_fn="bb_arch")
    assert res.returncode == 1
    assert "build-bundle: unsupported platform Linux/riscv64" in res.stderr


def test_bb_sha256_falls_back_to_shasum(stub_path: StubPath, tmp_path: Path) -> None:
    log = tmp_path / "shasum-argv.log"
    stubdir = stub_path.add("uname", _uname("Darwin", "arm64")).parent
    stub_path.add("shasum", f'printf "%s\\n" "$*" >> "{log}"')
    target = tmp_path / "devboost-darwin-arm64"
    target.write_text("frozen", encoding="utf-8")

    env = _sealed_env(stub_path, stubdir, tmp_path, "bash", "dirname")
    res = run_bash(SCRIPT, str(target), env=env, source_fn="bb_sha256")

    assert res.returncode == 0, res.stderr
    assert log.read_text(encoding="utf-8").strip() == f"-a 256 {target}"


def test_bb_sha256_prefers_sha256sum(stub_path: StubPath, tmp_path: Path) -> None:
    """Linux unchanged: when `sha256sum` exists it is used verbatim, no `-a 256`."""
    log = tmp_path / "sha256sum-argv.log"
    stubdir = stub_path.add("uname", _uname("Linux", "x86_64")).parent
    stub_path.add("sha256sum", f'printf "%s\\n" "$*" >> "{log}"')
    stub_path.add("shasum", 'echo "shasum must not run" >&2; exit 9')
    target = tmp_path / "devboost-x86_64"
    target.write_text("frozen", encoding="utf-8")

    env = _sealed_env(stub_path, stubdir, tmp_path, "bash", "dirname")
    res = run_bash(SCRIPT, str(target), env=env, source_fn="bb_sha256")

    assert res.returncode == 0, res.stderr
    assert log.read_text(encoding="utf-8").strip() == str(target)


def test_sourcing_the_script_has_no_side_effects(stub_path: StubPath) -> None:
    """The body lives in `bb_main`; sourcing must not rm/mkdir/build anything."""
    stub_path.add("uname", _uname("Darwin", "arm64"))
    for forbidden in ("rm", "mkdir", "tar", "uv", "pyinstaller", "mktemp", "install"):
        stub_path.add(forbidden, f'echo "{forbidden} ran on source" >&2; exit 97')
    res = run_bash(SCRIPT, env=stub_path.env(), source_fn="true")
    assert res.returncode == 0, res.stderr
    assert res.stderr.strip() == ""


def test_linux_branch_still_ships_the_ventoy_archive() -> None:
    """Linux unchanged: the tar.gz staging and the two-line checksums file are intact,
    and the Darwin branch is what skips them."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'tar -czf "${DIST}/devboost-${arch}.tar.gz"' in text
    assert 'bb_sha256 "devboost-${arch}" "devboost-${arch}.tar.gz"' in text
    assert 'bb_sha256 "devboost-${arch}" > "checksums-${arch}.txt"' in text


def test_darwin_verifies_the_signature_and_never_resigns() -> None:
    """D2: PyInstaller ad-hoc signs; build-bundle only verifies, never re-signs."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'codesign --verify --strict "${DIST}/devboost-${arch}"' in text
    code = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    assert "--codesign-identity" not in code
    assert "codesign -s" not in code
    assert "codesign --sign" not in code
    assert "codesign -f" not in code


def test_darwin_smokes_version_then_list_macos() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert '"${DIST}/devboost-${arch}" list macos' in text


def _fixture_repo(tmp_path: Path) -> Path:
    """A minimal repo tree holding a copy of build-bundle.sh, ready for `bb_main`."""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "engine").mkdir(parents=True)
    (root / "profiles.toml").write_text("# fixture\n", encoding="utf-8")
    copy = root / "scripts" / "build-bundle.sh"
    shutil.copy2(SCRIPT, copy)
    copy.chmod(0o755)
    return copy


# A `uv` stub standing in for PyInstaller: writes `<distpath>/devboost`, a tiny shell binary
# answering `--version` and `list <group>`.
UV_STUB = """
next=0
for a in "$@"; do
  if [ "$next" = 1 ]; then dp="$a"; next=0; fi
  [ "$a" = "--distpath" ] && next=1
done
cat > "$dp/devboost" <<'INNER'
#!/bin/sh
case "$1" in
  --version) echo "devboost 9.9.9" ;;
  list) echo "modules for $2" ;;
  *) exit 3 ;;
esac
INNER
chmod +x "$dp/devboost"
"""


def test_darwin_build_writes_the_binary_and_a_one_line_checksums_file(
    stub_path: StubPath, tmp_path: Path
) -> None:
    """End to end on a Darwin stub: no tar, no Ventoy staging, one checksum line."""
    codesign_log = tmp_path / "codesign-argv.log"
    stub_path.add("uname", _uname("Darwin", "arm64"))
    stub_path.add("uv", UV_STUB)
    stub_path.add("codesign", f'printf "%s\\n" "$*" >> "{codesign_log}"')
    script = _fixture_repo(tmp_path)

    res = run_bash(script, env=stub_path.env())

    assert res.returncode == 0, res.stdout + res.stderr
    dist = script.parent.parent / "dist"
    assert (dist / "devboost-darwin-arm64").is_file()
    assert not (dist / "devboost-darwin-arm64.tar.gz").exists()
    sums = (dist / "checksums-darwin-arm64.txt").read_text(encoding="utf-8")
    assert sums.splitlines() == [line for line in sums.splitlines() if line]
    assert len(sums.strip().splitlines()) == 1
    assert sums.strip().endswith("  devboost-darwin-arm64")
    assert codesign_log.read_text(encoding="utf-8").strip() == (
        f"--verify --strict {dist / 'devboost-darwin-arm64'}"
    )
    assert "list macos" in res.stdout


def test_linux_build_still_writes_the_tarball_and_two_checksum_lines(
    stub_path: StubPath, tmp_path: Path
) -> None:
    """Linux unchanged, end to end: binary + Ventoy archive + two checksum lines, and
    `codesign` is never invoked."""
    stub_path.add("uname", _uname("Linux", "x86_64"))
    stub_path.add("uv", UV_STUB)
    stub_path.add("codesign", 'echo "codesign must not run on Linux" >&2; exit 42')
    script = _fixture_repo(tmp_path)

    res = run_bash(script, env=stub_path.env())

    assert res.returncode == 0, res.stdout + res.stderr
    dist = script.parent.parent / "dist"
    assert (dist / "devboost-x86_64").is_file()
    assert (dist / "devboost-x86_64.tar.gz").is_file()
    names = [
        line.split("  ", 1)[1]
        for line in (dist / "checksums-x86_64.txt").read_text(encoding="utf-8").splitlines()
    ]
    assert names == ["devboost-x86_64", "devboost-x86_64.tar.gz"]
    assert "codesign" not in res.stderr
    assert "list macos" not in res.stdout

    with tarfile.open(dist / "devboost-x86_64.tar.gz") as archive:
        member = archive.getmember("opt/dev-boost/devboost")
    assert member.mode & 0o755 == 0o755


def test_script_is_shellcheck_clean() -> None:
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
