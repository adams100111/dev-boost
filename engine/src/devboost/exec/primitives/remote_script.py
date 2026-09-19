"""Run an upstream installer script: download it into a private temp dir, then run it.

Download-then-run (never `curl | sh`) makes a failed download fail loudly instead of
piping nothing into the shell. The `mktemp -d` dir is made through the executor (0700; a
demoting executor makes it the target user's), so nothing lands at a guessable /tmp path.
"""

from __future__ import annotations

from collections.abc import Mapping

from devboost.core.errors import InstallError
from devboost.model import Ctx

_DOWNLOAD = ("curl", "-fsSL", "--proto", "=https", "--tlsv1.2", "-o")


def run_script(
    ctx: Ctx,
    who: str,
    url: str,
    interpreter: str,
    *args: str,
    env: Mapping[str, str] | None = None,
) -> None:
    """Download *url* and run it as ``<interpreter> <script> <args…>`` (with *env*)."""
    mk = ctx.ex.run(["mktemp", "-d"])
    tmp = mk.stdout.strip()
    if not mk.ok or not tmp.startswith("/"):
        raise InstallError(who, "mktemp -d", mk.code or 1)
    script = f"{tmp}/install.sh"
    try:
        for argv in ([*_DOWNLOAD, script, url], [interpreter, script, *args]):
            res = ctx.ex.run(argv, env=env)
            if not res.ok:
                raise InstallError(who, " ".join(argv), res.code)
    finally:
        ctx.ex.run(["rm", "-rf", tmp])
