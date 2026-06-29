"""Install a managed user's bootstrap_profiles as that user, via DemotingExecutor."""

from __future__ import annotations

import os
from pathlib import Path

from devboost.accounts.config import ManagedUser
from devboost.accounts.reconcile import home_of
from devboost.core.graph import toposort
from devboost.core.plan import build_plan
from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load, validate_profiles
from devboost.core.runner import run_plan
from devboost.exec.executor import DemotingExecutor
from devboost.model import Ctx


def _run_profiles(ctx: Ctx, tokens: list[str], root: Path) -> None:
    modules = load()
    profiles = load_profiles(root / "profiles.toml")
    validate_profiles(modules, set(profiles))
    order = toposort(expand(tokens, profiles, modules), modules)
    plan = build_plan(order, modules, ctx.os)
    run_plan(plan, modules, ctx)


def bootstrap_user(ctx: Ctx, user: ManagedUser, *, root: Path) -> None:
    """Install user.bootstrap_profiles for *user*: root for privileged, user for the rest."""
    os.environ["HOME"] = home_of(user)  # modules compute ~paths from $HOME
    demoted = Ctx(
        os=ctx.os,
        ex=DemotingExecutor(ctx.ex, user.name),
        force=ctx.force,
        dry_run=ctx.dry_run,
    )
    _run_profiles(demoted, list(user.bootstrap_profiles), root)
