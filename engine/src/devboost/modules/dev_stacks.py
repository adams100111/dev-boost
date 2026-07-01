"""dev-stacks profiles — python, web, laravel, dotnet, data, devops, react-native."""

from __future__ import annotations

import os
from pathlib import Path

from devboost.core.registry import register
from devboost.exec.primitives import mise, pkg
from devboost.exec.resources import resource_path
from devboost.model import Ctx, Module
from devboost.modules._lsp import LspModule
from devboost.modules.base import Chezmoi  # noqa: F401 — keeps base import side effects predictable
from devboost.modules.ddev import Ddev
from devboost.modules.docker import Docker
from devboost.modules.editors import Fresh
from devboost.modules.mise import Mise

_UV_VERSION = "0.11.23"


def _home() -> Path:
    return Path(os.environ["HOME"])


# --- python ------------------------------------------------------------------------------


@register
class Uv(Module):
    name = "uv"
    category = "python"
    description = "uv — fast Python package/project manager."
    profiles = ("python",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("uv")

    def install(self, ctx: Ctx) -> None:
        ctx.ex.run(["sh", "-c", f"curl -LsSf https://astral.sh/uv/{_UV_VERSION}/install.sh | sh"])


@register
class PythonLsp(LspModule):
    name = "python-lsp"
    description = "basedpyright + ruff for Python (fresh)."
    requires = (Fresh, Mise, Uv)
    profiles = ("python",)
    servers_file = "python-lsp.tsv"


# --- web ---------------------------------------------------------------------------------


@register
class WebRuntimes(Module):
    name = "web-runtimes"
    category = "web"
    description = "node/pnpm/bun via mise."
    requires = (Mise,)
    profiles = ("web",)
    _SPECS = ("node@22", "pnpm@11.8.0", "bun@1.3.14")

    def verify(self, ctx: Ctx) -> bool:
        return all(ctx.ex.which(c) for c in ("node", "pnpm", "bun"))

    def install(self, ctx: Ctx) -> None:
        ctx.ex.run(["mise", "use", "-g", *self._SPECS])


@register
class WebLsp(LspModule):
    name = "web-lsp"
    description = "ts/eslint/tailwind/prettier servers (fresh)."
    requires = (Fresh, Mise, WebRuntimes)
    profiles = ("web",)
    servers_file = "web-lsp.tsv"


# --- laravel -----------------------------------------------------------------------------


@register
class LaravelLsp(LspModule):
    name = "laravel-lsp"
    description = "intelephense for Laravel/PHP (fresh)."
    requires = (Fresh, Mise, Ddev)
    profiles = ("laravel",)
    servers_file = "laravel-lsp.tsv"


# --- dotnet ------------------------------------------------------------------------------


@register
class DotnetSdk(Module):
    name = "dotnet-sdk"
    category = "dotnet"
    description = ".NET 10 LTS SDK."
    profiles = ("dotnet",)

    def verify(self, ctx: Ctx) -> bool:
        out = ctx.ex.run(["dotnet", "--list-sdks"])
        return out.ok and any(ln.startswith("10.") for ln in out.stdout.splitlines())

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "debian":
            # Microsoft's config package wires up the correct prod repo AND its current
            # signing key for the running Ubuntu release; a hand-rolled repo + the
            # generic microsoft.asc misses that key (NO_PUBKEY on the prod suite).
            deb = (
                "https://packages.microsoft.com/config/ubuntu/"
                f"{ctx.os.version_id}/packages-microsoft-prod.deb"
            )
            ctx.ex.run(
                ["sh", "-c", f"curl -fsSL -o /tmp/packages-microsoft-prod.deb {deb}"]
            )
            ctx.ex.run(["dpkg", "-i", "/tmp/packages-microsoft-prod.deb"], sudo=True)
            ctx.ex.run(
                ["apt-get", "update"],
                sudo=True,
                env={"DEBIAN_FRONTEND": "noninteractive"},
            )
            pkg.install(ctx, "dotnet-sdk-10.0")
        else:
            pkg.install(ctx, "dotnet-sdk-10.0")


@register
class Aspire(Module):
    name = "aspire"
    category = "dotnet"
    description = "Aspire CLI (dotnet global tool)."
    requires = (DotnetSdk,)
    profiles = ("dotnet",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("aspire")

    def install(self, ctx: Ctx) -> None:
        ctx.ex.run(["dotnet", "tool", "install", "-g", "Aspire.Cli"])


@register
class DotnetLsp(Module):
    name = "dotnet-lsp"
    category = "dotnet"
    description = "csharp-ls + csharpier (dotnet global tools)."
    requires = (Fresh, DotnetSdk)
    profiles = ("dotnet",)

    def verify(self, ctx: Ctx) -> bool:
        return (_home() / ".dotnet" / "tools" / "csharp-ls").exists()

    def install(self, ctx: Ctx) -> None:
        ctx.ex.run(["dotnet", "tool", "install", "-g", "csharp-ls"])
        ctx.ex.run(["dotnet", "tool", "install", "-g", "csharpier"])


# --- data --------------------------------------------------------------------------------


@register
class DataServices(Module):
    name = "data-services"
    category = "data"
    description = "Containerized data services (postgres/valkey/dbgate) compose template."
    requires = (Docker,)
    profiles = ("data",)

    def _compose(self) -> Path:
        return resource_path("templates", "data", "compose.yaml")

    def verify(self, ctx: Ctx) -> bool:
        c = self._compose()
        if not c.exists():
            return False
        text = c.read_text(encoding="utf-8")
        return all(m in text for m in ("postgres:18", "valkey/valkey", "dbgate/dbgate"))

    def install(self, ctx: Ctx) -> None:
        # The compose template ships in-repo (bundled); nothing to fetch.
        return


# --- devops ------------------------------------------------------------------------------


@register
class DevopsTools(Module):
    name = "devops-tools"
    category = "devops"
    description = "OpenTofu/kubectl/helm/k9s via mise."
    requires = (Mise,)
    profiles = ("devops",)
    _SPECS = (
        "aqua:opentofu/opentofu@1.11.6",
        "aqua:kubernetes/kubectl@1.35.2",
        "aqua:helm/helm@4.1.4",
        "aqua:derailed/k9s@0.51.0",
    )

    def verify(self, ctx: Ctx) -> bool:
        return all(ctx.ex.which(c) for c in ("tofu", "kubectl", "helm", "k9s"))

    def install(self, ctx: Ctx) -> None:
        ctx.ex.run(["mise", "use", "-g", *self._SPECS])


@register
class DevopsLsp(LspModule):
    name = "devops-lsp"
    description = "tofu-ls for Terraform/OpenTofu (fresh)."
    requires = (Fresh, Mise, DevopsTools)
    profiles = ("devops",)
    servers_file = "devops-lsp.tsv"


# --- react-native ------------------------------------------------------------------------


@register
class AndroidSdk(Module):
    name = "android-sdk"
    category = "react-native"
    description = "Android SDK (cmdline-tools + platform/build-tools) + JDK via mise."
    requires = (Mise,)
    profiles = ("react-native",)
    _CMDLINE_VERSION = "13114758"

    def _home_sdk(self) -> Path:
        return Path(os.environ.get("ANDROID_HOME", str(_home() / "Android" / "Sdk")))

    def verify(self, ctx: Ctx) -> bool:
        return (self._home_sdk() / "platform-tools" / "adb").exists()

    def install(self, ctx: Ctx) -> None:
        mise.use_global(ctx, "java@temurin-17")
        if ctx.os.family == "debian":
            # libfuse2 is required by the Android Emulator on Ubuntu (FUSE2 compat layer).
            pkg.install(ctx, "libfuse2")
        sdk = self._home_sdk()
        tools = sdk / "cmdline-tools" / "latest"
        if not (tools / "bin" / "sdkmanager").exists():
            url = (
                "https://dl.google.com/android/repository/"
                f"commandlinetools-linux-{self._CMDLINE_VERSION}_latest.zip"
            )
            zip_path = sdk / "cmdline-tools.zip"
            sdk.mkdir(parents=True, exist_ok=True)
            ctx.ex.run(["curl", "-fsSL", "-o", str(zip_path), url])
            ctx.ex.run(["unzip", "-q", "-o", str(zip_path), "-d", str(sdk / "cmdline-tools")])
            # The zip extracts to cmdline-tools/cmdline-tools/ (nested); rename to
            # cmdline-tools/latest/ so sdkmanager is found at the expected path.
            extracted = sdk / "cmdline-tools" / "cmdline-tools"
            if extracted.is_dir() and not tools.exists():
                extracted.rename(tools)
        sm = str(tools / "bin" / "sdkmanager")
        ctx.ex.run(
            ["sh", "-c", f"yes | {sm} --sdk_root={sdk} 'platform-tools' "
             "'platforms;android-35' 'build-tools;35.0.0'"]
        )
        # Persist ANDROID_HOME so shells pick it up after reboot.
        profile_d = Path("/etc/profile.d")
        android_sh = profile_d / "devboost-android.sh"
        content = (
            f"# written by devboost android-sdk\n"
            f"export ANDROID_HOME=\"{sdk}\"\n"
            f"export PATH=\"$PATH:$ANDROID_HOME/cmdline-tools/latest/bin"
            f":$ANDROID_HOME/platform-tools\"\n"
        )
        ctx.ex.run(["tee", str(android_sh)], sudo=True, stdin=content)


@register
class Expo(Module):
    name = "expo"
    category = "react-native"
    description = "React Native / Expo project template (npx-only; no global expo-cli)."
    requires = (WebRuntimes,)
    profiles = ("react-native",)

    def verify(self, ctx: Ctx) -> bool:
        return resource_path("templates", "react-native", "README.md").exists()

    def install(self, ctx: Ctx) -> None:
        # The template ships in-repo (bundled); projects use `npx create-expo-app`.
        return
