"""The `pass` sub-app: the shared store across devices (status, approve, revoke, sync…)."""

from __future__ import annotations

from typing import Annotated, NoReturn

import typer
from rich.console import Console
from rich.table import Table

from devboost.core import log, osinfo
from devboost.core.errors import DevbootError, NeedsUser
from devboost.exec.executor import RealExecutor
from devboost.model import Ctx
from devboost.modules import _credentials as creds_src
from devboost.passstore import approve as approve_flow
from devboost.passstore import audit as audit_flow
from devboost.passstore import enroll as enroll_flow
from devboost.passstore import paths
from devboost.passstore import sync as sync_flow
from devboost.passstore.layout import DeviceRecord, Kind, Store

app = typer.Typer(
    help="The shared pass store: devices, enrollment, approval, revocation, sync.",
    no_args_is_help=True,
)

ScopeOpt = Annotated[
    list[str],
    typer.Option("--scope", help="limit access to this store folder (repeatable; servers)"),
]


def _ctx() -> Ctx:
    return Ctx(os=osinfo.detect(), ex=RealExecutor())


def _store() -> Store:
    return Store(paths.store_dir())


def _fail(exc: Exception) -> NoReturn:
    log.error(str(exc))
    raise typer.Exit(1) from exc


def _need_store(store: Store) -> None:
    if not store.is_clone():
        log.error(f"no pass store at {store.root} — run: devboost install pass-store")
        raise typer.Exit(1)


def _describe(rec: DeviceRecord) -> str:
    scope = ", ".join(rec.scope) if rec.scope else "whole store (workstation)"
    return (f"  name:        {rec.name}\n  os:          {rec.os}\n"
            f"  fingerprint: {rec.fingerprint}\n"
            f"  requested:   {rec.requested_at or rec.enrolled_at or '-'}\n  scope:       {scope}")


def _ask(verb: str) -> approve_flow.Confirm:
    def confirm(rec: DeviceRecord) -> bool:
        typer.echo(f"{verb} this device?\n{_describe(rec)}")
        answer = str(typer.prompt("Type y to confirm", default="n", show_default=False))
        return answer.strip().lower() == "y"

    return confirm


@app.command()
def status() -> None:
    """This device's enrollment, pending requests, rotation backlog and last sync."""
    ctx, store = _ctx(), _store()
    _need_store(store)
    try:  # gather everything first: a bad config or store file exits cleanly, not midway
        device = paths.device_name()
        repo = paths.pass_repo()
        acc = enroll_flow.local_access(ctx, store, device)
        todo = approve_flow.unrotated(ctx, store)
        report = audit_flow.audit(ctx, store)
    except DevbootError as exc:
        _fail(exc)
    name = acc.record.name if acc.record else device
    typer.echo(f"repo:      {repo}")
    typer.echo(f"store:     {store.root}")
    typer.echo(f"device:    {name} ({acc.state})")
    typer.echo(f"key:       {acc.key.fingerprint if acc.key else '-'}")
    typer.echo(f"pending:   {len(store.records('pending'))}")
    typer.echo(f"rotation:  {len(todo)} entries to rotate")
    typer.echo(f"recipients: {len(report.mismatches)} entries differ from their .gpg-id")
    typer.echo(f"last sync: {sync_flow.last_sync() or 'never'}")


@app.command()
def devices() -> None:
    """Enrolled devices and pending requests."""
    store = _store()
    _need_store(store)
    table = Table("name", "state", "os", "fingerprint", "scope", "since")
    rows: tuple[tuple[Kind, str], ...] = (("devices", "enrolled"), ("pending", "pending"))
    for kind, label in rows:
        for r in store.records(kind):
            table.add_row(r.name, label, r.os, r.fingerprint,
                          ", ".join(r.scope) if r.scope else "-",
                          r.enrolled_at or r.requested_at or "-")
    Console(width=200).print(table)


