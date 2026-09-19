"""Colima — the default Docker runtime on macOS (MIT; spec §4, plan D10–D13).

Colima runs dockerd in a Lima VM (Apple Virtualization.framework, virtiofs mounts). The
brew formulae give the docker CLI, compose and buildx; ``brew services`` keeps Colima
running across logins; a root LaunchDaemon re-creates ``/var/run/docker.sock`` at boot.

Colima 0.10.3 appends an ``Include`` line for its Lima SSH config to ``~/.ssh/config`` on
first start. That is Colima's own behaviour and is left alone here (M4-D16; documented in
docs/docker-runtimes.md).
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from devboost.core import log
from devboost.core.errors import ConfigError, InstallError, NeedsUser
from devboost.core.userconfig import DockerRuntimeName
from devboost.exec.primitives import config, launchd, pkg
from devboost.model import Ctx
from devboost.modules._docker_runtime import (
    contains,
    docker_config_path,
    engine_verified,
    read_json,
    rosetta_usable,
    vm_size,
    wait_for_engine,
)

FORMULAE: tuple[str, ...] = ("colima", "docker", "docker-compose", "docker-buildx")
#: Where the brew compose/buildx formulae put their CLI plugins.
CLI_PLUGINS_DIR = "/opt/homebrew/lib/docker/cli-plugins"
SOCKET_LABEL = launchd.label("docker-sock")
#: The well-known socket third-party tools (Testcontainers, IDEs) expect. Module attribute
#: so tests can redirect it.
DOCKER_SOCK = Path("/var/run/docker.sock")
DISK_GIB = 100


def colima_home() -> Path:
    """Colima's config dir, resolved the way Colima 0.10 resolves it (config/files.go)."""
    explicit = os.environ.get("COLIMA_HOME")
    if explicit and Path(explicit).exists():
        return Path(explicit)
    home = Path(os.environ["HOME"])
    dot = home / ".colima"
    if dot.exists():
        return dot
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    xdg_dir = (Path(xdg) if xdg else home / ".config") / "colima"
    if xdg or xdg_dir.exists():
        return xdg_dir
    return dot


def service_colima_home() -> Path:
    """The dir Colima resolves under ``brew services``: launchd starts it with neither
    XDG_CONFIG_HOME nor COLIMA_HOME, so only ``~/.colima`` and ``~/.config/colima`` count."""
    home = Path(os.environ["HOME"])
    dot = home / ".colima"
    if dot.exists():
        return dot
    default_xdg = home / ".config" / "colima"
    return default_xdg if default_xdg.exists() else dot


def ensure_colima_home() -> Path:
    """Pin one Colima home that this shell and ``brew services`` both resolve (plan D10).

    Shells export XDG_CONFIG_HOME (env.sh) but launchd does not, so a fresh Mac gets
    ``~/.config/colima``, which both sides then find. A custom XDG_CONFIG_HOME or a
    COLIMA_HOME would split them (two VMs), so there the home is ``~/.colima``, which Colima
    picks first everywhere. An existing split cannot be fixed without moving a VM: that is
    ``NeedsUser``.
    """
    home = Path(os.environ["HOME"])
    dot = home / ".colima"
    default_xdg = home / ".config" / "colima"
    explicit = os.environ.get("COLIMA_HOME", "")
    xdg = os.environ.get("XDG_CONFIG_HOME", "")
    shell_xdg = (Path(xdg) if xdg else home / ".config") / "colima"
    if not dot.exists() and not (explicit and Path(explicit).exists()):
        if explicit or shell_xdg != default_xdg:
            if not shell_xdg.exists() and not default_xdg.exists():
                dot.mkdir(parents=True)
        elif not default_xdg.exists():
            default_xdg.mkdir(parents=True)
    shell, service = colima_home(), service_colima_home()
    if shell != service:
        raise NeedsUser(
            f"Colima would use {shell} from your shell but {service} under brew services "
            "(launchd sets neither XDG_CONFIG_HOME nor COLIMA_HOME)",
            f"move the VM there (`colima stop; mv '{shell}' '{dot}'`) or unset COLIMA_HOME, "
            "then re-run",
        )
    return shell


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML ({exc})") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: expected a mapping at the top level")
    return data


def socket_daemon_args() -> list[str]:
    """The socket LaunchDaemon's ProgramArguments: link Colima's socket to DOCKER_SOCK."""
    # -h: never follow an existing link at DOCKER_SOCK (root must not write through it).
    return ["/bin/ln", "-shf", str(colima_home() / "default" / "docker.sock"), str(DOCKER_SOCK)]


def socket_daemon_current(ctx: Ctx) -> bool:
    """True when ``configure`` would leave the socket daemon alone: its plist exists with
    exactly the bytes ``launchd.system_daemon`` would write, and it is loaded.

    Read-only (no sudo) — ``Docker.sudo_needed`` asks this before a run (M4-D5).
    """
    if not colima_home().exists():
        # configure's ensure_colima_home may still pick a different home, which changes
        # the daemon's args: never report "current" before the home exists.
        return False
    path = launchd.DAEMONS_DIR / f"{SOCKET_LABEL}.plist"
    if not path.exists():
        return False
    # Same body system_daemon builds (launchd has no public "daemon_current" yet).
    body = launchd._plist(
        SOCKET_LABEL,
        socket_daemon_args(),
        start_interval=None,
        start_calendar=None,
        run_at_load=True,
        env=None,
    )
    return path.read_bytes() == body and launchd.daemon_loaded(ctx, SOCKET_LABEL)


