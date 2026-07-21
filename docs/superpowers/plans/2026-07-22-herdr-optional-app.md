# herdr Optional Agent-Multiplexer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add herdr — an agent-aware terminal multiplexer — to dev-boost as an opt-in, pinned, SHA256-verified app with a curated pinned plugin set and a chezmoi-managed config.

**Architecture:** herdr ships as a single Rust release binary (no Fedora package), pinned in `catalog.toml` like ventoy and installed into `~/.local/bin` with checksum verification. Two typed `Module`s under a new opt-in `optional-agents` profile: `Herdr` (binary) and `HerdrPlugins` (curated `herdr plugin install` set, non-blocking). Config is a chezmoi source file, not module-written. Fedora is the reference path; a Homebrew branch is left as an OS seam.

**Tech Stack:** Python 3.12, Typer/Pydantic engine, `pkgutil`-discovered `@register` modules, injected `Executor` seam, `mypy --strict` + ruff + pytest.

**Reference spec:** `docs/superpowers/specs/2026-07-22-herdr-optional-app-design.md`

## Global Constraints

- Merge gates: `mypy --strict`, `ruff check`, and `pytest` must all pass. Run from `engine/`.
- Fedora is the only reference implementation; keep an OS-dispatch seam (do not hard-fail other OSes at import — only at install).
- The `optional-agents` profile is opt-in: it must NOT be added to the `full` aggregate in `profiles.toml`.
- Every pin in `catalog.toml` carries a 64-hex lowercase `sha256`; the loader validates it.
- A profile name must never equal a module name (`optional-agents` ≠ `herdr`/`herdr-plugins`).
- Commit messages contain no Claude/Anthropic attribution and no `Co-Authored-By`/`Generated with` trailers.
- Plugins are unsandboxed — only the hand-vetted, pinned set in this plan is shipped; each plugin repo is skimmed before its ref is pinned.
- herdr binary: `ogulcancelik/herdr`, assets `herdr-linux-x86_64` / `herdr-linux-aarch64`; config path `~/.config/herdr/config.toml` (TOML).

---

### Task 1: Pin herdr in `catalog.toml` + loader

**Files:**
- Modify: `catalog.toml` (add `[herdr]` tooling table)
- Modify: `engine/src/devboost/media/catalog.py`
- Test: `engine/tests/media/test_catalog.py`

**Interfaces:**
- Produces: `HerdrAsset(url: str, sha256: str)`, `HerdrSpec(version: str, assets: dict[str, HerdrAsset])`, and `herdr_pin() -> HerdrSpec` (arch key → asset, e.g. `"x86_64"`, `"aarch64"`). Consumed by `Herdr.install` in Task 2.

- [ ] **Step 1: Resolve the real per-arch SHA256 for the pinned version**

Run (records the exact digests to paste in Step 4):
```bash
curl -fsSL https://api.github.com/repos/ogulcancelik/herdr/releases/tags/v0.7.5 \
  | jq -r '.assets[] | select(.name|test("linux")) | "\(.name)  \(.digest)"'
```
Expected: two lines like `herdr-linux-x86_64  sha256:<64hex>` and `herdr-linux-aarch64  sha256:<64hex>`. Strip the `sha256:` prefix. If `digest` is null, hash directly:
```bash
for a in x86_64 aarch64; do
  curl -fsSL -o /tmp/h "https://github.com/ogulcancelik/herdr/releases/download/v0.7.5/herdr-linux-$a"
  echo "$a $(sha256sum /tmp/h | cut -d' ' -f1)"
done
```

- [ ] **Step 2: Write the failing tests**

