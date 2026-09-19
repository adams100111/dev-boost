"""`devboost secrets` — manage bootstrap-secret material on this machine."""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Annotated

import typer

from devboost.core import log, osinfo
from devboost.exec.executor import RealExecutor
from devboost.modules.secrets import KEYCHAIN_ACCOUNT, KEYCHAIN_SERVICE

app = typer.Typer(help="bootstrap secrets (age key)", no_args_is_help=True)


def _secret_key_line(path: Path) -> str:
    """The single `AGE-SECRET-KEY-…` line of an age identity file.

    `age-keygen -o` writes `# created:` / `# public key:` comment lines above the key, so
    comments and blank lines are skipped; zero or several keys is refused.
    """
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    content = [ln for ln in lines if ln and not ln.startswith("#")]
    keys = [ln for ln in content if ln.startswith("AGE-SECRET-KEY-")]
    if len(keys) != 1:
        raise typer.BadParameter(
            f"{path} must contain exactly one AGE-SECRET-KEY- line (found {len(keys)})"
        )
    return keys[0]


@app.command("import-key")
def import_key(
    path: Annotated[
        Path,
        typer.Argument(
            exists=True,
            dir_okay=False,
            readable=True,
            help="age identity file (AGE-SECRET-KEY-…), e.g. from age-keygen -o",
        ),
    ],
) -> None:
    """Store an age key in the macOS login keychain (then the file can be deleted)."""
    if osinfo.detect().family != "macos":
        raise typer.BadParameter("import-key is macOS-only; on Linux keep the key file")
    key = _secret_key_line(path)
    # `security -i` reads the command from stdin, so the key never appears in argv / ps.
    cmd = (
        f"add-generic-password -U -a {KEYCHAIN_ACCOUNT} -s {KEYCHAIN_SERVICE} "
        f"-w {shlex.quote(key)}\n"
    )
    if not RealExecutor().run(["security", "-i"], stdin=cmd).ok:
        log.error("could not write the key to the keychain")
        raise typer.Exit(code=1)
    log.ok(f"age key stored in the login keychain ({KEYCHAIN_SERVICE}); you may delete {path}")
