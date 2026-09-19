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
    after = ()                    # ordering only: run after these IF they are in the plan; never pulls them in, never blocked by them
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

Use `after` for a soft input the module can do without — e.g. `claude-plugins` reads a token from
`pass` and runs `after = (PassStore,)`, so a device awaiting approval still installs Claude and just
skips the token.

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

## macOS

- Simple tools: `PackageModule` works as-is; set `brew_pkg` when the formula name differs
  from the module name (e.g. `delta` → `git-delta`), or `brew_cask` for app-only tools.
- A `PackageModule` that needs a custom **Linux** path overrides `install_linux` /
  `verify_linux` (never `install` / `verify`), so macOS stays on Homebrew automatically.
- GUI apps: set `cask` on your `FlatpakApp` subclass.
- Custom install logic: declare the macOS answer as data —
  `per_os = OsMap(macos=BrewFormula("tool"))` or `OsMap(macos=BrewCask("App"))` (from
  `modules/_brew.py`), or your own `Installer` strategy. A module whose own
  `install`/`verify` implement the Linux path hands off first:
  `if (s := self.os_strategy(ctx)) is not None: return s.install(ctx)`. The plan treats
  that own `install` as the fallback for OSes `per_os` does not name.
- Or: `families = ("fedora", "debian", "arch")` if the module cannot exist on a Mac,
  `provided_by = ("macos",)` if macOS already covers it, or `portable = True` once you have
  verified it runs unchanged.
- Background jobs: use `launchd.user_agent(...)` (label `launchd.label("<name>")`).
- Privacy permissions: `tcc = (TccGrant("Accessibility", "AppName"),)`.
- `tests/core/test_macos_contract.py` fails if you add a module with no macOS answer.
- A module whose macOS install uses Homebrew **requires `Homebrew`** (`modules/macos.py`).
  `PackageModule` and `FlatpakApp` already do; a custom strategy that calls brew sets
  `uses_brew: ClassVar[bool] = True` and its module lists `Homebrew` in `requires`
  (`tests/core/test_homebrew_edges.py` enforces it). Linux plans drop Homebrew.
- A macOS path that a later milestone owns: `per_os = OsMap(macos=MacosPending("M4",
  "<manual workaround>"))` (`modules/_pending.py`). The module reports `blocked` on a Mac
  and stays in `KNOWN_GAPS` (module → milestone) until the real strategy lands.
- A pinned binary is keyed by OS **and** arch: `media.catalog.asset_key(ctx.os)` →
  `linux-x86_64`, `linux-aarch64`, `macos-aarch64`. Never key by arch alone.
- An installer script: `remote_script.run_script(ctx, name, url, "bash", *args)` —
  downloads into a private temp dir, then runs it.
- A step that opens a macOS dialog runs only when `_credentials.is_interactive()`;
  otherwise raise `NeedsUser(reason, how_to_fix)`.
- Default apps: add rows to `data/macos/default-apps.tsv` and call
  `default_apps.apply(ctx, rows, can_prompt=…)`.
