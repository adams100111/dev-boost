"""ssh-setup — generate an ed25519 key and register it with GitHub (non-blocking)."""

from __future__ import annotations

import os
import socket
from pathlib import Path

from devboost.core import log
from devboost.core.errors import GithubError
from devboost.core.registry import register
from devboost.exec.primitives import github
from devboost.model import Ctx, Module
from devboost.modules import _credentials as creds_src
from devboost.modules.secrets import Secrets, home

_BEGIN = "# BEGIN devboost-managed"
_END = "# END devboost-managed"
_BLOCK = (
    f"{_BEGIN}\n"
    "Host *\n"
    "  IdentityFile ~/.ssh/id_ed25519\n"
    "  IdentitiesOnly yes\n"
    "  AddKeysToAgent yes\n"
    "  HashKnownHosts yes\n"
    f"{_END}"
)


#: The host every dev-boost install clones from, and the one a fresh machine has never
#: seen. Without its key in known_hosts, `git clone git@github.com:…` fails with "Host key
#: verification failed" — which reads like a credentials problem and is not one.
_GITHUB_HOST = "github.com"


def _known_hosts() -> Path:
    return home() / ".ssh" / "known_hosts"


def github_known(text: str) -> bool:
    """Whether *text* already carries a github.com entry (hashed entries included)."""
    return any(
        line.strip() and not line.lstrip().startswith("#") and _GITHUB_HOST in line
        for line in text.splitlines()
    )


def seed_github_host_keys(ctx: Ctx) -> None:
    """Add GitHub's published SSH host keys to known_hosts, once.

    Best-effort: with no network the install carries on and the next run retries. An
    existing github.com entry is never touched — a pinned or hashed entry the user already
    trusts stays exactly as it is.
    """
    path = _known_hosts()
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if github_known(existing):
        return
    keys = github.host_keys()
    if not keys:
        log.warn("ssh-setup: could not fetch GitHub's host keys — SSH clones may prompt; "
                 "the next run retries")
        return
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    body = "".join(f"{_GITHUB_HOST} {k}\n" for k in keys)
    with path.open("a", encoding="utf-8") as fh:
        if existing and not existing.endswith("\n"):
            fh.write("\n")
        fh.write(body)
    path.chmod(0o600)
    log.ok(f"ssh-setup: trusted {len(keys)} GitHub host key(s)")


def _state_marker() -> Path:
    state = os.environ.get("XDG_STATE_HOME") or str(home() / ".local" / "state")
    return Path(state) / "devboost" / "ssh-key-registered"


def _ensure_block(text: str) -> str:
    if _BEGIN not in text:
        return (text + "\n" if text and not text.endswith("\n") else text) + _BLOCK + "\n"
    out: list[str] = []
    skipping = False
    for line in text.splitlines():
        if line.strip() == _BEGIN:
            out.extend(_BLOCK.splitlines())
            skipping = True
            continue
        if skipping:
            if line.strip() == _END:
                skipping = False
            continue
        out.append(line)
    return "\n".join(out) + "\n"


@register
class SshSetup(Module):
    name = "ssh-setup"
    category = "base"
    description = "Generate ed25519 key and register it with GitHub (non-blocking)."
    requires = (Secrets,)
    profiles = ("base",)
    # ssh-keygen ships with macOS; the upload is a urllib call and the token comes from
    # _credentials.github_credentials — nothing Linux-only on this path.
    portable = True

    def verify(self, ctx: Ctx) -> bool:
        # Deliberately NOT including the known_hosts entry: seeding it needs a network
        # fetch, so a machine that cannot reach api.github.com would verify as broken for
        # something that is hygiene, not a broken install. install() seeds it and is
        # idempotent, so a re-run repairs a machine that predates this.
        return (home() / ".ssh" / "id_ed25519.pub").exists() and _state_marker().exists()

    def install(self, ctx: Ctx) -> None:
        ssh = home() / ".ssh"
        ssh.mkdir(mode=0o700, parents=True, exist_ok=True)
        key = ssh / "id_ed25519"
        title = f"devboost:{socket.gethostname()}"
        if not key.exists():
            ctx.ex.run(
                ["ssh-keygen", "-t", "ed25519", "-N", "", "-C", title, "-f", str(key)]
            )

        # Before anything that clones: a fresh machine has never seen github.com.
        seed_github_host_keys(ctx)

        cfg = ssh / "config"
        cfg.write_text(
            _ensure_block(cfg.read_text(encoding="utf-8") if cfg.exists() else ""),
            encoding="utf-8",
        )

        pub = ssh / "id_ed25519.pub"
        if not pub.exists():
            return  # keygen deferred to a real run; nothing to upload yet
        data = creds_src.github_credentials(ctx)
        if data is None:
            log.warn(
                "ssh-setup: no GitHub credentials found (bundle, gh, git credentials) "
                "— key not uploaded yet"
            )
            return  # non-blocking; retried next run
        try:
            ok = github.upload_ssh_key(data["GITHUB_PAT"], pub.read_text(encoding="utf-8"), title)
        except GithubError:
            log.warn("ssh-setup: GitHub key upload failed — will retry on next run")
            return  # non-blocking
        if ok:
            marker = _state_marker()
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.touch()
