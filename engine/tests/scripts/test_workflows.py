"""Text/regex checks over the CI and release workflow YAML — Task 5 (Lane D).

These read the workflow files as plain text, matching the other `scripts/*.sh` test
suites in this milestone: no PyYAML dependency, and every assertion names the exact
string that must (or must not) appear. `test_actionlint_clean` is the one structural
check, delegated to the real `actionlint` binary (skipped when it is absent).
"""

from __future__ import annotations

import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from tests.scripts.conftest import StubPath, run_bash

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WORKFLOWS_DIR = _REPO_ROOT / ".github" / "workflows"
_CI = (_WORKFLOWS_DIR / "ci.yml").read_text()
_RELEASE = (_WORKFLOWS_DIR / "release.yml").read_text()
_VM_SMOKE = (_WORKFLOWS_DIR / "vm-smoke.yml").read_text()
_GLIBC_CHECK = _REPO_ROOT / "scripts" / "check-glibc-floor.sh"

# GitHub-hosted "larger runner" labels: billed even on public repos (V2), so none of
# them may appear anywhere in either workflow.
_PAID_LABEL_RE = re.compile(r"-xlarge|-large|-intel")


def _job_body(text: str, job_name: str) -> str:
    """The body of a top-level `<job_name>:` job, up to the next 2-space-indented key."""
    pattern = rf"^  {re.escape(job_name)}:\n(.*?)(?=^  \S|\Z)"
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    assert match, f"no `{job_name}:` job found"
    return match.group(1)


def test_ci_runs_checks_on_macos_15() -> None:
    engine_job = _job_body(_CI, "engine")
    assert "macos-15" in engine_job


def test_ci_xcode_27_non_blocking() -> None:
    engine_job = _job_body(_CI, "engine")
    assert "xcode-27" in engine_job
    assert re.search(r"continue-on-error:.*xcode-27", engine_job)


def test_release_binary_matrix_has_darwin() -> None:
    binary_job = _job_body(_RELEASE, "binary")
    match = re.search(
        r"runner:\s*macos-15\s*\n\s*arch:\s*darwin-arm64", binary_job
    )
    assert match, "arch: darwin-arm64 does not sit under runner: macos-15"


def test_release_checksums_include_darwin() -> None:
    release_job = _job_body(_RELEASE, "release")
    sha_match = re.search(r"sha256sum.*?>\s*checksums\.txt", release_job, re.DOTALL)
    assert sha_match, "no sha256sum ... > checksums.txt combine step"
    assert "devboost-darwin-arm64" in sha_match.group(0)
    upload = _step(release_job, "Upload every asset + checksums.txt to the draft")
    assert "out/devboost-darwin-arm64" in upload


# --- release.yml publishes safely: draft -> upload -> verify -> publish (N2) ----------

_ASSETS = (
    "devboost-x86_64",
    "devboost-aarch64",
    "devboost-darwin-arm64",
    "devboost-x86_64.tar.gz",
    "devboost-aarch64.tar.gz",
    "checksums.txt",
)


def _step(job: str, name: str) -> str:
    """The body of the step called *name* in *job*, up to the next step."""
    match = re.search(
        rf"^      - name: {re.escape(name)}\n(.*?)(?=^      - |\Z)", job, re.DOTALL | re.MULTILINE
    )
    assert match, f"no step named {name!r}"
    return match.group(1)


def test_release_job_no_longer_publishes_with_softprops() -> None:
    """softprops/action-gh-release creates the release published, so it was `latest`
    before its uploads finished (and it re-uploads over an existing release)."""
    assert "softprops/action-gh-release" not in _RELEASE


def test_release_job_creates_a_draft_and_refuses_a_published_release() -> None:
    body = _step(
        _job_body(_RELEASE, "release"), "Create the release as a draft (never over a published one)"
    )
    assert 'gh release create "${TAG}" --draft --verify-tag' in body
    assert "--latest" not in body
    assert "--json isDraft --jq .isDraft" in body
    assert "is already published; a release is never re-uploaded over" in body


