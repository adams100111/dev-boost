"""apps profile — Flathub GUI apps + obsidian-sync vault provisioning."""

from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import ClassVar

from devboost.core import log
from devboost.core.errors import GithubError, UnsupportedOS
from devboost.core.registry import register
from devboost.exec.primitives import age, flatpak, github, pkg, systemd
from devboost.model import Ctx, Module
from devboost.modules.base import Flatpak
from devboost.modules.secrets import Secrets, bundle_path, key_path
from devboost.modules.ssh_setup import SshSetup


class FlatpakApp(Module):
    """A GUI application: Flathub on Fedora/Ubuntu, a native package on the Arch family.

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
    category = "apps"
    gui = True
    requires = (Flatpak,)
    profiles = ("apps",)

    def _arch_name(self) -> str | None:
        return self.arch_pkg or self.aur_pkg

    def verify(self, ctx: Ctx) -> bool:
        if ctx.os.family == "arch":
            name = self._arch_name()
            return name is not None and pkg.installed(ctx, name)
        return ctx.ex.run(["flatpak", "info", self.app_id]).ok

    def install(self, ctx: Ctx) -> None:
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


@register
class Bruno(FlatpakApp):
    name = "bruno"
    description = "Bruno API client."
    app_id = "com.usebruno.Bruno"
    aur_pkg = "bruno-bin"


@register
class Bitwarden(FlatpakApp):
    name = "bitwarden"
    description = "Bitwarden desktop."
    app_id = "com.bitwarden.desktop"
    arch_pkg = "bitwarden"


@register
class Flameshot(FlatpakApp):
    name = "flameshot"
    description = "Flameshot screenshots."
    app_id = "org.flameshot.Flameshot"
    arch_pkg = "flameshot"
    provided_by: ClassVar[tuple[str, ...]] = ("omarchy",)


@register
class Localsend(FlatpakApp):
    name = "localsend"
    description = "LocalSend file sharing."
    app_id = "org.localsend.localsend_app"
    arch_pkg = "localsend"


@register
class Vlc(FlatpakApp):
    name = "vlc"
    description = "VLC media player."
    app_id = "org.videolan.VLC"
    arch_pkg = "vlc"


@register
class Gearlever(FlatpakApp):
    name = "gearlever"
    description = "Gear Lever — integrate & update AppImages (LM Studio, WezTerm, …)."
    app_id = "it.mijorus.gearlever"
    aur_pkg = "gearlever"


def _home() -> Path:
    return Path(os.environ["HOME"])


def _vault_dir() -> Path:
    return Path(os.environ.get("VAULT_DIR", str(_home() / "Vault")))


_SSH_ALIAS = "devboost-vault.github.com"
_DEPLOY_KEY = ".ssh/devboost-vault"


@register
class ObsidianSync(Module):
    name = "obsidian-sync"
    category = "apps"
    description = "Provision the Obsidian vault: deploy key, clone, daily push backstop."
    requires = (Obsidian, Secrets, SshSetup)
    profiles = ("apps",)

    def verify(self, ctx: Ctx) -> bool:
        return (_vault_dir() / ".git").is_dir()

    def install(self, ctx: Ctx) -> None:
        repo = os.environ.get("DEVBOOST_VAULT_REPO")
        if not repo:
            log.warn("obsidian-sync: DEVBOOST_VAULT_REPO not set — skipping (non-blocking)")
            return
        creds = age.decrypt(ctx, bundle_path(), key_path())
        owner, pat = creds["GIT_USER"], creds["GITHUB_PAT"]

        key = _home() / _DEPLOY_KEY
        if not key.exists():
            key.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            ctx.ex.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C",
                        f"devboost-vault:{socket.gethostname()}", "-f", str(key)])
        self._ssh_alias(ctx, key)

        pub = key.with_suffix(".pub")
        if pub.exists():
            try:
                github.add_deploy_key(pat, owner, repo, pub.read_text(encoding="utf-8"),
                                      f"devboost-vault:{socket.gethostname()}")
            except GithubError:
                log.warn("obsidian-sync: deploy-key registration failed (non-blocking)")
                return

        vault = _vault_dir()
        if not (vault / ".git").is_dir():
            ctx.ex.run(["git", "clone", f"git@{_SSH_ALIAS}:{owner}/{repo}.git", str(vault)])
        self._systemd_backstop(ctx, vault)

    def _ssh_alias(self, ctx: Ctx, key: Path) -> None:
        cfg = _home() / ".ssh" / "config"
        block = (
            f"\nHost {_SSH_ALIAS}\n  HostName github.com\n  User git\n"
            f"  IdentityFile {key}\n  IdentitiesOnly yes\n"
        )
        text = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
        if _SSH_ALIAS not in text:
            cfg.write_text(text + block, encoding="utf-8")

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
