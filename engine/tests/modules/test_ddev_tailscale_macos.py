"""ddev (tap + mkcert), Tailscale (app + CLI + approval) and Playwright on macOS."""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

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


def _ca_on_disk_but_untrusted(tmp_path: Path) -> Scripted:
    ca = tmp_path / "ca"
    ca.mkdir(exist_ok=True)
    (ca / "rootCA.pem").write_text("pem", encoding="utf-8")  # e.g. a cancelled -install
    return Scripted(answers={
        ("brew", "list"): Result(0),
        ("mkcert", "-CAROOT"): Result(0, stdout=f"{ca}\n"),
        ("security", "verify-cert"): Result(1, stderr="CSSMERR_TP_NOT_TRUSTED"),
    })


def test_ddev_a_ca_file_macos_does_not_trust_is_not_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ex = _ca_on_disk_but_untrusted(tmp_path)
    assert Ddev().verify(Ctx(os=MAC, ex=ex)) is False
    pem = str(tmp_path / "ca" / "rootCA.pem")
    assert ["security", "verify-cert", "-c", pem] in ex.calls
    monkeypatch.setattr("devboost.modules.ddev.is_interactive", lambda: True)
    ex = _ca_on_disk_but_untrusted(tmp_path)
    Ddev().install(Ctx(os=MAC, ex=ex))
    assert ["mkcert", "-install"] in ex.calls
    monkeypatch.setattr("devboost.modules.ddev.is_interactive", lambda: False)
    with pytest.raises(NeedsUser, match="mkcert -install"):
        Ddev().install(Ctx(os=MAC, ex=_ca_on_disk_but_untrusted(tmp_path)))


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


def _record_key_files(
    ex: Scripted, monkeypatch: pytest.MonkeyPatch
) -> list[tuple[Path, str, int, int]]:
    """While each call runs, read any `--auth-key=file:` it names: (path, text, file mode,
    dir mode). The file only exists during the call."""
    seen: list[tuple[Path, str, int, int]] = []
    real = ex.run

    def run(argv: Sequence[str], **kw: Any) -> Result:
        for arg in argv:
            if arg.startswith("--auth-key=file:"):
                path = Path(arg.removeprefix("--auth-key=file:"))
                seen.append((path, path.read_text(encoding="utf-8"),
                             path.stat().st_mode & 0o777, path.parent.stat().st_mode & 0o777))
        return real(argv, **kw)

    monkeypatch.setattr(ex, "run", run)
    return seen


def test_tailscale_joins_with_the_bundle_key_as_a_plain_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server, "_secret", lambda ctx, field: "tskey-abc")
    ex = _tailscale(tmp_path, "NeedsLogin")
    seen = _record_key_files(ex, monkeypatch)
    Tailscale().install(Ctx(os=MAC, ex=ex))
    cli = str(tmp_path / ".local" / "bin" / "tailscale")
    ups = [c for c in ex.calls if c[:2] == [cli, "up"]]
    assert len(ups) == 1 and len(ups[0]) == 3 and ups[0][2].startswith("--auth-key=file:")
    # The key never appears on argv (`ps` shows argv); it sits in a private 0600 file
    # that is gone once `tailscale up` returns.
    assert not any("tskey-abc" in arg for c in ex.calls for arg in c)
    [(path, text, file_mode, dir_mode)] = seen
    assert (text, file_mode, dir_mode) == ("tskey-abc", 0o600, 0o700)
    assert not path.exists() and not path.parent.exists()
    assert not any("--ssh" in c for c in ex.calls)
    assert not any(c[0] == "sudo" for c in ex.calls)


def test_tailscale_removes_the_key_file_when_up_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server, "_secret", lambda ctx, field: "tskey-old")
    ex = _tailscale(tmp_path, "NeedsLogin")
    seen = _record_key_files(ex, monkeypatch)
    ex.answers[(str(tmp_path / ".local" / "bin" / "tailscale"), "up")] = Result(1)
    with pytest.raises(NeedsUser):
        Tailscale().install(Ctx(os=MAC, ex=ex))
    [(path, _, _, _)] = seen
    assert not path.parent.exists()