def test_release_job_uploads_every_asset_plus_checksums() -> None:
    body = _step(_job_body(_RELEASE, "release"), "Upload every asset + checksums.txt to the draft")
    assert "gh release upload" in body
    for name in _ASSETS:
        assert f"out/{name}" in body, name


def test_release_job_verifies_the_downloaded_draft() -> None:
    body = _step(_job_body(_RELEASE, "release"), "Verify the draft's assets against checksums.txt")
    assert "gh release download" in body
    assert "sha256sum -c checksums.txt" in body
    assert "has no entry in checksums.txt" in body
    for name in _ASSETS:
        assert name in body, name


def test_release_job_publishes_and_marks_latest_as_the_last_step() -> None:
    job = _job_body(_RELEASE, "release")
    steps = re.findall(r"^      - (?:name: (.*)|uses: .*)$", job, re.MULTILINE)
    assert steps[-1] == "Publish the release and mark it latest (last step)"
    order = [
        job.index("gh release create"),
        job.index("gh release upload"),
        job.index("gh release download"),
        job.index("gh release edit"),
    ]
    assert order == sorted(order)
    last = _step(job, "Publish the release and mark it latest (last step)")
    assert 'gh release edit "${TAG}" --draft=false --latest' in last
    assert job.count("--latest") == 1


def test_release_job_gh_steps_have_a_token_and_repo() -> None:
    """The release job has no checkout, so gh needs GH_REPO as well as GH_TOKEN."""
    job = _job_body(_RELEASE, "release")
    gh_steps = [s for s in re.split(r"^      - ", job, flags=re.MULTILINE) if "gh release" in s]
    assert len(gh_steps) == 4
    for step in gh_steps:
        assert "GH_TOKEN: ${{ github.token }}" in step
        assert "GH_REPO: ${{ github.repository }}" in step


def test_release_linux_assets_unchanged() -> None:
    release_job = _job_body(_RELEASE, "release")
    for name in (
        "devboost-x86_64",
        "devboost-aarch64",
        "devboost-x86_64.tar.gz",
        "devboost-aarch64.tar.gz",
    ):
        assert name in release_job, f"{name} missing from the release job"


def test_no_grep_P_in_workflows() -> None:
    for text, path in ((_CI, "ci.yml"), (_RELEASE, "release.yml")):
        for line in text.splitlines():
            if "grep" in line:
                assert "-oP" not in line and re.search(r"-\w*P\b", line) is None, (
                    f"grep -P survives in {path}: {line!r}"
                )


def test_no_paid_runner_labels() -> None:
    for text, path in ((_CI, "ci.yml"), (_RELEASE, "release.yml")):
        assert not _PAID_LABEL_RE.search(text), f"a paid runner label appears in {path}"


# --- the ubuntu-22.04 runner deprecation + the glibc 2.35 floor (ruling C-M6-R1) ------


def test_no_deprecated_ubuntu_22_04_runner_anywhere() -> None:
    """The ubuntu-22.04 runner image is in its brownout/deprecation window; no job may
    run on it. (The ubuntu:22.04 *container image* is fine — that is the floor.)"""
    for text, path in ((_CI, "ci.yml"), (_RELEASE, "release.yml"), (_VM_SMOKE, "vm-smoke.yml")):
        code = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
        assert "ubuntu-22.04" not in code, f"a job still runs on ubuntu-22.04 in {path}"


@pytest.mark.parametrize("arch", ["x86_64", "aarch64"])
def test_release_linux_legs_build_in_an_ubuntu_22_04_container(arch: str) -> None:
    binary_job = _job_body(_RELEASE, "binary")
    leg = re.search(
        rf"- runner:\s*(\S+)\s*\n\s*arch:\s*{arch}\s*\n\s*container:\s*(\S+)", binary_job
    )
    assert leg, f"no {arch} leg with a container"
    assert leg.group(1).startswith("ubuntu-24.04")
    assert leg.group(2) == "ubuntu:22.04"
    assert "container: ${{ matrix.container }}" in binary_job


def test_release_darwin_leg_has_no_container() -> None:
    binary_job = _job_body(_RELEASE, "binary")
    assert re.search(r"arch:\s*darwin-arm64\s*\n\s*container:\s*''", binary_job)


