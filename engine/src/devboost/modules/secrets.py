"""secrets — decrypt the provisioned bundle, configure git identity + HTTPS credentials."""

from __future__ import annotations

import os
from pathlib import Path

from devboost.core import log
from devboost.core.errors import SecretsError
from devboost.core.registry import register
from devboost.exec.primitives import age, pkg
from devboost.model import Ctx, Module
from devboost.modules import _credentials as creds_src


def home() -> Path:
    return Path(os.environ["HOME"])


def _bootstrap_root() -> Path:
    """Resolve the directory containing secrets.age and age-key.txt.

    Priority:
      1. DEVBOOST_BOOTSTRAP_DIR env var (set by the firstboot service / kickstart %post)
      2. /opt/dev-boost (CONTRACT: kickstart %post copies the bundle here)

    Never falls back to the current working directory — a missing bundle produces a
    clear SecretsError rather than a confusing "file not found: ./secrets.age".
    """
    val = os.environ.get("DEVBOOST_BOOTSTRAP_DIR")
    if val:
        return Path(val)
    return Path("/opt/dev-boost")


def bundle_path() -> Path:
    override = os.environ.get("DEVBOOST_SECRETS")
    return Path(override) if override else _bootstrap_root() / "secrets.age"


def key_path() -> Path:
    override = os.environ.get("DEVBOOST_SECRETS_KEY")
    return Path(override) if override else _bootstrap_root() / "age-key.txt"


@register
class Secrets(Module):
    name = "secrets"
    category = "base"
    description = "Decrypt provisioned secrets; configure git identity + HTTPS credentials."
    profiles = ("base",)

    def verify(self, ctx: Ctx) -> bool:
        if not ctx.ex.run(["git", "config", "--global", "user.email"]).ok:
            return False
        creds = home() / ".git-credentials"
        if creds.exists() and "@github.com" in creds.read_text(encoding="utf-8"):
            return True
        # An authenticated gh is an equally good (better, actually — no plaintext token on
        # disk) source of GitHub credentials, and `gh auth setup-git` wires git to use it.
        # Requiring the .git-credentials line specifically would report a correctly
        # configured box as unconfigured, and reinstall over it on every run.
        return creds_src.gh_is_authenticated(ctx)

    def _resolve(self, ctx: Ctx) -> dict[str, str]:
        """Get credentials from the bundle, else fall back (see modules/_credentials)."""
        if bundle_path().exists():
            if not ctx.ex.which("age"):
                pkg.install(ctx, "age")
            data = age.decrypt(ctx, bundle_path(), key_path())
            for field in age.REQUIRED_FIELDS:
                if not data.get(field):
                    raise SecretsError(f"missing required field {field}")
            return data

        # No bundle. See whether an already-authenticated gh can supply them.
        from_gh = creds_src.from_gh(ctx) if creds_src.gh_is_authenticated(ctx) else None

        if creds_src.is_interactive():
            # Offer it — including the account name — rather than adopting an identity the
            # operator never chose for this machine. "skip" is respected, not overridden.
            chosen = creds_src.resolve_interactively(ctx, existing=from_gh)
            if chosen:
                return chosen
        elif from_gh:
            # Unattended: nobody to confirm with, and using it beats failing outright.
            log.ok(f"secrets: using the authenticated GitHub CLI ({from_gh['GIT_USER']})")
            return from_gh

        raise SecretsError(creds_src.NO_CREDENTIALS_HELP)

    def install(self, ctx: Ctx) -> None:
        data = self._resolve(ctx)

        ctx.ex.run(["git", "config", "--global", "user.name", data["GIT_USER"]])
        ctx.ex.run(["git", "config", "--global", "user.email", data["GIT_EMAIL"]])
        ctx.ex.run(["git", "config", "--global", "credential.helper", "store"])

        creds = home() / ".git-credentials"
        line = f"https://{data['GIT_USER']}:{data['GITHUB_PAT']}@github.com"
        # (Written for every source: downstream modules — ssh-setup, obsidian-sync — talk
        # to the REST API with this token, and `git clone` over HTTPS needs it too. When
        # gh supplied it, `gh auth setup-git` is also configured, and gh's helper wins.)
        kept = [
            ln
            for ln in (creds.read_text(encoding="utf-8").splitlines() if creds.exists() else [])
            if not ln.endswith("@github.com")
        ]
        creds.write_text("\n".join([*kept, line]) + "\n", encoding="utf-8")
        creds.chmod(0o600)
