"""env.sh: the user's local.sh wins; DOTNET_ROOT for the user .NET SDK on macOS."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ENV_SH = Path(__file__).resolve().parents[3] / "dotfiles" / "dot_config" / "devboost" / "env.sh"
SHELLS = [s for s in ("sh", "bash", "zsh") if shutil.which(s)]


def _env(shell: str, home: Path, uname: str, keys: list[str]) -> dict[str, str]:
    fake = home / "bin"
    fake.mkdir(exist_ok=True)
    exe = fake / "uname"
    exe.write_text(f"#!/bin/sh\necho {uname}\n", encoding="utf-8")
    exe.chmod(0o755)
    fields = " ".join(f'"${{{k}-<unset>}}"' for k in keys)
    out = subprocess.run(
        [shell, "-c", f'. "{ENV_SH}"; printf "%s\\n" {fields}'],
        env={"PATH": f"{fake}:/usr/bin:/bin", "HOME": str(home)},
        capture_output=True, text=True, check=True,
    )
    return dict(zip(keys, out.stdout.splitlines(), strict=True))


@pytest.mark.parametrize("shell", SHELLS)
def test_local_sh_overrides_editor_and_visual(shell: str, tmp_path: Path) -> None:
    local = tmp_path / ".config" / "devboost" / "local.sh"
    local.parent.mkdir(parents=True)
    local.write_text('export EDITOR=nvim\nexport VISUAL="code --wait"\n', encoding="utf-8")
    env = _env(shell, tmp_path, "Darwin", ["EDITOR", "VISUAL"])
    assert env == {"EDITOR": "nvim", "VISUAL": "code --wait"}


@pytest.mark.parametrize("shell", SHELLS)
def test_without_local_sh_the_defaults_stand(shell: str, tmp_path: Path) -> None:
    assert _env(shell, tmp_path, "Linux", ["EDITOR"]) == {"EDITOR": "fresh"}


@pytest.mark.parametrize("shell", SHELLS)
def test_darwin_exports_dotnet_root_for_the_user_sdk(shell: str, tmp_path: Path) -> None:
    assert _env(shell, tmp_path, "Darwin", ["DOTNET_ROOT"]) == {"DOTNET_ROOT": "<unset>"}
    sdk = tmp_path / ".dotnet"
    sdk.mkdir()
    (sdk / "dotnet").write_text("#!/bin/sh\n", encoding="utf-8")
    (sdk / "dotnet").chmod(0o755)
    env = _env(shell, tmp_path, "Darwin", ["DOTNET_ROOT", "PATH"])
    assert env["DOTNET_ROOT"] == str(sdk)
    assert str(sdk) in env["PATH"].split(":")
    assert _env(shell, tmp_path, "Linux", ["DOTNET_ROOT"]) == {"DOTNET_ROOT": "<unset>"}


def test_env_sh_is_still_posix() -> None:
    assert subprocess.run(["sh", "-n", str(ENV_SH)], check=False).returncode == 0
