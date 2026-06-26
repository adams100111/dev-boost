from __future__ import annotations

from pathlib import Path

from devboost.cli import devhygiene as dh
from devboost.cli import lifecycle as lc
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx

FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_scaffold_module_writes_typed_file(tmp_path: Path) -> None:
    path = lc.scaffold_module(tmp_path, "ripgrep-extra")
    assert path.name == "ripgrep_extra.py"
    text = path.read_text(encoding="utf-8")
    assert "class RipgrepExtra(Module):" in text
    assert 'name = "ripgrep-extra"' in text


def test_write_lock_is_sorted_and_deterministic(tmp_path: Path) -> None:
    (tmp_path / "profiles.toml").write_text(
        '[profiles]\nbase = ["docker"]\ncli = ["ripgrep"]\nshell = ["starship"]\n'
        'gnome = ["gnome-settings"]\ngnome-theme = ["gnome-theme-bundle"]\n'
        'gnome-aesthetics = ["gnome-aesthetics-bundle"]\n'
        'multimedia = ["openh264"]\neditors = ["fresh"]\n'
        'python = ["uv"]\nweb = ["web-runtimes"]\ndotnet = ["dotnet-sdk"]\n'
        'data = ["data-services"]\ndevops = ["devops-tools"]\n'
        'react-native = ["expo"]\napps = ["obsidian"]\ndev-hygiene = ["aspire-gc"]\n'
        'system = ["gpu-detect"]\n'
        'hardware-nvidia = ["nvidia-akmod"]\n'
        'optional-editors = ["neovim"]\n'
        'security-cli = ["pass"]\n'
        'laravel = ["ddev"]\n',
        encoding="utf-8",
    )
    lock = lc.write_lock(tmp_path)
    lines = lock.read_text(encoding="utf-8").splitlines()
    assert lines == sorted(lines)
    assert "ddev" in lines and "ripgrep" in lines


def test_export_snapshot_writes_files(tmp_path: Path) -> None:
    ctx = _ctx(present={"dnf"}, scripts={"dnf": Result(0, stdout="git\ncurl\n")})
    out = lc.export_snapshot(ctx, tmp_path / "exports")
    assert (out / "dnf.txt").read_text(encoding="utf-8") == "git\ncurl\n"
    assert "flatpak unavailable" in (out / "flatpak.txt").read_text(encoding="utf-8")


def test_dev_gc_removes_orphans() -> None:
    ctx = _ctx(scripts={"docker": Result(0, stdout="abc123\ndef456\n")})
    count = dh.gc(ctx)
    assert count == 2
    assert ["docker", "rm", "-f", "abc123"] in ctx.ex.calls  # type: ignore[attr-defined]
