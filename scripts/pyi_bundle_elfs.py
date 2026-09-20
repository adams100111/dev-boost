#!/usr/bin/env python3
"""Extract every ELF object a PyInstaller onefile bundle carries.

Usage: pyi_bundle_elfs.py BUNDLE OUTDIR

A PyInstaller onefile is the prebuilt bootloader with a CArchive (PKG) embedded in it.
`objdump -T BUNDLE` sees only the bootloader: libpython and every extension module sit
inside the archive as opaque data. This reads that archive's table of contents, writes each
entry whose payload is an ELF object (libpython, `lib-dynload/*.so`, the wheels' `*.so`,
any other collected shared library) to OUTDIR, and prints one `<extracted path>\\t<name>`
line per object, so check-glibc-floor.sh can run `objdump -T` over what actually ships.

Stdlib only, so it runs under any Python (the ubuntu:22.04 build container has none but
uv's). The on-disk format is PyInstaller's, as its own reader parses it
(`PyInstaller.archive.readers.CArchiveReader`, PyInstaller 6.x): a cookie
`!8sIIII64s` (magic, archive length, TOC offset, TOC length, Python version, libpython
name) found by scanning back from the end of the file, then TOC entries `!IIIIBc` + a
NUL-padded name, entry data optionally zlib-compressed.

Exit 0: at least one ELF extracted, including the libpython the cookie names.
Exit 2: usage error, not a PyInstaller bundle, or no ELF libpython inside it. A reader
that finds nothing fails loudly, so the floor check can never silently pass on the stub.
"""

from __future__ import annotations

import os
import struct
import sys
import zlib
from pathlib import Path

_MAGIC = b"MEI\014\013\012\013\016"
_COOKIE = "!8sIIII64s"
_COOKIE_LEN = struct.calcsize(_COOKIE)
_ENTRY = "!IIIIBc"
_ENTRY_LEN = struct.calcsize(_ENTRY)
_ELF = b"\x7fELF"
_CHUNK = 8192


class BundleError(Exception):
    """The file is not a readable PyInstaller onefile bundle."""


def _find_cookie(data: bytes) -> int:
    # Last occurrence wins, like CArchiveReader's back-to-front scan.
    pos = data.rfind(_MAGIC)
    if pos == -1:
        raise BundleError("no PyInstaller archive cookie (not a onefile bundle?)")
    return pos


def read_bundle(path: Path) -> tuple[str, list[tuple[str, str, bytes]]]:
    """Return (libpython name, [(name, typecode, data)]) for every TOC entry."""
    data = path.read_bytes()
    cookie_at = _find_cookie(data)
    cookie = data[cookie_at : cookie_at + _COOKIE_LEN]
    if len(cookie) != _COOKIE_LEN:
        raise BundleError("truncated archive cookie")
    _magic, arch_len, toc_off, toc_len, _pyvers, pylib = struct.unpack(_COOKIE, cookie)
    end = cookie_at + _COOKIE_LEN
    start = end - arch_len
    if start < 0 or toc_off + toc_len > arch_len:
        raise BundleError("archive cookie points outside the file")
    pylib_name = pylib.rstrip(b"\0").decode("utf-8")
    if not pylib_name:
        raise BundleError("archive cookie names no Python shared library")

    toc = data[start + toc_off : start + toc_off + toc_len]
    entries: list[tuple[str, str, bytes]] = []
    pos = 0
    while pos < len(toc):
        if pos + _ENTRY_LEN > len(toc):
            raise BundleError("truncated TOC entry")
        entry_len, off, length, _ulen, compressed, code = struct.unpack(
            _ENTRY, toc[pos : pos + _ENTRY_LEN]
        )
        if entry_len < _ENTRY_LEN:
            raise BundleError("corrupt TOC entry length")
        name = toc[pos + _ENTRY_LEN : pos + entry_len].rstrip(b"\0").decode("utf-8")
        pos += entry_len
        typecode = code.decode("ascii")
        if typecode == "o":  # runtime option, no payload
            continue
        blob = data[start + off : start + off + length]
        if len(blob) != length:
            raise BundleError(f"entry {name!r} runs past the archive")
        if compressed:
            blob = zlib.decompress(blob)
        entries.append((name, typecode, blob))
    return pylib_name, entries


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: pyi_bundle_elfs.py BUNDLE OUTDIR", file=sys.stderr)
        return 2
    bundle, outdir = Path(argv[1]), Path(argv[2])
    try:
        pylib, entries = read_bundle(bundle)
    except (OSError, BundleError, struct.error, zlib.error, UnicodeDecodeError) as exc:
        print(f"pyi_bundle_elfs: {bundle}: {exc}", file=sys.stderr)
        return 2

    outdir.mkdir(parents=True, exist_ok=True)
    found: list[tuple[Path, str]] = []
    for index, (name, _typecode, blob) in enumerate(entries):
        if not blob.startswith(_ELF):
            continue
        target = outdir / f"{index:05d}-{os.path.basename(name)}"
        target.write_bytes(blob)
        found.append((target, name))

    if not any(name == pylib for _target, name in found):
        print(
            f"pyi_bundle_elfs: {bundle}: the bundle has no ELF {pylib!r} "
            f"({len(found)} ELF objects found) — refusing to report a partial check",
            file=sys.stderr,
        )
        return 2
    for target, name in found:
        print(f"{target}\t{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
