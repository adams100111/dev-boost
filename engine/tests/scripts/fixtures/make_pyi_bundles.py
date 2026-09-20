"""Regenerate the tiny PyInstaller onefile fixtures for the glibc floor tests.

Run: cd engine && uv run --with pyinstaller python tests/scripts/fixtures/make_pyi_bundles.py

Not run by the tests. The archives are written by PyInstaller's own `CArchiveWriter`, so
the tests prove `scripts/pyi_bundle_elfs.py` parses the real on-disk format. Each "ELF"
is a fake: the ELF magic, then a `GLIBC_x.y` marker the tests' fake objdump reports.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from PyInstaller.archive.writers import CArchiveWriter  # type: ignore[import-untyped]

HERE = Path(__file__).resolve().parent
PYLIB = "libpython3.12.so.1.0"


def _elf(marker: str) -> bytes:
    return b"\x7fELF " + marker.encode() + b" " + b"\0" * 64


def build(out: Path, dynload_glibc: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        files = {
            PYLIB: (_elf("GLIBC_2.34"), "b"),
            "lib-dynload/_ssl.cpython-312-x86_64-linux-gnu.so": (
                _elf(f"GLIBC_{dynload_glibc}"),
                "x",
            ),
            "pydantic_core/_pydantic_core.cpython-312-x86_64-linux-gnu.so": (
                _elf("GLIBC_2.28"),
                "x",
            ),
            "profiles.toml": (b"[profiles]\n", "x"),  # data, not ELF: skipped
        }
        entries = [("pyi-python-flag Py_GIL_DISABLED", "", False, "o")]
        for i, (name, (blob, code)) in enumerate(files.items()):
            src = t / str(i)
            src.write_bytes(blob)
            entries.append((name, str(src), True, code))
        pkg = t / "pkg"
        CArchiveWriter(str(pkg), entries, PYLIB)
        # The bootloader stub: its own dynamic symbols stop at GLIBC_2.14, as the real one.
        out.write_bytes(_elf("GLIBC_2.14") + pkg.read_bytes())


if __name__ == "__main__":
    build(HERE / "pyi-onefile-ok.bin", "2.35")
    build(HERE / "pyi-onefile-glibc239.bin", "2.39")