@pytest.mark.parametrize(("text", "job", "key"), [
    (_RELEASE, "binary", "matrix.arch"),
    (_CI, "frozen-smoke", "matrix.key"),
])
def test_linux_builds_check_the_glibc_floor(text: str, job: str, key: str) -> None:
    body = _job_body(text, job)
    # objdump comes from binutils, installed in the container before anything runs.
    assert "binutils" in body
    assert body.index("binutils") < body.index("actions/checkout")
    check = f'bash scripts/check-glibc-floor.sh "dist/devboost-${{{{ {key} }}}}" 2.35'
    assert check in body
    assert body.index("build-bundle.sh") < body.index(check)


def test_release_gates_on_the_per_arch_checksums() -> None:
    """B-I5: the build-time per-arch hashes are verified against the downloaded assets
    before the combined checksums.txt is generated — and every asset must be covered."""
    release_job = _job_body(_RELEASE, "release")
    for arch in ("x86_64", "aarch64", "darwin-arm64"):
        assert f"checksums-{arch}.txt" in release_job
    verify = release_job.index("sha256sum -c ../per-arch-checksums.txt")
    combine = release_job.index("> checksums.txt")
    assert verify < combine
    assert "has no build-time checksum" in release_job
    assert release_job.index("has no build-time checksum") < combine


def test_binary_compat_verifies_the_darwin_checksum_first() -> None:
    body = _job_body(_RELEASE, "binary-compat")
    assert body.index("shasum -a 256 -c checksums-darwin-arm64.txt") < body.index("chmod +x")


def test_build_artifacts_fail_when_a_file_is_missing() -> None:
    assert "if-no-files-found: error" in _job_body(_RELEASE, "binary")


# --- scripts/check-glibc-floor.sh -------------------------------------------------------
#
# The bundles are tiny PyInstaller onefiles whose archives PyInstaller's own CArchiveWriter
# wrote (fixtures/make_pyi_bundles.py): a fake bootloader stub marked GLIBC_2.14, then a
# compressed archive holding libpython (GLIBC_2.34), two extension modules (GLIBC_2.28 and
# either 2.35 or 2.39) and one non-ELF data file. The fake objdump reports the marker in
# the first 64 bytes of whichever file it is given, so each ELF reports its own version.

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_BUNDLE_OK = _FIXTURES / "pyi-onefile-ok.bin"
_BUNDLE_239 = _FIXTURES / "pyi-onefile-glibc239.bin"
_PER_FILE_OBJDUMP = (
    "head -c 64 \"$2\" | tr -c 'A-Za-z0-9_.' '\\n' | grep '^GLIBC_' | while read -r v; do\n"
    '  echo "0000000000000000      DF *UND*  0000000000000000 ($v) fn_$v"\n'
    "done"
)


def _objdump(stub_path: StubPath, *versions: str) -> None:
    """An objdump that reports the same *versions* for every file it is given."""
    lines = "".join(
        f"0000000000000000      DF *UND*  0000000000000000 (GLIBC_{v}) sym_{v.replace('.', '_')}\\n"
        for v in versions
    )
    stub_path.add("objdump", f"printf '{lines}'")


def _glibc(
    stub_path: StubPath, bundle: Path, *args: str, **env: str
) -> tuple[int, str, str]:
    res = run_bash(
        _GLIBC_CHECK,
        str(bundle),
        *args,
        env=stub_path.env(GLIBC_FLOOR_PYTHON=sys.executable, **env),
    )
    return res.returncode, res.stdout, res.stderr


def test_glibc_floor_passes_at_2_35(stub_path: StubPath) -> None:
    _objdump(stub_path, "2.2.5", "2.34", "2.35", "2.4")
    rc, out, err = _glibc(stub_path, _BUNDLE_OK, "2.35")
    assert rc == 0, err
    assert "highest GLIBC_2.35 <= 2.35" in out


def test_glibc_floor_fails_above_and_names_the_symbol(stub_path: StubPath) -> None:
    _objdump(stub_path, "2.2.5", "2.35", "2.38", "2.39")
    rc, _out, err = _glibc(stub_path, _BUNDLE_OK)  # default floor 2.35
    assert rc == 1
    assert "needs GLIBC_2.39, above the 2.35 floor" in err
    assert "sym_2_38" in err and "sym_2_39" in err
    assert "sym_2_35" not in err


