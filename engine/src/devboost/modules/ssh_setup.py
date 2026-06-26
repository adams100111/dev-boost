"""ssh-setup — generate an ed25519 key and register it with GitHub (non-blocking)."""

from __future__ import annotations

import os
import socket
from pathlib import Path

from devboost.core import log
from devboost.core.errors import GithubError
from devboost.core.registry import register
from devboost.exec.primitives import age, github
from devboost.model import Ctx, Module
from devboost.modules.secrets import Secrets, bundle_path, home, key_path

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

    def verify(self, ctx: Ctx) -> bool:
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

        cfg = ssh / "config"
        cfg.write_text(
            _ensure_block(cfg.read_text(encoding="utf-8") if cfg.exists() else ""),
            encoding="utf-8",
        )

        pub = ssh / "id_ed25519.pub"
        if not pub.exists():
            return  # keygen deferred to a real run; nothing to upload yet
        data = age.decrypt(ctx, bundle_path(), key_path())
        try:
            ok = github.upload_ssh_key(data["GITHUB_PAT"], pub.read_text(encoding="utf-8"), title)
        except GithubError:
            log.warn("ssh-setup: GitHub key upload failed — will retry on next run")
            return  # non-blocking
        if ok:
            marker = _state_marker()
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.touch()
