"""apps profile — Flathub GUI apps + obsidian-sync vault provisioning."""

from __future__ import annotations

import os
import shlex
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from devboost.core.errors import GithubError, NeedsUser, UnsupportedOS
from devboost.core.osinfo import LINUX_FAMILIES, OsMap
from devboost.core.registry import register
from devboost.exec.primitives import flatpak, github, pkg, systemd
from devboost.model import Ctx, Module
from devboost.modules import _credentials as creds_src
from devboost.modules._brew import BrewCask
from devboost.modules._launchd_jobs import job_scheduled, schedule_job
from devboost.modules.base import Flatpak
from devboost.modules.macos import Homebrew
from devboost.modules.secrets import Secrets
from devboost.modules.ssh_setup import SshSetup


class FlatpakApp(Module):
    """A GUI application: Flathub on Fedora/Ubuntu, a native package on Arch, a Homebrew
    cask on macOS.

    Flathub is a *delivery mechanism*, not the product. On Arch every app dev-boost ships
    exists as a real package, so installing a ~1 GB Flatpak runtime to duplicate them would
    cost disk and give up pacman's own upgrade path. Subclasses therefore name an Arch
    package (``arch_pkg``, official repos or Omarchy's own) or an ``aur_pkg`` fallback,
    and the Arch branch installs that instead.
    """

    app_id: ClassVar[str]
    #: Official Arch / Omarchy repo package name. Preferred over aur_pkg when both are set.
    arch_pkg: ClassVar[str | None] = None
    #: AUR package name, used only when the app is absent from the official repos.
    aur_pkg: ClassVar[str | None] = None
    #: Homebrew cask on macOS (Flathub does not exist there).
    cask: ClassVar[str | None] = None
    category = "apps"
    gui = True
    requires: ClassVar[tuple[type[Module], ...]] = (Flatpak, Homebrew)
    profiles = ("apps",)

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        # Homebrew is needed only to install a cask. An app with none never touches brew
        # (on macOS it is provided by the OS or scoped to Linux), so pulling Homebrew — and
        # the CLT under it — into its plan would install both for nothing.
        if cls.cask is None and "requires" not in cls.__dict__:
            cls.requires = tuple(r for r in cls.requires if r is not Homebrew)

    def _arch_name(self) -> str | None:
        return self.arch_pkg or self.aur_pkg

    def verify(self, ctx: Ctx) -> bool:
        if ctx.os.family == "macos":
            return self.cask is not None and BrewCask(self.cask).verify(ctx)
        if ctx.os.family == "arch":
            name = self._arch_name()
            return name is not None and pkg.installed(ctx, name)
        return ctx.ex.run(["flatpak", "info", self.app_id]).ok

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "macos":
            if self.cask is None:
                raise UnsupportedOS(f"{self.name}: no macOS cask declared (set cask)")
            BrewCask(self.cask).install(ctx)
            return
        if ctx.os.family == "arch":
            if self.arch_pkg is not None:
                pkg.install(ctx, self.arch_pkg)
            elif self.aur_pkg is not None:
                pkg.install_aur(ctx, self.aur_pkg)
            else:
                raise UnsupportedOS(
                    f"{self.name}: no Arch package declared (set arch_pkg or aur_pkg)"
                )
            return
        flatpak.install(ctx, self.app_id)


@register
class Obsidian(FlatpakApp):
    name = "obsidian"
    description = "Obsidian notes."
    app_id = "md.obsidian.Obsidian"
    arch_pkg = "obsidian"
    cask = "obsidian"


@register
class Bruno(FlatpakApp):
    name = "bruno"
    description = "Bruno API client."
    app_id = "com.usebruno.Bruno"
    aur_pkg = "bruno-bin"
    cask = "bruno"


@register
class Bitwarden(FlatpakApp):
    name = "bitwarden"
    description = "Bitwarden desktop."
    app_id = "com.bitwarden.desktop"
    arch_pkg = "bitwarden"
    cask = "bitwarden"


@register
class Flameshot(FlatpakApp):
    name = "flameshot"
    description = "Flameshot screenshots."
    app_id = "org.flameshot.Flameshot"
    arch_pkg = "flameshot"
    # macOS: ⌘⇧5 is built in; the brew cask is deprecated
    provided_by: ClassVar[tuple[str, ...]] = ("omarchy", "macos")


@register
class Localsend(FlatpakApp):
    name = "localsend"
    description = "LocalSend file sharing."
    app_id = "org.localsend.localsend_app"
    arch_pkg = "localsend"
    cask = "localsend"


@register
class Vlc(FlatpakApp):
    name = "vlc"
    description = "VLC media player."
    app_id = "org.videolan.VLC"
    arch_pkg = "vlc"
    cask = "vlc"


@register
class Gearlever(FlatpakApp):
    name = "gearlever"
    description = "Gear Lever — integrate & update AppImages (LM Studio, WezTerm, …)."
    app_id = "it.mijorus.gearlever"
    aur_pkg = "gearlever"
    # AppImage manager
    families: ClassVar[tuple[str, ...]] = LINUX_FAMILIES


