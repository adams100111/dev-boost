"""The primitive helpers (thin, typed wrappers over system tools).

Submodules are imported and listed in ``__all__`` so they are *explicitly* exported.
``strict`` implies ``--no-implicit-reexport``, under which a plain
``from devboost.exec.primitives import pkg`` resolves only when something else in the
build happened to import that submodule first — so it passes or fails by build order
rather than by anything in the code.
"""

from devboost.exec.primitives import (
    age,
    config,
    copr,
    dconf,
    flatpak,
    fs,
    github,
    gpu,
    mise,
    pkg,
    shell,
    systemd,
    usermgmt,
)

__all__ = [
    "age",
    "config",
    "copr",
    "dconf",
    "flatpak",
    "fs",
    "github",
    "gpu",
    "mise",
    "pkg",
    "shell",
    "systemd",
    "usermgmt",
]
