"""Package primitive with OS dispatch.

The package manager is selected from ctx.os; no module ever names dnf/apt directly.
Dnf (Fedora), Apt (Debian/Ubuntu) and Pacman (Arch/Omarchy) are implemented.
"""

from __future__ import annotations

import re
import shlex
from typing import Protocol, runtime_checkable

from devboost.core import log
from devboost.core.errors import InstallError, PresentUnmanaged, UnsupportedOS
from devboost.core.osinfo import OsInfo, OsMap
from devboost.exec.executor import Result
from devboost.model import AptRepo, BrewTap, Ctx, DnfRepo

# A package name: a plain string, or per-OS names resolved distro->family->default.
Pkg = str | OsMap[str]
# A third-party install source per OS.
Repo = DnfRepo | AptRepo | BrewTap
Source = OsMap[Repo]


@runtime_checkable
class PackageManager(Protocol):
    def install(self, ctx: Ctx, *pkgs: str) -> None: ...
    def installed(self, ctx: Ctx, pkg: str) -> bool: ...
    def add_repo(self, ctx: Ctx, repo: Repo) -> None: ...


class Dnf:
    def install(self, ctx: Ctx, *pkgs: str) -> None:
        if pkgs:
            result = ctx.ex.run(["dnf", "install", "-y", *pkgs], sudo=True)
            if not result.ok:
                raise InstallError("dnf", f"dnf install -y {' '.join(pkgs)}", result.code)

    def installed(self, ctx: Ctx, pkg: str) -> bool:
        return ctx.ex.run(["rpm", "-q", pkg]).ok

    def add_repo(self, ctx: Ctx, repo: Repo) -> None:
        if not isinstance(repo, DnfRepo):
            raise TypeError(f"Dnf.add_repo expects DnfRepo, got {type(repo).__name__}")
        body = (
            f"[{repo.name}]\nname={repo.name}\nbaseurl={repo.baseurl}\n"
            f"gpgcheck={1 if repo.gpgcheck else 0}\nenabled=1\n"
        )
        if repo.gpgkey is not None:
            body += f"gpgkey={repo.gpgkey}\n"
        dest = f"/etc/yum.repos.d/{repo.name}.repo"
        result = ctx.ex.run(["tee", dest], sudo=True, stdin=body)
        if not result.ok:
            raise InstallError("dnf", f"tee {dest}", result.code)


def _apt_slug(list_line: str) -> str:
    """Derive a stable filename slug from the first URL in an apt list_line."""
    m = re.search(r"https?://([^/\s]+)", list_line)
    return m.group(1).replace(".", "-") if m else "custom-repo"


# Ubuntu 24.04's apt post-hook runs needrestart, which pops whiptail prompts that hang a
# non-interactive (agent / curl|bash) install: a "restart which services?" prompt AND a
# "pending kernel upgrade" msgbox. NEEDRESTART_MODE=a silences the first, but the kernel
# hint is only disabled via config — so drop in a conf that turns both off.
_NEEDRESTART_CONF = "/etc/needrestart/conf.d/99-devboost.conf"
_NEEDRESTART_BODY = (
    "# devboost — keep apt's needrestart hook from hanging non-interactive installs.\n"
    "$nrconf{restart} = 'a';\n"       # auto-restart services, don't ask
    "$nrconf{kernelhints} = -1;\n"    # no 'pending kernel upgrade' msgbox
    "$nrconf{ucodehints} = 0;\n"      # no microcode msgbox
)


