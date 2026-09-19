"""Typed access to macOS user defaults via the `defaults` CLI (never by editing plists).

`defaults` owns cfprefsd's cache, so writing through it needs no `killall cfprefsd`.
Values are typed on the way out (`-bool`/`-int`/`-float`/`-string`) and on the way in
(`read-type` first), so a revert can restore exactly what was there.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from devboost.core.errors import InstallError
from devboost.model import Ctx

Kind = Literal["bool", "int", "float", "string", "other"]
Scalar = bool | int | float | str

#: `defaults read-type` prints "Type is <name>"; anything not listed is kept as "other".
_READ_TYPES: dict[str, Kind] = {
    "boolean": "bool",
    "integer": "int",
    "float": "float",
    "string": "string",
}


@dataclass(frozen=True)
class Value:
    """A typed defaults value. For kind "other" *value* is the type name (not writable)."""

    kind: Kind
    value: Scalar


def _parse(kind: Kind, raw: str) -> Scalar:
    if kind == "string":
        return raw.rstrip("\n")
    text = raw.strip()
    if kind == "bool":
        return text in ("1", "true", "YES")
    if kind == "int":
        return int(text)
    if kind == "float":
        return float(text)
    return text


def read(ctx: Ctx, domain: str, key: str) -> Value | None:
    """The key's typed value, or None when it is absent."""
    typed = ctx.ex.run(["defaults", "read-type", domain, key])
    if not typed.ok:
        return None
    type_name = typed.stdout.strip().removeprefix("Type is ").strip()
    kind = _READ_TYPES.get(type_name)
    if kind is None:
        return Value("other", type_name)
    res = ctx.ex.run(["defaults", "read", domain, key])
    if not res.ok:
        return None
    return Value(kind, _parse(kind, res.stdout))


def _flag(v: Value) -> list[str]:
    if v.kind == "bool":
        return ["-bool", "true" if v.value else "false"]
    if v.kind == "int":
        return ["-int", str(int(v.value))]
    if v.kind == "float":
        return ["-float", repr(float(v.value))]
    if v.kind == "string":
        return ["-string", str(v.value)]
    raise ValueError(f"cannot write a defaults value of kind 'other' ({v.value})")


def write(ctx: Ctx, domain: str, key: str, v: Value) -> None:
    argv = ["defaults", "write", domain, key, *_flag(v)]
    res = ctx.ex.run(argv)
    if not res.ok:
        raise InstallError("macos-defaults", " ".join(argv), res.code)


def delete(ctx: Ctx, domain: str, key: str) -> None:
    """Remove the key, bringing back the system default. Absent is fine (exit 1 ignored)."""
    ctx.ex.run(["defaults", "delete", domain, key])
