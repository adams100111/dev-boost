"""secrets — decrypt the provisioned bundle, configure git identity + HTTPS credentials."""

from __future__ import annotations

import os
from pathlib import Path

from devboost.core.errors import SecretsError
from devboost.core.registry import register
from devboost.exec.primitives import age, pkg
from devboost.model import Ctx, Module


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
        creds = home() / ".git-credentials"
        email_set = ctx.ex.run(["git", "config", "--global", "user.email"]).ok
        return email_set and creds.exists() and "@github.com" in creds.read_text(encoding="utf-8")

    def install(self, ctx: Ctx) -> None:
        if not ctx.ex.which("age"):
            pkg.install(ctx, "age")
        data = age.decrypt(ctx, bundle_path(), key_path())
        for field in age.REQUIRED_FIELDS:
            if not data.get(field):
                raise SecretsError(f"missing required field {field}")

        ctx.ex.run(["git", "config", "--global", "user.name", data["GIT_USER"]])
        ctx.ex.run(["git", "config", "--global", "user.email", data["GIT_EMAIL"]])
        ctx.ex.run(["git", "config", "--global", "credential.helper", "store"])

        creds = home() / ".git-credentials"
        line = f"https://{data['GIT_USER']}:{data['GITHUB_PAT']}@github.com"
        kept = [
            ln
            for ln in (creds.read_text(encoding="utf-8").splitlines() if creds.exists() else [])
            if not ln.endswith("@github.com")
        ]
        creds.write_text("\n".join([*kept, line]) + "\n", encoding="utf-8")
        creds.chmod(0o600)
