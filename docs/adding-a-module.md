# Adding a module (or an OS)

## Add a tool — one typed file

```sh
devboost add <name>            # scaffolds engine/src/devboost/modules/<name>.py
```

A module is one typed Python class. Most tools are a package install:

```python
from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import Ctx, Module

@register
class Ripgrep(Module):
    name = "ripgrep"
    category = "cli"
    requires = ()                 # references to other Module classes (topo-sorted before this)
    profiles = ("cli",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("rg")          # True ⇒ already installed ⇒ skipped (idempotency guard)

    def install(self, ctx: Ctx) -> None:
        pkg.install(ctx, "ripgrep")        # OS-dispatched; never names dnf/apt
```

For the common case there's a shared base — `class Ripgrep(PackageModule)` with
`cmd`/`fedora_pkg` attributes (see `modules/cli_tools.py`). Add the name to a profile in
`profiles.toml`, then:

```sh
uv run devboost list cli       # see it resolve
uv run pytest                  # add a FakeExecutor test for non-trivial modules
uv run mypy && uv run ruff check
```

## Dependencies are typed references

`requires = (Docker,)` references the depended-on **class**, so `mypy --strict` proves the graph and
the IDE refactors/navigates it. The registry validates the whole catalog at load (unique names,
deps resolve, profiles exist, no cycles) before any side effect.

## Side effects go through the injected executor

Never call `subprocess` directly. Use `ctx.ex.run([...])` (argv lists, never a shell string) or a
typed primitive (`pkg`, `flatpak`, `copr`, `mise`, `config`, `dconf`, `age`, `github`, `systemd`,
`fs`, `gpu`; `shell.run(...)` is the rare escape hatch). In tests, inject a `FakeExecutor` that
records calls — no real `dnf`/network.

## Add an OS — localized, no engine change

The package manager is selected from `ctx.os` (Fedora's `Dnf` is implemented; `Apt`/`Pacman` are
seams). Per-OS differences escalate only where needed:

1. **Same package name** → nothing to do (`pkg.install(ctx, "git")`).
2. **Name differs** → `pkg.install(ctx, OsMap(fedora="fd-find", default="fd"))`.
3. **Source differs** (repo/script) → a typed `Source = OsMap[DnfRepo | AptRepo | Script]`.
4. **Steps differ** → declare `per_os = OsMap(fedora=FooFedora(), debian=FooDebian())` of `Installer`
   strategies; the engine calls the one resolved for the detected OS.

Adding Ubuntu = implement the `Apt` manager once + fill `debian=` entries only in the modules that
truly diverge. The OS-agnostic majority is untouched.
