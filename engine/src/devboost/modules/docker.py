"""Docker — dependency of ddev. Official docker-ce on Linux (Fedora via Docker's Fedora repo,
Debian/Ubuntu via Docker's apt repo, Arch from [extra]). On macOS the engine runs in a
switchable runtime — Colima by default, OrbStack or Docker Desktop on request (spec §4,
``_docker_runtime``)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from devboost.core import log
from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.exec.primitives import config, pkg, systemd
from devboost.model import AptRepo, Ctx, Module
from devboost.modules import _docker_colima, _docker_desktop
from devboost.modules._docker_runtime import (
    DockerRuntime,
    current_context,
    license_note,
    selected_runtime,
    use_context,
)
from devboost.modules.macos import Homebrew, Rosetta

#: Docker's official engine package set on Debian/Ubuntu. `docker.io` (Ubuntu's own
#: package) is deliberately NOT used — Docker's docs list it as a *conflicting*
#: package, so installing it on a box with the docker-ce repo fails.
_CE_PKGS = (
    "docker-ce", "docker-ce-cli", "containerd.io",
    "docker-buildx-plugin", "docker-compose-plugin",
)


def _docker_apt_source(ctx: Ctx) -> pkg.Source:
    """Docker's official apt repo for the running Ubuntu release (suite = codename)."""
    return OsMap(
        debian=AptRepo(
            list_line=(
                "deb [arch=amd64,arm64"
                " signed-by=/etc/apt/keyrings/download-docker-com.gpg]"
                f" https://download.docker.com/linux/ubuntu {ctx.os.codename} stable"
            ),
            key_url="https://download.docker.com/linux/ubuntu/gpg",
        )
    )


def _invoking_user() -> str:
    """Return the real (non-root) user; prefers SUDO_USER over USER."""
    return os.environ.get("SUDO_USER") or os.environ.get("USER") or ""


# Docker CE on Fedora, per Docker's official docs (docs.docker.com/engine/install/fedora).
# Fedora Workstation ships podman + toolbox, not docker; but a `podman-docker` shim, if the
# user added one, CONFLICTS with docker-ce, so remove it first (harmless when absent). Real
# Docker is a deliberate choice, consistent with the Ubuntu VPS. `config-manager
# addrepo` is dnf5 (Fedora 41+); the `--add-repo` fallback covers older dnf4.
_DOCKER_CE_FEDORA = (
    "set -e\n"
    "dnf -y install dnf-plugins-core\n"
    "dnf config-manager addrepo --from-repofile"
    " https://download.docker.com/linux/fedora/docker-ce.repo 2>/dev/null"
    " || dnf config-manager --add-repo"
    " https://download.docker.com/linux/fedora/docker-ce.repo\n"
    "dnf -y remove podman-docker || true\n"  # the optional shim that conflicts with docker-ce
    "dnf -y install docker-ce docker-ce-cli containerd.io"
    " docker-buildx-plugin docker-compose-plugin\n"
)


@dataclass(frozen=True)
class _MacDocker:
    """macOS: bring up the selected runtime — Colima unless configured otherwise (§4).

    A runtime step that needs the user (Colima's home split, a root-owned docker config,
    OrbStack's first launch) raises ``NeedsUser``; it propagates, so the run reports
    ``blocked`` and nothing after that step runs.
    """

    uses_brew: ClassVar[bool] = True  # every runtime installs through brew (M4-D9)

    def verify(self, ctx: Ctx) -> bool:
        return selected_runtime().verify(ctx)

    def install(self, ctx: Ctx) -> None:
        rt = selected_runtime()
        note = license_note(rt.name)
        if note:
            log.warn(f"docker: {rt.name} — {note}")
        rt.install(ctx)
        rt.configure(ctx)
        rt.start(ctx)
        _point_cli_at(ctx, rt)


#: The contexts devboost's runtimes create — switching between these is ours to do.
_RUNTIME_CONTEXTS = frozenset({"colima", "orbstack", "desktop-linux", "default"})


def _point_cli_at(ctx: Ctx, rt: DockerRuntime) -> None:
    """Make ``rt``'s context the docker CLI's current one — unless it already is, or the
    user pinned another one with ``DOCKER_CONTEXT`` (which beats config.json anyway)."""
    pinned = os.environ.get("DOCKER_CONTEXT")
    if pinned:
        if pinned != rt.context_name:
            log.warn(
                f"docker: DOCKER_CONTEXT={pinned} is set, so the CLI will not use "
                f"{rt.name} ({rt.context_name}); unset it or run "
                f"`export DOCKER_CONTEXT={rt.context_name}`"
            )
        return
    previous = current_context(ctx)
    if previous == rt.context_name:
        return
    if previous and previous not in _RUNTIME_CONTEXTS:
        log.warn(
            f"docker: switching the CLI from your context '{previous}' to "
            f"'{rt.context_name}' ({rt.name}); `docker context use {previous}` switches back"
        )
    use_context(ctx, rt.context_name)


