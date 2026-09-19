"""Text/regex checks over the CI and release workflow YAML — Task 5 (Lane D).

These read the workflow files as plain text, matching the other `scripts/*.sh` test
suites in this milestone: no PyYAML dependency, and every assertion names the exact
string that must (or must not) appear. `test_actionlint_clean` is the one structural
check, delegated to the real `actionlint` binary (skipped when it is absent).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WORKFLOWS_DIR = _REPO_ROOT / ".github" / "workflows"
_CI = (_WORKFLOWS_DIR / "ci.yml").read_text()
_RELEASE = (_WORKFLOWS_DIR / "release.yml").read_text()

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
    files_re = re.compile(r"files:\s*\|(.*?)(?=^\s{6}\S|\Z)", re.DOTALL | re.MULTILINE)
    files_match = files_re.search(release_job)
    assert files_match, "no `files:` block in the release step"
    assert "devboost-darwin-arm64" in files_match.group(1)


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
