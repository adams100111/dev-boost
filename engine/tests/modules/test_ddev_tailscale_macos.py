"""ddev (tap + mkcert), Tailscale (app + CLI + approval) and Playwright on macOS."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from devboost.core.errors import NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.modules import server
from devboost.modules.ddev import Ddev, DdevRemote
from devboost.modules.dev_stacks import Playwright
from devboost.modules.server import Tailscale
from tests.scripted import Scripted

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
APP_BIN = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"


@pytest.fixture(autouse=True)
def _no_host_tailscale_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Hermetic: the host's own /Applications/Tailscale.app must not change the outcome.
    monkeypatch.setattr(server, "_TS_APP", tmp_path / "absent" / "Tailscale.app")


def _no_brew_formulae(caroot: Path) -> Scripted:
    return Scripted(answers={
        ("brew", "list"): Result(1),
        ("mkcert", "-CAROOT"): Result(0, stdout=f"{caroot}\n"),
    })


def test_ddev_taps_installs_and_trusts_the_ca_when_someone_is_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("devboost.modules.ddev.is_interactive", lambda: True)
    ex = _no_brew_formulae(tmp_path / "ca")
    Ddev().install(Ctx(os=MAC, ex=ex))
    assert ["brew", "tap", "ddev/ddev"] in ex.calls
    assert ["brew", "install", "--formula", "-y", "ddev/ddev/ddev"] in ex.calls
    assert ["brew", "install", "--formula", "-y", "mkcert"] in ex.calls
    i = ex.calls.index(["mkcert", "-install"])
    assert ex.interactives[i] is True
    assert not any(c[0] == "sudo" for c in ex.calls)


def test_ddev_unattended_leaves_the_ca_to_the_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")  # nobody at the terminal
    ex = _no_brew_formulae(tmp_path / "ca")
    with pytest.raises(NeedsUser, match="mkcert -install"):
        Ddev().install(Ctx(os=MAC, ex=ex))
    assert ["mkcert", "-install"] not in ex.calls


def test_ddev_verify_needs_both_formulae_and_the_ca(tmp_path: Path) -> None:
    ca = tmp_path / "ca"
    ca.mkdir()
    (ca / "rootCA.pem").write_text("pem", encoding="utf-8")
    ready = Scripted(answers={("mkcert", "-CAROOT"): Result(0, stdout=f"{ca}\n")})
    assert Ddev().verify(Ctx(os=MAC, ex=ready)) is True
    no_ca = Scripted(answers={("mkcert", "-CAROOT"): Result(0, stdout=f"{tmp_path}/x\n")})
    assert Ddev().verify(Ctx(os=MAC, ex=no_ca)) is False


def test_ddev_update_upgrades_both_formulae(tmp_path: Path) -> None:
    ca = tmp_path / "ca"
    ca.mkdir()
    (ca / "rootCA.pem").write_text("pem", encoding="utf-8")
    ex = Scripted(answers={("mkcert", "-CAROOT"): Result(0, stdout=f"{ca}\n")})
    Ddev().install(Ctx(os=MAC, ex=ex, force=True))
    assert ["brew", "upgrade", "--formula", "ddev", "mkcert"] in ex.calls
    assert not any(c[:2] == ["brew", "install"] for c in ex.calls)


def test_ddev_remote_and_playwright_are_portable() -> None:
    assert DdevRemote.portable and Playwright.portable


def _tailscale(home: Path, state: str | None, *, installed: bool = True) -> Scripted:
    cli = str(home / ".local" / "bin" / "tailscale")
    status = (Result(0, stdout=json.dumps({"BackendState": state})) if state
              else Result(1, stderr="The Tailscale GUI failed to start"))
    return Scripted(answers={
        ("brew", "list"): Result(0 if installed else 1),
        ("brew", "info"): Result(0, stdout='{"casks": [{"auto_updates": true}]}'),
        (cli, "status", "--json"): status,
    })


def test_tailscale_connected_is_done_and_its_cli_is_on_path(tmp_path: Path) -> None:
    Tailscale().install(Ctx(os=MAC, ex=_tailscale(tmp_path, "Running")))
    cli = tmp_path / ".local" / "bin" / "tailscale"
    text = cli.read_text(encoding="utf-8")
    assert text.startswith("#!/bin/sh\n") and f'exec "{APP_BIN}" "$@"' in text
    assert os.access(cli, os.X_OK)
    assert Tailscale().verify(Ctx(os=MAC, ex=_tailscale(tmp_path, "Running"))) is True


def test_tailscale_installs_the_app_cask(tmp_path: Path) -> None:
    ex = _tailscale(tmp_path, "Running", installed=False)
    Tailscale().install(Ctx(os=MAC, ex=ex))
    assert ["brew", "install", "--cask", "-y", "--adopt", "tailscale-app"] in ex.calls


def test_tailscale_hand_installed_app_still_gets_its_cli_and_state_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # R6: brew reports the cask yet cannot take over the app on disk (PresentUnmanaged).
    # The app is there, so the wrapper and the connection check still happen.
    app = tmp_path / "Tailscale.app"
    app.mkdir()
    monkeypatch.setattr(server, "_TS_APP", app)
    ex = _tailscale(tmp_path, "Running")
    ex.answers[("brew", "install", "--cask")] = Result(
        1, stderr="Error: It seems the App source '/x/Tailscale.app' is different from "
        "the one being installed."
    )
    Tailscale().install(Ctx(os=MAC, ex=ex))
    cli = str(tmp_path / ".local" / "bin" / "tailscale")
    assert Path(cli).is_file()
    assert [cli, "status", "--json"] in ex.calls
    verify_ex = _tailscale(tmp_path, "Running", installed=False)
    assert Tailscale().verify(Ctx(os=MAC, ex=verify_ex)) is True


def test_tailscale_leaves_a_hand_installed_app_alone_and_writes_its_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # C-R21: the cask is a .pkg that brew cannot adopt, so an app brew does not manage is
    # never reinstalled over; the wrapper and the connection check still happen.
    app = tmp_path / "Tailscale.app"
    app.mkdir()
    monkeypatch.setattr(server, "_TS_APP", app)
    ex = _tailscale(tmp_path, "Running", installed=False)
    Tailscale().install(Ctx(os=MAC, ex=ex))
    assert not any(c[:2] == ["brew", "install"] for c in ex.calls)
    cli = tmp_path / ".local" / "bin" / "tailscale"
    assert f'exec "{APP_BIN}" "$@"' in cli.read_text(encoding="utf-8")
    assert [str(cli), "status", "--json"] in ex.calls


def test_tailscale_asks_for_sudo_up_front_on_macos() -> None:
    # The .pkg cask needs cached sudo; lazy sudo prompts only while tailscale is pending.
    assert Tailscale.needs_sudo_on_macos is True


def test_tailscale_joins_with_the_bundle_key_as_a_plain_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server, "_secret", lambda ctx, field: "tskey-abc")
    ex = _tailscale(tmp_path, "NeedsLogin")
    Tailscale().install(Ctx(os=MAC, ex=ex))
    cli = str(tmp_path / ".local" / "bin" / "tailscale")
    assert [cli, "up", "--authkey=tskey-abc"] in ex.calls
    assert not any("--ssh" in c for c in ex.calls)
    assert not any(c[0] == "sudo" for c in ex.calls)


def test_tailscale_awaiting_approval_needs_the_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server, "_secret", lambda ctx, field: None)
    ex = _tailscale(tmp_path, None)
    with pytest.raises(NeedsUser, match="Network Extensions"):
        Tailscale().install(Ctx(os=MAC, ex=ex))
    assert ["open", "-a", "Tailscale"] in ex.calls
    assert Tailscale().verify(Ctx(os=MAC, ex=_tailscale(tmp_path, None))) is False


def test_playwright_on_macos_skips_the_system_libraries(tmp_path: Path) -> None:
    ex = Scripted()
    Playwright().install(Ctx(os=MAC, ex=ex))
    assert not any("dnf" in c or "install-deps" in c for c in ex.calls)
    assert ["npx", "--yes", "playwright", "install", "chromium",
            "chromium-headless-shell"] in ex.calls
