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


def _fixture_repo(
    tmp_path: Path, pyproject_version: str, init_version: str, *, workflow: bool = False
) -> Path:
    """A minimal repo tree holding a copy of release.sh and the two version files (and,
    with *workflow*, a .github/workflows/release.yml beside them)."""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    if workflow:
        (root / ".github" / "workflows").mkdir(parents=True)
        (root / ".github" / "workflows" / "release.yml").write_text("name: release\n")
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


def test_release_dry_run_creates_a_draft_and_publishes_last(
    stub_path: StubPath, tmp_path: Path
) -> None:
    rc, out, err = _dry_run(stub_path, tmp_path)
    assert rc == 0, err
    lines = out.splitlines()
    create = next(ln for ln in lines if ln.startswith("+ gh release create"))
    assert "--draft" in create
    assert "--latest" not in create
    assert lines[-1].startswith("+ gh release edit v1.2.3 --draft=false --latest")


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


# --------------------------------------------------------------------------- real runs
# A gh stub backed by a directory per release (``<store>/<tag>/``) plus a draft flag file,
# so a full (non-dry) run can be observed end to end: every call is logged in order.

GH_STORE_STUB = r"""
printf '%s\n' "$*" >> "$GH_LOG"
[ "$1" = auth ] && exit 0
if [ "$1" = workflow ]; then
  [ -n "${GH_WF_STATE:-}" ] && echo "$GH_WF_STATE"
  exit 0
fi
[ "$1" = release ] || exit 0
sub="$2"; tag="$3"; shift 3
rel="$GH_STORE/$tag"
case "$sub" in
  view)
    [ -d "$rel" ] || exit 1
    case "$*" in
      "--json isDraft --jq .isDraft") cat "$rel.draft" ;;
      "--json assets --jq .assets[].name") ls "$rel" ;;
      --json*) printf 'assets: %s\n' "$(ls "$rel" | tr '\n' ' ')" ;;
    esac ;;
  create)
    mkdir -p "$rel"
    draft=false
    for a in "$@"; do [ "$a" = --draft ] && draft=true; done
    echo "$draft" > "$rel.draft" ;;
  upload)
    for a in "$@"; do
      case "$a" in --*) ;; *) cp "$a" "$rel/" ;; esac
    done ;;
  download)
    pat=""; dir=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --pattern) pat="$2"; shift 2 ;;
        --dir) dir="$2"; shift 2 ;;
        *) shift ;;
      esac
    done
    for f in "$rel"/*; do
      n="${f##*/}"
      if [ -n "$pat" ]; then
        case "$n" in $pat) ;; *) continue ;; esac
      fi
      cp "$f" "$dir/$n"
    done
    if [ -z "$pat" ] && [ -n "${GH_TAMPER:-}" ]; then echo evil > "$dir/$GH_TAMPER"; fi ;;
  edit)
    for a in "$@"; do [ "$a" = --draft=false ] && echo false > "$rel.draft"; done ;;
esac
exit 0
"""

#: The fake build: writes this host's assets into dist/ the way build-bundle.sh does.
FAKE_BUILD = """#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p dist
case "$(uname -s)" in
  Darwin) echo "darwin-bin" > dist/devboost-darwin-arm64 ;;
  *) echo "x86-bin" > dist/devboost-x86_64; echo "x86-tar" > dist/devboost-x86_64.tar.gz ;;
esac
"""

#: `git ls-remote --exit-code` succeeds only when GIT_TAG_ON_ORIGIN is set.
GIT_STUB = """
case "$1" in
  ls-remote) [ -n "${GIT_TAG_ON_ORIGIN:-}" ] && exit 0; exit 2 ;;
  *) echo abc1234 ;;
esac
"""

LINUX_AND_ARM = {
    "devboost-x86_64": "x86-bin",
    "devboost-x86_64.tar.gz": "x86-tar",
    "devboost-aarch64": "arm-bin",
    "devboost-aarch64.tar.gz": "arm-tar",
}


