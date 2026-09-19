"""pass multi-device: per-device GPG keys, enroll/approve/revoke, auto-sync.

Library code only — the `pass`/`pass-store` modules and the `devboost pass` CLI
call in. Every side effect goes through the injected Executor. See docs/pass.md.

Submodules are imported and listed in ``__all__`` so they are *explicitly* exported.
``strict`` implies ``--no-implicit-reexport``, under which a plain
``from devboost.passstore import paths`` resolves only when something else in the build
happened to import that submodule first — so it passes or fails by build order rather
than by anything in the code (see devboost/exec/primitives/__init__.py for the same fix).
"""

from devboost.passstore import approve, enroll, git, gpg, layout, notify, paths

__all__ = ["approve", "enroll", "git", "gpg", "layout", "notify", "paths"]