Append to `engine/tests/media/test_catalog.py`:
```python
# ---------------------------------------------------------------------------
# herdr pin
# ---------------------------------------------------------------------------

def test_load_catalog_ignores_herdr_section_in_os_validation(tmp_path: Path) -> None:
    toml = _VALID + (
        "\n[herdr]\nversion = \"0.7.5\"\n"
        "[herdr.assets.x86_64]\n"
        'url = "https://x/herdr-linux-x86_64"\n'
        f'sha256 = "{"a" * 64}"\n'
    )
    p = tmp_path / "catalog.toml"
    p.write_text(toml, encoding="utf-8")
    cat = load_catalog(p)
    assert "herdr" not in cat and "fedora-99" in cat


def test_herdr_pin_is_present_in_live_catalog() -> None:
    from devboost.media.catalog import HerdrSpec, herdr_pin

    pin = herdr_pin()
    assert isinstance(pin, HerdrSpec)
    assert pin.version
    assert "x86_64" in pin.assets and "aarch64" in pin.assets
    for asset in pin.assets.values():
        assert asset.url.startswith("https://github.com/ogulcancelik/herdr/")
        assert re.fullmatch(r"[0-9a-f]{64}", asset.sha256)


def test_herdr_pin_raises_for_missing_section(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    p = tmp_path / "catalog.toml"
    p.write_text(_VALID, encoding="utf-8")  # no [herdr] block

    class _FakeSettings:
        catalog_path = p

    monkeypatch.setattr("devboost.media.catalog.settings", _FakeSettings())
    from devboost.media.catalog import herdr_pin
    herdr_pin.cache_clear()
    try:
        with pytest.raises(MediaError, match="herdr"):
            herdr_pin()
    finally:
        herdr_pin.cache_clear()
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd engine && .venv/bin/pytest tests/media/test_catalog.py -k herdr -v`
Expected: FAIL — `ImportError: cannot import name 'HerdrSpec'` / `herdr_pin`.

- [ ] **Step 4: Add the `[herdr]` pin to `catalog.toml`**

Append below the `[ventoy]` block (use the real digests from Step 1):
```toml
[herdr]
version = "0.7.5"

[herdr.assets.x86_64]
url = "https://github.com/ogulcancelik/herdr/releases/download/v0.7.5/herdr-linux-x86_64"
sha256 = "PASTE_X86_64_DIGEST_FROM_STEP_1"

[herdr.assets.aarch64]
url = "https://github.com/ogulcancelik/herdr/releases/download/v0.7.5/herdr-linux-aarch64"
sha256 = "PASTE_AARCH64_DIGEST_FROM_STEP_1"
```

- [ ] **Step 5: Implement the loader**

In `engine/src/devboost/media/catalog.py`:

Add `"herdr"` to the non-OS sections set:
```python
_NON_OS_SECTIONS: frozenset[str] = frozenset({"ventoy", "herdr"})
```

Add the value objects (near `VentoySpec`):
```python
@dataclass(frozen=True)
class HerdrAsset:
    url: str
    sha256: str


@dataclass(frozen=True)
class HerdrSpec:
    """Pinned herdr release (from the ``[herdr]`` block in catalog.toml)."""

    version: str
    assets: dict[str, HerdrAsset]  # arch ("x86_64"|"aarch64") -> asset
```

Add the pydantic rows (near `_VentoyRow`):
```python
class _HerdrAssetRow(BaseModel):
    url: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class _HerdrRow(BaseModel):
    version: str
    assets: dict[str, _HerdrAssetRow] = Field(min_length=1)
```

Add the accessor (near `ventoy_pin`):
```python
@cache
def herdr_pin() -> HerdrSpec:
    """The pinned herdr release (cached). Read from the ``[herdr]`` block in catalog.toml."""
    path = settings.catalog_path
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        row = _HerdrRow.model_validate(raw["herdr"])
    except (OSError, KeyError, ValueError) as exc:
        raise MediaError(f"[herdr] pin missing or invalid in {path}: {exc}") from exc
    return HerdrSpec(
        version=row.version,
        assets={a: HerdrAsset(url=r.url, sha256=r.sha256) for a, r in row.assets.items()},
    )
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd engine && .venv/bin/pytest tests/media/test_catalog.py -k herdr -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add catalog.toml engine/src/devboost/media/catalog.py engine/tests/media/test_catalog.py
git commit -m "feat(herdr): pin herdr release binary in catalog.toml"
```

---

### Task 2: `Herdr` binary module + `optional-agents` profile

**Files:**
- Create: `engine/src/devboost/modules/herdr.py`
- Modify: `profiles.toml`
- Test: `engine/tests/modules/test_herdr.py`

**Interfaces:**
- Consumes: `herdr_pin()` from Task 1.
- Produces: `Herdr` (module `name = "herdr"`, installs `~/.local/bin/herdr`). Consumed by `HerdrPlugins.requires` in Task 3.

- [ ] **Step 1: Add the opt-in profile to `profiles.toml`**

Add this line inside `[profiles]` (below `security-cli`):
```toml
optional-agents  = ["herdr"]
```
Also update the `full` comment's excluded-profile list to include `optional-agents` (so the "opt-in profiles are excluded" note stays accurate). Do NOT add `optional-agents` to the `full` list itself.

- [ ] **Step 2: Write the failing test**

