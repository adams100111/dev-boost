from __future__ import annotations

import re
from pathlib import Path

from typer.testing import CliRunner

from devboost.cli.app import app

runner = CliRunner()


def _strip_ansi(s: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


def test_usb_help_lists_the_command() -> None:
    result = runner.invoke(app, ["installer", "--help"])
    assert result.exit_code == 0
    clean = _strip_ansi(result.stdout)
    assert "--device" in clean and "--profile" in clean


def test_usb_no_wizard_requires_device() -> None:
    # --no-wizard with no --device should error out (exit 1), not prompt.
    result = runner.invoke(app, ["installer", "--no-wizard"])
    assert result.exit_code != 0


def test_usb_dry_run_previews_without_building(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import devboost.cli.installer as cli_installer
    from devboost.media.probe import DiskState

    monkeypatch.setattr(cli_installer, "probe", lambda ctx, device: DiskState("blank"))

    called = {"build": False}
    monkeypatch.setattr(cli_installer, "build", lambda *a, **k: called.__setitem__("build", True))

    result = runner.invoke(
        app, ["installer", "--device", "/dev/sdb", "--no-wizard", "--dry-run", "--yes"]
    )
    assert result.exit_code == 0
    clean = _strip_ansi(result.stdout)
    assert "/dev/sdb" in clean and "build" in clean
    assert called["build"] is False
    assert "Zero-touch" in clean or "netinst" in clean


def test_usb_yes_on_devboost_stick_updates_not_wipes(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import devboost.cli.installer as cli_installer
    from devboost.media.marker import Marker
    from devboost.media.probe import DiskState

    marker = Marker(version="0.1.0", os_id="fedora-44", arch="x86_64",
                    built_at="2026-06-26T00:00:00+00:00")
    monkeypatch.setattr(cli_installer, "probe", lambda ctx, device: DiskState("devboost", marker))
    monkeypatch.setattr(cli_installer, "build", lambda *a, **k: None)
    result = runner.invoke(
        app, ["installer", "--device", "/dev/sdb", "--no-wizard", "--dry-run", "--yes"]
    )
    assert result.exit_code == 0
    clean = _strip_ansi(result.stdout)
    assert "update" in clean  # --yes alone does NOT force a wipe on a dev-boost stick


def test_usb_rebuild_flag_forces_build_on_devboost_stick(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import devboost.cli.installer as cli_installer
    from devboost.media.marker import Marker
    from devboost.media.probe import DiskState

    marker = Marker(version="0.1.0", os_id="fedora-44", arch="x86_64",
                    built_at="2026-06-26T00:00:00+00:00")
    monkeypatch.setattr(cli_installer, "probe", lambda ctx, device: DiskState("devboost", marker))
    monkeypatch.setattr(cli_installer, "build", lambda *a, **k: None)
    result = runner.invoke(
        app, ["installer", "--device", "/dev/sdb", "--no-wizard", "--dry-run", "--rebuild"]
    )
    assert result.exit_code == 0
    assert "build" in _strip_ansi(result.stdout)


def test_usb_build_failure_exits_cleanly_without_a_traceback(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A MediaError out of build() is a user-facing refusal, not a crash: clean exit 1.

    DeviceError subclasses MediaError; installer() only guarded MediaConfig construction, so
    a refusal from build() escaped as a PyInstaller traceback.
    """
    import devboost.cli.installer as cli_installer
    from devboost.core.errors import DeviceError
    from devboost.media.probe import DiskState

    monkeypatch.setattr(cli_installer, "probe", lambda ctx, device: DiskState("blank"))

    def _boom(*a, **k):  # type: ignore[no-untyped-def]
        raise DeviceError("refusing /dev/sdb: partition /dev/sdb1 is mounted (/run/media/x)")

    monkeypatch.setattr(cli_installer, "build", _boom)

    result = runner.invoke(
        app, ["installer", "--device", "/dev/sdb", "--no-wizard", "--yes"]
    )
    assert result.exit_code == 1
    assert not isinstance(result.exception, DeviceError)  # handled, not propagated


def test_usb_unpinned_arch_exits_cleanly(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import devboost.cli.installer as cli_installer
    from devboost.media.probe import DiskState

    monkeypatch.setattr(cli_installer, "probe", lambda ctx, device: DiskState("blank"))
    result = runner.invoke(
        app,
        ["installer", "--device", "/dev/sdb", "--no-wizard",
         "--arch", "riscv64", "--dry-run", "--yes"],
    )
    assert result.exit_code == 1  # iso_for raises MediaError → caught → clean exit, not a traceback


def test_usb_wizard_honours_the_answered_cache_dir(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The wizard asks "Cache dir for downloads:" — so the answer must be used, and the
    downloads must survive the build. Checking the --cache-dir *flag* (always None on the
    wizard path) instead sent every run to a temp dir that was then deleted, silently
    re-downloading the ISO every time while the prompt implied otherwise.
    """
    import devboost.cli.installer as cli_installer
    from devboost.media import wizard
    from devboost.media.config import IsoSpec, MediaConfig
    from devboost.media.probe import DiskState

    answered = tmp_path / "keepme"
    cfg = MediaConfig(
        device="/dev/sdb",
        arch="x86_64",
        iso=IsoSpec(id="fedora-44", url="https://x/f.iso", sha256="a" * 64, edition="Everything"),
        cache_dir=answered,
        assume_yes=True,
    )
    monkeypatch.setattr(wizard, "run", lambda ctx: cfg)  # same module object installer() uses
    monkeypatch.setattr(cli_installer, "probe", lambda ctx, device: DiskState("blank"))

    seen: dict[str, object] = {}

    def _build(ctx, c, dl, cache, *, reporter):  # type: ignore[no-untyped-def]
        seen["cache_dir"] = c.cache_dir
        (cache.cache_dir / "fedora-44.iso").write_bytes(b"a 2GB ISO, pretend")

    monkeypatch.setattr(cli_installer, "build", _build)

    result = runner.invoke(app, ["installer"])
    assert result.exit_code == 0
    assert seen["cache_dir"] == answered  # the answer reaches the stages
    assert (answered / "fedora-44.iso").exists()  # and is NOT deleted afterwards


def test_usb_flags_path_without_cache_dir_stays_ephemeral(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """--device without --cache-dir keeps the documented opt-in behaviour: a temp dir that is
    cleaned up. Only the wizard, which explicitly asks, implies keeping them."""
    import devboost.cli.installer as cli_installer
    from devboost.media.probe import DiskState

    monkeypatch.setattr(cli_installer, "probe", lambda ctx, device: DiskState("blank"))
    seen: dict[str, object] = {}

    def _build(ctx, c, dl, cache, *, reporter):  # type: ignore[no-untyped-def]
        seen["cache_dir"] = c.cache_dir

    monkeypatch.setattr(cli_installer, "build", _build)
    result = runner.invoke(app, ["installer", "--device", "/dev/sdb", "--no-wizard", "--yes"])
    assert result.exit_code == 0
    assert not Path(str(seen["cache_dir"])).exists()  # cleaned up after the build


def test_usb_secrets_paths_expand_a_tilde(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """`--secrets ~/secrets.age` must not look for a literal `~` directory.

    Nothing in media/ or cli/installer.py expanded ~, so a tilde path was staged as-is and
    then silently failed to exist — compounding the ks.cfg `blkid -L VTOY` bug, which meant
    the age bundle never reached the target even when the path was correct.
    """
    import devboost.cli.installer as cli_installer
    from devboost.media.probe import DiskState

    home = tmp_path / "home"
    home.mkdir()
    (home / "secrets.age").write_bytes(b"age")
    (home / "age-key.txt").write_bytes(b"key")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(cli_installer, "probe", lambda ctx, device: DiskState("blank"))

    seen: dict[str, object] = {}

    def _build(ctx, c, dl, cache, *, reporter):  # type: ignore[no-untyped-def]
        seen["secrets"] = c.secrets_path
        seen["key"] = c.secrets_key_path

    monkeypatch.setattr(cli_installer, "build", _build)
    result = runner.invoke(
        app,
        ["installer", "--device", "/dev/sdb", "--no-wizard", "--yes",
         "--secrets", "~/secrets.age", "--secrets-key", "~/age-key.txt"],
    )
    assert result.exit_code == 0
    assert seen["secrets"] == (home / "secrets.age").resolve()
    assert seen["key"] == (home / "age-key.txt").resolve()


def test_usb_iso_path_serves_the_local_file_without_downloading(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """--iso-path supplies the bytes; the catalog still supplies id/url/sha/family."""
    import devboost.cli.installer as cli_installer
    from devboost.media.catalog import iso_for
    from devboost.media.probe import DiskState

    pinned = iso_for("fedora-44", "x86_64")
    local = tmp_path / "Fedora.iso"
    local.write_bytes(b"pinned bytes")
    # Pretend this file IS the pinned release.
    monkeypatch.setattr("devboost.media.download.sha256_of", lambda p: pinned.sha256)
    monkeypatch.setattr(cli_installer, "probe", lambda ctx, device: DiskState("blank"))

    seen: dict[str, object] = {}

    def _build(ctx, cfg, dl, cache, *, reporter):  # type: ignore[no-untyped-def]
        seen["path"] = dl.fetch(pinned.url, "fedora-44.iso", pinned.sha256)

    monkeypatch.setattr(cli_installer, "build", _build)

    result = runner.invoke(
        app,
        ["installer", "--device", "/dev/sdb", "--no-wizard", "--yes", "--iso-path", str(local)],
    )
    assert result.exit_code == 0
    assert seen["path"] == local.resolve()  # served from disk, no network


def test_usb_bad_iso_path_fails_before_anything_is_wiped(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The primary ISO is fetched AFTER the wipe and the Ventoy install, so verification must
    happen before build() is entered — otherwise a wrong ISO costs the stick before it is
    ever read. Same late-validation shape as the auto-mount refusal."""
    import devboost.cli.installer as cli_installer
    from devboost.media.probe import DiskState

    wrong = tmp_path / "wrong.iso"
    wrong.write_bytes(b"not the pinned release")
    monkeypatch.setattr(cli_installer, "probe", lambda ctx, device: DiskState("blank"))

    called = {"build": False}
    monkeypatch.setattr(cli_installer, "build", lambda *a, **k: called.__setitem__("build", True))

    result = runner.invoke(
        app,
        ["installer", "--device", "/dev/sdb", "--no-wizard", "--yes", "--iso-path", str(wrong)],
    )
    assert result.exit_code == 1
    assert called["build"] is False  # nothing was wiped


def test_usb_iso_path_expands_a_tilde(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Nothing in media/ expands ~, so Path("~/x.iso") would look for a literal ~ dir."""
    import devboost.cli.installer as cli_installer
    from devboost.media.catalog import iso_for
    from devboost.media.probe import DiskState

    pinned = iso_for("fedora-44", "x86_64")
    home = tmp_path / "home"
    (home / "isos").mkdir(parents=True)
    (home / "isos" / "f.iso").write_bytes(b"x")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr("devboost.media.download.sha256_of", lambda p: pinned.sha256)
    monkeypatch.setattr(cli_installer, "probe", lambda ctx, device: DiskState("blank"))

    seen: dict[str, object] = {}

    def _build(ctx, cfg, dl, cache, *, reporter):  # type: ignore[no-untyped-def]
        seen["iso_path"] = cfg.iso_path

    monkeypatch.setattr(cli_installer, "build", _build)
    result = runner.invoke(
        app,
        ["installer", "--device", "/dev/sdb", "--no-wizard", "--yes", "--iso-path", "~/isos/f.iso"],
    )
    assert result.exit_code == 0
    assert seen["iso_path"] == (home / "isos" / "f.iso").resolve()
