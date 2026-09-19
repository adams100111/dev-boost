"""Final review minors: the Linux cap under --force, relinking, the ddev tap, ~/.docker."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules import _docker_colima as col
from devboost.modules import _docker_runtime as rt
from devboost.modules.ddev import Ddev
from devboost.modules.docker import DockerBuildCacheGc
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
#: `brew info --json=v2 --formula docker` for an installed but UNLINKED keg.
UNLINKED = json.dumps({"formulae": [{"name": "docker", "linked_keg": None}]})
LINKED = json.dumps({"formulae": [{"name": "docker", "linked_keg": "28.0.1"}]})


@pytest.fixture(autouse=True)
def _seams(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(col, "DOCKER_SOCK", tmp_path / "run" / "docker.sock")
    monkeypatch.setattr(rt, "_sleep", lambda s: None)


def _ctx(*rules: tuple[tuple[str, ...], Result]) -> Ctx:
    return Ctx(os=MAC, ex=RuleExecutor(rules=list(rules)))


def _calls(ctx: Ctx) -> list[list[str]]:
    return ctx.ex.calls  # type: ignore[attr-defined, no-any-return]


# ── M1: --force never overrides the user's own cap on Linux either ──────────────────────
def test_linux_force_keeps_the_users_cap_and_never_restarts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon = tmp_path / "daemon.json"
    daemon.write_text(
        json.dumps({"builder": {"gc": {"enabled": True, "defaultKeepStorage": "50GB"}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("DEVBOOST_DOCKER_DAEMON_JSON", str(daemon))
    ctx = Ctx(os=FEDORA, ex=FakeExecutor(), force=True)
    DockerBuildCacheGc().install(ctx)
    data = json.loads(daemon.read_text(encoding="utf-8"))
    assert data["builder"]["gc"]["defaultKeepStorage"] == "50GB"
    assert not any("restart" in " ".join(c) for c in _calls(ctx))


def test_linux_still_writes_the_cap_when_there_is_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon = tmp_path / "daemon.json"
    monkeypatch.setenv("DEVBOOST_DOCKER_DAEMON_JSON", str(daemon))
    ctx = Ctx(os=FEDORA, ex=FakeExecutor())
    DockerBuildCacheGc().install(ctx)
    data = json.loads(daemon.read_text(encoding="utf-8"))
    assert data["builder"]["gc"] == {"enabled": True, "defaultKeepStorage": "20GB"}
    assert ["sudo", "systemctl", "restart", "docker.service"] in _calls(ctx)


# ── M2: relink whenever the docker formula is unlinked, cask or no cask ─────────────────
def test_colima_relinks_an_unlinked_docker_formula_without_the_cask() -> None:
    ctx = _ctx(
        (("list", "--cask", "docker-desktop"), Result(1)),  # the cask is NOT installed
        (("info", "--json=v2", "--formula", "docker"), Result(0, stdout=UNLINKED)),
    )
    col.Colima().install(ctx)
    assert ["brew", "link", "--overwrite", "docker", "docker-compose"] in _calls(ctx)


def test_colima_leaves_a_linked_formula_alone() -> None:
    ctx = _ctx(
        (("list", "--cask", "docker-desktop"), Result(1)),
        (("info", "--json=v2", "--formula", "docker"), Result(0, stdout=LINKED)),
    )
    col.Colima().install(ctx)
    assert not any(c[:2] == ["brew", "link"] for c in _calls(ctx))


def test_colima_still_relinks_when_the_cask_is_installed() -> None:
    ctx = _ctx()  # everything installed, `brew info` unparsable → the cask decides
    col.Colima().install(ctx)
    assert ["brew", "link", "--overwrite", "docker", "docker-compose"] in _calls(ctx)


# ── M3: the ddev tap is trusted before an upgrade too ───────────────────────────────────
def _ca_ready_ctx(
    tmp_path: Path, *rules: tuple[tuple[str, ...], Result], force: bool = False
) -> Ctx:
    """A ctx whose mkcert CA is already installed and trusted (so install runs to the end)."""
    caroot = tmp_path / "caroot"
    caroot.mkdir()
    (caroot / "rootCA.pem").write_text("pem", encoding="utf-8")
    return Ctx(
        os=MAC,
        ex=RuleExecutor(rules=[*rules, (("-CAROOT",), Result(0, stdout=f"{caroot}\n"))]),
        force=force,
    )



def test_ddev_trusts_its_tap_before_upgrading(tmp_path: Path) -> None:
    """M3: the trust store moves with XDG_CONFIG_HOME, so --force must trust again."""
    ctx = _ca_ready_ctx(tmp_path, force=True)  # ddev + mkcert already installed
    Ddev().install(ctx)
    calls = _calls(ctx)
    trust = calls.index(["brew", "trust", "--tap", "ddev/ddev"])
    upgrade = next(i for i, c in enumerate(calls) if c[:2] == ["brew", "upgrade"])
    assert trust < upgrade


def test_ddev_trusts_its_tap_before_installing(tmp_path: Path) -> None:
    ctx = _ca_ready_ctx(tmp_path, (("--versions", "ddev"), Result(1)))
    Ddev().install(ctx)
    calls = _calls(ctx)
    trust = calls.index(["brew", "trust", "--tap", "ddev/ddev"])
    install = next(i for i, c in enumerate(calls) if c[:3] == ["brew", "install", "--formula"])
    assert trust < install


# ── M5: ~/.docker/config.json is written atomically, keeping its mode ────────────────────
def test_docker_config_is_written_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / ".docker" / "config.json"
    cfg.parent.mkdir()
    cfg.write_text(json.dumps({"auths": {"ghcr.io": {"auth": "x"}}}), encoding="utf-8")
    cfg.chmod(0o600)
    seen: list[str] = []
    real_replace = os.replace

    def _spy(src: object, dst: object) -> None:
        seen.append(str(dst))
        real_replace(src, dst)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "replace", _spy)
    col.Colima().install(_ctx())
    assert seen == [str(cfg)]  # a temp file renamed into place, never a truncating write
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert data["auths"] == {"ghcr.io": {"auth": "x"}}
    assert data["cliPluginsExtraDirs"] == [col.CLI_PLUGINS_DIR]
    assert oct(cfg.stat().st_mode)[-3:] == "600"
    assert not [p.name for p in cfg.parent.iterdir() if p.name.startswith(".config.json")]
