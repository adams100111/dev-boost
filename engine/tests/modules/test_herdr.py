from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from devboost.core import log
from devboost.core.errors import InstallError
from devboost.core.osinfo import OsInfo
from devboost.core.settings import settings
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.herdr import Herdr

FEDORA_X86 = OsInfo(distro="fedora", family="fedora", arch="x86_64")
FEDORA_ARM = OsInfo(distro="fedora", family="fedora", arch="aarch64")


def _ctx(os_: OsInfo = FEDORA_X86, **kw: object) -> Ctx:
    return Ctx(os=os_, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_herdr_is_optional_agents_profile() -> None:
    assert Herdr.profiles == ("cli", "brain-tools")
    assert Herdr.category == "cli"


def test_herdr_verify_uses_which() -> None:
    assert Herdr().verify(_ctx(present=set())) is False
    on_path = _ctx(present={"herdr"}, scripts={"herdr": Result(0, stdout="herdr 0.9.1")})
    assert Herdr().verify(on_path) is True


def test_herdr_install_downloads_verified_x86_64(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    ctx = _ctx()
    Herdr().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert len(calls) == 1 and calls[0][:2] == ["sh", "-c"]
    script = calls[0][2]
    assert "herdr-linux-x86_64" in script
    assert "sha256sum -c -" in script
    assert "/home/tester/.local/bin/herdr" in script


def test_herdr_install_selects_aarch64(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    ctx = _ctx(FEDORA_ARM)
    Herdr().install(ctx)
    script = ctx.ex.calls[0][2]  # type: ignore[attr-defined]
    assert "herdr-linux-aarch64" in script


def test_herdr_install_traps_the_tmp_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    # A curl failure or checksum mismatch under `set -e` must still clean up $tmp — a
    # trailing `rm -rf` never runs on early exit, a trap does.
    monkeypatch.setenv("HOME", "/home/tester")
    ctx = _ctx()
    Herdr().install(ctx)
    script = ctx.ex.calls[0][2]  # type: ignore[attr-defined]
    assert 'trap \'rm -rf "$tmp"\' EXIT' in script


def test_herdr_install_pins_https_on_the_download(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    ctx = _ctx()
    Herdr().install(ctx)
    script = ctx.ex.calls[0][2]  # type: ignore[attr-defined]
    assert "--proto '=https'" in script


def test_herdr_verify_treats_an_unparseable_version_as_drift() -> None:
    # A corrupt or wrong-arch binary makes `herdr --version` fail or print junk — that
    # must not be mistaken for "installed" (I3), or the broken binary is never replaced.
    unparseable = _ctx(present={"herdr"}, scripts={"herdr": Result(0, stdout="not a version")})
    assert Herdr().verify(unparseable) is False
    failing = _ctx(present={"herdr"}, scripts={"herdr": Result(1, stderr="boom")})
    assert Herdr().verify(failing) is False


def test_herdr_install_raises_on_checksum_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    ctx = _ctx(scripts={"sh": Result(1, stderr="sha256sum: WARNING")})
    with pytest.raises(InstallError, match="checksum"):
        Herdr().install(ctx)


def test_herdr_install_raises_on_unknown_arch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    ctx = _ctx(OsInfo(distro="fedora", family="fedora", arch="riscv64"))
    with pytest.raises(InstallError, match="riscv64"):
        Herdr().install(ctx)


def test_optional_agents_profile_registered() -> None:
    data = tomllib.loads(settings.profiles_path.read_text(encoding="utf-8"))
    assert "herdr" in data["profiles"]["cli"]


from devboost.modules.herdr import _PLUGINS, HerdrPlugins  # noqa: E402


def test_herdr_plugins_requires_herdr() -> None:
    assert Herdr in HerdrPlugins.requires
    assert HerdrPlugins.profiles == ("cli", "optional-agents", "brain-tools")


def test_herdr_plugins_requires_xcode_clt_on_macos() -> None:
    # `herdr plugin install` runs `git rev-parse` internally (I1) — ordered after the CLT
    # on macOS (families=("macos",) drops the edge from Linux plans).
    from devboost.modules.macos import XcodeClt

    assert XcodeClt in HerdrPlugins.requires


def test_herdr_plugins_pins_a_ref_for_every_entry() -> None:
    assert _PLUGINS  # non-empty curated set
    for pid, source, ref in _PLUGINS:
        assert pid and "/" in source and ref  # id, owner/repo, and a pinned ref


def test_herdr_plugins_install_pins_each_plugin() -> None:
    ctx = _ctx()
    HerdrPlugins().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    for _pid, source, ref in _PLUGINS:
        assert ["herdr", "plugin", "install", source, "--ref", ref, "--yes"] in calls


def test_herdr_plugins_install_is_non_blocking() -> None:
    # Every `herdr` call fails, yet install must not raise and must attempt them all.
    ctx = _ctx(scripts={"herdr": Result(1, stderr="boom")})
    HerdrPlugins().install(ctx)  # no exception
    install_calls = [c for c in ctx.ex.calls if c[:3] == ["herdr", "plugin", "install"]]  # type: ignore[attr-defined]
    assert len(install_calls) == len(_PLUGINS)


def test_herdr_plugins_verify_checks_listing() -> None:
    ids = " ".join(pid for pid, _, _ in _PLUGINS)
    assert HerdrPlugins().verify(_ctx(scripts={"herdr": Result(0, stdout=ids)})) is True
    assert HerdrPlugins().verify(_ctx(scripts={"herdr": Result(0, stdout="none")})) is False


def test_herdr_plugins_configure_notify_writes_env_secrets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DEVBOOST_HERDR_TELEGRAM_TOKEN", "test-token")
    monkeypatch.setenv("DEVBOOST_HERDR_TELEGRAM_CHAT_ID", "test-chat")
    cfg_dir = tmp_path / "cfg"
    ctx = _ctx(scripts={"herdr": Result(0, stdout=str(cfg_dir))})
    HerdrPlugins()._configure_notify(ctx)
    env_file = cfg_dir / ".env"
    assert env_file.exists()
    text = env_file.read_text(encoding="utf-8")
    assert "TELEGRAM_BOT_TOKEN=test-token" in text
    assert "TELEGRAM_CHAT_ID=test-chat" in text


def test_herdr_plugins_configure_notify_skips_when_env_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DEVBOOST_HERDR_TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("DEVBOOST_HERDR_TELEGRAM_CHAT_ID", raising=False)
    cfg_dir = tmp_path / "cfg"
    ctx = _ctx(scripts={"herdr": Result(0, stdout=str(cfg_dir))})
    HerdrPlugins()._configure_notify(ctx)  # no exception
    assert not (cfg_dir / ".env").exists()
    assert not cfg_dir.exists()


def test_herdr_config_parses_and_sets_prefix() -> None:
    cfg = settings.root / "dotfiles" / "dot_config" / "herdr" / "config.toml"
    data = tomllib.loads(cfg.read_text(encoding="utf-8"))
    assert data["keys"]["prefix"] == "ctrl+b"
    assert "theme" in data


def test_herdr_plugins_reads_telegram_from_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("DEVBOOST_HERDR_TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("DEVBOOST_HERDR_TELEGRAM_CHAT_ID", raising=False)
    cfg_dir = tmp_path / "cfg"
    ctx = _ctx(present={"pass"}, scripts={
        "herdr": Result(0, stdout=str(cfg_dir)),
        "pass": Result(0, stdout="telegram\ntoken: P-TOKEN\nchat_id: P-CHAT\n"),
    })
    HerdrPlugins()._configure_notify(ctx)
    text = (cfg_dir / ".env").read_text(encoding="utf-8")
    assert "TELEGRAM_BOT_TOKEN=P-TOKEN" in text and "TELEGRAM_CHAT_ID=P-CHAT" in text
    assert ["pass", "show", "devboost/herdr-telegram"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_herdr_plugins_orders_after_pass_store() -> None:
    from devboost.modules.pass_store import PassStore

    assert HerdrPlugins.after == (PassStore,)


def test_herdr_plugins_pass_absent_is_a_skip_not_a_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    warned: list[str] = []
    skipped: list[str] = []
    monkeypatch.setattr(log, "warn", warned.append)
    monkeypatch.setattr(log, "skip", skipped.append)
    monkeypatch.setenv("DEVBOOST_HERDR_TELEGRAM_TOKEN", "E-TOKEN")
    monkeypatch.setenv("DEVBOOST_HERDR_TELEGRAM_CHAT_ID", "E-CHAT")
    ctx = _ctx(scripts={"herdr": Result(0, stdout=str(tmp_path / "cfg"))})  # no pass
    HerdrPlugins()._configure_notify(ctx)
    assert any("pass not installed" in m for m in skipped)
    assert not any("pass" in m for m in warned)


def test_herdr_plugins_mixes_pass_and_env_per_field(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The pass entry holds only the token: chat_id falls back to the env, field by field."""
    monkeypatch.setenv("DEVBOOST_HERDR_TELEGRAM_TOKEN", "E-TOKEN")
    monkeypatch.setenv("DEVBOOST_HERDR_TELEGRAM_CHAT_ID", "E-CHAT")
    cfg_dir = tmp_path / "cfg"
    ctx = _ctx(present={"pass"}, scripts={
        "herdr": Result(0, stdout=str(cfg_dir)),
        "pass": Result(0, stdout="telegram\ntoken: P-TOKEN\n"),
    })
    HerdrPlugins()._configure_notify(ctx)
    text = (cfg_dir / ".env").read_text(encoding="utf-8")
    assert "TELEGRAM_BOT_TOKEN=P-TOKEN" in text and "TELEGRAM_CHAT_ID=E-CHAT" in text
