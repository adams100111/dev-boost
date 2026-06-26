"""dev-hygiene verbs: dev status / gc / down (orphaned dev-container cleanup)."""

from __future__ import annotations

from devboost.model import Ctx

_LABEL = "devboost"


def status(ctx: Ctx) -> str:
    return ctx.ex.run(
        ["docker", "ps", "-a", "--filter", f"label={_LABEL}", "--format",
         "{{.Names}}\t{{.Status}}"]
    ).stdout


def _ids(ctx: Ctx, *filters: str) -> list[str]:
    args = ["docker", "ps", "-aq", "--filter", f"label={_LABEL}"]
    for f in filters:
        args += ["--filter", f]
    out = ctx.ex.run(args).stdout
    return [ln for ln in out.splitlines() if ln.strip()]


def gc(ctx: Ctx) -> int:
    """Remove orphaned dev containers (label devboost, not marked persistent). Returns count."""
    ids = _ids(ctx, "label=persistent=false")
    for cid in ids:
        ctx.ex.run(["docker", "rm", "-f", cid])
    return len(ids)


def down(ctx: Ctx) -> int:
    """Stop all dev containers. Returns count."""
    ids = _ids(ctx)
    for cid in ids:
        ctx.ex.run(["docker", "stop", cid])
    return len(ids)