class Colima:
    name: DockerRuntimeName = "colima"
    context_name = "colima"

    def daemon_config_path(self) -> Path:
        return colima_home() / "default" / "colima.yaml"

    def socket_path(self) -> Path:
        return colima_home() / "default" / "docker.sock"

    def installed(self, ctx: Ctx) -> bool:
        return all(pkg.installed(ctx, f) for f in FORMULAE)

    def install(self, ctx: Ctx) -> None:
        missing = [f for f in FORMULAE if not pkg.installed(ctx, f)]
        if missing:
            pkg.install(ctx, *missing)
        if pkg.cask_installed(ctx, "docker-desktop"):
            # Docker Desktop's cask links its own docker/docker-compose into the brew
            # prefix (plan D14); take the names back for the formulae.
            res = pkg.brew_link(ctx, "docker", "docker-compose", overwrite=True)
            if not res.ok:
                log.warn("colima: `brew link --overwrite docker docker-compose` failed; "
                         "`docker` may still be Docker Desktop's CLI")
        self._cli_plugins(ctx)

    def _cli_plugins(self, ctx: Ctx) -> None:
        path = docker_config_path()
        dirs = read_json(path).get("cliPluginsExtraDirs")
        current = [d for d in dirs if isinstance(d, str)] if isinstance(dirs, list) else []
        if CLI_PLUGINS_DIR not in current:
            probe = path if path.exists() else next(a for a in path.parents if a.exists())
            if not os.access(probe, os.W_OK):
                # e.g. root-owned after a `sudo docker login`: never write a user file as root.
                raise NeedsUser(
                    f"{probe} is not writable by you, so compose/buildx cannot be registered "
                    f"in {path}",
                    f"sudo chown -R \"$USER\" '{probe}', then re-run",
                )
            config.json_merge(
                ctx, str(path), {"cliPluginsExtraDirs": [*current, CLI_PLUGINS_DIR]}
            )

    def start_args(self, ctx: Ctx) -> list[str]:
        size = vm_size(ctx)
        args = ["--vm-type", "vz"]
        if rosetta_usable(ctx):  # M4-D8: supported by this macOS AND installed
            args.append("--vz-rosetta")
        else:
            log.info("colima: Rosetta 2 is unavailable — amd64 images run under qemu (slower)")
        return [
            *args,
            "--mount-type", "virtiofs",
            "--cpu", str(size.cpu),
            "--memory", str(size.memory_gib),
            "--disk", str(DISK_GIB),
        ]

    def configure(self, ctx: Ctx) -> None:
        ensure_colima_home()
        if not self.daemon_config_path().exists():
            # First run: create the VM, which saves these flags to colima.yaml, then stop
            # it so `brew services` (a bare `colima start -f`) owns it from now on (D11).
            argv = ["colima", "start", *self.start_args(ctx)]
            res = ctx.ex.run(argv)
            if not res.ok:
                raise InstallError("colima", " ".join(argv), res.code)
            if not ctx.ex.run(["colima", "stop"]).ok:
                log.warn("colima: `colima stop` failed after the first start; run it by hand "
                         "so brew services can own the VM")
        # macOS empties /var/run at boot, so the link is re-made by a root daemon (D13).
        launchd.system_daemon(ctx, SOCKET_LABEL, socket_daemon_args(), run_at_load=True)

    def start(self, ctx: Ctx) -> None:
        if not pkg.service_running(ctx, "colima"):
            res = pkg.brew_services(ctx, "start", "colima")
            if not res.ok:
                raise InstallError("colima", "brew services start colima", res.code)
        wait_for_engine(ctx, self.context_name)

    def stop(self, ctx: Ctx) -> None:
        pkg.brew_services(ctx, "stop", "colima")
        ctx.ex.run(["colima", "stop"])  # a VM started by hand, outside brew services

    def disable_autostart(self, ctx: Ctx) -> None:
        pkg.brew_services(ctx, "stop", "colima")  # also unregisters the login agent

    def release_socket(self, ctx: Ctx) -> None:
        # Least privilege: no sudo at all when the daemon was never installed.
        plist = launchd.DAEMONS_DIR / f"{SOCKET_LABEL}.plist"
        if plist.exists() or launchd.daemon_loaded(ctx, SOCKET_LABEL):
            launchd.remove_daemon(ctx, SOCKET_LABEL)
        if DOCKER_SOCK.is_symlink() and Path(os.readlink(DOCKER_SOCK)) == self.socket_path():
            ctx.ex.run(["rm", "-f", str(DOCKER_SOCK)], sudo=True)

    def merge_daemon_config(self, ctx: Ctx, patch: Mapping[str, Any]) -> bool:
        path = self.daemon_config_path()
        data = _load_yaml(path)
        current = data.get("docker")
        docker: dict[str, Any] = dict(current) if isinstance(current, dict) else {}
        merged = config.deep_merge(docker, patch)  # user keys beside ours survive
        if merged == docker:
            return False
        data["docker"] = merged
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic: a crash mid-write must not leave Colima an empty colima.yaml.
        mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".colima.yaml.")
        try:
            os.fchmod(fd, mode)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(yaml.safe_dump(data, sort_keys=False))
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return True

    def daemon_config_has(self, patch: Mapping[str, Any]) -> bool:
        docker = _load_yaml(self.daemon_config_path()).get("docker")
        return isinstance(docker, dict) and contains(docker, patch)

    def restart_engine(self, ctx: Ctx) -> None:
        if not pkg.service_running(ctx, "colima"):
            return  # the new config is read at the next start
        res = pkg.brew_services(ctx, "restart", "colima")
        if not res.ok:
            raise InstallError("colima", "brew services restart colima", res.code)
        wait_for_engine(ctx, self.context_name)

    def verify(self, ctx: Ctx) -> bool:
        return self.installed(ctx) and engine_verified(ctx, self.context_name)
