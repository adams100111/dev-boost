from __future__ import annotations

import pytest

from devboost.core.errors import InstallError, UnsupportedOS
from devboost.core.osinfo import OsInfo, OsMap
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import pkg
from devboost.model import AptRepo, Ctx, DnfRepo

FEDORA = OsInfo("fedora", "fedora", "x86_64")
UBUNTU = OsInfo("ubuntu", "debian", "x86_64")
ARCH = OsInfo("arch", "arch", "x86_64")
OMARCHY = OsInfo("omarchy", "arch", "x86_64", id_like=("arch",))
UNKNOWN = OsInfo("plan9", "plan9", "x86_64")


# ---------------------------------------------------------------------------
# Fedora / Dnf paths
# ---------------------------------------------------------------------------


def test_install_uses_dnf_on_fedora() -> None:
    ex = FakeExecutor()
    pkg.install(Ctx(os=FEDORA, ex=ex), "git", "curl")
    assert ["sudo", "dnf", "install", "-y", "git", "curl"] in ex.calls


def test_install_with_source_adds_repo_then_installs_refresh() -> None:
    ex = FakeExecutor()
    src: pkg.Source = OsMap[DnfRepo | AptRepo](
        fedora=DnfRepo("ddev", "https://pkg.ddev.com/yum/", gpgcheck=False)
    )
    pkg.install(Ctx(os=FEDORA, ex=ex), "ddev", source=src, refresh=True)
    assert ["sudo", "tee", "/etc/yum.repos.d/ddev.repo"] in ex.calls
    assert ["sudo", "dnf", "install", "--refresh", "-y", "ddev"] in ex.calls


def test_install_resolves_per_os_name() -> None:
    ex = FakeExecutor()
    name: OsMap[str] = OsMap(fedora="fd-find", default="fd")
    pkg.install(Ctx(os=FEDORA, ex=ex), name)
    assert ["sudo", "dnf", "install", "-y", "fd-find"] in ex.calls


def test_dnf_install_failure_raises_install_error() -> None:
    ex = FakeExecutor(scripts={"dnf": Result(1, stderr="no such package")})
    with pytest.raises(InstallError) as exc_info:
        pkg.install(Ctx(os=FEDORA, ex=ex), "nonexistent-pkg")
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# refresh_index — one-time package-index refresh before the install loop
# ---------------------------------------------------------------------------


def test_refresh_index_runs_apt_update_on_debian() -> None:
    ex = FakeExecutor()
    pkg.refresh_index(Ctx(os=UBUNTU, ex=ex))
    assert ["sudo", "apt-get", "update"] in ex.calls


def test_refresh_index_noop_on_fedora() -> None:
    ex = FakeExecutor()
    pkg.refresh_index(Ctx(os=FEDORA, ex=ex))
    assert ex.calls == []


def test_refresh_index_best_effort_never_raises() -> None:
    """A failing apt-get update must not abort the run — installs still attempt."""
    ex = FakeExecutor(scripts={"apt-get": Result(1, stderr="mirror down")})
    pkg.refresh_index(Ctx(os=UBUNTU, ex=ex))  # must not raise
    assert ["sudo", "apt-get", "update"] in ex.calls


def test_refresh_index_writes_apt_lock_timeout_dropin_on_debian() -> None:
    """apt should WAIT for a held lock (cloud-init/unattended-upgrades) instead of failing
    with exit 100 — a DPkg::Lock::Timeout drop-in applies to every apt call."""
    ex = FakeExecutor()
    pkg.refresh_index(Ctx(os=UBUNTU, ex=ex))
    flat = [" ".join(c) for c in ex.calls]
    assert any("/etc/apt/apt.conf.d/" in s and "lock-timeout" in s for s in flat)
    assert ["sudo", "apt-get", "update"] in ex.calls  # update still runs
    assert pkg._APT_LOCK_TIMEOUT >= 60  # waits a meaningful duration


def test_dnf_add_repo_failure_raises_install_error() -> None:
    ex = FakeExecutor(scripts={"tee": Result(1, stderr="permission denied")})
    repo = DnfRepo("test-repo", "https://example.com/repo/", gpgcheck=False)
    with pytest.raises(InstallError) as exc_info:
        pkg.manager_for(FEDORA).add_repo(Ctx(os=FEDORA, ex=ex), repo)
    assert exc_info.value.code == 1


