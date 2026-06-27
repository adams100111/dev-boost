from __future__ import annotations

import json
from pathlib import Path

import pytest

from devboost.core.errors import SecretsError
from devboost.core.osinfo import OsInfo
from devboost.core.registry import load, validate_profiles
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.base import BuildTools, ChezmoiRepo, DnfTune, Flatpak, Rpmfusion
from devboost.modules.cli_tools import Fd, Lazydocker, Lazygit
from devboost.modules.mise import Mise

FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_fd_uses_fedora_package_name() -> None:
    ctx = _ctx()
    Fd().install(ctx)
    assert ["sudo", "dnf", "install", "-y", "fd-find"] in ctx.ex.calls  # type: ignore[attr-defined]


def test_lazygit_enables_copr_then_installs() -> None:
    ctx = _ctx()
    Lazygit().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "dnf", "copr", "enable", "-y", "atim/lazygit"] in calls
    assert ["sudo", "dnf", "install", "-y", "lazygit"] in calls


def test_rpmfusion_installs_release_rpms() -> None:
    ctx = _ctx(scripts={"rpm": Result(0, stdout="41\n")})
    Rpmfusion().install(ctx)
    flat = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert any("rpmfusion-free-release-41.noarch.rpm" in c for c in flat)
    assert any("rpmfusion-nonfree-release-41.noarch.rpm" in c for c in flat)


def test_dnf_tune_writes_and_verifies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    conf = tmp_path / "dnf.conf"
    monkeypatch.setenv("DEVBOOST_DNF_CONF", str(conf))
    ctx = _ctx()
    assert DnfTune().verify(ctx) is False
    DnfTune().install(ctx)
    assert DnfTune().verify(ctx) is True


def test_flatpak_module_adds_remote() -> None:
    ctx = _ctx(scripts={"flatpak": Result(0, stdout="")}, present={"flatpak"})
    Flatpak().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["flatpak", "remote-add", "--if-not-exists", "flathub",
            "https://flathub.org/repo/flathub.flatpakrepo"] in calls


def test_build_tools_installs_toolchain() -> None:
    ctx = _ctx()
    BuildTools().install(ctx)
    flat = " ".join(ctx.ex.calls[0])  # type: ignore[attr-defined]
    assert "gcc" in flat and "cmake" in flat and "make" in flat


def test_mise_migrates_nvm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".nvm" / "alias").mkdir(parents=True)
    (tmp_path / ".nvm" / "alias" / "default").write_text("v22.1.0\n", encoding="utf-8")
    (tmp_path / ".bashrc").write_text(
        "# BEGIN NVM\nexport NVM_DIR=$HOME/.nvm\n# END NVM\n", encoding="utf-8"
    )
    ctx = _ctx(present={"mise"})
    Mise().install(ctx)
    assert ["mise", "use", "-g", "node@22.1.0"] in ctx.ex.calls  # type: ignore[attr-defined]
    bashrc = (tmp_path / ".bashrc").read_text(encoding="utf-8")
    assert "# export NVM_DIR=$HOME/.nvm" in bashrc
    assert "migrated nvm init to mise" in bashrc


def test_lazydocker_uses_correct_copr_repo() -> None:
    ctx = _ctx()
    Lazydocker().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "dnf", "copr", "enable", "-y", "atim/lazydocker"] in calls
    assert ["sudo", "dnf", "install", "-y", "lazydocker"] in calls


def test_chezmoi_repo_raises_when_no_repo_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEVBOOST_DOTFILES_REPO", raising=False)
    # No secrets bundle — age decrypt will fail / bundle absent → SecretsError raised
    monkeypatch.setenv("DEVBOOST_BOOTSTRAP_DIR", str(tmp_path))
    # tmp_path has no secrets.age → age.decrypt raises SecretsError
    ctx = _ctx()
    with pytest.raises(SecretsError, match="DEVBOOST_DOTFILES_REPO"):
        ChezmoiRepo().install(ctx)


def test_chezmoi_repo_reads_url_from_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEVBOOST_DOTFILES_REPO", "https://github.com/user/dotfiles")
    ctx = _ctx()
    ChezmoiRepo().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["chezmoi", "init", "--apply", "https://github.com/user/dotfiles"] in calls


def test_chezmoi_repo_reads_url_from_secrets_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEVBOOST_DOTFILES_REPO", raising=False)
    bundle = tmp_path / "secrets.age"
    bundle.write_text("cipher", encoding="utf-8")
    monkeypatch.setenv("DEVBOOST_SECRETS", str(bundle))
    monkeypatch.setenv("DEVBOOST_SECRETS_KEY", str(tmp_path / "key"))
    secrets_json = json.dumps({
        "GIT_USER": "u", "GIT_EMAIL": "u@x", "GITHUB_PAT": "ghp_x",
        "DOTFILES_REPO": "https://github.com/user/dotfiles",
    })
    ctx = _ctx(scripts={"age": Result(0, stdout=secrets_json)})
    ChezmoiRepo().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["chezmoi", "init", "--apply", "https://github.com/user/dotfiles"] in calls


def test_registry_loads_base_and_cli_and_profiles_validate() -> None:
    modules = load()
    expected = {"rpmfusion", "dnf-tune", "flatpak", "build-tools", "chezmoi", "chezmoi-repo",
                "mise", "eza", "lazygit", "fd", "gh", "tpm", "claude-code"}
    assert expected <= set(modules)
    # every module's declared profiles exist in the real profiles.toml
    import tomllib

    from devboost.core.settings import settings

    data = tomllib.loads(settings.profiles_path.read_text(encoding="utf-8"))
    validate_profiles(modules, set(data["profiles"]))