class _Store:
    def __init__(self, root: Path, log: Path) -> None:
        self.root = root
        self.log = log

    def seed(self, tag: str, files: dict[str, str], *, draft: bool) -> None:
        rel = self.root / tag
        rel.mkdir(parents=True)
        for name, body in files.items():
            (rel / name).write_text(body + "\n", encoding="utf-8")
        (self.root / f"{tag}.draft").write_text(
            "true\n" if draft else "false\n", encoding="utf-8"
        )

    def draft(self, tag: str) -> bool:
        return (self.root / f"{tag}.draft").read_text(encoding="utf-8").strip() == "true"

    def calls(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines()


def _real_run(
    stub_path: StubPath,
    tmp_path: Path,
    store: _Store,
    *args: str,
    system: str = "Darwin",
    machine: str = "arm64",
    workflow: bool = False,
    **env: str,
) -> subprocess.CompletedProcess[str]:
    stub_path.add("uname", _uname(system, machine))
    stub_path.add("gh", GH_STORE_STUB)
    stub_path.add("git", GIT_STUB)
    mk = tmp_path / "mk"
    mk.mkdir(exist_ok=True)
    stub_path.add("mktemp", f'/usr/bin/mktemp -d "{mk}/r.XXXXXX"')
    script = _fixture_repo(tmp_path, "1.2.3", "1.2.3", workflow=workflow)
    build = script.parent / "build-bundle.sh"
    build.write_text(FAKE_BUILD, encoding="utf-8")
    build.chmod(0o755)
    return run_bash(
        script,
        *args,
        env=stub_path.env(GH_STORE=str(store.root), GH_LOG=str(store.log), **env),
    )


@pytest.fixture
def store(tmp_path: Path) -> _Store:
    root = tmp_path / "store"
    root.mkdir()
    return _Store(root, tmp_path / "gh.log")


def test_first_host_leaves_a_verified_draft(
    stub_path: StubPath, tmp_path: Path, store: _Store
) -> None:
    """A-I5: the first host's run must never make a one-arch release `latest`."""
    res = _real_run(stub_path, tmp_path, store)
    assert res.returncode == 0, res.stderr
    assert store.draft("v1.2.3")
    calls = store.calls()
    create = next(c for c in calls if c.startswith("release create"))
    assert "--draft" in create and "--latest" not in create
    assert not [c for c in calls if c.startswith("release edit")]
    assert "left as a DRAFT — still missing: devboost-x86_64" in res.stdout
    assert "verified 1 asset(s) against checksums.txt" in res.stdout
    sums = (store.root / "v1.2.3" / "checksums.txt").read_text(encoding="utf-8")
    assert sums.split()[1] == "devboost-darwin-arm64"


def test_last_host_verifies_then_publishes_latest(
    stub_path: StubPath, tmp_path: Path, store: _Store
) -> None:
    """With every other arch already on the draft, the run uploads, regenerates and
    uploads checksums.txt, downloads it all back to verify, and only THEN publishes."""
    store.seed("v1.2.3", LINUX_AND_ARM, draft=True)
    res = _real_run(stub_path, tmp_path, store)
    assert res.returncode == 0, res.stderr
    assert not store.draft("v1.2.3")
    calls = store.calls()
    order = [
        next(i for i, c in enumerate(calls) if c.startswith("release upload") and "dist/" in c),
        next(i for i, c in enumerate(calls) if "checksums.txt" in c and "upload" in c),
        next(
            i for i, c in enumerate(calls)
            if c.startswith("release download") and "--pattern" not in c
        ),
        next(i for i, c in enumerate(calls) if c.startswith("release edit")),
    ]
    assert order == sorted(order), calls
    assert calls[order[-1]] == "release edit v1.2.3 --draft=false --latest"
    assert "published and marked latest" in res.stdout
    names = sorted(
        ln.split()[1]
        for ln in (store.root / "v1.2.3" / "checksums.txt").read_text().splitlines()
    )
    assert names == sorted([*LINUX_AND_ARM, "devboost-darwin-arm64"])


def test_a_tampered_asset_is_never_published(
    stub_path: StubPath, tmp_path: Path, store: _Store
) -> None:
    store.seed("v1.2.3", LINUX_AND_ARM, draft=True)
    res = _real_run(stub_path, tmp_path, store, GH_TAMPER="devboost-aarch64")
    assert res.returncode == 1
    assert "do not match checksums.txt — left as a draft" in res.stderr
    assert store.draft("v1.2.3")
    assert not [c for c in store.calls() if c.startswith("release edit")]


def test_publish_flag_ships_a_partial_release(
    stub_path: StubPath, tmp_path: Path, store: _Store
) -> None:
    res = _real_run(stub_path, tmp_path, store, "--publish")
    assert res.returncode == 0, res.stderr
    assert not store.draft("v1.2.3")
    assert "release edit v1.2.3 --draft=false --latest" in store.calls()


def test_a_published_release_is_never_clobbered(
    stub_path: StubPath, tmp_path: Path, store: _Store
) -> None:
    """Replacing an asset on a live release would serve it against stale checksums."""
    store.seed("v1.2.3", {**LINUX_AND_ARM, "devboost-darwin-arm64": "old"}, draft=False)
    res = _real_run(stub_path, tmp_path, store)
    assert res.returncode == 1
    assert "already published and has devboost-darwin-arm64" in res.stderr
    assert not [c for c in store.calls() if c.startswith("release upload")]
    body = (store.root / "v1.2.3" / "devboost-darwin-arm64").read_text(encoding="utf-8")
    assert body == "old\n"


def test_linux_host_uploads_binary_and_archive(
    stub_path: StubPath, tmp_path: Path, store: _Store
) -> None:
    res = _real_run(stub_path, tmp_path, store, system="Linux", machine="x86_64")
    assert res.returncode == 0, res.stderr
    assert sorted(p.name for p in (store.root / "v1.2.3").iterdir()) == [
        "checksums.txt",
        "devboost-x86_64",
        "devboost-x86_64.tar.gz",
    ]
    assert store.draft("v1.2.3")


# ------------------------------------------- N2: release.yml is the canonical release path


def _nothing_happened(store: _Store) -> None:
    calls = store.calls()
    assert not [c for c in calls if c.startswith(("release create", "release upload"))]
    assert not [c for c in calls if c.startswith("release edit")]
    assert list(store.root.iterdir()) == []


@pytest.mark.parametrize("state", ["active", ""], ids=["active", "state-unreadable"])
def test_refuses_while_release_yml_is_enabled(
    stub_path: StubPath, tmp_path: Path, store: _Store, state: str
) -> None:
    """Publishing a release.sh draft creates the tag, which starts release.yml, which
    rebuilds and uploads over the published release: so no manual run at all."""
    store.seed("v1.2.3", LINUX_AND_ARM, draft=True)
    before = sorted(p.name for p in (store.root / "v1.2.3").iterdir())
    res = _real_run(stub_path, tmp_path, store, workflow=True, GH_WF_STATE=state)
    assert res.returncode == 1
    assert "refusing — .github/workflows/release.yml is enabled" in res.stderr
    assert "git tag v1.2.3 && git push origin v1.2.3" in res.stderr
    assert not (tmp_path / "repo" / "dist").exists(), "built before refusing"
    assert not [c for c in store.calls() if c.startswith(("release upload", "release edit"))]
    assert sorted(p.name for p in (store.root / "v1.2.3").iterdir()) == before
    assert store.draft("v1.2.3")


def test_refuses_on_a_fresh_version_too(
    stub_path: StubPath, tmp_path: Path, store: _Store
) -> None:
    res = _real_run(stub_path, tmp_path, store, workflow=True, GH_WF_STATE="active")
    assert res.returncode == 1
    _nothing_happened(store)


def test_runs_when_release_yml_is_disabled(
    stub_path: StubPath, tmp_path: Path, store: _Store
) -> None:
    store.seed("v1.2.3", LINUX_AND_ARM, draft=True)
    res = _real_run(
        stub_path, tmp_path, store, workflow=True, GH_WF_STATE="disabled_manually"
    )
    assert res.returncode == 0, res.stderr
    assert "is disabled_manually — the manual path is allowed" in res.stdout
    assert "WARNING" not in res.stderr
    assert not store.draft("v1.2.3")


def test_emergency_override_warns_and_keeps_a_draft_when_the_tag_is_not_pushed(
    stub_path: StubPath, tmp_path: Path, store: _Store
) -> None:
    """Publishing would create the tag and start release.yml: stop at a verified draft."""
    store.seed("v1.2.3", LINUX_AND_ARM, draft=True)
    res = _real_run(
        stub_path,
        tmp_path,
        store,
        workflow=True,
        GH_WF_STATE="active",
        DEVBOOST_RELEASE_EMERGENCY="1",
    )
    assert res.returncode == 1
    assert "WARNING — EMERGENCY OVERRIDE (DEVBOOST_RELEASE_EMERGENCY=1)" in res.stderr
    assert "v1.2.3 is not on origin — publishing would push it" in res.stderr
    assert "verified 5 asset(s) against checksums.txt" in res.stdout
    assert store.draft("v1.2.3")
    assert not [c for c in store.calls() if c.startswith("release edit")]


def test_emergency_override_publishes_when_the_tag_is_already_on_origin(
    stub_path: StubPath, tmp_path: Path, store: _Store
) -> None:
    """Publishing a draft for a tag that already exists pushes no tag: no workflow run."""
    store.seed("v1.2.3", LINUX_AND_ARM, draft=True)
    res = _real_run(
        stub_path,
        tmp_path,
        store,
        workflow=True,
        GH_WF_STATE="active",
        DEVBOOST_RELEASE_EMERGENCY="1",
        GIT_TAG_ON_ORIGIN="1",
    )
    assert res.returncode == 0, res.stderr
    assert "WARNING — EMERGENCY OVERRIDE" in res.stderr
    assert not store.draft("v1.2.3")
    assert store.calls()[-2] == "release edit v1.2.3 --draft=false --latest"


def test_the_override_needs_exactly_1(
    stub_path: StubPath, tmp_path: Path, store: _Store
) -> None:
    res = _real_run(
        stub_path,
        tmp_path,
        store,
        workflow=True,
        GH_WF_STATE="active",
        DEVBOOST_RELEASE_EMERGENCY="yes",
    )
    assert res.returncode == 1
    assert "refusing" in res.stderr
    _nothing_happened(store)
