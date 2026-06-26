from __future__ import annotations

from pathlib import Path

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import config, copr, flatpak, mise
from devboost.model import Ctx

FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_copr_enable() -> None:
    ctx = _ctx()
    copr.enable(ctx, "atim/lazygit")
    assert ["sudo", "dnf", "copr", "enable", "-y", "atim/lazygit"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_flatpak_remote_add_idempotent() -> None:
    ctx = _ctx(scripts={"flatpak": Result(0, stdout="flathub\n")})
    flatpak.remote_add(ctx, "flathub", "url")
    assert not any("remote-add" in c for c in ctx.ex.calls)  # type: ignore[attr-defined]


def test_flatpak_remote_add_when_absent() -> None:
    ctx = _ctx(scripts={"flatpak": Result(0, stdout="")})
    flatpak.remote_add(ctx, "flathub", "url")
    assert ["flatpak", "remote-add", "--if-not-exists", "flathub", "url"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_mise_use_global() -> None:
    ctx = _ctx()
    mise.use_global(ctx, "node@22")
    assert ["mise", "use", "-g", "node@22"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_config_write_kv_appends_then_replaces(tmp_path: Path) -> None:
    conf = tmp_path / "dnf.conf"
    ctx = _ctx()
    config.write_kv(ctx, str(conf), "max_parallel_downloads", "10")
    assert "max_parallel_downloads=10" in conf.read_text(encoding="utf-8")
    config.write_kv(ctx, str(conf), "max_parallel_downloads", "20")
    text = conf.read_text(encoding="utf-8")
    assert "max_parallel_downloads=20" in text and "=10" not in text


def test_config_comment_block() -> None:
    text = "# BEGIN NVM\nexport NVM_DIR=x\n# END NVM\nkeep\n"
    out = config.comment_block(text, "# BEGIN NVM", "# END NVM")
    assert "# export NVM_DIR=x" in out and "keep" in out