def test_install_refresh_failure_raises_install_error() -> None:
    ex = FakeExecutor(scripts={"dnf": Result(1, stderr="GPG check failed")})
    src: pkg.Source = OsMap[DnfRepo | AptRepo](
        fedora=DnfRepo("myrepo", "https://example.com/", gpgcheck=False)
    )
    with pytest.raises(InstallError):
        pkg.install(Ctx(os=FEDORA, ex=ex), "mypkg", source=src, refresh=True)


# ---------------------------------------------------------------------------
# Ubuntu / Apt paths
# ---------------------------------------------------------------------------


def test_manager_for_debian_family_returns_apt() -> None:
    mgr = pkg.manager_for(UBUNTU)
    assert isinstance(mgr, pkg.Apt)


def test_install_uses_apt_get_on_ubuntu() -> None:
    ex = FakeExecutor()
    pkg.install(Ctx(os=UBUNTU, ex=ex), "git", "curl")
    assert ["sudo", "apt-get", "install", "-y", "git", "curl"] in ex.calls


def test_apt_installed_uses_dpkg() -> None:
    ex = FakeExecutor(scripts={"dpkg": Result(0)})
    assert pkg.installed(Ctx(os=UBUNTU, ex=ex), "git") is True
    assert ["dpkg", "-s", "git"] in ex.calls


def test_apt_install_failure_raises_install_error() -> None:
    ex = FakeExecutor(scripts={"apt-get": Result(1, stderr="unable to fetch")})
    with pytest.raises(InstallError) as exc_info:
        pkg.install(Ctx(os=UBUNTU, ex=ex), "nonexistent-pkg")
    assert exc_info.value.code == 1


def test_apt_add_repo_writes_list_and_updates() -> None:
    ex = FakeExecutor()
    repo = AptRepo(
        list_line="deb https://download.example.com/linux/ubuntu focal stable",
        key_url="https://download.example.com/linux/ubuntu/gpg",
    )
    pkg.manager_for(UBUNTU).add_repo(Ctx(os=UBUNTU, ex=ex), repo)
    flat = [" ".join(c) for c in ex.calls]
    assert any("keyrings/download-example-com" in s for s in flat)
    assert any("sources.list.d/download-example-com" in s for s in flat)
    assert any("apt-get update" in s for s in flat)


def test_apt_add_repo_dearmors_key_to_binary_keyring() -> None:
    """Vendor keys (armored .asc from ddev/Microsoft/Docker) must be dearmored into the
    binary .gpg keyring named in signed-by — writing armored text to .gpg trips NO_PUBKEY."""
    ex = FakeExecutor()
    repo = AptRepo(
        list_line="deb https://pkg.ddev.example/apt/ * *",
        key_url="https://pkg.ddev.example/apt/gpg.key",
    )
    pkg.manager_for(UBUNTU).add_repo(Ctx(os=UBUNTU, ex=ex), repo)
    flat = [" ".join(c) for c in ex.calls]
    assert any(
        "gpg --dearmor" in s and "keyrings/pkg-ddev-example.gpg" in s for s in flat
    )
    assert any("pkg.ddev.example/apt/gpg.key" in s for s in flat)


def test_apt_add_repo_no_key_skips_keyring() -> None:
    ex = FakeExecutor()
    repo = AptRepo(
        list_line="deb https://ppa.example.com/ubuntu focal main",
        key_url="",
    )
    pkg.manager_for(UBUNTU).add_repo(Ctx(os=UBUNTU, ex=ex), repo)
    assert not any("keyrings" in " ".join(c) for c in ex.calls)
    assert any("sources.list.d" in " ".join(c) for c in ex.calls)


def test_apt_add_repo_failure_raises_install_error() -> None:
    ex = FakeExecutor(scripts={"tee": Result(1, stderr="permission denied")})
    repo = AptRepo(
        list_line="deb https://pkg.example.com/ubuntu focal stable",
        key_url="",
    )
    with pytest.raises(InstallError) as exc_info:
        pkg.manager_for(UBUNTU).add_repo(Ctx(os=UBUNTU, ex=ex), repo)
    assert exc_info.value.code == 1


def test_install_per_os_name_resolves_on_ubuntu() -> None:
    ex = FakeExecutor()
    name: OsMap[str] = OsMap(fedora="fd-find", debian="fd", default="fd")
    pkg.install(Ctx(os=UBUNTU, ex=ex), name)
    assert ["sudo", "apt-get", "install", "-y", "fd"] in ex.calls