@app.command(name="approve")
def approve_cmd(
    name: Annotated[str | None, typer.Argument(help="pending device (default: each)")] = None,
    scope: ScopeOpt = [],  # noqa: B006
) -> None:
    """Grant a pending device access (typed confirmation; re-encrypts the store)."""
    ctx, store = _ctx(), _store()
    _need_store(store)
    try:
        done = approve_flow.approve(ctx, store, paths.device_name(), name, _ask("Approve"),
                                    scope_override=scope or None)
    except DevbootError as exc:
        _fail(exc)
    if not done:
        typer.echo("nothing approved")
        return
    for a in done:
        typer.echo(f"approved {a.name} — it gets access on its next sync")


@app.command(name="revoke")
def revoke_cmd(name: Annotated[str, typer.Argument(help="enrolled device to revoke")]) -> None:
    """Remove a device's access and print what must now be rotated."""
    ctx, store = _ctx(), _store()
    _need_store(store)
    try:
        entry = approve_flow.revoke(ctx, store, paths.device_name(), name, _ask("REVOKE"))
    except DevbootError as exc:
        _fail(exc)
    if entry is None:
        typer.echo("revoke cancelled")
        return
    typer.echo(f"revoked {name}. Git history still holds ciphertexts its key can read — "
               f"rotate these {len(entry.entries)} entries (pass edit <entry>):")
    for e in entry.entries:
        typer.echo(f"  [ ] {e}")
    typer.echo("`devboost doctor` tracks what is left.")


@app.command(name="sync")
def sync_cmd(
    resolve: Annotated[
        bool, typer.Option("--resolve", help="explain how to fix a conflict")
    ] = False,
    push_only: Annotated[bool, typer.Option("--push-only", hidden=True)] = False,
    quiet: Annotated[bool, typer.Option("--quiet", help="print only problems")] = False,
) -> None:
    """Pull + push the store now (the timer does this every 15 min)."""
    ctx, store = _ctx(), _store()
    if resolve:
        _need_store(store)
        typer.echo(sync_flow.resolve_guidance(ctx, store))
        return
    try:
        device = paths.device_name()
    except DevbootError as exc:
        _fail(exc)
    res = sync_flow.run(ctx, store, device, push_only=push_only)
    problem = res.status in ("conflict", "pull-failed", "push-failed", "no-store")
    if problem or not quiet:
        typer.echo(f"pass sync: {res.status}" + (f" — {res.detail}" if res.detail else ""))
    if problem:
        raise typer.Exit(1)


@app.command(name="enroll")
def enroll_cmd(
    name: Annotated[str | None, typer.Option("--name", help="device name (default: host)")] = None,
    scope: ScopeOpt = [],  # noqa: B006
) -> None:
    """Request access for this device (generates its key; passphrase via pinentry)."""
    ctx, store = _ctx(), _store()
    try:
        device = paths.sanitize_name(name) if name else paths.device_name()
        enroll_flow.ensure_clone(ctx, store, paths.pass_repo())
        acc = enroll_flow.ensure_access(ctx, store, device, interactive=creds_src.is_interactive(),
                                        scope=scope or None)
    except NeedsUser as exc:
        typer.echo(f"{exc.reason}\nnext: {exc.how_to_fix}")
        return
    except DevbootError as exc:
        _fail(exc)
    typer.echo(f"this device is enrolled as {acc.record.name if acc.record else device}")


@app.command(name="audit")
def audit_cmd() -> None:
    """Entries not encrypted to exactly their .gpg-id keys (read from packets; no decrypt)."""
    ctx, store = _ctx(), _store()
    _need_store(store)
    try:
        report = audit_flow.audit(ctx, store)
    except DevbootError as exc:
        _fail(exc)
    for folder in report.unauditable:
        typer.echo(f"not checked: {folder}/.gpg-id names keys by email")
    if not report.mismatches:
        typer.echo("every entry matches its .gpg-id")
        return
    for m in report.mismatches:
        typer.echo(f"{m.entry}\n  extra:   {', '.join(m.extra) or '-'}\n"
                   f"  missing: {', '.join(m.missing) or '-'}\n"
                   f"  fix:     {audit_flow.fix_hint(store, m)}")
    raise typer.Exit(1)
