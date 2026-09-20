"""secrets — configure git identity + GitHub access.

Credentials come from the provisioned age bundle, an authenticated `gh`, or an
interactive prompt — see modules/_credentials.py and docs/credentials.md.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from devboost.core import log
from devboost.core.errors import InstallError, NeedsUser, SecretsError
from devboost.core.registry import register
from devboost.exec.primitives import age, pkg
from devboost.model import Ctx, Module
from devboost.modules import _credentials as creds_src
from devboost.modules.macos import Homebrew


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


#: Where `devboost secrets import-key` keeps the age identity in the macOS login keychain.
KEYCHAIN_SERVICE = "devboost-age"
KEYCHAIN_ACCOUNT = "devboost"


@contextmanager
def age_key(ctx: Ctx) -> Iterator[Path | None]:
    """The age identity file to decrypt with, wherever it lives.

    A key file (env override or bootstrap dir) wins; off macOS the configured path is
    always returned. On macOS the key may instead live in the login keychain
    (`devboost secrets import-key`); it is then materialized as a 0600 temp file only for
    the duration of the decrypt, and None means "no key anywhere".
    """
    explicit = key_path()
    if explicit.exists() or ctx.os.family != "macos":
        # Off macOS this is exactly the old behaviour: the configured path, and `age`
        # itself reports a missing key.
        yield explicit
        return
    res = ctx.ex.run([
        "security", "find-generic-password",
        "-a", KEYCHAIN_ACCOUNT, "-s", KEYCHAIN_SERVICE, "-w",
    ])
    if not res.ok or not res.stdout.strip():
        yield None
        return
    # mkstemp creates the file 0600 already; the fchmod makes that explicit, not assumed.
    fd, name = tempfile.mkstemp(prefix="devboost-age-")
    path = Path(name)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, (res.stdout.strip() + "\n").encode("utf-8"))
        os.close(fd)
        fd = -1
        yield path
    finally:
        if fd >= 0:
            os.close(fd)
        path.unlink(missing_ok=True)


@register
class Secrets(Module):
    name = "secrets"
    category = "base"
    description = "Configure git identity + GitHub access (age bundle, gh, or prompt)."
    profiles = ("base",)
    # macOS: pkg.install dispatches to brew for `age`, the age key may come from the
    # keychain, and the token goes to osxkeychain / gh — never ~/.git-credentials.
    portable = True
    requires = (Homebrew,)  # macOS installs `age` via brew when the bundle needs it

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
        if creds_src.gh_is_authenticated(ctx):
            return True
        # macOS never writes ~/.git-credentials: a bundle/manual token lives in the login
        # keychain behind git's osxkeychain helper instead. The helper being configured
        # proves nothing (the keychain entry may be missing) — ask it for the token.
        if ctx.os.family == "macos":
            return creds_src._from_git_credential_fill(ctx) is not None
        return False

    def _resolve(self, ctx: Ctx) -> tuple[dict[str, str], str]:
        """Credentials plus their source: "bundle", "gh" or "manual".

        Bundle first, else fall back (see modules/_credentials).
        """
        if bundle_path().exists():
            if not ctx.ex.which("age"):
                pkg.install(ctx, "age")
            with age_key(ctx) as key:
                if key is None:
                    raise SecretsError(
                        "secrets bundle present but no age key (file, env, or keychain)"
                    )
                data = age.decrypt(ctx, bundle_path(), key)
            for field in age.REQUIRED_FIELDS:
                if not data.get(field):
                    raise SecretsError(f"missing required field {field}")
            return data, "bundle"

        # No bundle. See whether an already-authenticated gh can supply them.
        from_gh: dict[str, str] | None = None
        gh_problem = creds_src.NO_GH
        if creds_src.gh_is_authenticated(ctx):
            from_gh, gh_problem = creds_src.from_gh_or_reason(ctx)

        if creds_src.is_interactive():
            # Offer it — including the account name — rather than adopting an identity the
            # operator never chose for this machine. "skip" is respected, not overridden.
            chosen = creds_src.resolve_interactively(ctx, existing=from_gh)
            if chosen:
                # "use-gh" returns the gh dict itself; "gh" signs in fresh via gh too.
                if chosen is from_gh:
                    return chosen, "gh"
                gh_token = (
                    ctx.ex.run(["gh", "auth", "token"]).stdout.strip()
                    if ctx.ex.which("gh")
                    else ""
                )
                came_from_gh = bool(gh_token) and chosen["GITHUB_PAT"] == gh_token
                return chosen, "gh" if came_from_gh else "manual"
        elif from_gh:
            # Unattended: nobody to confirm with, and using it beats failing outright.
            log.ok(f"secrets: using the authenticated GitHub CLI ({from_gh['GIT_USER']})")
            return from_gh, "gh"

        # Nobody can have credentials on a brand-new machine: that is a step for the user,
        # reported as blocked with the exact fix, not a failure of the run.
        raise NeedsUser(
            f"no secrets bundle, and {gh_problem}",
            creds_src.no_credentials_fix(),
        )

    def install(self, ctx: Ctx) -> None:
        data, source = self._resolve(ctx)

        ctx.ex.run(["git", "config", "--global", "user.name", data["GIT_USER"]])
        ctx.ex.run(["git", "config", "--global", "user.email", data["GIT_EMAIL"]])
        if ctx.os.family == "macos":
            self._install_macos(ctx, data, source)
            return
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

    def _install_macos(self, ctx: Ctx, data: dict[str, str], source: str) -> None:
        """No plaintext token on disk: gh's helper, or the macOS keychain.

        Downstream modules (ssh-setup, obsidian-sync) get their token from
        `_credentials.github_credentials` — bundle, then gh — not from a file.
        """
        if source == "gh":
            ctx.ex.run(["gh", "auth", "setup-git"])
            return
        ctx.ex.run(["git", "config", "--global", "credential.helper", "osxkeychain"])
        # The token goes to the helper on stdin — never argv, never a file — so the
        # error below (argv only) cannot leak it.
        res = ctx.ex.run(
            ["git", "credential", "approve"],
            stdin=(
                "protocol=https\nhost=github.com\n"
                f"username={data['GIT_USER']}\npassword={data['GITHUB_PAT']}\n\n"
            ),
        )
        if not res.ok:
            raise InstallError(self.name, "git credential approve", res.code)