# ---------------------------------------------------------------------------
# Unsupported OS
# ---------------------------------------------------------------------------


def test_unsupported_os_raises() -> None:
    ex = FakeExecutor()
    with pytest.raises(UnsupportedOS):
        pkg.install(Ctx(os=UNKNOWN, ex=ex), "git")


# ---------------------------------------------------------------------------
# Arch / Omarchy / Pacman paths
# ---------------------------------------------------------------------------


def test_install_uses_pacman_on_arch() -> None:
    ex = FakeExecutor()
    pkg.install(Ctx(os=ARCH, ex=ex), "git", "curl")
    assert ["sudo", "pacman", "-S", "--needed", "--noconfirm", "git", "curl"] in ex.calls


def test_install_prefers_omarchy_helper_when_present() -> None:
    """On Omarchy, delegate to the platform's own idempotent, root-aware helper."""
    ex = FakeExecutor(present={"omarchy-pkg-add"})
    pkg.install(Ctx(os=OMARCHY, ex=ex), "git")
    assert ["omarchy-pkg-add", "git"] in ex.calls
    # Never wrapped in sudo — the helper elevates itself; nesting would double-prompt.
    assert not any(c[:2] == ["sudo", "omarchy-pkg-add"] for c in ex.calls)
    assert not any("pacman" in c for c in ex.calls)


def test_pacman_install_failure_raises_install_error() -> None:
    ex = FakeExecutor(scripts={"pacman": Result(1, stderr="target not found")})
    with pytest.raises(InstallError) as exc_info:
        pkg.install(Ctx(os=ARCH, ex=ex), "nonexistent-pkg")
    assert exc_info.value.code == 1


def test_installed_uses_pacman_query() -> None:
    ex = FakeExecutor()
    assert pkg.installed(Ctx(os=ARCH, ex=ex), "git") is True
    assert ["pacman", "-Q", "git"] in ex.calls


def test_arch_resolves_per_os_package_name() -> None:
    ex = FakeExecutor()
    name: OsMap[str] = OsMap(fedora="fd-find", arch="fd", default="fd-find")
    pkg.install(Ctx(os=OMARCHY, ex=ex), name)
    assert ["sudo", "pacman", "-S", "--needed", "--noconfirm", "fd"] in ex.calls


def test_add_repo_on_arch_raises_rather_than_no_op() -> None:
    """A per-OS Source that does not apply to Arch must fail loudly, not silently pass."""
    ex = FakeExecutor()
    src: pkg.Source = OsMap[DnfRepo | AptRepo](
        fedora=DnfRepo("ddev", "https://pkg.ddev.com/yum/", gpgcheck=False),
        default=DnfRepo("ddev", "https://pkg.ddev.com/yum/", gpgcheck=False),
    )
    with pytest.raises(UnsupportedOS):
        pkg.install(Ctx(os=ARCH, ex=ex), "ddev", source=src)


# --- AUR --------------------------------------------------------------------


def test_install_aur_prefers_omarchy_helper() -> None:
    ex = FakeExecutor(present={"omarchy-pkg-aur-add", "yay"})
    pkg.install_aur(Ctx(os=OMARCHY, ex=ex), "ddev-bin")
    assert ["omarchy-pkg-aur-add", "ddev-bin"] in ex.calls


def test_install_aur_falls_back_to_yay_never_as_root() -> None:
    ex = FakeExecutor(present={"yay"})
    pkg.install_aur(Ctx(os=ARCH, ex=ex), "ddev-bin")
    assert ["yay", "-S", "--needed", "--noconfirm", "ddev-bin"] in ex.calls
    # yay refuses to run as root; a sudo-wrapped call would abort the install.
    assert not any(c and c[0] == "sudo" for c in ex.calls)


def test_install_aur_without_a_helper_raises() -> None:
    ex = FakeExecutor()
    with pytest.raises(UnsupportedOS):
        pkg.install_aur(Ctx(os=ARCH, ex=ex), "ddev-bin")


def test_install_aur_off_arch_raises() -> None:
    ex = FakeExecutor()
    with pytest.raises(UnsupportedOS):
        pkg.install_aur(Ctx(os=FEDORA, ex=ex), "ddev-bin")


def test_refresh_index_never_partial_syncs_on_arch() -> None:
    """`pacman -Sy` without -u is a partial upgrade — the classic way to break Arch."""
    ex = FakeExecutor()
    pkg.refresh_index(Ctx(os=OMARCHY, ex=ex))
    assert ex.calls == []
