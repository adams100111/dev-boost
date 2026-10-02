"""superfile on every OS: Homebrew, pacman on Arch, upstream's pinned installer elsewhere."""

from __future__ import annotations

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules.cli_tools import SUPERFILE_VERSION, Superfile

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
UBUNTU = OsInfo("ubuntu", "debian", "x86_64", version_id="24.04")
ARCH = OsInfo("arch", "arch", "x86_64")
OMARCHY = OsInfo("omarchy", "arch", "aarch64", id_like=("arch",))


def test_superfile_uses_the_packaged_build_where_one_exists() -> None:
    # Homebrew core has it on macOS; Arch ships it in `extra`. Let the package manager
    # own the binary there rather than dropping an unmanaged one next to it.
    for os_info, call in (
        (MAC, ["brew", "install", "--formula", "-y", "superfile"]),
        (ARCH, ["sudo", "pacman", "-S", "--needed", "--noconfirm", "superfile"]),
    ):
        ex = FakeExecutor()
        Superfile().install(Ctx(os=os_info, ex=ex))
        assert ex.calls[-1] == call, os_info.distro


def test_superfile_on_omarchy_uses_the_omarchy_pkg_helper() -> None:
    ex = FakeExecutor(present={"omarchy-pkg-add"})
    Superfile().install(Ctx(os=OMARCHY, ex=ex))
    assert ex.calls[-1] == ["omarchy-pkg-add", "superfile"]


def test_superfile_on_fedora_and_debian_runs_upstreams_installer_as_root() -> None:
    # Neither distro packages it (Fedora has only personal COPRs), so both take the one
    # installer upstream documents. Running it as root matters: its `sudo mv ./spf
    # /usr/local/bin/` then succeeds, so the fallback branch that appends `export
    # PATH=...` to ~/.bashrc / ~/.zshrc — files chezmoi owns here — never executes.
    for os_info in (FEDORA, UBUNTU):
        ex = FakeExecutor()
        Superfile().install(Ctx(os=os_info, ex=ex))
        assert ex.calls[-1][:3] == ["sudo", "sh", "-c"], os_info.distro
        script = ex.calls[-1][-1]
        assert "https://superfile.dev/install.sh" in script
        # Pinned: reproducible, and it skips the script's unauthenticated
        # api.github.com "latest" lookup, which hard-exits when rate-limited.
        assert f"SPF_INSTALL_VERSION={SUPERFILE_VERSION} " in script
        # -f so an HTTP error page is never piped into bash.
        assert "curl -fsSLo-" in script


def test_superfile_verifies_the_spf_binary_not_its_package_name() -> None:
    # Upstream renamed the binary: the package is `superfile`, the command is `spf`.
    ctx = Ctx(os=FEDORA, ex=FakeExecutor(present={"spf"}))
    assert Superfile().verify(ctx) is True
    assert Superfile().verify(Ctx(os=FEDORA, ex=FakeExecutor(present={"superfile"}))) is False


def test_superfile_is_opt_in_and_re_runnable() -> None:
    # In no profile: a TUI file manager is a preference, not toolchain (the reasoning
    # `base` spells out for voxtype), and `cli` already ships eza/fd/fzf/zoxide/bat.
    # Install it by name: `devboost install superfile`.
    assert Superfile.profiles == ()
    assert Superfile.self_updating is True
