"""The shipped ks.cfg must actually parse — as Fedora's own installer parses it.

This exists because it did not. Every btrfs subvolume line carried `--fsoptions`, which the
btrfs command has never accepted (it takes --mkfsoptions; --fsoptions belongs to part/logvol).
Anaconda 44.30 refused the file outright:

    Unexpected arguments to btrfs command: ['/', 'fedora', '--fsoptions=compress=zstd:1']
    The installer will now terminate.

Nothing caught it: pytest, mypy and ruff all stop at the Python boundary, and the kickstart is
only read by Anaconda — on a real machine, after the disk is already wiped. So parse it here,
with the same library Anaconda uses.
"""

from __future__ import annotations

from pathlib import Path

import pytest

KS = Path(__file__).resolve().parents[3] / "ventoy" / "ks.cfg"


def _parse() -> object:
    """Parse ks.cfg with the F44 handler, as the installer does.

    followIncludes=False: `%include /tmp/diskdetect.ks` is written at run time by %pre and
    cannot exist at parse time.
    """
    pykickstart = pytest.importorskip("pykickstart")
    from pykickstart.parser import KickstartParser
    from pykickstart.version import makeVersion

    assert pykickstart  # silence the unused name; importorskip is the real gate
    parser = KickstartParser(makeVersion("F44"), followIncludes=False)
    parser.readKickstart(str(KS))
    return parser


def test_kickstart_parses_under_fedora_44() -> None:
    """The whole file, through pykickstart's F44 handler. Any bad command fails here."""
    assert _parse() is not None


def test_btrfs_lines_use_no_invalid_fsoptions() -> None:
    """Guard the specific mistake, so the message stays legible if it ever returns.

    `btrfs` accepts: --noformat --useexisting --label --data --metadata --subvol --parent
    --name --mkfsoptions. It does NOT accept --fsoptions.
    """
    offenders = [
        line
        for line in KS.read_text(encoding="utf-8").splitlines()
        if line.startswith("btrfs") and "--fsoptions" in line
    ]
    assert offenders == []


# --- the %post fstab rewrite: compression moved here because `btrfs` cannot express it ------

_FSTAB_AWK = r"""
    $1 !~ /^#/ && NF >= 4 && $3 == "btrfs" && $4 !~ /compress=/ { $4 = $4 ",compress=zstd:1" }
    { print }
"""

_FSTAB = """# /etc/fstab
UUID=aaaa /                       btrfs   subvol=root,x-systemd.device-timeout=0 0 0
UUID=aaaa /home                   btrfs   subvol=home 0 0
UUID=aaaa /var/log                btrfs   subvol=var-log,compress=zstd:1 0 0
UUID=bbbb /boot/efi               vfat    umask=0077,shortname=winnt 0 2
tmpfs     /dev/shm                tmpfs   defaults 0 0
"""


def _rewrite(fstab: str, tmp_path: Path) -> str:
    """Run the exact awk from ks.cfg's %post against *fstab*."""
    import shutil
    import subprocess

    awk = shutil.which("awk")
    if awk is None:  # pragma: no cover - awk is present on any host that can build media
        pytest.skip("awk not available")
    src = tmp_path / "fstab"
    src.write_text(fstab, encoding="utf-8")
    out = subprocess.run(
        [awk, "-v", "OFS=\t", _FSTAB_AWK, str(src)],
        capture_output=True, text=True, check=True,
    )
    return out.stdout


def test_post_fstab_compresses_every_btrfs_mount(tmp_path: Path) -> None:
    out = _rewrite(_FSTAB, tmp_path)
    btrfs = [ln for ln in out.splitlines() if "\tbtrfs\t" in ln or " btrfs " in ln]
    assert len(btrfs) == 3
    assert all("compress=zstd:1" in ln for ln in btrfs)