def _home() -> Path:
    return Path(os.environ["HOME"])


def _vault_dir() -> Path:
    return Path(os.environ.get("VAULT_DIR", str(_home() / "Vault")))


_SSH_ALIAS = "devboost-vault.github.com"
_DEPLOY_KEY = ".ssh/devboost-vault"


def _ssh_alias(ctx: Ctx, key: Path) -> None:
    cfg = _home() / ".ssh" / "config"
    block = (
        f"\nHost {_SSH_ALIAS}\n  HostName github.com\n  User git\n"
        f"  IdentityFile {key}\n  IdentitiesOnly yes\n"
    )
    text = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
    if _SSH_ALIAS not in text:
        cfg.write_text(text + block, encoding="utf-8")


def _provision_vault(ctx: Ctx) -> Path:
    """Deploy key, SSH alias, clone; the vault dir.

    What only the user can supply — the repo name, GitHub credentials, a PAT allowed to add
    deploy keys — raises ``NeedsUser``: the run reports ``blocked`` with the fix, never a
    ``fail`` from a verify that could not pass (final review I2; M3 reported it blocked too).
    """
    repo = os.environ.get("DEVBOOST_VAULT_REPO")
    if not repo:
        raise NeedsUser(
            "obsidian-sync: no vault repo configured",
            "export DEVBOOST_VAULT_REPO=<repo> (a GitHub repo name) and re-run",
        )
    creds = creds_src.github_credentials(ctx)
    if creds is None:
        raise NeedsUser(
            "obsidian-sync: no GitHub credentials found (bundle, gh, git credentials)",
            "run `gh auth login` (or add GIT_USER and GITHUB_PAT to the secrets bundle) "
            "and re-run",
        )
    owner, pat = creds["GIT_USER"], creds["GITHUB_PAT"]

    key = _home() / _DEPLOY_KEY
    if not key.exists():
        key.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        ctx.ex.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C",
                    f"devboost-vault:{socket.gethostname()}", "-f", str(key)])
    _ssh_alias(ctx, key)

    pub = key.with_suffix(".pub")
    if pub.exists():
        try:
            github.add_deploy_key(pat, owner, repo, pub.read_text(encoding="utf-8"),
                                  f"devboost-vault:{socket.gethostname()}")
        except GithubError as exc:
            raise NeedsUser(
                f"obsidian-sync: GitHub refused the deploy key for {owner}/{repo} ({exc})",
                f"check that {owner}/{repo} exists and your token may add deploy keys "
                "to it, then re-run",
            ) from exc

    vault = _vault_dir()
    if not (vault / ".git").is_dir():
        ctx.ex.run(["git", "clone", f"git@{_SSH_ALIAS}:{owner}/{repo}.git", str(vault)])
    return vault


_VAULT_JOB = "obsidian-sync"


def _vault_script(vault: Path) -> str:
    return (
        f"cd {shlex.quote(str(vault))} && git add -A && "
        "git commit -m auto >/dev/null 2>&1; git pull --rebase && git push"
    )


@dataclass(frozen=True)
class _MacObsidianSync:
    """macOS: the same provisioning, with the daily push as a launchd agent (plan D5)."""

    def verify(self, ctx: Ctx) -> bool:
        vault = _vault_dir()
        return (vault / ".git").is_dir() and job_scheduled(
            ctx, _VAULT_JOB, _vault_script(vault), "daily"
        )

    def install(self, ctx: Ctx) -> None:
        vault = _provision_vault(ctx)
        schedule_job(ctx, _VAULT_JOB, _vault_script(vault), "daily")


@register
class ObsidianSync(Module):
    name = "obsidian-sync"
    category = "apps"
    description = "Provision the Obsidian vault: deploy key, clone, daily push backstop."
    requires = (Obsidian, Secrets, SshSetup)
    profiles = ("apps",)
    per_os = OsMap(macos=_MacObsidianSync())

    def verify(self, ctx: Ctx) -> bool:
        if (s := self.os_strategy(ctx)) is not None:
            return s.verify(ctx)
        return (_vault_dir() / ".git").is_dir()

    def install(self, ctx: Ctx) -> None:
        if (s := self.os_strategy(ctx)) is not None:
            s.install(ctx)
            return
        self._systemd_backstop(ctx, _provision_vault(ctx))

    def _systemd_backstop(self, ctx: Ctx, vault: Path) -> None:
        service = (
            "[Unit]\nDescription=devboost Obsidian vault sync\n\n[Service]\nType=oneshot\n"
            f"ExecStart=/bin/sh -c 'cd {vault} && git add -A && "
            "git commit -m auto >/dev/null 2>&1; git pull --rebase && git push'\n"
        )
        timer = (
            "[Unit]\nDescription=daily Obsidian vault push\n\n[Timer]\n"
            "OnCalendar=daily\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n"
        )
        systemd.write_user_unit(ctx, "devboost-vault-sync.service", service)
        systemd.write_user_unit(ctx, "devboost-vault-sync.timer", timer)
        systemd.enable_user_unit(ctx, "devboost-vault-sync.timer", now=True)
