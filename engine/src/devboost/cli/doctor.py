"""`doctor` — environment preflight in Python (replaces install.sh's dep-ensure).

Subsystem checks (secrets state, mise drift, --gpu) are stubbed here and filled in by
their milestones (M1 secrets, M9 gpu).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from devboost.exec.primitives import age
from devboost.model import Ctx
from devboost.modules.secrets import bundle_path, key_path

# Binaries that must be present on the host before the engine can run.
# Note: jq is NOT used by the Python engine; curl is required (chezmoi, uv, nerd-fonts,
# android tools, claude-code bootstrap all fetch over HTTPS).
_REQUIRED_DEPS = ("curl", "age")

# Minimum free disk space required (in bytes).  A full workstation install uses ~5 GB.
_MIN_FREE_BYTES = 5 * 1024 ** 3  # 5 GiB

# URL used for the network reachability probe (lightweight HEAD request).
_PROBE_URL = "https://fedoraproject.org/"


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

    # Disk space: use shutil.disk_usage on "/" (pure stdlib, no subprocess needed).
    try:
        free = shutil.disk_usage("/").free
        checks.append(
            Check(
                "disk-space",
                free >= _MIN_FREE_BYTES,
                f"{free // (1024 ** 3)} GiB free (need ≥5 GiB)",
            )
        )
    except OSError as exc:
        checks.append(Check("disk-space", False, str(exc)))

    # Network reachability: a cheap curl --head call (timeout 5 s).
    net_result = ctx.ex.run([
        "curl", "--head", "--silent", "--connect-timeout", "5",
        "-o", "/dev/null", "-w", "%{http_code}", _PROBE_URL,
    ])
    checks.append(
        Check(
            "network",
            net_result.ok,
            f"HEAD {_PROBE_URL} → exit {net_result.code}",
        )
    )

    # secrets state: 'missing' is a warning (ok), but a present-yet-broken bundle fails.
    state = age.doctor_state(ctx, bundle_path(), key_path())
    checks.append(Check("secrets", state in ("ok", "missing"), state))
    return checks


def all_ok(checks: list[Check]) -> bool:
    return all(c.ok for c in checks)
