"""shell — the explicit, greppable escape hatch for the rare irreducible shell one-liner."""

from __future__ import annotations

from devboost.exec.executor import Result
from devboost.model import Ctx


def run(ctx: Ctx, script: str) -> Result:
    """Run a `sh -c` one-liner. Use ONLY where a piped/heredoc upstream installer demands it."""
    return ctx.ex.run(["sh", "-c", script])