Create `engine/tests/modules/test_herdr.py`:
```python
from __future__ import annotations

import tomllib

import pytest

from devboost.core.errors import InstallError
from devboost.core.osinfo import OsInfo
from devboost.core.settings import settings
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.herdr import Herdr

FEDORA_X86 = OsInfo(distro="fedora", family="fedora", arch="x86_64")
FEDORA_ARM = OsInfo(distro="fedora", family="fedora", arch="aarch64")


def _ctx(os_: OsInfo = FEDORA_X86, **kw: object) -> Ctx:
    return Ctx(os=os_, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_herdr_is_optional_agents_profile() -> None:
    assert Herdr.profiles == ("optional-agents",)
    assert Herdr.category == "optional-agents"


def test_herdr_verify_uses_which() -> None:
    assert Herdr().verify(_ctx(present=set())) is False
    assert Herdr().verify(_ctx(present={"herdr"})) is True


def test_herdr_install_downloads_verified_x86_64(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    ctx = _ctx()
    Herdr().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert len(calls) == 1 and calls[0][:2] == ["sh", "-c"]
    script = calls[0][2]
    assert "herdr-linux-x86_64" in script
    assert "sha256sum -c -" in script
    assert "/home/tester/.local/bin/herdr" in script


def test_herdr_install_selects_aarch64(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    ctx = _ctx(FEDORA_ARM)
    Herdr().install(ctx)
    script = ctx.ex.calls[0][2]  # type: ignore[attr-defined]
    assert "herdr-linux-aarch64" in script


def test_herdr_install_raises_on_checksum_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    ctx = _ctx(scripts={"sh": Result(1, stderr="sha256sum: WARNING")})
    with pytest.raises(InstallError, match="checksum"):
        Herdr().install(ctx)


def test_herdr_install_raises_on_unknown_arch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", "/home/tester")
    ctx = _ctx(OsInfo(distro="fedora", family="fedora", arch="riscv64"))
    with pytest.raises(InstallError, match="riscv64"):
        Herdr().install(ctx)


def test_optional_agents_profile_registered() -> None:
    data = tomllib.loads(settings.profiles_path.read_text(encoding="utf-8"))
    assert "herdr" in data["profiles"]["optional-agents"]
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd engine && .venv/bin/pytest tests/modules/test_herdr.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'devboost.modules.herdr'`.

- [ ] **Step 4: Implement the module**

Create `engine/src/devboost/modules/herdr.py`:
```python
"""herdr — opt-in agent-aware terminal multiplexer (pinned, SHA256-verified binary)."""

from __future__ import annotations

import os
from pathlib import Path

from devboost.core.errors import InstallError
from devboost.core.registry import register
from devboost.media.catalog import herdr_pin
from devboost.model import Ctx, Module


@register
class Herdr(Module):
    name = "herdr"
    category = "optional-agents"
    description = "herdr — agent-aware terminal multiplexer (pinned binary)."
    profiles = ("optional-agents",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("herdr")

    def install(self, ctx: Ctx) -> None:
        pin = herdr_pin()
        asset = pin.assets.get(ctx.os.arch)
        if asset is None:
            raise InstallError(f"herdr: no pinned binary for arch {ctx.os.arch!r}")
        bindir = Path(os.environ["HOME"]) / ".local" / "bin"
        # Download → verify SHA256 (sha256sum -c fails the `set -e` script on mismatch,
        # before install) → install onto PATH. No native package exists for herdr.
        script = (
            "set -e\n"
            "tmp=$(mktemp -d)\n"
            f'curl -fL --retry 2 -o "$tmp/herdr" "{asset.url}"\n'
            f'echo "{asset.sha256}  $tmp/herdr" | sha256sum -c -\n'
            f'install -Dm755 "$tmp/herdr" "{bindir}/herdr"\n'
            'rm -rf "$tmp"\n'
        )
        if not ctx.ex.run(["sh", "-c", script]).ok:
            raise InstallError("herdr: download or checksum verification failed")
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd engine && .venv/bin/pytest tests/modules/test_herdr.py -v`
Expected: PASS (7 tests).

- [ ] **Step 6: Run the profile-validation guard tests**

Run: `cd engine && .venv/bin/pytest tests/modules/test_base.py tests/modules/test_system.py -k profile -v`
Expected: PASS — confirms `optional-agents` satisfies the live-profiles validation for the new module.

- [ ] **Step 7: Commit**

```bash
git add engine/src/devboost/modules/herdr.py engine/tests/modules/test_herdr.py profiles.toml
git commit -m "feat(herdr): install pinned herdr binary under optional-agents profile"
```

