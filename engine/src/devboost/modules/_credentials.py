"""Where git/GitHub credentials come from when there is no provisioned bundle.

The age bundle exists for the **zero-touch** path: a Ventoy USB install has nobody at the
keyboard, so `GIT_USER`/`GIT_EMAIL`/`GITHUB_PAT` are pre-provisioned once, encrypted, and
decrypted during firstboot. That is the right design *for that path*.

It is the wrong demand to make of somebody who installed the OS themselves and ran
`devboost install` by hand — there is no USB, no `/opt/dev-boost`, and no reason to build
an encrypted bundle just to tell dev-boost an email address. Before this, that person got
a hard `SecretsError` and three blocked modules.

So credentials resolve in order of decreasing automation:

1. **The age bundle**, if provisioned — unchanged, and still first, so zero-touch installs
   behave exactly as before and never reach any of the steps below.
2. **An already-authenticated `gh`** — most developers ran `gh auth login` long ago.
   At a terminal this is *offered as the default choice*, not assumed: the session on this
   machine may be a different account than the one this box should commit as, and adopting
   it silently would write the wrong name and email into every commit. With nobody to ask
   (an unattended run) it is used directly, since the alternative is failing outright.
3. **An interactive choice** — only when a real terminal is attached: use the signed-in
   account, sign in as someone else, type the details in, or skip.
4. Otherwise a `SecretsError` that names these options instead of just reporting a
   missing file.

Step 4 is what keeps unattended installs honest: nothing here ever blocks waiting for
input that nobody is there to give.
"""

from __future__ import annotations

import json
import os
import sys

from devboost.core import log
from devboost.model import Ctx

#: What `secrets` needs to configure git + the GitHub API paths that follow it.
Credentials = dict[str, str]


def is_interactive() -> bool:
    """True only when a human can actually answer a prompt.

    `DEVBOOST_NONINTERACTIVE=1` forces this off — useful for CI and for reproducing an
    unattended run on a workstation.
    """
    if os.environ.get("DEVBOOST_NONINTERACTIVE"):
        return False
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (AttributeError, ValueError):  # detached/closed streams
        return False


# --- 2. an already-authenticated gh ------------------------------------------------------


def gh_is_authenticated(ctx: Ctx) -> bool:
    return ctx.ex.which("gh") and ctx.ex.run(["gh", "auth", "status"]).ok


def _gh_api_user(ctx: Ctx) -> dict[str, str]:
    res = ctx.ex.run(["gh", "api", "user"])
    if not res.ok:
        return {}
    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError:
        return {}
    return {str(k): str(v) for k, v in data.items() if v is not None}


def _gh_email(ctx: Ctx, user: dict[str, str]) -> str:
    """Best public email, else the account's primary, else git's configured email."""
    if user.get("email"):
        return user["email"]
    res = ctx.ex.run(["gh", "api", "user/emails"])
    if res.ok:
        try:
            for row in json.loads(res.stdout):
                if row.get("primary") and row.get("email"):
                    return str(row["email"])
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
    configured = ctx.ex.run(["git", "config", "--global", "user.email"])
    return configured.stdout.strip() if configured.ok else ""


def from_gh(ctx: Ctx) -> Credentials | None:
    """Derive credentials from an authenticated `gh`, or None if unusable."""
    user = _gh_api_user(ctx)
    login = user.get("login")
    if not login:
        return None
    token = ctx.ex.run(["gh", "auth", "token"])
    if not token.ok or not token.stdout.strip():
        return None
    email = _gh_email(ctx, user)
    if not email:
        return None
    return {
        "GIT_USER": login,
        "GIT_EMAIL": email,
        "GITHUB_PAT": token.stdout.strip(),
    }


# --- 3. the interactive path -------------------------------------------------------------

def menu_for(signed_in_as: str | None) -> list[tuple[str, str]]:
    """(key, label) rows, with the already-signed-in account offered first when there is one.

    An authenticated `gh` is *offered*, never assumed. The session on this machine may well
    be a different account than the one this box should commit as — adopting it silently
    would write the wrong name and email into every commit, and be invisible until someone
    noticed the git log.
    """
    rows: list[tuple[str, str]] = []
    if signed_in_as:
        rows.append(("use-gh", f"Use the signed-in GitHub account ({signed_in_as})"))
        rows.append(("gh", "Sign in as a different GitHub account"))
    else:
        rows.append(("gh", "Sign in with GitHub CLI (recommended — no token to copy or store)"))
    rows.append(("manual", "Enter name, email and a personal access token myself"))
    rows.append(("skip", "Skip — configure git credentials later"))
    return rows


def _ask_choice(signed_in_as: str | None) -> str:
    """Ask how to proceed. Not unit-tested (needs a TTY), mirroring cli/selection.py."""
    import questionary

    prompt = (
        f"GitHub CLI is already signed in as {signed_in_as}. How should dev-boost set up "
        "git + GitHub?"
        if signed_in_as
        else "No provisioned secrets bundle found. How should dev-boost set up git + GitHub?"
    )
    answer = questionary.select(
        prompt,
        choices=[
            questionary.Choice(title=label, value=key)
            for key, label in menu_for(signed_in_as)
        ],
    ).ask()
    return str(answer) if answer else "skip"


def _ask_manual() -> Credentials | None:
    import questionary

    user = questionary.text("GitHub username:").ask()
    email = questionary.text("Git email:").ask()
    # `password` masks the input — a PAT should never be echoed into scrollback.
    token = questionary.password("GitHub personal access token:").ask()
    if not (user and email and token):
        return None
    return {"GIT_USER": str(user), "GIT_EMAIL": str(email), "GITHUB_PAT": str(token)}


def _run_gh_login(ctx: Ctx) -> Credentials | None:
    """Install gh if needed, hand it the terminal, then read back what it knows."""
    from devboost.exec.primitives import pkg

    if not ctx.ex.which("gh"):
        log.info("gh is not installed yet — installing it first")
        pkg.install(ctx, "github-cli" if ctx.os.family == "arch" else "gh")
    # `gh auth login` runs its own TUI and opens a browser: it needs the real terminal,
    # so this is one of the few calls that must not have its output captured.
    if not ctx.ex.run(["gh", "auth", "login"], interactive=True).ok:
        log.warn("gh auth login did not complete")
        return None
    # Point git at gh for HTTPS pushes, so no token is written to disk in plaintext.
    ctx.ex.run(["gh", "auth", "setup-git"])
    return from_gh(ctx)


def resolve_interactively(ctx: Ctx, existing: Credentials | None = None) -> Credentials | None:
    """Ask the operator. *existing* is what an already-signed-in gh offers, if anything."""
    choice = _ask_choice(existing["GIT_USER"] if existing else None)
    if choice == "use-gh":
        return existing
    if choice == "gh":
        return _run_gh_login(ctx)
    if choice == "manual":
        return _ask_manual()
    return None  # "skip" — the caller reports it; we never fall back to gh behind their back


# --- the message shown when nothing is available and nobody can be asked ------------------

NO_CREDENTIALS_HELP = (
    "no secrets bundle, and no authenticated GitHub CLI to fall back on.\n"
    "  Pick whichever fits:\n"
    "    • gh auth login                    then re-run — dev-boost picks it up automatically\n"
    "    • scripts/make-secrets.sh --out DIR then DEVBOOST_BOOTSTRAP_DIR=DIR devboost install\n"
    "    • run devboost install from a terminal to be walked through it\n"
    "  Only ssh-setup, chezmoi-repo and obsidian-sync need this; everything else installs."
)
