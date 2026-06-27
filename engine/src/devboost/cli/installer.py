"""The `devboost installer` command: flags or wizard -> build/update a bootable Ventoy drive.

NOTE (frozen binary): the Ventoy injection archive (devboost-<arch>.tar.gz) must be present
*alongside* the frozen binary — it is NOT bundled inside the binary.  Build it first via
``scripts/build-bundle.sh``; the frozen ``installer`` command locates it next to sys.executable.

Download cache is **opt-in**: by default downloads go to a temporary directory that is
deleted after the build.  Pass ``--cache-dir`` to persist across runs.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Annotated

import questionary
import typer

from devboost.core import log, osinfo
from devboost.core.errors import MediaError
from devboost.exec.executor import RealExecutor
from devboost.media import wizard
from devboost.media.builder import build
from devboost.media.cache import Cache
from devboost.media.catalog import autoinstall_for, default_iso, iso_for
from devboost.media.config import MediaConfig
from devboost.media.download import UrllibDownloader
from devboost.media.preview import render_plan
from devboost.media.probe import DiskState, probe
from devboost.media.report import RichReporter
from devboost.model import Ctx


def _iso_note(cfg: MediaConfig) -> str:
    """Best-effort combined ISO download size note (for the plan preview; never raises).

    This must NOT fire real network requests or create a cache dir in --dry-run mode.
    Callers in dry-run must pass ``cfg.cache_dir`` pointing to an existing dir (e.g. a
    tmpdir) or call ``_iso_note`` only when not in dry-run.
    """
    specs = [cfg.iso] + ([cfg.autoinstall_iso] if cfg.autoinstall_iso is not None else [])
    try:
        if not cfg.cache_dir.exists():
            return "unknown"
        import urllib.request

        cache = Cache(cfg.cache_dir)
        total = 0
        all_cached = True
        for spec in specs:
            if cache.has(f"{spec.id}.iso", spec.sha256):
                continue
            all_cached = False
            req = urllib.request.Request(spec.url, method="HEAD")
            with urllib.request.urlopen(req) as resp:
                total += int(resp.headers.get("Content-Length", 0) or 0)
        if all_cached:
            return "cached"
        return f"≈{total / 1e9:.1f} GB" if total else "unknown"
    except OSError:
        return "unknown"


def _summary_text(cfg: MediaConfig) -> str:
    verb = "Updated" if cfg.mode == "update" else "Built"
    extras: list[str] = []
    if cfg.offline_mirror:
        extras.append("offline-mirror: yes")
    if cfg.extra_isos:
        extras.append(f"+{len(cfg.extra_isos)} extra ISO")
    tail = (" · " + " · ".join(extras)) if extras else ""
    media = "Workstation Live" + (
        " + netinst (zero-touch)" if cfg.autoinstall_iso is not None else ""
    )
    head = (
        f"✅ {verb} {cfg.device} — {cfg.iso.id} ({cfg.arch}) · media: {media} · "
        f"profiles: {' '.join(cfg.profiles)}{tail}"
    )
    if cfg.mode == "update":
        body = (
            "ISOs/secrets preserved. Reboot the target; "
            "the firstboot service re-runs your profiles."
        )
    else:
        body = (
            "Boot it: insert the USB → firmware boot menu → pick the USB → Fedora installs "
            "(auto/zero-touch or manual) → on first boot dev-boost installs your profiles. "
            'Bad update later? Reboot → GRUB "Fedora snapshots".'
        )
    return head + "\n" + body


def installer(
    device: Annotated[
        str | None, typer.Option(help="Target removable disk, e.g. /dev/sdb")
    ] = None,
    arch: Annotated[str, typer.Option(help="x86_64 | aarch64")] = "",
    iso: Annotated[str, typer.Option(help="Catalog ISO id (default: fedora-44)")] = "",
    profile: Annotated[list[str], typer.Option(help="Profiles for firstboot (repeatable)")] = [],
    secrets: Annotated[Path | None, typer.Option(help="Path to secrets.age")] = None,
    secrets_key: Annotated[
        Path | None, typer.Option(help="Path to age-key.txt (staged alongside secrets.age)")
    ] = None,
    cache_dir: Annotated[
        Path | None,
        typer.Option(
            help=(
                "Persistent download cache directory. "
                "Omit to use an ephemeral temp dir (deleted after build)."
            )
        ),
    ] = None,
    cache_ttl_days: Annotated[
        int | None,
        typer.Option(help="Evict cached files older than N days (only with --cache-dir)"),
    ] = None,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Skip the wipe-confirmation prompt")
    ] = False,
    no_wizard: Annotated[
        bool, typer.Option("--no-wizard", help="Fail instead of prompting")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Resolve + print the plan; touch nothing")
    ] = False,
    refresh_iso: Annotated[
        bool, typer.Option("--refresh-iso", help="On update, also re-download the pinned ISO")
    ] = False,
    rebuild: Annotated[
        bool, typer.Option("--rebuild", help="Wipe & rebuild even an existing dev-boost USB")
    ] = False,
) -> None:
    """Build (or non-destructively update) a bootable dev-boost Ventoy drive."""
    if device is None and no_wizard:
        log.error("--device is required with --no-wizard")
        raise typer.Exit(code=1)

    state: DiskState | None = None
    if device is None:
        ctx = Ctx(os=osinfo.detect(), ex=RealExecutor())
        cfg = wizard.run(ctx)
    else:
        os_info = osinfo.detect()
        ctx = Ctx(os=os_info, ex=RealExecutor())
        resolved_arch = arch or os_info.arch
        state = probe(ctx, device)

        if state.kind == "devboost" and not rebuild:
            mode, assume_yes = "update", True  # detected dev-boost stick → non-destructive update
        else:
            mode, assume_yes = "build", yes
            if not assume_yes and not dry_run:
                ok = questionary.confirm(
                    f"WIPE {device}? All data on it is destroyed.", default=False
                ).ask()
                if not (ok or False):
                    log.error("aborted")
                    raise typer.Exit(code=1)
                assume_yes = True

        try:
            os_id = iso or default_iso().id
            cfg = MediaConfig(
                device=device,
                arch=resolved_arch,
                iso=iso_for(os_id, resolved_arch),
                autoinstall_iso=autoinstall_for(os_id, resolved_arch),
                profiles=tuple(profile) or ("full",),
                secrets_path=secrets,
                secrets_key_path=secrets_key,
                # cache_dir is filled below (after dry-run check)
                cache_dir=cache_dir or Path(tempfile.gettempdir()) / "devboost-usb-tmp",
                cache_ttl_days=cache_ttl_days,
                mode=mode,  # type: ignore[arg-type]  # narrowed from str to Literal above
                refresh_iso=refresh_iso,
                assume_yes=assume_yes,
            )
        except MediaError as exc:
            log.error(str(exc))
            raise typer.Exit(code=1) from exc

    if dry_run:
        # Truly inert: no network, no cache dir creation.
        if state is None:
            state = probe(ctx, cfg.device)
        typer.echo(render_plan(cfg, state, download_note="(dry-run — not fetched)"))
        raise typer.Exit()

    reporter = RichReporter()

    # Cache is opt-in.  When --cache-dir is supplied, use it persistently (and evict stale
    # files if --cache-ttl-days is set).  Otherwise allocate an ephemeral tmpdir and clean
    # it up after the build regardless of success or failure.
    if cache_dir is not None:
        actual_cache_dir: Path = cache_dir
        persistent_cache = True
    else:
        actual_cache_dir = Path(tempfile.mkdtemp(prefix="devboost-usb-"))
        persistent_cache = False

    # Update cfg with the resolved cache dir so stages can construct Cache objects from it.
    cfg = cfg.model_copy(update={"cache_dir": actual_cache_dir})

    try:
        cache = Cache(actual_cache_dir, ttl_days=cache_ttl_days)
        if persistent_cache:
            cache.evict_stale()
        build(ctx, cfg, UrllibDownloader(cache, reporter), cache, reporter=reporter)
    finally:
        if not persistent_cache:
            shutil.rmtree(actual_cache_dir, ignore_errors=True)

    reporter.summary(_summary_text(cfg))