@register
class Docker(Module):
    name = "docker"
    category = "base"
    description = "Container engine (daemon enabled; invoking user added to docker group)."
    profiles = ("base",)
    requires = (Homebrew,)  # families=("macos",): dropped from Linux plans (spec §1)
    after = (Rosetta,)  # --vz-rosetta needs Rosetta when both are in the plan (§0)
    per_os = OsMap(macos=_MacDocker())
    # Colima's socket LaunchDaemon (D13) is written with sudo; see sudo_needed (M4-D5).
    needs_sudo_on_macos: ClassVar[bool] = True

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        # docker-ce daemon on BOTH Fedora and Debian. On Fedora, a podman-docker shim provides
        # a `docker` command but no daemon — is-enabled(docker.service) is what proves a real
        # engine, so a shim-only box correctly verifies False and gets docker-ce installed.
        if not ctx.ex.which("docker"):
            return False
        if not systemd.is_enabled(ctx, "docker.service"):
            return False
        user = _invoking_user()
        if user:
            res = ctx.ex.run(["id", "-nG", user])
            if not res.ok or "docker" not in res.stdout.split():
                return False
        return True

    def sudo_needed(self, ctx: Ctx) -> bool:
        if ctx.os.family != "macos":
            return super().sudo_needed(ctx)
        # Read-only, and never under-reports (M4-D5a): a missed prompt becomes a failing
        # `sudo -n`, or brew's own sudo hanging on a hidden tty. --force may upgrade or
        # re-run anything, so it always counts.
        if ctx.force:
            return True
        name = selected_runtime().name
        if name == "colima":  # (re)writing the socket LaunchDaemon (D13)
            return not _docker_colima.socket_daemon_current(ctx)
        if name == "docker-desktop":  # the cask links CLIs into /usr/local (root-owned)
            return _docker_desktop.links_need_root(ctx)
        # OrbStack's cask links into the brew prefix and its postflight
        # (`orbctl _internal brew-postflight`) runs without sudo (brew info, 2.2.3).
        return False

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
        # docker-ce on both OSes (one engine, consistent with the VPS). `which("dockerd")`
        # distinguishes a real engine already installed from a podman-docker shim, so the
        # repo setup + install runs only when there's no daemon yet.
        if not ctx.ex.which("dockerd"):
            if ctx.os.family == "debian":
                pkg.install(ctx, *_CE_PKGS, source=_docker_apt_source(ctx))
            elif ctx.os.family == "arch":
                # Arch packages the upstream engine directly in [extra] — no vendor repo,
                # no podman-docker shim to displace. Omarchy preinstalls these, so on a
                # provisioned box this is a no-op and only the service/group steps run.
                pkg.install(ctx, "docker", "docker-buildx", "docker-compose")
            else:
                # Fedora: docker-ce from Docker's official repo (removes the conflicting shim).
                ctx.ex.run(["sh", "-c", _DOCKER_CE_FEDORA], sudo=True)
        systemd.enable_system_unit(ctx, "docker.service", now=True)
        user = _invoking_user()
        if user:
            ctx.ex.run(["usermod", "-aG", "docker", user], sudo=True)


def _daemon_json() -> str:
    """Path to Docker's daemon config file (overridable for tests)."""
    return os.environ.get("DEVBOOST_DOCKER_DAEMON_JSON", "/etc/docker/daemon.json")


#: Cap the BuildKit build cache so it can't grow without bound — the #1 Docker disk hog on a
#: dev box (build cache reached tens of GB in the field). Merged into daemon.json so it composes
#: with other keys — notably the ``runtimes`` block ``nvidia-ctk runtime configure`` adds on
#: NVIDIA hosts — rather than clobbering them.
BUILDER_GC: dict[str, object] = {
    "builder": {"gc": {"enabled": True, "defaultKeepStorage": "20GB"}},
}
#: What "the cap is on" means, on both OSes: only builder.gc.enabled — a user's own
#: defaultKeepStorage, gc policy or other builder keys are theirs to keep.
_GC_ENABLED: dict[str, object] = {"builder": {"gc": {"enabled": True}}}


@dataclass(frozen=True)
class _MacBuildGc:
    """macOS: the same cache cap, in the selected runtime's daemon config (plan D2)."""

    uses_brew: ClassVar[bool] = True  # M4-D9 (Homebrew arrives through Docker)

    def verify(self, ctx: Ctx) -> bool:
        return selected_runtime().daemon_config_has(_GC_ENABLED)

    def install(self, ctx: Ctx) -> None:
        rt = selected_runtime()
        if rt.daemon_config_has(_GC_ENABLED):
            return  # already capped — even under --force, never override the user's cap
        # Deep merge (every runtime): other builder keys survive; restart only on change.
        if rt.merge_daemon_config(ctx, BUILDER_GC):
            rt.restart_engine(ctx)


@register
class DockerBuildCacheGc(Module):
    name = "docker-build-gc"
    category = "base"
    description = "Cap Docker's build cache (daemon.json builder.gc) so it can't fill the disk."
    requires = (Docker,)
    profiles = ("base",)
    per_os = OsMap(macos=_MacBuildGc())

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        p = Path(_daemon_json())
        if not p.exists():
            return False
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        builder = data.get("builder") if isinstance(data, dict) else None
        gc = builder.get("gc") if isinstance(builder, dict) else None
        return bool(isinstance(gc, dict) and gc.get("enabled"))

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
        # Deep merge preserves any existing daemon.json keys (e.g. the NVIDIA runtime)
        # AND any other keys the user has under "builder" itself (a shallow merge would
        # replace the whole "builder" object with just ours). Restart only when the file
        # actually changed, so re-runs — including under --force — are no-ops.
        if config.json_merge_deep(ctx, _daemon_json(), BUILDER_GC):
            ctx.ex.run(["systemctl", "restart", "docker.service"], sudo=True)