class Apt:
    def _quiet_needrestart(self, ctx: Ctx) -> None:
        ctx.ex.run(["mkdir", "-p", "/etc/needrestart/conf.d"], sudo=True)
        ctx.ex.run(["tee", _NEEDRESTART_CONF], sudo=True, stdin=_NEEDRESTART_BODY)

    def install(self, ctx: Ctx, *pkgs: str) -> None:
        if pkgs:
            self._quiet_needrestart(ctx)
            result = ctx.ex.run(
                ["apt-get", "install", "-y", *pkgs],
                sudo=True,
                env={"DEBIAN_FRONTEND": "noninteractive", "NEEDRESTART_MODE": "a"},
            )
            if not result.ok:
                raise InstallError("apt", f"apt-get install -y {' '.join(pkgs)}", result.code)

    def installed(self, ctx: Ctx, pkg: str) -> bool:
        return ctx.ex.run(["dpkg", "-s", pkg]).ok

    def add_repo(self, ctx: Ctx, repo: Repo) -> None:
        if not isinstance(repo, AptRepo):
            raise TypeError(f"Apt.add_repo expects AptRepo, got {type(repo).__name__}")
        slug = _apt_slug(repo.list_line)
        # Fetch the signing key and normalize it to a BINARY keyring. Vendors serve
        # either ASCII-armored keys (ddev, Microsoft, Docker) or binary keyrings;
        # `gpg --dearmor` accepts both and always emits binary, matching the `.gpg`
        # name used in signed-by. Writing an armored key straight to `.gpg` (the old
        # behavior) trips NO_PUBKEY. Pipe curl→gpg in one shell run so a binary key is
        # never corrupted by round-tripping through captured stdout.
        if repo.key_url:
            key_path = f"/etc/apt/keyrings/{slug}.gpg"
            script = (
                "mkdir -p /etc/apt/keyrings && "
                f"curl -fsSL {shlex.quote(repo.key_url)} "
                f"| gpg --dearmor --yes -o {shlex.quote(key_path)}"
            )
            put = ctx.ex.run(["sh", "-c", script], sudo=True)
            if not put.ok:
                raise InstallError("apt", f"import key {repo.key_url}", put.code)
        # Write the sources list entry.
        list_path = f"/etc/apt/sources.list.d/{slug}.list"
        put = ctx.ex.run(["tee", list_path], sudo=True, stdin=repo.list_line + "\n")
        if not put.ok:
            raise InstallError("apt", f"tee {list_path}", put.code)
        # Refresh the package index.
        upd = ctx.ex.run(
            ["apt-get", "update"],
            sudo=True,
            env={"DEBIAN_FRONTEND": "noninteractive"},
        )
        if not upd.ok:
            raise InstallError("apt", "apt-get update", upd.code)


# Omarchy ships idempotent package helpers that wrap pacman/yay, verify the package
# actually registered afterwards, and manage their own privilege elevation. When they are
# on PATH we delegate to them rather than shelling out to pacman ourselves: it is the
# platform's own convention, and it keeps dev-boost out of the sudo-prompt business.
_OMARCHY_ADD = "omarchy-pkg-add"
_OMARCHY_AUR_ADD = "omarchy-pkg-aur-add"


class Pacman:
    """Arch family. Official repos via pacman; AUR via an AUR helper.

    Deliberately never runs ``pacman -Sy``. On a rolling release, syncing the package
    database without also upgrading (``-Syu``) creates a *partial upgrade* — the classic
    way to break an Arch box, because a freshly-synced package can link against libraries
    the installed system has not upgraded to yet. Refreshing the index is therefore the
    OS updater's job (``omarchy update`` / ``pacman -Syu``), not an installer's; see
    ``refresh_index`` below.
    """

    def install(self, ctx: Ctx, *pkgs: str) -> None:
        if not pkgs:
            return
        if ctx.ex.which(_OMARCHY_ADD):
            # Manages its own elevation (root-aware); wrapping it in sudo would nest.
            result = ctx.ex.run([_OMARCHY_ADD, *pkgs])
            cmd = f"{_OMARCHY_ADD} {' '.join(pkgs)}"
        else:
            result = ctx.ex.run(
                ["pacman", "-S", "--needed", "--noconfirm", *pkgs], sudo=True
            )
            cmd = f"pacman -S --needed --noconfirm {' '.join(pkgs)}"
        if not result.ok:
            raise InstallError("pacman", cmd, result.code)

    def installed(self, ctx: Ctx, pkg: str) -> bool:
        return ctx.ex.run(["pacman", "-Q", pkg]).ok

    def add_repo(self, ctx: Ctx, repo: Repo) -> None:
        # Arch third-party software comes from the AUR or a distro-provided repo, not from
        # per-package repo files. A module reaching here has a per-OS Source that simply
        # does not apply to Arch — say so instead of silently doing nothing.
        raise UnsupportedOS(
            "pacman has no per-package repo mechanism; use install_aur() "
            "or an official/OPR package name on the Arch family"
        )

    def install_aur(self, ctx: Ctx, *pkgs: str) -> None:
        """Install AUR packages via an AUR helper (never as root — yay refuses)."""
        if not pkgs:
            return
        if ctx.ex.which(_OMARCHY_AUR_ADD):
            result = ctx.ex.run([_OMARCHY_AUR_ADD, *pkgs])
            cmd = f"{_OMARCHY_AUR_ADD} {' '.join(pkgs)}"
        elif ctx.ex.which("yay"):
            result = ctx.ex.run(["yay", "-S", "--needed", "--noconfirm", *pkgs])
            cmd = f"yay -S --needed --noconfirm {' '.join(pkgs)}"
        elif ctx.ex.which("paru"):
            result = ctx.ex.run(["paru", "-S", "--needed", "--noconfirm", *pkgs])
            cmd = f"paru -S --needed --noconfirm {' '.join(pkgs)}"
        else:
            raise UnsupportedOS(
                "no AUR helper found (looked for omarchy-pkg-aur-add, yay, paru)"
            )
        if not result.ok:
            raise InstallError("aur", cmd, result.code)