def test_glibc_floor_orders_versions_numerically(stub_path: StubPath) -> None:
    """2.4 < 2.35 (version order, not string order)."""
    _objdump(stub_path, "2.4", "2.17")
    rc, out, err = _glibc(stub_path, _BUNDLE_OK, "2.35")
    assert rc == 0, err
    assert "highest GLIBC_2.17" in out


def test_glibc_floor_checks_every_bundled_elf(stub_path: StubPath) -> None:
    """The stub plus the three bundled ELF objects; the data file is not one of them."""
    stub_path.add("objdump", _PER_FILE_OBJDUMP)
    rc, out, err = _glibc(stub_path, _BUNDLE_OK)
    assert rc == 0, err
    assert "highest GLIBC_2.35 <= 2.35 across 4 ELF objects (bootloader + 3 bundled)" in out


def test_glibc_floor_fails_on_a_bundled_extension_above_the_floor(
    stub_path: StubPath,
) -> None:
    """The regression N1 names: the bootloader stub needs only GLIBC_2.14, so a check of
    the stub alone passes; an extension module inside the archive needs 2.39 and must fail."""
    stub_path.add("objdump", _PER_FILE_OBJDUMP)
    stub_only = subprocess.run(
        ["objdump", "-T", str(_BUNDLE_239)],
        env=stub_path.env(),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "GLIBC_2.14" in stub_only and "GLIBC_2.39" not in stub_only

    rc, _out, err = _glibc(stub_path, _BUNDLE_239)
    assert rc == 1
    assert "needs GLIBC_2.39, above the 2.35 floor (checked 4 ELF objects)" in err
    assert "lib-dynload/_ssl.cpython-312-x86_64-linux-gnu.so:" in err
    assert "libpython" not in err


def test_glibc_floor_refuses_a_file_that_is_not_a_bundle(
    stub_path: StubPath, tmp_path: Path
) -> None:
    stub_path.add("objdump", _PER_FILE_OBJDUMP)
    plain = tmp_path / "devboost-x86_64"
    plain.write_bytes(b"\x7fELF GLIBC_2.14 " + b"\0" * 64)
    rc, _out, err = _glibc(stub_path, plain)
    assert rc == 2
    assert "no PyInstaller archive cookie" in err


def test_glibc_floor_refuses_a_bundle_without_an_elf_libpython(
    stub_path: StubPath, tmp_path: Path
) -> None:
    """An empty archive (or one the reader mis-parses) must error, never pass on the stub."""
    stub_path.add("objdump", _PER_FILE_OBJDUMP)
    cookie = struct.pack(
        "!8sIIII64s", b"MEI\014\013\012\013\016", 88, 0, 0, 312, b"libpython3.12.so.1.0"
    )
    empty = tmp_path / "devboost-x86_64"
    empty.write_bytes(b"\x7fELF GLIBC_2.14 " + b"\0" * 64 + cookie)
    rc, _out, err = _glibc(stub_path, empty)
    assert rc == 2
    assert "has no ELF 'libpython3.12.so.1.0'" in err


def test_glibc_floor_without_objdump_is_an_error(stub_path: StubPath) -> None:
    if shutil.which("objdump", path="/usr/bin:/bin"):
        pytest.skip("a system objdump is on the fallback PATH")
    rc, _out, err = _glibc(stub_path, _BUNDLE_OK)
    assert rc == 2
    assert "objdump not found — install binutils" in err


def test_glibc_check_is_shellcheck_clean() -> None:
    if shutil.which("shellcheck") is None:
        pytest.skip("shellcheck is not installed")
    res = subprocess.run(
        ["shellcheck", "-x", str(_GLIBC_CHECK)], capture_output=True, text=True, check=False
    )
    assert res.returncode == 0, res.stdout


def test_actionlint_clean() -> None:
    actionlint = shutil.which("actionlint")
    if actionlint is None:
        pytest.skip("actionlint is not installed")
    result = subprocess.run(
        [actionlint],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"actionlint failed:\n{result.stdout}\n{result.stderr}"
