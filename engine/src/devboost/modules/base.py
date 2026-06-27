"""base-profile infrastructure modules (repos, dnf tuning, flatpak, build tools, chezmoi)."""

from __future__ import annotations

import os
from pathlib import Path

from devboost.core import log
from devboost.core.errors import SecretsError, UnsupportedOS
from devboost.core.registry import register
from devboost.exec.primitives import age, config, flatpak, pkg
from devboost.model import Ctx, Module
from devboost.modules.secrets import Secrets, bundle_path, key_path

_BUILD_PKGS_FEDORA = (
    "make automake gcc gcc-c++ kernel-devel cmake git wget perl vim nano unzip "
    "gnupg fastfetch unrar android-tools fuse-libs ripgrep"
).split()

_BUILD_PKGS_DEBIAN = (
    "build-essential cmake git wget perl vim nano unzip gnupg fastfetch libfuse2 ripgrep"
).split()


@register
class Rpmfusion(Module):
    name = "rpmfusion"
    category = "base"
    description = "Enable RPM Fusion free + nonfree + AppStream metadata."
    profiles = ("base",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.run(["rpm", "-q", "rpmfusion-free-release", "rpmfusion-nonfree-release"]).ok

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family != "fedora":
            raise UnsupportedOS(f"rpmfusion is Fedora-only; detected {ctx.os.distro!r}")
        rel = ctx.ex.run(["rpm", "-E", "%fedora"]).stdout.strip()
        base = "https://mirrors.rpmfusion.org"
        pkg.install(
            ctx,
            f"{base}/free/fedora/rpmfusion-free-release-{rel}.noarch.rpm",
            f"{base}/nonfree/fedora/rpmfusion-nonfree-release-{rel}.noarch.rpm",
        )
        ctx.ex.run(["dnf", "upgrade", "--refresh", "-y"], sudo=True)
        pkg.install(ctx, "rpmfusion-*-appstream-data")


@register
class DnfTune(Module):
    name = "dnf-tune"
    category = "base"
    description = "Tune dnf.conf (parallel downloads, fastest mirror)."
    profiles = ("base",)

    def _conf(self) -> str:
        return os.environ.get("DEVBOOST_DNF_CONF", "/etc/dnf/dnf.conf")

    def verify(self, ctx: Ctx) -> bool:
        p = Path(self._conf())
        if not p.exists():
            return False
        text = p.read_text(encoding="utf-8")
        return "max_parallel_downloads=10" in text and "fastestmirror=true" in text

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family != "fedora":
            raise UnsupportedOS(f"dnf-tune is Fedora-only; detected {ctx.os.distro!r}")
        conf = self._conf()
        config.write_kv(ctx, conf, "max_parallel_downloads", "10")
        config.write_kv(ctx, conf, "fastestmirror", "true")


@register
class FedoraThirdParty(Module):
    name = "fedora-third-party"
    category = "base"
    description = "Enable Fedora third-party repositories."
    profiles = ("base",)

    def verify(self, ctx: Ctx) -> bool:
        return "enabled" in ctx.ex.run(["fedora-third-party", "query"]).stdout

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family != "fedora":
            raise UnsupportedOS(f"fedora-third-party is Fedora-only; detected {ctx.os.distro!r}")
        ctx.ex.run(["fedora-third-party", "enable"], sudo=True)


@register
class Flatpak(Module):
    name = "flatpak"
    category = "base"
    description = "Configure the (unfiltered) Flathub remote."
    profiles = ("base",)

    def verify(self, ctx: Ctx) -> bool:
        return "flathub" in ctx.ex.run(["flatpak", "remotes"]).stdout.split()

    def install(self, ctx: Ctx) -> None:
        if not ctx.ex.which("flatpak"):
            pkg.install(ctx, "flatpak")
        flatpak.remote_add(ctx, "flathub", "https://flathub.org/repo/flathub.flatpakrepo")
        flatpak.remote_modify(ctx, "flathub", "--no-filter")


@register
class BuildTools(Module):
    name = "build-tools"
    category = "base"
    description = "Compiler toolchain + common build dependencies."
    profiles = ("base",)

    def verify(self, ctx: Ctx) -> bool:
        return all(ctx.ex.which(c) for c in ("gcc", "make", "cmake"))

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "debian":
            pkg.install(ctx, *_BUILD_PKGS_DEBIAN)
        else:
            pkg.install(ctx, *_BUILD_PKGS_FEDORA)


@register
class Chezmoi(Module):
    name = "chezmoi"
    category = "base"
    description = "Install the chezmoi dotfiles manager."
    profiles = ("base",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("chezmoi")

    def install(self, ctx: Ctx) -> None:
        bindir = Path(os.environ["HOME"]) / ".local" / "bin"
        bindir.mkdir(parents=True, exist_ok=True)
        # Upstream installer is a curl|sh one-liner (escape hatch — no native package).
        ctx.ex.run(["sh", "-c", f"curl -fsLS get.chezmoi.io | sh -s -- -b {bindir}"])


@register
class ChezmoiRepo(Module):
    name = "chezmoi-repo"
    category = "base"
    description = "Clone + apply the managed dotfiles repo via the credential store."
    requires = (Chezmoi, Secrets)
    profiles = ("base",)

    def verify(self, ctx: Ctx) -> bool:
        return (Path(os.environ["HOME"]) / ".local" / "share" / "chezmoi").is_dir()

    def install(self, ctx: Ctx) -> None:
        repo = os.environ.get("DEVBOOST_DOTFILES_REPO")
        if not repo:
            # Fall back to DOTFILES_REPO key in the decrypted secrets bundle.
            try:
                data = age.decrypt(ctx, bundle_path(), key_path())
                repo = data.get("DOTFILES_REPO") or data.get("DEVBOOST_DOTFILES_REPO")
            except Exception:
                pass
        if not repo:
            raise SecretsError(
                "chezmoi-repo: dotfiles repo URL not found — set DEVBOOST_DOTFILES_REPO "
                "or add a DOTFILES_REPO key to the secrets bundle"
            )
        if not ctx.ex.run(["chezmoi", "init", "--apply", repo]).ok:
            log.warn("chezmoi-repo: init/clone failed — dotfiles not synced (non-blocking)")
