"""The bundled fresh language-server pins must use backends dev-boost can actually satisfy.

Two real failures from a Fedora 44 `devboost install full` motivated this:
  - taplo was pinned as `cargo:taplo-cli` — but dev-boost installs NO Rust toolchain, so the
    cargo backend cannot build and taplo was silently missing (fresh-lsp "verify failed").
  - tofu-ls was pinned `aqua:opentofu/tofu-ls@0.0.22` — a version that never existed (the repo
    is at v0.5.x), so mise 404'd and tofu-ls was missing (devops-lsp "verify failed").

These read the shipped TSVs directly, so a bad pin fails here instead of on a user's machine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_FRESH = Path(__file__).resolve().parents[3] / "data" / "fresh"
_TSVS = sorted(_FRESH.glob("*.tsv"))

# Backends dev-boost can satisfy on a stock box: aqua/ubi (prebuilt GitHub-release binaries),
# npm (node is installed), pipx (installed), go. NOT cargo — no Rust toolchain is provisioned.
_ALLOWED_BACKENDS = {"aqua", "ubi", "npm", "pipx", "go"}
_FORBIDDEN_BACKENDS = {"cargo"}


def _specs() -> list[tuple[str, str]]:
    """(tsv_name, mise_spec) for every server row across all bundled TSVs."""
    out: list[tuple[str, str]] = []
    for tsv in _TSVS:
        for line in tsv.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            cols = line.split("\t")
            if len(cols) >= 3:
                out.append((tsv.name, cols[2]))
    return out


def test_there_are_server_tsvs() -> None:
    assert _TSVS, "no data/fresh/*.tsv found"


@pytest.mark.parametrize("tsv,spec", _specs())
def test_no_server_uses_a_backend_devboost_cannot_satisfy(tsv: str, spec: str) -> None:
    backend = spec.split(":", 1)[0]
    assert backend not in _FORBIDDEN_BACKENDS, (
        f"{tsv}: `{spec}` uses the {backend} backend, but dev-boost installs no Rust toolchain "
        f"— use a prebuilt backend (aqua/ubi/npm)"
    )
    assert backend in _ALLOWED_BACKENDS, f"{tsv}: `{spec}` uses an unrecognised backend {backend!r}"


@pytest.mark.parametrize("tsv,spec", _specs())
def test_every_server_spec_is_version_pinned(tsv: str, spec: str) -> None:
    """Principle III: the pin is the source of truth. Every spec must carry an @version."""
    assert "@" in spec, f"{tsv}: `{spec}` is not version-pinned"