---

### Task 3: `HerdrPlugins` module (curated pinned set)

**Files:**
- Modify: `engine/src/devboost/modules/herdr.py`
- Modify: `profiles.toml`
- Test: `engine/tests/modules/test_herdr.py`

**Interfaces:**
- Consumes: `Herdr` from Task 2.
- Produces: `HerdrPlugins` (module `name = "herdr-plugins"`, `requires = (Herdr,)`).

- [ ] **Step 1: Resolve a pinned ref + plugin id for each curated plugin**

The vetted slugs are fixed below. For EACH, (a) skim the repo (security — plugins are unsandboxed), (b) read its `herdr-plugin.toml` `id`, (c) resolve the newest stable tag (fall back to the current default-branch commit if untagged):
```bash
for slug in nickmaglowsch/herdr-session-restore andrewchng/herdr-sessionizer \
            dcolinmorgan/herdr-remote ogulcancelik/herdr-plugin-examples \
            ridho9/switchr smarzban/herdr-file-viewer eugeneb50/herdr-mcp \
            cloudmanic/herdr-plus Taeyoung96/herdr-dotfiles; do
  echo -n "$slug  "; git ls-remote --tags --refs "https://github.com/$slug" \
    | awk -F/ 'END{print $NF ? $NF : "HEAD"}'
  git ls-remote "https://github.com/$slug" HEAD | cut -f1   # SHA fallback
done
```
Record the `(id, source, ref)` for each into the `_PLUGINS` tuple in Step 3. `id` is the value from each repo's `herdr-plugin.toml`; `source` is `owner/repo[/subdir]`; `ref` is the tag or commit SHA.

- [ ] **Step 2: Write the failing tests**

Append to `engine/tests/modules/test_herdr.py`:
```python
from devboost.modules.herdr import _PLUGINS, HerdrPlugins  # noqa: E402


def test_herdr_plugins_requires_herdr() -> None:
    assert Herdr in HerdrPlugins.requires
    assert HerdrPlugins.profiles == ("optional-agents",)


def test_herdr_plugins_pins_a_ref_for_every_entry() -> None:
    assert _PLUGINS  # non-empty curated set
    for pid, source, ref in _PLUGINS:
        assert pid and "/" in source and ref  # id, owner/repo, and a pinned ref


def test_herdr_plugins_install_pins_each_plugin() -> None:
    ctx = _ctx()
    HerdrPlugins().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    for _pid, source, ref in _PLUGINS:
        assert ["herdr", "plugin", "install", source, "--ref", ref, "--yes"] in calls


def test_herdr_plugins_install_is_non_blocking() -> None:
    # Every `herdr` call fails, yet install must not raise and must attempt them all.
    ctx = _ctx(scripts={"herdr": Result(1, stderr="boom")})
    HerdrPlugins().install(ctx)  # no exception
    install_calls = [c for c in ctx.ex.calls if c[:3] == ["herdr", "plugin", "install"]]  # type: ignore[attr-defined]
    assert len(install_calls) == len(_PLUGINS)


def test_herdr_plugins_verify_checks_listing() -> None:
    ids = " ".join(pid for pid, _, _ in _PLUGINS)
    assert HerdrPlugins().verify(_ctx(scripts={"herdr": Result(0, stdout=ids)})) is True
    assert HerdrPlugins().verify(_ctx(scripts={"herdr": Result(0, stdout="none")})) is False
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd engine && .venv/bin/pytest tests/modules/test_herdr.py -k plugins -v`
Expected: FAIL — `ImportError: cannot import name '_PLUGINS'`.

- [ ] **Step 4: Implement `HerdrPlugins`**

