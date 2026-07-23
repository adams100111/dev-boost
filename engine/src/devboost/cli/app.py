"""The devboost Typer CLI: install / verify / list / term / devtools."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Literal

import typer

from devboost import __version__
from devboost.cli import accounts as _accounts
from devboost.cli import devhygiene as dh
from devboost.cli import lifecycle as lc
from devboost.cli.doctor import all_ok, run_checks
from devboost.cli.installer import installer as _installer
from devboost.cli.selection import select_modules
from devboost.core import log, osinfo
from devboost.core.graph import toposort
from devboost.core.plan import PlannedModule, build_plan
from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load, validate_profiles
from devboost.core.runner import RunResult, run_plan
from devboost.core.settings import settings
from devboost.exec.executor import RealExecutor
from devboost.exec.primitives import pkg
from devboost.model import Ctx, Module

app = typer.Typer(help="dev-boost — typed workstation installer", no_args_is_help=True)

ProfilesArg = Annotated[list[str], typer.Argument(help="profiles/modules (default: full)")]
RootOpt = Annotated[Path, typer.Option(help="repo root with profiles.toml + modules")]
DryOpt = Annotated[bool, typer.Option("--dry-run", help="preview without executing")]
ForceOpt = Annotated[bool, typer.Option("--force", help="reinstall even if verify passes")]
AllOpt = Annotated[
    bool,
    typer.Option(
        "--all/--no-all",
        "-a",
        help="install all apps in the tier (default); --no-all opens an interactive picker",
    ),
]
AppOpt = Annotated[
    list[str],
    typer.Option("--app", help="install only this app (repeatable)"),
]


def _resolve(
    tokens: list[str], root: Path
) -> tuple[dict[str, type[Module]], list[str]]:
    modules = load()
    profiles = load_profiles(root / "profiles.toml")
    validate_profiles(modules, set(profiles))
    expanded = expand(tokens or ["full"], profiles, modules)
    return modules, expanded


def _order(tokens: list[str], root: Path) -> tuple[list[str], dict[str, type[Module]]]:
    modules, expanded = _resolve(tokens, root)
    return toposort(expanded, modules), modules


def _offline_installable(cls: type[Module]) -> bool:
    """True if a module installs from packages alone, with no network of its own.

    dnf/flatpak modules can be satisfied by a local repo or an already-populated cache;
    everything else (mise, npm, GitHub releases, curl|sh installers) reaches out itself.
    """
    from devboost.modules._pkgmodule import PackageModule
    from devboost.modules.apps import FlatpakApp

    return issubclass(cls, (PackageModule, FlatpakApp))


def _apply_offline_filter(
    plan: list[PlannedModule],
    modules: Mapping[str, type[Module]],
) -> list[PlannedModule]:
    """Replace network-only modules with a needs-network skip; leave already-skipped ones alone."""
    return [
        pm
        if pm.skip_reason is not None or _offline_installable(modules[pm.name])
        else PlannedModule(name=pm.name, skip_reason="needs-network")
        for pm in plan
    ]


def _run(
    tokens: list[str],
    root: Path,
    dry_run: bool,
    force: bool,
    offline: bool = False,
    *,
    all_: bool = True,
    apps: list[str] | None = None,
) -> list[RunResult]:
    modules, expanded = _resolve(tokens, root)
    selected = select_modules(expanded, modules, all_=all_, apps=apps or [])
    order = toposort(selected, modules)
    extra = [n for n in order if n not in selected]
    if extra:
        log.info(f"+{len(extra)} required dependencies added: {', '.join(extra)}")
    ctx = Ctx(os=osinfo.detect(), ex=RealExecutor(), force=force, dry_run=dry_run)
    plan = build_plan(order, modules, ctx.os)
    if offline:
        plan = _apply_offline_filter(plan, modules)
    elif not dry_run:
        # Refresh the package index once up front so installs don't fail against a stale
        # index on a fresh box (no network access happens in offline/dry-run modes).
        pkg.refresh_index(ctx)
    results = run_plan(plan, modules, ctx)
    if any(r.status == "fail" for r in results):
        raise typer.Exit(code=1)
    return results


def _version(value: bool | None) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


def _maybe_warn_update() -> None:
    """Print a one-line update hint to stderr if a newer release is cached. Never raises."""
    from devboost.core import selfupdate

    new = selfupdate.update_available()
    if new:
        typer.echo(
            f"dev-boost {new} is available (you have {__version__})"
            " — run: devboost self-update",
            err=True,
        )


@app.callback()
def main_callback(
    ctx: typer.Context,
    version: Annotated[
        bool | None, typer.Option("--version", callback=_version, is_eager=True)
    ] = None,
) -> None:
    """dev-boost CLI root."""
    if ctx.invoked_subcommand not in (None, "self-update"):
        _maybe_warn_update()


@app.command()
def install(
    profiles: ProfilesArg = [],
    root: RootOpt = settings.root,
    dry_run: DryOpt = False,
    force: ForceOpt = False,
    offline: Annotated[
        bool, typer.Option("--offline", help="skip modules that need network")
    ] = False,
    all_: AllOpt = True,
    app: AppOpt = [],
) -> None:
    """Install one or more profiles/modules (default: full)."""
    _run(profiles, root, dry_run, force, offline, all_=all_, apps=app)


@app.command()
def brain(
    root: RootOpt = settings.root,
    ram: Annotated[str, typer.Option("--ram", help="devbrain RAM cap")] = "8G",
    cpu: Annotated[str, typer.Option("--cpu", help="devbrain CPU cap")] = "200%",
    disk: Annotated[str, typer.Option("--disk", help="devbrain disk quota")] = "50G",
    tasks: Annotated[int, typer.Option("--tasks", help="devbrain max processes")] = 4096,
    ssh_key: Annotated[
        list[str], typer.Option("--ssh-key", help="authorized key for devbrain (repeatable)")
    ] = [],  # noqa: B006
    dry_run: DryOpt = False,
    force: ForceOpt = False,
    apply_: Annotated[bool, typer.Option("--apply/--no-apply")] = True,
) -> None:
    """Provision the sandboxed brain: install brain-host tools + the capped devbrain account."""
    from devboost.accounts import bootstrap as bs
    from devboost.accounts import reconcile
    from devboost.accounts.config import load_users
    from devboost.cli.brain import default_ssh_keys, devbrain_user

    # 1) host-level brain tools (sudo): mosh, caddy, crossarch-build.
    _run(["brain-host"], root, dry_run, force)

    # 2) the capped, sudo-less devbrain account (bootstraps brain-tools into its home).
    keys = tuple(ssh_key) or default_ssh_keys()
    if not keys:
        log.warn(
            "brain: no --ssh-key given and no ~/.ssh/*.pub found — add an authorized key "
            "before you can `mosh devbrain@this-host`"
        )
    user = devbrain_user(ssh_keys=keys, ram=ram, cpu=cpu, disk=disk, tasks=tasks)
    ctx = Ctx(os=osinfo.detect(), ex=RealExecutor(), force=force, dry_run=dry_run)
    users = load_users()
    users["devbrain"] = user
    reconcile.save(ctx, users)
    if apply_ and not dry_run:
        reconcile.apply_user(
            ctx, user, bootstrap=lambda c, u: bs.bootstrap_user(c, u, root=root)
        )
    log.info(
        "review devbrain caps for this box (ram/cpu/disk/tasks) — production headroom "
        "matters: devboost accounts edit devbrain"
    )


@app.command(name="list")
def list_(profiles: ProfilesArg = [], root: RootOpt = settings.root) -> None:
    """Print the resolved install order."""
    order, _ = _order(profiles, root)
    for name in order:
        typer.echo(name)


@app.command()
def verify(profiles: ProfilesArg = [], root: RootOpt = settings.root) -> None:
    """Report which modules are installed."""
    order, modules = _order(profiles, root)
    ctx = Ctx(os=osinfo.detect(), ex=RealExecutor())
    failed = False
    for name in order:
        if modules[name]().verify(ctx):
            log.ok(f"{name}: installed")
        else:
            log.error(f"{name}: missing")
            failed = True
    if failed:
        raise typer.Exit(code=1)


@app.command()
def doctor(
    root: RootOpt = settings.root,
    gpu: Annotated[bool, typer.Option("--gpu", help="NVIDIA-stack diagnostics")] = False,
) -> None:
    """Environment preflight."""
    if gpu:
        from devboost.exec.primitives import gpu as gpu_prim

        gpus = gpu_prim.detect(_ctx())
        vendors = [n for n, on in
                   (("intel", gpus.intel), ("amd", gpus.amd), ("nvidia", gpus.nvidia)) if on]
        log.ok(f"doctor --gpu: detected {', '.join(vendors) or 'no recognized GPU'}")
        if gpus.nvidia:
            ctx = _ctx()
            for chk, ok in (("akmod-nvidia", ctx.ex.run(["rpm", "-q", "akmod-nvidia"]).ok),
                            ("nvidia-ctk", ctx.ex.which("nvidia-ctk"))):
                (log.ok if ok else log.warn)(f"  {chk}: {'present' if ok else 'missing'}")
        return
    ctx = Ctx(os=osinfo.detect(), ex=RealExecutor())
    checks = run_checks(ctx, root)
    for c in checks:
        (log.ok if c.ok else log.error)(f"{c.name}: {c.detail or ('ok' if c.ok else 'missing')}")
    if not all_ok(checks):
        raise typer.Exit(code=1)


@app.command(name="term")
def term(
    root: RootOpt = settings.root,
    dry_run: DryOpt = False,
    force: ForceOpt = False,
    all_: AllOpt = True,
    app: AppOpt = [],
) -> None:
    """Install the terminal tier (--no-all to pick interactively, --app NAME for one)."""
    _run(["terminal"], root, dry_run, force, all_=all_, apps=app)


@app.command()
def devtools(
    root: RootOpt = settings.root,
    dry_run: DryOpt = False,
    force: ForceOpt = False,
    all_: AllOpt = True,
    app: AppOpt = [],
) -> None:
    """Install the devtools tier."""
    _run(["devtools"], root, dry_run, force, all_=all_, apps=app)


@app.command()
def server(
    root: RootOpt = settings.root,
    dry_run: DryOpt = False,
    force: ForceOpt = False,
    all_: AllOpt = True,
    app: AppOpt = [],
) -> None:
    """Install the server tier (headless-VPS hardening + ops; Ubuntu/Debian)."""
    _run(["server"], root, dry_run, force, all_=all_, apps=app)


def _ctx() -> Ctx:
    return Ctx(os=osinfo.detect(), ex=RealExecutor())


@app.command()
def add(name: str, root: RootOpt = settings.root) -> None:
    """Scaffold a new typed module file."""
    path = lc.scaffold_module(root / "engine" / "src" / "devboost" / "modules", name)
    log.ok(f"created {path}")


@app.command()
def export(root: RootOpt = settings.root) -> None:
    """Snapshot the actual installed state."""
    out = lc.export_snapshot(_ctx(), root / "workstation-config" / "exports")
    typer.echo(str(out))


@app.command()
def diff(profiles: ProfilesArg = [], root: RootOpt = settings.root) -> None:
    """Report declared-vs-actual drift (exit != 0 on drift)."""
    drift = lc.diff_drift(_ctx(), profiles, root)
    for name in drift:
        log.warn(f"drift: {name} not installed")
    if drift:
        raise typer.Exit(code=1)


@app.command()
def update(root: RootOpt = settings.root) -> None:
    """Regenerate the deterministic devboost.lock (no commit)."""
    log.ok(f"wrote {lc.write_lock(root)}")


@app.command(name="self-update")
def self_update(
    root: RootOpt = settings.root,
    check: Annotated[
        bool, typer.Option("--check", help="print current vs latest without installing")
    ] = False,
) -> None:
    """Update dev-boost to the latest release (or git-pull from source)."""
    from devboost.core import selfupdate

    if check:
        latest = selfupdate.latest_version()
        if latest is None:
            typer.echo("could not determine latest version (offline?)", err=True)
            raise typer.Exit(code=1)
        if selfupdate.version_tuple(latest) > selfupdate.version_tuple(__version__):
            typer.echo(f"update available: {__version__} → {latest}")
        else:
            typer.echo(f"up to date: {__version__}")
        return

    if selfupdate.is_frozen():
        latest = selfupdate.latest_version()
        if latest == __version__:
            typer.echo(f"already on the latest version ({__version__})")
            return
        try:
            old, new = selfupdate.update_frozen()
        except RuntimeError as exc:
            typer.echo(f"self-update failed: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(f"updated {old} → {new}")
    else:
        if not lc.self_update(_ctx(), root):
            raise typer.Exit(code=1)


@app.command()
def dev(action: Annotated[str, typer.Argument(help="status | gc | down")]) -> None:
    """Dev-environment resource hygiene."""
    valid: tuple[Literal["status", "gc", "down"], ...] = ("status", "gc", "down")
    if action not in valid:
        log.error("usage: devboost dev <status|gc|down>")
        raise typer.Exit(code=1)
    ctx = _ctx()
    if action == "status":
        typer.echo(dh.status(ctx))
    elif action == "gc":
        log.ok(f"gc: removed {dh.gc(ctx)} orphaned container(s)")
    else:
        log.ok(f"down: stopped {dh.down(ctx)} container(s)")


app.command(name="installer")(_installer)
app.add_typer(_accounts.app, name="accounts")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