def test_post_fstab_leaves_non_btrfs_and_existing_compression_alone(tmp_path: Path) -> None:
    """Anaconda may already compress an entry; appending twice would be wrong, and vfat/tmpfs
    must not be touched at all."""
    out = _rewrite(_FSTAB, tmp_path)
    assert "compress=zstd:1,compress=zstd:1" not in out
    assert "umask=0077,shortname=winnt" in out and "compress" not in out.split("vfat")[1]
    assert "tmpfs   defaults 0 0" in out or "tmpfs\tdefaults" in out


def test_post_fstab_rewrite_is_idempotent(tmp_path: Path) -> None:
    """%post can re-run; the second pass must change nothing."""
    once = _rewrite(_FSTAB, tmp_path)
    assert _rewrite(once, tmp_path) == once


# --- the secrets bootstrap contract, guarded across all three copies -----------------------
# secrets.py (runtime) reads DEVBOOST_BOOTSTRAP_DIR (default /opt/dev-boost) + the two secret
# filenames. autoinstall.py's firstboot unit and ks.cfg's %post both bake that path in. Three
# copies that must agree — the exact cross-file shape the `blkid -L VTOY` bug lived in, where
# one copy silently disagreed and secrets never reached the target. Pin them together.

_INSTALL_ROOT = "/opt/dev-boost"
_SECRETS_FILE = "secrets.age"
_KEY_FILE = "age-key.txt"


def test_secrets_runtime_paths_match_the_contract() -> None:
    """secrets.py must resolve to the same root + filenames the installers stage into."""
    import os

    from devboost.modules import secrets

    # Clear any host overrides so we see the baked-in defaults.
    for var in ("DEVBOOST_BOOTSTRAP_DIR", "DEVBOOST_SECRETS", "DEVBOOST_SECRETS_KEY"):
        os.environ.pop(var, None)
    assert str(secrets.bundle_path()) == f"{_INSTALL_ROOT}/{_SECRETS_FILE}"
    assert str(secrets.key_path()) == f"{_INSTALL_ROOT}/{_KEY_FILE}"


def test_firstboot_unit_env_matches_the_runtime_contract() -> None:
    """autoinstall.py's firstboot unit must set exactly the env vars secrets.py reads, at the
    contract paths — otherwise firstboot points the runtime at the wrong place."""
    from devboost.media.autoinstall import _FIRSTBOOT_SVC_LINES

    unit = "\n".join(_FIRSTBOOT_SVC_LINES)
    assert f"Environment=DEVBOOST_BOOTSTRAP_DIR={_INSTALL_ROOT}" in unit
    assert f"Environment=DEVBOOST_SECRETS={_INSTALL_ROOT}/{_SECRETS_FILE}" in unit
    assert f"Environment=DEVBOOST_SECRETS_KEY={_INSTALL_ROOT}/{_KEY_FILE}" in unit
    assert f"ConditionPathExists={_INSTALL_ROOT}/devboost" in unit


def test_kickstart_post_stages_secrets_at_the_contract_path() -> None:
    """ks.cfg's %post must copy the bundle to the SAME /opt/dev-boost the runtime reads from
    (as /mnt/sysimage/opt/dev-boost during install)."""
    code = "\n".join(
        line for line in KS.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )
    target = f"/mnt/sysimage{_INSTALL_ROOT}"
    assert f'DEST={target}' in code or target in code
    # Both secret filenames must be staged by name.
    assert _SECRETS_FILE in code and _KEY_FILE in code


def test_kickstart_partitions_boot_on_both_bios_and_uefi() -> None:
    """A GPT disk needs an ESP (UEFI) AND a biosboot partition (BIOS). Without biosboot,
    Anaconda refuses a BIOS/legacy install — "needs a special partition to boot from a GPT
    disk label ... Kickstart insufficient" — and drops to an interactive prompt that hangs
    the unattended install. Verified against a real Anaconda boot, not just pykickstart."""
    part_lines = [
        ln for ln in KS.read_text(encoding="utf-8").splitlines() if ln.startswith("part ")
    ]
    joined = "\n".join(part_lines)
    assert "--fstype=biosboot" in joined, "no biosboot partition — BIOS install will hang"
    assert "--fstype=efi" in joined, "no ESP — UEFI install cannot boot"
