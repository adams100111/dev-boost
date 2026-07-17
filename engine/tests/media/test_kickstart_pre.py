"""The kickstart's %pre disk detection — executed, not eyeballed.

ks.cfg is bash inside a Kickstart, so mypy/ruff/pytest all stop at its boundary. That gap
shipped a real failure: Fedora's installer runs zram for compressed swap, and /dev/zram0 is
TYPE=disk with RM=0 — indistinguishable from an internal disk by lsblk alone. %pre picked it
and Anaconda terminated with:

    Disk "zram0" given in ignoredisk command does not exist.

It hid because on most machines sda/nvme0n1 happens to sort before zram0. These tests run
the real %pre body from ventoy/ks.cfg against a faked lsblk/blkid and a faked sysfs, so the
ordering is ours to choose.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

_KS = Path(__file__).resolve().parents[3] / "ventoy" / "ks.cfg"


def _pre_body() -> str:
    """The %pre script out of the real ks.cfg — not a copy that can drift from it."""
    text = _KS.read_text(encoding="utf-8")
    m = re.search(r"^%pre\b[^\n]*\n(.*?)^%end$", text, re.S | re.M)
    assert m, "could not find the %pre block in ventoy/ks.cfg"
    return m.group(1)


def _run_pre(
    tmp_path: Path, *, lsblk_out: str, real_disks: list[str], vtoyefi: str = ""
) -> tuple[int, str, str]:
    """Run the %pre body with a faked lsblk/blkid and a faked /sys/block.

    *real_disks* get a `device` symlink, as real hardware has; everything else in lsblk_out
    is treated as a virtual block device (zram, loop, dm-…).
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # `lsblk -pno PKNAME <part>` resolves the parent disk (/dev/sdb2 -> sdb); every other
    # invocation is the plain disk listing the %pre iterates over.
    parent = Path(vtoyefi).name[:-1] if vtoyefi else ""
    (bin_dir / "lsblk").write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        f'  *PKNAME*) echo "{parent}" ;;\n'
        f"  *) cat <<'EOF'\n{lsblk_out.strip()}\nEOF\n  ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    (bin_dir / "blkid").write_text(f'#!/bin/sh\nprintf "%s" "{vtoyefi}"\n', encoding="utf-8")
    for f in bin_dir.iterdir():
        f.chmod(0o755)

    sysblock = tmp_path / "sys" / "block"
    for line in lsblk_out.strip().splitlines():
        name = Path(line.split()[0]).name
        (sysblock / name).mkdir(parents=True, exist_ok=True)
    for d in real_disks:
        (sysblock / d / "device").write_text("fake", encoding="utf-8")

    out = tmp_path / "diskdetect.ks"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "DEVBOOST_SYSBLOCK": str(sysblock),
        "DEVBOOST_KS_OUT": str(out),
    }
    proc = subprocess.run(
        ["sh", "-c", _pre_body()], env=env, capture_output=True, text=True, check=False
    )
    written = out.read_text(encoding="utf-8") if out.exists() else ""
    return proc.returncode, written, proc.stderr


def test_pre_never_targets_zram_even_when_it_enumerates_first(tmp_path: Path) -> None:
    """The reported failure, reproduced: zram0 first in lsblk, both TYPE=disk RM=0."""
    _, written, stderr = _run_pre(
        tmp_path,
        lsblk_out="/dev/zram0 disk 0\n/dev/nvme0n1 disk 0\n",
        real_disks=["nvme0n1"],
    )
    assert "zram0" not in written, f"picked the zram swap device:\n{written}"
    assert "ignoredisk --only-use=nvme0n1" in written
    assert "clearpart --all --initlabel --drives=nvme0n1" in written


def test_pre_skips_every_virtual_block_device(tmp_path: Path) -> None:
    """loop/dm are TYPE=disk too on some hosts; only real hardware may be a target."""
    _, written, _ = _run_pre(
        tmp_path,
        lsblk_out="/dev/loop0 disk 0\n/dev/dm-0 disk 0\n/dev/zram0 disk 0\n/dev/sda disk 0\n",
        real_disks=["sda"],
    )
    assert "ignoredisk --only-use=sda" in written


def test_pre_still_picks_a_plain_internal_disk(tmp_path: Path) -> None:
    """The ordinary case must keep working."""
    _, written, _ = _run_pre(
        tmp_path, lsblk_out="/dev/sda disk 0\n/dev/zram0 disk 0\n", real_disks=["sda"]
    )
    assert "ignoredisk --only-use=sda" in written


def test_pre_never_targets_the_boot_media(tmp_path: Path) -> None:
    """A USB reporting RM=0 (common for USB SSDs and some enclosures) must not be wiped:
    clearpart on the install media destroys the installer mid-run."""
    _, written, stderr = _run_pre(
        tmp_path,
        lsblk_out="/dev/sdb disk 0\n/dev/sda disk 0\n",
        real_disks=["sdb", "sda"],
        vtoyefi="/dev/sdb2",
    )
    assert "sdb" not in written, f"targeted the install media:\n{written}"
    assert "ignoredisk --only-use=sda" in written


def test_pre_refuses_rather_than_guessing_when_no_real_disk_exists(tmp_path: Path) -> None:
    """The old fallback accepted ANY disk, which could be the USB itself. When there is no
    real target, say so — do not guess at something destructive."""
    _, written, stderr = _run_pre(
        tmp_path, lsblk_out="/dev/zram0 disk 0\n", real_disks=[]
    )
    assert "clearpart" not in written
    assert "no usable" in (written + stderr).lower()


def test_kickstart_looks_up_the_label_ventoy_actually_writes() -> None:
    """The kickstart's secrets staging greps for the Ventoy data partition by label.

    It said `blkid -L VTOY`, which matches nothing — Ventoy writes "Ventoy" (VentoyWorker.sh:
    VTNEW_LABEL). Guarded by `if [ -n "$VTOY_DEV" ]`, so --secrets silently never reached the
    target. The same constant was already wrong in probe.py and stages.py; this is the copy
    that a src/-only grep missed. Pin it to the one Python definition so a fourth copy cannot
    quietly disagree.
    """
    from devboost.media.devices import VTOY_DATA_LABEL

    # Comments explain the old wrong label by name, so assert against code lines only.
    code = "\n".join(
        line for line in _KS.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )
    assert f"blkid -L {VTOY_DATA_LABEL}" in code
    # `blkid -L VTOYEFI` is correct and required (%pre uses the ESP to find the boot disk),
    # so match the bad label exactly rather than as a prefix.
    assert re.search(r"blkid -L VTOY(?!EFI)", code) is None