Append to `engine/src/devboost/modules/herdr.py` (add the `log` import at the top: `from devboost.core import log`):
```python
# Curated, pinned plugin set. (id, "owner/repo[/subdir]", ref) — id from each repo's
# herdr-plugin.toml; ref = newest stable tag (or default-branch commit). Each repo is
# skimmed before its ref is pinned (plugins run unsandboxed as the user).
_PLUGINS: tuple[tuple[str, str, str], ...] = (
    ("herdr-session-restore", "nickmaglowsch/herdr-session-restore", "REF"),
    ("herdr-sessionizer", "andrewchng/herdr-sessionizer", "REF"),
    ("herdr-remote", "dcolinmorgan/herdr-remote", "REF"),
    ("agent-telegram-notify", "ogulcancelik/herdr-plugin-examples/agent-telegram-notify", "REF"),
    ("switchr", "ridho9/switchr", "REF"),
    ("herdr-file-viewer", "smarzban/herdr-file-viewer", "REF"),
    ("herdr-mcp", "eugeneb50/herdr-mcp", "REF"),
    ("herdr-plus", "cloudmanic/herdr-plus", "REF"),
    ("herdr-dotfiles", "Taeyoung96/herdr-dotfiles", "REF"),
)


@register
class HerdrPlugins(Module):
    name = "herdr-plugins"
    category = "optional-agents"
    description = "Curated, pinned herdr plugin set."
    requires = (Herdr,)
    profiles = ("optional-agents",)

    def verify(self, ctx: Ctx) -> bool:
        listed = ctx.ex.run(["herdr", "plugin", "list"]).stdout
        return all(pid in listed for pid, _, _ in _PLUGINS)

    def install(self, ctx: Ctx) -> None:
        for pid, source, ref in _PLUGINS:
            res = ctx.ex.run(["herdr", "plugin", "install", source, "--ref", ref, "--yes"])
            if not res.ok:
                log.warn(f"herdr-plugins: {pid} install failed (non-blocking)")
        self._configure_notify(ctx)

    def _configure_notify(self, ctx: Ctx) -> None:
        """Provision the Telegram notify plugin from env, or skip with a warning.

        Var names (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID) confirmed against the
        agent-telegram-notify README during the skim step; adjust there if they differ.
        """
        token = os.environ.get("DEVBOOST_HERDR_TELEGRAM_TOKEN")
        chat = os.environ.get("DEVBOOST_HERDR_TELEGRAM_CHAT_ID")
        if not (token and chat):
            log.warn("herdr-plugins: Telegram token/chat unset — notify unconfigured (non-blocking)")
            return
        cfg = ctx.ex.run(["herdr", "plugin", "config-dir", "agent-telegram-notify"]).stdout.strip()
        if not cfg:
            log.warn("herdr-plugins: notify config dir unavailable (non-blocking)")
            return
        env_file = Path(cfg) / ".env"
        env_file.parent.mkdir(parents=True, exist_ok=True)
        env_file.write_text(
            f"TELEGRAM_BOT_TOKEN={token}\nTELEGRAM_CHAT_ID={chat}\n", encoding="utf-8"
        )
```
Replace each `"REF"` with the real tag/SHA resolved in Step 1.

- [ ] **Step 5: Extend the profile**

In `profiles.toml`, change the `optional-agents` line to include the plugins module:
```toml
optional-agents  = ["herdr","herdr-plugins"]
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd engine && .venv/bin/pytest tests/modules/test_herdr.py -v`
Expected: PASS (all herdr tests).

- [ ] **Step 7: Commit**

```bash
git add engine/src/devboost/modules/herdr.py engine/tests/modules/test_herdr.py profiles.toml
git commit -m "feat(herdr): install curated pinned herdr plugin set (non-blocking)"
```

---

### Task 4: chezmoi-managed herdr config

**Files:**
- Create: `dotfiles/dot_config/herdr/config.toml`
- Test: `engine/tests/modules/test_herdr.py` (parse guard)

**Interfaces:** none (static chezmoi source). Applied by the existing `dotfiles`/`chezmoi-repo` flow.

- [ ] **Step 1: Write the failing parse-guard test**

Append to `engine/tests/modules/test_herdr.py`:
```python
def test_herdr_config_parses_and_sets_prefix() -> None:
    from devboost.core.settings import settings

    cfg = settings.root / "dotfiles" / "dot_config" / "herdr" / "config.toml"
    data = tomllib.loads(cfg.read_text(encoding="utf-8"))
    assert data["keys"]["prefix"] == "ctrl+b"
    assert "theme" in data
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd engine && .venv/bin/pytest tests/modules/test_herdr.py -k config -v`
Expected: FAIL — `FileNotFoundError` (config not created yet).

- [ ] **Step 3: Create the config**