def test_tailscale_verify_never_starts_a_stopped_app(tmp_path: Path) -> None:
    # On macOS the CLI is the app binary: `status` against a stopped app may launch the GUI.
    ex = _tailscale(tmp_path, "Running")
    ex.answers[("pgrep", "-x", "Tailscale")] = Result(1)
    (tmp_path / ".local" / "bin").mkdir(parents=True)
    (tmp_path / ".local" / "bin" / "tailscale").write_text("x", encoding="utf-8")
    assert Tailscale().verify(Ctx(os=MAC, ex=ex)) is False
    assert not any(c[1:2] == ["status"] for c in ex.calls)
    assert ["pgrep", "-x", "Tailscale"] in ex.calls


def test_tailscale_sudo_needed_only_without_the_app_or_its_cask(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Installed but not approved (state NeedsLogin) needs the user, never a password.
    assert Tailscale().sudo_needed(Ctx(os=MAC, ex=_tailscale(tmp_path, "NeedsLogin"))) is False
    absent = _tailscale(tmp_path, None, installed=False)
    assert Tailscale().sudo_needed(Ctx(os=MAC, ex=absent)) is True
    # --force upgrades a brew-managed .pkg cask, which runs its installer with sudo.
    forced = Ctx(os=MAC, ex=_tailscale(tmp_path, "Running"), force=True)
    assert Tailscale().sudo_needed(forced) is True
    # A hand-installed app is left alone (C-R21), even under --force: no sudo.
    app = tmp_path / "Tailscale.app"
    app.mkdir()
    monkeypatch.setattr(server, "_TS_APP", app)
    assert Tailscale().sudo_needed(Ctx(os=MAC, ex=absent)) is False
    hand = _tailscale(tmp_path, "Running", installed=False)
    assert Tailscale().sudo_needed(Ctx(os=MAC, ex=hand, force=True)) is False


def test_tailscale_awaiting_approval_needs_the_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server, "is_interactive", lambda: True)
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


def test_tailscale_unattended_never_opens_the_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")  # nobody at the terminal
    monkeypatch.setattr(server, "_secret", lambda ctx, field: None)
    ex = _tailscale(tmp_path, None)
    with pytest.raises(NeedsUser, match="open Tailscale and approve"):
        Tailscale().install(Ctx(os=MAC, ex=ex))
    assert not any(c[0] == "open" for c in ex.calls)


def test_tailscale_a_rejected_auth_key_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server, "_secret", lambda ctx, field: "tskey-old")
    ex = _tailscale(tmp_path, "NeedsLogin")
    cli = str(tmp_path / ".local" / "bin" / "tailscale")
    ex.answers[(cli, "up")] = Result(1, stderr="invalid key: unable to validate API key")
    with pytest.raises(NeedsUser, match=r"TAILSCALE_AUTHKEY .* rejected \(expired or revoked\)"):
        Tailscale().install(Ctx(os=MAC, ex=ex))
    assert not any(c[0] == "open" for c in ex.calls)


def test_tailscale_leaves_a_symlinked_cli_alone(tmp_path: Path) -> None:
    target = tmp_path / "their-tailscale"
    target.write_bytes(b"\xcf\xfa\xed\xfe not utf-8")  # a Mach-O-like binary
    cli = tmp_path / ".local" / "bin" / "tailscale"
    cli.parent.mkdir(parents=True)
    cli.symlink_to(target)
    Tailscale().install(Ctx(os=MAC, ex=_tailscale(tmp_path, "Running")))
    assert cli.is_symlink() and cli.readlink() == target
    assert target.read_bytes() == b"\xcf\xfa\xed\xfe not utf-8"


@pytest.mark.parametrize(
    "content", [b"#!/bin/sh\nexec my-own-tailscale \"$@\"\n", b"\xcf\xfa\xed\xfe binary"]
)
def test_tailscale_leaves_a_foreign_cli_file_alone(tmp_path: Path, content: bytes) -> None:
    cli = tmp_path / ".local" / "bin" / "tailscale"
    cli.parent.mkdir(parents=True)
    cli.write_bytes(content)
    Tailscale().install(Ctx(os=MAC, ex=_tailscale(tmp_path, "Running")))
    assert cli.read_bytes() == content


def test_tailscale_repairs_the_exec_bit_of_its_own_wrapper(tmp_path: Path) -> None:
    cli = tmp_path / ".local" / "bin" / "tailscale"
    cli.parent.mkdir(parents=True)
    cli.write_bytes(server._TS_WRAPPER.encode("utf-8"))
    cli.chmod(0o644)
    Tailscale().install(Ctx(os=MAC, ex=_tailscale(tmp_path, "Running")))
    assert os.access(cli, os.X_OK)
