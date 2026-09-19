"""pi-harness — bootstrap the operator's Pi agent-harness (harness-cli) and delegate config."""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar

from devboost.core import log
from devboost.core.errors import ConfigError
from devboost.core.registry import register
from devboost.exec.primitives import mise
from devboost.model import Ctx, Module
from devboost.modules.mise import Mise
from devboost.modules.pass_store import PassStore
from devboost.modules.secrets import Secrets

DEFAULT_HARNESS_REPO = "adams100111/agent-harness"
DEFAULT_HARNESS_REF = "main"


@register
class PiHarness(Module):
    name = "pi-harness"
    category = "cli"
    description = (
        "Bootstrap the Pi coding-agent harness (clone+build harness-cli; delegate config)."
    )
    requires = (Mise, Secrets)
    after = (PassStore,)
    profiles = ("pi",)
    portable: ClassVar[bool] = True  # git clone (gh helper on macOS) + harness CLI

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("harness")

    def _repo(self) -> str:
        return os.environ.get("DEVBOOST_HARNESS_REPO", DEFAULT_HARNESS_REPO)

    def _ref(self) -> str:
        return os.environ.get("DEVBOOST_HARNESS_REF", DEFAULT_HARNESS_REF)

    def _pass_ready(self, ctx: Ctx) -> bool:
        store = os.environ.get("PASSWORD_STORE_DIR") or str(
            Path(os.environ["HOME"]) / ".password-store"
        )
        return ctx.ex.which("pass") and Path(store).is_dir()

    def install(self, ctx: Ctx) -> None:
        if not ctx.ex.which("node"):
            mise.use_global(ctx, "node@lts")

        # Bootstrap (HARD). Auth = whatever git already uses for GitHub, set up by the
        # `secrets` module: gh's credential helper (`gh auth setup-git`; macOS, gh users) or
        # the bundle token in ~/.git-credentials (Linux). One source:
        # _credentials.github_credentials. Shallow-clone the default branch just to obtain
        # install.sh; it then does the HARNESS_REF-pinned clone itself.
        repo, ref = self._repo(), self._ref()
        url = f"https://github.com/{repo}"
        # install.sh re-clones $HARNESS_REPO@$HARNESS_REF into ~/.local/share/harness itself
        # (our temp checkout is only the source of install.sh's bytes), so BOTH env vars must be
        # passed — and install.sh's HARNESS_REPO is a full URL, not owner/repo.
        script = (
            f"set -e; d=$(mktemp -d); trap 'rm -rf \"$d\"' EXIT; "
            f'git clone --depth 1 {url} "$d/h"; '
            f'HARNESS_REPO={url} HARNESS_REF={ref} bash "$d/h/install.sh"'
        )
        res = ctx.ex.run(["sh", "-c", script])
        if not res.ok:
            raise ConfigError(
                f"pi-harness: bootstrapping agent-harness ({repo}@{ref}) failed "
                f"(exit {res.code}) — check that git can read the private repo: "
                f"`gh auth status` (or the secrets-bundle token) needs access to {repo}"
            )

        # Provision secrets from pass (SOFT) — only when a pass store is present.
        if self._pass_ready(ctx):
            init = ctx.ex.run(["harness", "secrets", "init", "--backend", "pass", "--yes"])
            if not init.ok:
                log.warn("pi-harness: `harness secrets init` failed — provision manually later")
            elif not ctx.ex.run(["harness", "provision"]).ok:
                log.warn("pi-harness: `harness provision` failed — run `harness provision` later")
        else:
            log.warn(
                "pi-harness: no pass store — skipping secret provisioning "
                "(run `harness secrets init` + `harness provision` later)"
            )

        # Reconcile the manifest (SOFT) — never red the full build if the manifest is pre-release
        # or secrets are missing. First Pi session still needs a one-time `pi /login`.
        if not ctx.ex.run(["harness", "install", "--yes"]).ok:
            log.warn(
                "pi-harness: `harness install` incomplete — run `harness doctor` then "
                "`harness install`; first Pi session needs a one-time `pi /login`"
            )
        else:
            log.info("pi-harness: installed; first Pi session needs a one-time `pi /login`")