#: Every brew call runs with these. Auto-update is replaced by one explicit `brew update`
#: per run (refresh_index); cleanup and hints are noise in an unattended install.
BREW_ENV: dict[str, str] = {
    "HOMEBREW_NO_AUTO_UPDATE": "1",
    "HOMEBREW_NO_INSTALL_CLEANUP": "1",
    "HOMEBREW_NO_ENV_HINTS": "1",
    "NONINTERACTIVE": "1",
}

# brew's messages when a cask's app already exists and cannot be taken over
# (Homebrew 7.0.4, cask/artifact/moved.rb). With --adopt, a hand-installed app whose
# bundle version differs raises the first; the second is the wording without
# --adopt/--force, kept as a fallback should brew's flow change.
_ALREADY_PRESENT = (
    "is different from the one being installed",
    "already an App at",
)


class Brew:
    """macOS. Formulae and casks via Homebrew — never under sudo (brew refuses root).

    ``brew`` is invoked by name: the executor puts ``/opt/homebrew/bin`` on PATH on
    macOS, so this works before the user's shell has brew's shellenv.
    """

    def _brew(self, ctx: Ctx, *args: str) -> Result:
        return ctx.ex.run(["brew", *args], env=BREW_ENV)

    def install(self, ctx: Ctx, *pkgs: str) -> None:
        if not pkgs:
            return
        res = self._brew(ctx, "install", "--formula", "-y", *pkgs)
        if not res.ok:
            raise InstallError("brew", f"brew install --formula -y {' '.join(pkgs)}", res.code)

    def install_cask(self, ctx: Ctx, *casks: str) -> None:
        if not casks:
            return
        res = self._brew(ctx, "install", "--cask", "-y", "--adopt", *casks)
        if res.ok:
            return
        output = f"{res.stdout}\n{res.stderr}"
        if any(marker in output for marker in _ALREADY_PRESENT):
            raise PresentUnmanaged(", ".join(casks))
        raise InstallError("brew", f"brew install --cask -y --adopt {' '.join(casks)}", res.code)

    def installed(self, ctx: Ctx, pkg: str) -> bool:
        return self._brew(ctx, "list", "--formula", "--versions", pkg).ok

    def cask_installed(self, ctx: Ctx, cask: str) -> bool:
        return self._brew(ctx, "list", "--cask", "--versions", cask).ok

    def upgrade(self, ctx: Ctx, *pkgs: str) -> None:
        if not pkgs:
            return
        res = self._brew(ctx, "upgrade", "--formula", *pkgs)
        if not res.ok:
            raise InstallError("brew", f"brew upgrade --formula {' '.join(pkgs)}", res.code)

    def add_repo(self, ctx: Ctx, repo: Repo) -> None:
        if not isinstance(repo, BrewTap):
            raise TypeError(f"Brew.add_repo expects BrewTap, got {type(repo).__name__}")
        args = ["tap", repo.name, *([repo.url] if repo.url else [])]
        res = self._brew(ctx, *args)
        if not res.ok:
            raise InstallError("brew", f"brew {' '.join(args)}", res.code)


def manager_for(os_info: OsInfo) -> PackageManager:
    if os_info.family == "fedora":
        return Dnf()
    if os_info.family == "debian":
        return Apt()
    if os_info.family == "arch":
        return Pacman()
    if os_info.family == "macos":
        return Brew()
    raise UnsupportedOS(f"no package manager implemented for {os_info.distro!r}")


def _resolve_names(ctx: Ctx, pkgs: tuple[Pkg, ...]) -> list[str]:
    names: list[str] = []
    for p in pkgs:
        if isinstance(p, str):
            names.append(p)
        else:
            name = p.get(ctx.os)
            if name is None:
                raise UnsupportedOS(f"no package name for {ctx.os.distro!r}")
            names.append(name)
    return names


