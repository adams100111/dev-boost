from __future__ import annotations

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.ddev import Ddev, DdevRemote
from devboost.modules.docker import Docker, _invoking_user

FEDORA = OsInfo("fedora", "fedora", "x86_64")
UBUNTU = OsInfo("ubuntu", "debian", "x86_64", version_id="24.04", codename="noble")
UBUNTU_HEADLESS = OsInfo("ubuntu", "debian", "x86_64", headless=True)


def test_ddev_debian_uses_canonical_apt_repo() -> None:
    """On Debian, set up ddev's OWN repo (ddev.sources + ddev.asc, per ddev docs) and remove
    the old conflicting file, then install via the Apt primitive — no Signed-By clash."""
    ctx = Ctx(os=UBUNTU, ex=FakeExecutor(present={"mkcert"}))  # type: ignore[arg-type]
    Ddev().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    repo = next(c for c in calls if c[:3] == ["sudo", "sh", "-c"])
    script = repo[3]
    assert "/etc/apt/sources.list.d/ddev.sources" in script
    assert "/etc/apt/keyrings/ddev.asc" in script
    assert "pkg-ddev-com.list" in script  # the conflicting third-party file is removed
    assert ["sudo", "apt-get", "install", "-y", "ddev"] in calls  # install via Apt primitive


def test_ddev_remote_binds_all_interfaces_on_a_server() -> None:
    ctx = Ctx(os=UBUNTU_HEADLESS, ex=FakeExecutor())
    DdevRemote().install(ctx)
    assert ["ddev", "config", "global", "--router-bind-all-interfaces"] in ctx.ex.calls


def test_ddev_remote_is_a_noop_on_a_gui_laptop() -> None:
    ctx = Ctx(os=FEDORA, ex=FakeExecutor())  # headless=False → keep ddev on localhost
    DdevRemote().install(ctx)
    assert ctx.ex.calls == []
    assert DdevRemote().verify(ctx) is True


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


# ── docker ──────────────────────────────────────────────────────────────────


def test_docker_uses_rootless_podman_on_fedora(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fedora is Podman-native (podman-docker conflicts with moby-engine AND docker-ce), so
    don't install a root Docker daemon — use rootless Podman + its docker-compat socket."""
    monkeypatch.setenv("SUDO_USER", "alice")
    ctx = _ctx()  # FEDORA
    Docker().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "dnf", "install", "-y", "podman", "podman-docker"] in calls
    assert ["systemctl", "--user", "enable", "--now", "podman.socket"] in calls
    # no moby-engine, no root docker.service, no docker group on the podman path
    assert not any("moby-engine" in " ".join(c) for c in calls)
    assert not any(c == ["sudo", "systemctl", "enable", "--now", "docker.service"] for c in calls)


def test_docker_install_uses_official_ce_repo_on_ubuntu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On Ubuntu, install Docker's official docker-ce set — never docker.io (which
    conflicts with docker-ce) nor the Fedora-only moby-engine."""
    monkeypatch.setenv("SUDO_USER", "alice")
    ctx = Ctx(os=UBUNTU, ex=FakeExecutor())  # type: ignore[arg-type]
    Docker().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert [
        "sudo", "apt-get", "install", "-y",
        "docker-ce", "docker-ce-cli", "containerd.io",
        "docker-buildx-plugin", "docker-compose-plugin",
    ] in calls
    assert not any("docker.io" in " ".join(c) for c in calls)
    assert not any("moby-engine" in " ".join(c) for c in calls)
    assert ["sudo", "systemctl", "enable", "--now", "docker.service"] in calls
    assert ["sudo", "usermod", "-aG", "docker", "alice"] in calls


def test_docker_apt_source_targets_official_ce_repo() -> None:
    from devboost.model import AptRepo
    from devboost.modules.docker import _docker_apt_source

    ctx = Ctx(os=UBUNTU, ex=FakeExecutor())  # type: ignore[arg-type]
    repo = _docker_apt_source(ctx).get(UBUNTU)
    assert isinstance(repo, AptRepo)
    assert "download.docker.com/linux/ubuntu noble stable" in repo.list_line
    assert repo.key_url == "https://download.docker.com/linux/ubuntu/gpg"


def test_docker_install_skips_repo_when_already_present_on_ubuntu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If Docker is already installed (e.g. set up out-of-band), don't re-add the repo
    — that avoids a conflicting Signed-By against an existing docker.asc entry. Still
    (re)enable the daemon and add the user to the docker group."""
    monkeypatch.setenv("SUDO_USER", "alice")
    ctx = Ctx(os=UBUNTU, ex=FakeExecutor(present={"docker"}))  # type: ignore[arg-type]
    Docker().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert not any("docker-ce" in " ".join(c) for c in calls)
    assert not any("apt-get" in " ".join(c) for c in calls)
    assert ["sudo", "systemctl", "enable", "--now", "docker.service"] in calls
    assert ["sudo", "usermod", "-aG", "docker", "alice"] in calls


def test_docker_install_skips_usermod_when_no_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SUDO_USER", raising=False)
    monkeypatch.delenv("USER", raising=False)
    ctx = _ctx()
    Docker().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert not any("usermod" in " ".join(c) for c in calls)


def _ubuntu_ctx(**kw: object) -> Ctx:
    return Ctx(os=UBUNTU, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_docker_verify_checks_daemon_enabled_and_group_on_ubuntu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUDO_USER", "alice")
    ctx = _ubuntu_ctx(
        present={"docker"},
        scripts={"systemctl": Result(0), "id": Result(0, stdout="alice docker wheel")},
    )
    assert Docker().verify(ctx) is True


def test_docker_verify_false_when_daemon_disabled_on_ubuntu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUDO_USER", "alice")
    ctx = _ubuntu_ctx(
        present={"docker"},
        scripts={"systemctl": Result(1), "id": Result(0, stdout="alice docker")},
    )
    assert Docker().verify(ctx) is False


def test_docker_verify_false_when_user_not_in_group_on_ubuntu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUDO_USER", "alice")
    ctx = _ubuntu_ctx(
        present={"docker"},
        scripts={"systemctl": Result(0), "id": Result(0, stdout="alice wheel")},
    )
    assert Docker().verify(ctx) is False


def test_docker_verify_podman_socket_on_fedora() -> None:
    """Fedora path: podman present + rootless podman.socket enabled."""
    assert Docker().verify(_ctx(present={"podman"}, scripts={"systemctl": Result(0)})) is True
    assert Docker().verify(_ctx(present={"podman"}, scripts={"systemctl": Result(1)})) is False
    assert Docker().verify(_ctx(scripts={"systemctl": Result(0)})) is False  # podman absent


def test_invoking_user_prefers_sudo_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUDO_USER", "bob")
    monkeypatch.setenv("USER", "root")
    assert _invoking_user() == "bob"


def test_invoking_user_falls_back_to_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUDO_USER", raising=False)
    monkeypatch.setenv("USER", "carol")
    assert _invoking_user() == "carol"


# ── ddev ────────────────────────────────────────────────────────────────────


def test_ddev_install_installs_mkcert_if_missing() -> None:
    ctx = _ctx()  # mkcert not in present → which("mkcert") is False
    Ddev().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["sudo", "dnf", "install", "-y", "mkcert"] in calls
    assert ["mkcert", "-install"] in calls


def test_ddev_install_skips_mkcert_pkg_when_already_present() -> None:
    ctx = _ctx(present={"mkcert"})
    Ddev().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert not any(c == ["sudo", "dnf", "install", "-y", "mkcert"] for c in calls)
    assert ["mkcert", "-install"] in calls
