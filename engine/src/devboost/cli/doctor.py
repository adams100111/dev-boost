"""`doctor` — environment preflight in Python (replaces install.sh's dep-ensure).

Subsystem checks (secrets state, mise drift, --gpu) are stubbed here and filled in by
their milestones (M1 secrets, M9 gpu).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from devboost.exec.primitives import age
from devboost.model import Ctx
from devboost.modules.secrets import bundle_path, key_path

_REQUIRED_DEPS = ("jq", "age")


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""


def run_checks(ctx: Ctx, root: Path) -> list[Check]:
    checks: list[Check] = [
        Check("os", ctx.os.distro != "unknown", f"{ctx.os.distro}/{ctx.os.family} {ctx.os.arch}"),
        Check("profiles", (root / "profiles.toml").exists(), str(root / "profiles.toml")),
    ]
    for dep in _REQUIRED_DEPS:
        checks.append(Check(f"dep:{dep}", ctx.ex.which(dep)))
    # secrets state: 'missing' is a warning (ok), but a present-yet-broken bundle fails.
    state = age.doctor_state(ctx, bundle_path(), key_path())
    checks.append(Check("secrets", state in ("ok", "missing"), state))
    return checks


def all_ok(checks: list[Check]) -> bool:
    return all(c.ok for c in checks)