def install(
    ctx: Ctx,
    *pkgs: Pkg,
    source: Source | None = None,
    refresh: bool = False,
) -> None:
    mgr = manager_for(ctx.os)
    if source is not None:
        repo = source.get(ctx.os)
        if repo is None:
            raise UnsupportedOS(f"no install source for {ctx.os.distro!r}")
        mgr.add_repo(ctx, repo)
    names = _resolve_names(ctx, pkgs)
    if refresh and isinstance(mgr, Dnf) and names:
        result = ctx.ex.run(["dnf", "install", "--refresh", "-y", *names], sudo=True)
        if not result.ok:
            raise InstallError("dnf", f"dnf install --refresh -y {' '.join(names)}", result.code)
        return
    mgr.install(ctx, *names)


def installed(ctx: Ctx, pkg: str) -> bool:
    return manager_for(ctx.os).installed(ctx, pkg)


def install_aur(ctx: Ctx, *pkgs: str) -> None:
    """Install AUR packages. Arch family only — raises UnsupportedOS elsewhere.

    Kept separate from ``install`` because the AUR is not a repo you add but a build
    service you invoke: it needs a helper, must not run as root, and carries a different
    trust model (unreviewed third-party PKGBUILDs) that a caller should opt into by name.
    """
    mgr = manager_for(ctx.os)
    if not isinstance(mgr, Pacman):
        raise UnsupportedOS(f"the AUR is Arch-only; detected {ctx.os.distro!r}")
    mgr.install_aur(ctx, *pkgs)


def _brew_or_raise(ctx: Ctx, what: str) -> Brew:
    mgr = manager_for(ctx.os)
    if not isinstance(mgr, Brew):
        raise UnsupportedOS(f"{what} is macOS-only; detected {ctx.os.distro!r}")
    return mgr


def install_cask(ctx: Ctx, *casks: str) -> None:
    """Install Homebrew casks (GUI apps). macOS only."""
    _brew_or_raise(ctx, "casks").install_cask(ctx, *casks)


def cask_installed(ctx: Ctx, cask: str) -> bool:
    """True when the cask is installed; always False off macOS (never raises)."""
    if ctx.os.family != "macos":
        return False
    return Brew().cask_installed(ctx, cask)


def upgrade(ctx: Ctx, *pkgs: str) -> None:
    """Upgrade formulae in place (`devboost install --update` on macOS)."""
    _brew_or_raise(ctx, "brew upgrade").upgrade(ctx, *pkgs)


#: Seconds apt waits for a held dpkg/apt lock before giving up (drop-in below).
_APT_LOCK_TIMEOUT = 300
_APT_LOCK_CONF = "/etc/apt/apt.conf.d/99-devboost-lock-timeout"


def refresh_index(ctx: Ctx) -> None:
    """Refresh the package index once before the install loop (best-effort).

    On Debian/Ubuntu a fresh or minimal system can carry a stale/incomplete apt index,
    so installing an otherwise-available package (e.g. ``du-dust`` from universe) fails
    with apt exit 100.  A single ``apt-get update`` up front makes installs robust without
    per-package overhead.  No-op on Fedora (dnf refreshes metadata on demand) and on any
    OS without a package manager.  Failures are logged, never raised: a transient mirror
    error must not abort the run, and a usable cached index may still satisfy installs.

    Also a deliberate no-op on Arch: ``pacman -Sy`` without ``-u`` is a partial upgrade,
    the standard way to break a rolling-release system.  Syncing belongs to the OS updater
    (``omarchy update`` / ``pacman -Syu``), which snapshots first.
    On macOS it is a single best-effort `brew update`.
    """
    if ctx.os.family == "macos":
        # One explicit update per run (auto-update is disabled on every other brew call).
        res = ctx.ex.run(["brew", "update"], env=BREW_ENV)
        if not res.ok:
            log.warn(f"brew update failed (code {res.code}); using the existing index")
        return
    if ctx.os.family != "debian":
        return
    # Make every apt call WAIT up to _APT_LOCK_TIMEOUT for a held dpkg/apt lock (e.g.
    # cloud-init / unattended-upgrades on a fresh VM) instead of failing with exit 100.
    # A drop-in applies globally — including the user's own later `apt`. Best-effort.
    ctx.ex.run(
        ["tee", _APT_LOCK_CONF],
        sudo=True,
        stdin=f'DPkg::Lock::Timeout "{_APT_LOCK_TIMEOUT}";\n',
    )
    result = ctx.ex.run(
        ["apt-get", "update"],
        sudo=True,
        env={"DEBIAN_FRONTEND": "noninteractive"},
    )
    if not result.ok:
        log.warn(f"apt-get update failed (code {result.code}); using the existing index")