Create `dotfiles/dot_config/herdr/config.toml`:
```toml
# herdr — agent-aware terminal multiplexer. Managed by chezmoi (dev-boost).
# Invalid values revert to safe defaults with a startup warning; run `herdr` once
# after apply and confirm no config warnings. Docs: https://herdr.dev/docs/configuration/

[keys]
prefix = "ctrl+b"          # tmux-style prefix — muscle memory carries over
new_tab = "prefix+c"
next_tab = "prefix+n"
previous_tab = "prefix+p"
split_horizontal = "prefix+minus"
focus_pane_left = "prefix+h"

[theme]
palette = "tokyo-night"    # matches the wezterm/terminal aesthetic

[ui.toast]
enabled = true
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd engine && .venv/bin/pytest tests/modules/test_herdr.py -k config -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dotfiles/dot_config/herdr/config.toml engine/tests/modules/test_herdr.py
git commit -m "feat(herdr): chezmoi-managed herdr config (tmux keys, tokyo-night)"
```

---

### Task 5: Docs — README + roadmap

**Files:**
- Modify: `README.md` (optional-apps / profiles section)
- Modify: `docs/roadmap.md`

**Interfaces:** none.

- [ ] **Step 1: Locate the optional-profiles section in the README**

Run: `grep -n "optional-editors\|security-cli\|Optional" README.md`
Expected: the profile/app catalog table or list where opt-in profiles are documented.

- [ ] **Step 2: Add herdr to the README**

In the section found in Step 1, add a `optional-agents` entry mirroring the `optional-editors` / `security-cli` style, one line:
> **`optional-agents`** — herdr (agent-aware terminal multiplexer) + a curated, pinned plugin set. Opt-in; not part of `full`. Runs alongside tmux.

- [ ] **Step 3: Note herdr in the roadmap**

In `docs/roadmap.md`, add a line under the appropriate (shipped/optional) section:
> - herdr optional agent-multiplexer — pinned binary + curated plugins + chezmoi config (`optional-agents` profile). Spec: `docs/superpowers/specs/2026-07-22-herdr-optional-app-design.md`.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/roadmap.md
git commit -m "docs(herdr): document optional-agents profile"
```

---

### Task 6: Full merge-gate verification

**Files:** none (verification only).

- [ ] **Step 1: Type-check**

Run: `cd engine && .venv/bin/mypy --strict src/devboost/modules/herdr.py src/devboost/media/catalog.py`
Expected: `Success: no issues found`.

- [ ] **Step 2: Lint**

Run: `cd engine && .venv/bin/ruff check src/devboost/modules/herdr.py src/devboost/media/catalog.py tests/modules/test_herdr.py`
Expected: `All checks passed!`

- [ ] **Step 3: Full test suite**

Run: `cd engine && .venv/bin/pytest -q`
Expected: all tests pass (herdr, catalog, live-profile validation in `test_base.py`/`test_system.py`).

- [ ] **Step 4: Confirm the profile is opt-in (not in `full`)**

Run: `cd engine && .venv/bin/python -c "import tomllib,pathlib; d=tomllib.loads(pathlib.Path('../profiles.toml').read_text())['profiles']; assert 'optional-agents' not in d['full']; assert d['optional-agents']==['herdr','herdr-plugins']; print('ok')"`
Expected: `ok`.

- [ ] **Step 5: Final review commit (if any docs/comment fixups were needed)**

```bash
git add -A && git commit -m "chore(herdr): finalize optional-agents integration" || echo "nothing to finalize"
```

---

## Self-Review

**Spec coverage:**
- §2 placement/profile → Task 2 (profile), Tasks 2–3 (module file). ✅
- §3 pinned binary + SHA256 + arch + OS seam → Task 1 (pin) + Task 2 (install/verify/arch/raise). ✅
- §4 curated pinned plugins, non-blocking, secret skip-with-warning → Task 3 (`_PLUGINS`, non-blocking loop, `_configure_notify`). ✅
- §5 chezmoi config → Task 4. ✅
- §6 docs → Task 5. ✅
- §7 tests (catalog sha256, download/verify/mismatch sequence, per-plugin install, non-blocking) → Tasks 1–4 tests; gates in Task 6. ✅

**Placeholder scan:** The only unresolved literals are the SHA256 digests (Task 1 Step 1 gives the exact command to obtain them) and the plugin `REF`s + ids (Task 3 Step 1 gives the exact resolution command). These are pin-time values with a defined procedure, not vague TODOs — same class as the ventoy sha256 already in the repo.

**Type consistency:** `HerdrSpec.assets: dict[str, HerdrAsset]` keyed by `ctx.os.arch` ("x86_64"/"aarch64") is consumed consistently in `Herdr.install`. `_PLUGINS` is a `tuple[tuple[str, str, str], ...]` (id, source, ref) used identically in `verify`, `install`, and all Task 3 tests. `herdr_pin()`/`HerdrSpec`/`HerdrAsset` names match between `catalog.py` and its tests.
