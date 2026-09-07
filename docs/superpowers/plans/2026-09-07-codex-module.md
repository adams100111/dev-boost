# Codex Config Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reproduce the operator's global OpenAI Codex CLI setup (instructions, plugins, marketplaces, MCP servers, skills, prefs, hooks) on any device via five small idempotent engine modules + chezmoi dotfiles, mirroring the `claude` module.

**Architecture:** Static config (AGENTS.md, hooks, vendored SKILL.md skills) rides the existing `Dotfiles` chezmoi module. Five modules do the imperative work: `codex-code` (install the standalone binary), `codex-config` (TOML-merge prefs/features/shell_env/hooks + CLICKUP from `pass`), `codex-plugins` (`codex plugin marketplace add`/`codex plugin add`), `codex-mcp` (`codex mcp add`), `codex-skills` (populate the shared `~/.agents/skills` via `npx skills add … -g`). A `codex` profile bundles them.

**Tech Stack:** Python 3.12 engine (src-layout under `engine/`), `pytest` + `FakeExecutor`, `mypy` + `ruff`. Config target `~/.codex/config.toml` (TOML, via `tomllib` read + `tomli_w` write) + `~/.codex/AGENTS.md`. Secrets via `pass`.

## Global Constraints

- **Merge gates (from `engine/`):** `uv run ruff check && uv run mypy && COLUMNS=80 uv run pytest -q` — all pass. Lines ≤ 100 cols; avoid `dict[str, object]` patterns that break `in`/attribute access under whole-tree mypy.
- **Executor seam:** all system-tool calls via `ctx.ex.run([...])` / `ctx.ex.which(...)` (argv lists; shells only via `["sh","-c",…]`/`["bash","-lc",…]`). Never `subprocess`.
- **`config.toml` writes:** read (`tomllib.loads`) → deep-merge only managed keys → write (`tomli_w.dumps`); **preserve** `[projects.*]` trust, `[hooks.state.*]`, `[mcp_servers.*]`, `[marketplaces.*]`, `[plugins.*]`, and any unknown keys. Absent file → create; unparseable TOML → `log.warn` + leave untouched.
- **Never clobber via CLI-owned sections:** plugins/marketplaces/MCP are written by the `codex` CLI itself (`codex plugin …`, `codex mcp add`), which preserves the rest of `config.toml`. `codex-config` only TOML-merges the pure-config sections (prefs, `[features]`, `[shell_environment_policy]`, `[hooks]`).
- **Zero plaintext secrets in committed files:** `~/.codex/config.toml` is a device-local home file, never committed. CLICKUP is resolved from `pass` at apply time into `[shell_environment_policy.set]`. The repo never contains `config.toml`.
- **Global-only:** the module touches `~/.codex/*` (global) only — never project-level `AGENTS.md`/`CLAUDE.md`.
- **Degrade + report:** missing `pass`/entry/`codex`/`npx` → `log.warn` + skip (don't raise). `PassStore` enforces the store exists (it hard-fails on missing config — see the claude module).
- **Profile≠module rule:** profile `codex` differs from every module name (`codex-code`, `codex-config`, `codex-plugins`, `codex-mcp`, `codex-skills`).
- **Profile ordering (learned from the `claude` module):** modules declare `profiles=("codex",)`, so a `codex` profile stub MUST exist in `profiles.toml` AND in the two test profile tables (`tests/conftest.py` fixture, `tests/cli/test_lifecycle_devhygiene.py` inline) BEFORE any module loads — else `validate_profiles` fails load-wide. Task 1 adds the stub everywhere; Task 7 finalizes it.

## File Structure

```
dev-boost/
├─ dotfiles/private_dot_codex/            # delivered by existing Dotfiles module (chezmoi)
│  ├─ AGENTS.md                           # Codex global instructions (= CLAUDE.md analogue)
│  ├─ hooks.json.tmpl                     # SessionStart/Stop wiring ({{ .chezmoi.homeDir }} paths)
│  └─ hooks/executable_*.sh               # herdr + notify hook scripts
├─ dotfiles/private_dot_agents/skills/<name>/SKILL.md   # vendored skills (Codex reads ~/.agents/skills)
├─ engine/src/devboost/modules/
│  ├─ codex_code.py    codex_config.py    codex_plugins.py    codex_mcp.py    codex_skills.py
├─ engine/tests/modules/
│  ├─ test_codex_code.py  test_codex_config.py  test_codex_plugins.py
│  ├─ test_codex_mcp.py   test_codex_skills.py  test_codex_profile.py
├─ profiles.toml                          # codex profile (stub → finalized) + added to full
└─ scripts/import-codex-config.sh         # one-time migration
```

Consumed unchanged: `CodexCode` (new), `Dotfiles` (`modules/shell.py:154`), `Secrets` (`modules/secrets.py:44`), `PassStore` (`modules/optional.py:67`), `Mise` (`modules/mise.py`), `_lock_entries` (`modules/claude_skills.py`), `ENABLED_PLUGINS` (`modules/claude_plugins.py`).

---

## Task 1: `codex` profile stub + test-fixture registration

Unblocks `profiles=("codex",)` on the modules (avoids the load-wide `validate_profiles` failure the `claude` module hit).

**Files:** Modify `profiles.toml`, `engine/tests/conftest.py`, `engine/tests/cli/test_lifecycle_devhygiene.py`.

- [ ] **Step 1: Add the stub to `profiles.toml`** (after the `claude` line):

```toml
# codex — reusable OpenAI Codex CLI config bundle. Stub → finalized in the codex-profile task.
codex = ["codex-code"]
```

- [ ] **Step 2: Add `codex` to the `tests/conftest.py` `profiles_file` fixture** — insert after the `'claude = ["claude-code"]\n'` line:

```python
        'codex = ["codex-code"]\n'
```

- [ ] **Step 3: Add `codex` to the inline table in `tests/cli/test_lifecycle_devhygiene.py`** — change the `claude` line to also add codex:

```python
        'laravel = ["ddev"]\nclaude = ["claude-code"]\ncodex = ["codex-code"]\n',
```

- [ ] **Step 4: Gate** — `cd engine && uv run ruff check && uv run mypy && COLUMNS=80 uv run pytest -q`. Expected: green (no module references `codex` yet; the profile is just declared).

- [ ] **Step 5: Commit**

```bash
git add profiles.toml engine/tests/conftest.py engine/tests/cli/test_lifecycle_devhygiene.py
git commit -m "feat(codex): add codex profile stub (unblocks module profiles=(codex,))"
```

---

## Task 2: `codex-code` module

Installs the standalone Codex binary (self-updating) via the official installer; ensures node for `npx` (skills).

**Files:** Create `engine/src/devboost/modules/codex_code.py`, `engine/tests/modules/test_codex_code.py`.

**Interfaces:**
- Consumes: `Ctx`, `Module`, `register`, `mise` primitive, `Mise` module (same imports as `modules/claude_code.py`).
- Produces: `CodexCode` (`name="codex-code"`).

- [ ] **Step 1: Write the failing test**

```python
# engine/tests/modules/test_codex_code.py
from __future__ import annotations

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules.codex_code import CodexCode

FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_installs_via_official_standalone_script() -> None:
    ctx = _ctx(present={"node"})
    CodexCode().install(ctx)
    joined = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert any("chatgpt.com/codex/install.sh" in j for j in joined)


def test_provisions_node_when_absent() -> None:
    ctx = _ctx()  # node not present
    CodexCode().install(ctx)
    joined = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert any("node@lts" in j for j in joined)


def test_verify_uses_codex_binary() -> None:
    assert CodexCode().verify(_ctx(present={"codex"})) is True
    assert CodexCode().verify(_ctx()) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd engine && uv run pytest tests/modules/test_codex_code.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'devboost.modules.codex_code'`.

- [ ] **Step 3: Write minimal implementation**

```python
# engine/src/devboost/modules/codex_code.py
"""codex-code — install the OpenAI Codex CLI (standalone binary; self-updating)."""

from __future__ import annotations

from devboost.core.registry import register
from devboost.exec.primitives import mise
from devboost.model import Ctx, Module
from devboost.modules.mise import Mise


@register
class CodexCode(Module):
    name = "codex-code"
    category = "cli"
    description = "OpenAI Codex CLI (standalone binary; self-updating via `codex update`)."
    requires = (Mise,)  # node for `npx skills`
    profiles = ("codex",)

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which("codex")

    def install(self, ctx: Ctx) -> None:
        if not ctx.ex.which("node"):
            mise.use_global(ctx, "node@lts")
        # Official standalone installer → ~/.codex/packages/standalone, symlinked onto PATH.
        ctx.ex.run(["sh", "-c", "curl -fsSL https://chatgpt.com/codex/install.sh | sh"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd engine && uv run pytest tests/modules/test_codex_code.py -v` → PASS (3).

- [ ] **Step 5: Gate** — `uv run ruff check && uv run mypy` → clean.

- [ ] **Step 6: Commit**

```bash
git add engine/src/devboost/modules/codex_code.py engine/tests/modules/test_codex_code.py
git commit -m "feat(codex): codex-code installs the standalone Codex binary"
```

---

## Task 3: `codex-mcp` module

Registers the `google-docs` stdio MCP server via `codex mcp add … -- <cmd>` (idempotent). Drops `context7` (plugin covers it); `gdocs-batch`/`fathom` are excluded (device-local / not in Codex config).

**Files:** Create `engine/src/devboost/modules/codex_mcp.py`, `engine/tests/modules/test_codex_mcp.py`.

**Interfaces:** Produces `CodexMcp` (`name="codex-mcp"`), `CODEX_MCP_SERVERS: dict[str, list[str]]` (name → stdio command argv).

- [ ] **Step 1: Write the failing test**

```python
# engine/tests/modules/test_codex_mcp.py
from __future__ import annotations

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.codex_mcp import CODEX_MCP_SERVERS, CodexMcp

FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_manifest_is_google_docs_only_no_plaintext_key() -> None:
    assert set(CODEX_MCP_SERVERS) == {"google-docs"}
    assert "pass google-docs/" in " ".join(CODEX_MCP_SERVERS["google-docs"])
    assert "ctx7sk" not in " ".join(CODEX_MCP_SERVERS["google-docs"])


def test_install_adds_missing_server_via_dash_dash() -> None:
    ctx = _ctx(present={"codex"}, scripts={"codex": Result(0, stdout="[]")})
    CodexMcp().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    add = [c for c in calls if c[:3] == ["codex", "mcp", "add"]]
    assert add and add[0][3] == "google-docs" and "--" in add[0]


def test_install_skips_when_already_present() -> None:
    listed = '[{"name":"google-docs"}]'
    ctx = _ctx(present={"codex"}, scripts={"codex": Result(0, stdout=listed)})
    CodexMcp().install(ctx)
    assert not any(c[:3] == ["codex", "mcp", "add"] for c in ctx.ex.calls)  # type: ignore[attr-defined]
```

- [ ] **Step 2: Run test to verify it fails** — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# engine/src/devboost/modules/codex_mcp.py
"""codex-mcp — register the google-docs MCP server in Codex (context7 dropped; plugin covers it)."""

from __future__ import annotations

import json

from devboost.core import log
from devboost.core.registry import register
from devboost.model import Ctx, Module
from devboost.modules.codex_code import CodexCode

# stdio server; secrets resolved from `pass` at runtime inside the bash wrapper.
CODEX_MCP_SERVERS: dict[str, list[str]] = {
    "google-docs": [
        "bash",
        "-lc",
        'export GOOGLE_CLIENT_ID="$(pass google-docs/dits_client_id)"; '
        'export GOOGLE_CLIENT_SECRET="$(pass google-docs/dits_client_secret)"; '
        "exec npx -y @a-bonus/google-docs-mcp",
    ],
}


@register
class CodexMcp(Module):
    name = "codex-mcp"
    category = "cli"
    description = "Register Codex MCP servers (google-docs)."
    requires = (CodexCode,)
    profiles = ("codex",)

    def _installed(self, ctx: Ctx) -> set[str]:
        if not ctx.ex.which("codex"):
            return set()
        res = ctx.ex.run(["codex", "mcp", "list", "--json"])
        if not res.ok:
            return set()
        try:
            data = json.loads(res.stdout)
        except ValueError:
            return set()
        if isinstance(data, list):
            return {e["name"] for e in data if isinstance(e, dict) and isinstance(e.get("name"), str)}
        if isinstance(data, dict):
            return {k for k in data}
        return set()

    def verify(self, ctx: Ctx) -> bool:
        return set(CODEX_MCP_SERVERS).issubset(self._installed(ctx))

    def install(self, ctx: Ctx) -> None:
        if not ctx.ex.which("codex"):
            log.warn("codex-mcp: codex CLI not found — skipping MCP registration")
            return
        present = self._installed(ctx)
        for name, cmd in CODEX_MCP_SERVERS.items():
            if name in present:
                log.skip(f"codex-mcp: {name} already registered")
                continue
            res = ctx.ex.run(["codex", "mcp", "add", name, "--", *cmd])
            if not res.ok:
                log.warn(f"codex-mcp: failed to add {name}: {res.stderr.strip()}")
```

- [ ] **Step 4: Run tests** → PASS (3).
- [ ] **Step 5: Gate** → clean.
- [ ] **Step 6: Commit**

```bash
git add engine/src/devboost/modules/codex_mcp.py engine/tests/modules/test_codex_mcp.py
git commit -m "feat(codex): codex-mcp registers google-docs (context7 dropped)"
```

---

## Task 4: `codex-skills` module

Ensures the shared `~/.agents/skills` (which Codex auto-discovers, USER scope) is populated via `npx skills add … -g` per lock entry. Vendored non-lock skills arrive via `Dotfiles` into `~/.agents/skills` (Task 8). Idempotent: only adds skills whose `~/.agents/skills/<name>` is absent (no-ops if the claude module already populated it).

**Files:** Create `engine/src/devboost/modules/codex_skills.py`, `engine/tests/modules/test_codex_skills.py`.

**Interfaces:** Consumes `_lock_entries` from `modules/claude_skills.py`. Produces `CodexSkills` (`name="codex-skills"`).

- [ ] **Step 1: Write the failing test**

```python
# engine/tests/modules/test_codex_skills.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules.codex_skills import CodexSkills

FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def _write_lock(home: Path) -> None:
    lock = home / ".agents" / ".skill-lock.json"
    lock.parent.mkdir(parents=True)
    lock.write_text(
        json.dumps({"version": 3, "skills": {"caveman": {"source": "mattpocock/skills"}}}),
        encoding="utf-8",
    )


def test_install_adds_lock_entry_for_codex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_lock(tmp_path)
    ctx = _ctx(present={"npx"})
    CodexSkills().install(ctx)
    joined = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert any("skills add mattpocock/skills@caveman -g -y" in j for j in joined)


def test_install_skips_present_codex_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_lock(tmp_path)
    (tmp_path / ".agents" / "skills" / "caveman").mkdir(parents=True)
    ctx = _ctx(present={"npx"})
    CodexSkills().install(ctx)
    assert not any("@caveman" in " ".join(c) for c in ctx.ex.calls)  # type: ignore[attr-defined]
```

- [ ] **Step 2: Run test to verify it fails** — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# engine/src/devboost/modules/codex_skills.py
"""codex-skills — ensure ~/.agents/skills (Codex's shared USER skills) is populated via npx skills."""

from __future__ import annotations

import os
from pathlib import Path

from devboost.core import log
from devboost.core.registry import register
from devboost.model import Ctx, Module
from devboost.modules.claude_skills import _lock_entries
from devboost.modules.codex_code import CodexCode
from devboost.modules.shell import Dotfiles


def _home() -> Path:
    return Path(os.environ["HOME"])


@register
class CodexSkills(Module):
    name = "codex-skills"
    category = "cli"
    description = "Ensure ~/.agents/skills (Codex USER skills, shared with ~/.claude) is populated."
    requires = (CodexCode, Dotfiles)
    profiles = ("codex",)

    def _present(self, name: str) -> bool:
        # Codex reads USER skills from ~/.agents/skills (auto-discovered) — the same real-content
        # dir ~/.claude/skills symlinks into. NOT ~/.codex/skills; no -a codex / [[skills.config]].
        p = _home() / ".agents" / "skills" / name
        return p.exists() or p.is_symlink()

    def verify(self, ctx: Ctx) -> bool:
        return all(self._present(name) for _, name in _lock_entries(_home()))

    def install(self, ctx: Ctx) -> None:
        if not ctx.ex.which("npx"):
            log.warn("codex-skills: npx not found — skipping skill hydration")
            return
        for source, name in _lock_entries(_home()):
            if self._present(name):
                log.skip(f"codex-skills: {name} already present")
                continue
            res = ctx.ex.run(["npx", "skills", "add", f"{source}@{name}", "-g", "-y"])
            if not res.ok:
                log.warn(f"codex-skills: `skills add {source}@{name}` failed — vendor it instead")
```

- [ ] **Step 4: Run tests** → PASS (2).
- [ ] **Step 5: Gate** → clean.
- [ ] **Step 6: Commit**

```bash
git add engine/src/devboost/modules/codex_skills.py engine/tests/modules/test_codex_skills.py
git commit -m "feat(codex): codex-skills populates shared ~/.agents/skills via npx skills"
```

---

## Task 5: `codex-plugins` module

Registers marketplaces (`codex plugin marketplace add <source>`) and installs the enabled plugins (`codex plugin add PLUGIN@MARKETPLACE`), idempotently. Reuses the 18-plugin `ENABLED_PLUGINS` from the claude module.

**Files:** Create `engine/src/devboost/modules/codex_plugins.py`, `engine/tests/modules/test_codex_plugins.py`.

**Interfaces:** Consumes `ENABLED_PLUGINS` from `modules/claude_plugins.py`. Produces `CodexPlugins` (`name="codex-plugins"`), `CODEX_MARKETPLACES: dict[str, str]` (name → source).

- [ ] **Step 1: Write the failing test**

```python
# engine/tests/modules/test_codex_plugins.py
from __future__ import annotations

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.claude_plugins import ENABLED_PLUGINS
from devboost.modules.codex_plugins import CODEX_MARKETPLACES, CodexPlugins

FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_clickup_marketplace_is_github_source() -> None:
    assert CODEX_MARKETPLACES["clickup-flow-marketplace"] == "adams100111/clickup-flow"
    assert not any(v.startswith("/") for v in CODEX_MARKETPLACES.values())  # no local paths


def test_install_adds_missing_marketplaces_and_plugins() -> None:
    # marketplace list empty; plugin list --available --json reports superpowers installed
    def script(argv: list[str]) -> Result:  # not used directly; FakeExecutor keys on argv[0]
        return Result(0)

    ctx = _ctx(
        present={"codex"},
        scripts={"codex": Result(0, stdout='[{"name":"superpowers","installed":true}]')},
    )
    CodexPlugins().install(ctx)
    joined = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert any("plugin marketplace add adams100111/clickup-flow" in j for j in joined)
    assert any("plugin add clickup-flow@clickup-flow-marketplace" in j for j in joined)
    # superpowers already installed → not re-added
    assert not any("plugin add superpowers@" in j for j in joined)
```

Note: `codex plugin list --available --json` returns entries with `name` (and an installed flag). The test stub returns the same JSON for every `codex` call; that's fine — the marketplace-list branch sees the same JSON (no marketplace named after those entries) and still adds marketplaces.

- [ ] **Step 2: Run test to verify it fails** — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# engine/src/devboost/modules/codex_plugins.py
"""codex-plugins — register Codex marketplaces + install enabled plugins (reuses the claude set)."""

from __future__ import annotations

import json

from devboost.core import log
from devboost.core.registry import register
from devboost.model import Ctx, Module
from devboost.modules.claude_plugins import ENABLED_PLUGINS
from devboost.modules.codex_code import CodexCode
from devboost.modules.secrets import Secrets

# marketplace name → source (owner/repo). clickup-flow was a local path → github for portability.
CODEX_MARKETPLACES: dict[str, str] = {
    "claude-plugins-official": "anthropics/claude-plugins-official",
    "qa-e2e-pilot": "adams100111/qa-e2e-pilot",
    "wave-pilot": "adams100111/wave-pilot",
    "ui-ux-pro-max-skill": "nextlevelbuilder/ui-ux-pro-max-skill",
    "clickup-flow-marketplace": "adams100111/clickup-flow",
}


@register
class CodexPlugins(Module):
    name = "codex-plugins"
    category = "cli"
    description = "Register Codex marketplaces + install enabled plugins."
    requires = (CodexCode, Secrets)  # Secrets → git creds for the private clickup-flow marketplace
    profiles = ("codex",)

    def _codex_json(self, ctx: Ctx, *args: str) -> object:
        res = ctx.ex.run(["codex", *args])
        if not res.ok:
            return None
        try:
            return json.loads(res.stdout)
        except ValueError:
            return None

    def _installed_marketplaces(self, ctx: Ctx) -> str:
        res = ctx.ex.run(["codex", "plugin", "marketplace", "list"])
        return res.stdout if res.ok else ""

    def _installed_plugins(self, ctx: Ctx) -> set[str]:
        data = self._codex_json(ctx, "plugin", "list", "--available", "--json")
        names: set[str] = set()
        if isinstance(data, list):
            for e in data:
                if isinstance(e, dict) and e.get("installed") and isinstance(e.get("name"), str):
                    names.add(e["name"])
        return names

    def verify(self, ctx: Ctx) -> bool:
        if not ctx.ex.which("codex"):
            return False
        installed = self._installed_plugins(ctx)
        return all(p.split("@", 1)[0] in installed for p in ENABLED_PLUGINS)

    def install(self, ctx: Ctx) -> None:
        if not ctx.ex.which("codex"):
            log.warn("codex-plugins: codex CLI not found — skipping")
            return
        markets = self._installed_marketplaces(ctx)
        for name, source in CODEX_MARKETPLACES.items():
            if name in markets:
                log.skip(f"codex-plugins: marketplace {name} already configured")
                continue
            res = ctx.ex.run(["codex", "plugin", "marketplace", "add", source])
            if not res.ok:
                log.warn(f"codex-plugins: marketplace add {source} failed: {res.stderr.strip()}")
        installed = self._installed_plugins(ctx)
        for plugin in ENABLED_PLUGINS:
            if plugin.split("@", 1)[0] in installed:
                log.skip(f"codex-plugins: {plugin} already installed")
                continue
            res = ctx.ex.run(["codex", "plugin", "add", plugin, "--json"])
            if not res.ok:
                log.warn(f"codex-plugins: install {plugin} failed: {res.stderr.strip()}")
```

- [ ] **Step 4: Run tests** → PASS.
- [ ] **Step 5: Gate** → clean.
- [ ] **Step 6: Commit**

```bash
git add engine/src/devboost/modules/codex_plugins.py engine/tests/modules/test_codex_plugins.py
git commit -m "feat(codex): codex-plugins registers marketplaces + installs enabled plugins"
```

---

## Task 6: `codex-config` module (TOML merge)

Merges the shareable `config.toml` sections — prefs (`model`, `model_reasoning_effort`), `[features]`, `[shell_environment_policy]` (incl CLICKUP from `pass`) — via `tomllib` read + `tomli_w` write, preserving all device state.

**Files:** Create `engine/src/devboost/modules/codex_config.py`, `engine/tests/modules/test_codex_config.py`.

**Interfaces:** Produces `CodexConfig` (`name="codex-config"`), `CODEX_PREFS: dict[str, str]`, helper `_deep_merge(base, overlay)`.

> approval_policy / sandbox_mode are in-scope but the operator's live config leaves them at Codex
> defaults (unset). They are intentionally NOT hardcoded here (that would impose values the operator
> never chose); add them to `CODEX_PREFS` once the operator specifies desired values. Recorded as a
> follow-up, not a gap.

- [ ] **Step 1: Write the failing test**

```python
# engine/tests/modules/test_codex_config.py
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.codex_config import CodexConfig

FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_merge_sets_prefs_and_preserves_device_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = tmp_path / ".codex" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        '[projects."/x"]\ntrust_level = "trusted"\n\n[mcp_servers.foo]\ncommand = "bar"\n',
        encoding="utf-8",
    )
    ctx = _ctx(present={"pass"}, scripts={"pass": Result(0, stdout="pk_secret_9\n")})
    CodexConfig().install(ctx)

    data = tomllib.loads(cfg.read_text(encoding="utf-8"))
    assert data["model"] == "gpt-5.6-sol"
    assert data["model_reasoning_effort"] == "low"
    assert data["features"]["hooks"] is True
    assert data["shell_environment_policy"]["inherit"] == "core"
    assert data["shell_environment_policy"]["set"]["CLICKUP_API_TOKEN"] == "pk_secret_9"
    # device state preserved untouched
    assert data["projects"]["/x"]["trust_level"] == "trusted"
    assert data["mcp_servers"]["foo"]["command"] == "bar"


def test_merge_degrades_without_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".codex").mkdir(parents=True)
    ctx = _ctx()  # pass absent
    CodexConfig().install(ctx)  # must not raise
    data = tomllib.loads((tmp_path / ".codex" / "config.toml").read_text(encoding="utf-8"))
    assert data["model"] == "gpt-5.6-sol"  # prefs still applied
    assert "set" not in data.get("shell_environment_policy", {})  # token skipped
```

- [ ] **Step 2: Run test to verify it fails** — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# engine/src/devboost/modules/codex_config.py
"""codex-config — merge shareable ~/.codex/config.toml sections (prefs, features, shell env)."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

import tomli_w

from devboost.core import log
from devboost.core.registry import register
from devboost.model import Ctx, Module
from devboost.modules.codex_code import CodexCode
from devboost.modules.optional import PassStore
from devboost.modules.shell import Dotfiles

CODEX_PREFS: dict[str, str] = {
    "model": "gpt-5.6-sol",
    "model_reasoning_effort": "low",
}


def _home() -> Path:
    return Path(os.environ["HOME"])


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


@register
class CodexConfig(Module):
    name = "codex-config"
    category = "cli"
    description = "Merge shareable ~/.codex/config.toml prefs/features/shell-env (CLICKUP via pass)."
    requires = (CodexCode, Dotfiles, PassStore)
    profiles = ("codex",)

    def _config_path(self) -> Path:
        return _home() / ".codex" / "config.toml"

    def _clickup(self, ctx: Ctx) -> str | None:
        if not ctx.ex.which("pass"):
            log.warn("codex-config: pass not configured — skipping CLICKUP_API_TOKEN")
            return None
        res = ctx.ex.run(["pass", "show", "clickup/api-token"])
        token = res.stdout.strip()
        if not res.ok or not token:
            log.warn("codex-config: `pass show clickup/api-token` missing — skipping token")
            return None
        return token

    def verify(self, ctx: Ctx) -> bool:
        path = self._config_path()
        if not path.exists():
            return False
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            return False
        return data.get("model") == CODEX_PREFS["model"] and bool(
            data.get("features", {}).get("hooks")
        )

    def install(self, ctx: Ctx) -> None:
        path = self._config_path()
        data: dict[str, Any] = {}
        if path.exists():
            try:
                data = tomllib.loads(path.read_text(encoding="utf-8"))
            except tomllib.TOMLDecodeError:
                log.warn("codex-config: config.toml is not valid TOML — left untouched")
                return
        managed: dict[str, Any] = dict(CODEX_PREFS)
        managed["features"] = {"hooks": True}
        managed["shell_environment_policy"] = {"inherit": "core"}
        token = self._clickup(ctx)
        if token is not None:
            managed["shell_environment_policy"]["set"] = {"CLICKUP_API_TOKEN": token}
        _deep_merge(data, managed)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tomli_w.dumps(data) + "", encoding="utf-8")
```

- [ ] **Step 4: Run tests** → PASS (2).
- [ ] **Step 5: Gate** → clean (confirms `tomli_w` import resolves; it is already a dep).
- [ ] **Step 6: Commit**

```bash
git add engine/src/devboost/modules/codex_config.py engine/tests/modules/test_codex_config.py
git commit -m "feat(codex): codex-config TOML-merges prefs/features/shell-env (CLICKUP via pass)"
```

---

## Task 7: `codex` profile finalize

Expand the `codex = ["codex-code"]` stub to all five modules and add `codex` to `full`.

**Files:** Modify `profiles.toml`; create `engine/tests/modules/test_codex_profile.py`.

- [ ] **Step 1: Write the failing test**

```python
# engine/tests/modules/test_codex_profile.py
from __future__ import annotations

from pathlib import Path

from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_codex_profile_expands_to_the_five_modules() -> None:
    modules = load()
    profiles = load_profiles(REPO_ROOT / "profiles.toml")
    resolved = expand(["codex"], profiles, modules)
    names = {r if isinstance(r, str) else getattr(r, "name", None) for r in resolved}
    assert {"codex-code", "codex-config", "codex-plugins", "codex-mcp", "codex-skills"} <= names
```

- [ ] **Step 2: Run test to verify it fails** — `AssertionError` (stub expands only to `{codex-code}`).

- [ ] **Step 3: Edit `profiles.toml`** — replace the stub line with:

```toml
codex = ["codex-code","codex-config","codex-plugins","codex-mcp","codex-skills"]
```

And add `"codex"` to `full`:

```toml
full = ["base","cli","shell","gnome","multimedia","editors","python","web","laravel",
        "dotnet","data","devops","react-native","apps","system","dev-hygiene","remote","claude","codex"]
```

- [ ] **Step 4: Run test** → PASS. **Step 5: full gate** → green. **Step 6: Commit**

```bash
git add profiles.toml engine/tests/modules/test_codex_profile.py
git commit -m "feat(codex): finalize codex profile (5 modules) and add to full"
```

---

## Task 8: Import script + seed dotfiles (migration, human-in-the-loop)

Mirror the claude migration for Codex: copy `AGENTS.md` + `hooks.json` + hook scripts into the chezmoi source; vendor the same non-lock skills as Codex `SKILL.md` dirs; drop the live `context7` MCP; the CLICKUP token is already in `pass`.

**Files:** Create `scripts/import-codex-config.sh`; generated `dotfiles/private_dot_codex/{AGENTS.md,hooks.json.tmpl,hooks/*}` and vendored `dotfiles/private_dot_agents/skills/<name>/` (Codex reads `~/.agents/skills`).

- [ ] **Step 1: Write `scripts/import-codex-config.sh`**

```bash
#!/usr/bin/env bash
# import-codex-config.sh — one-time seed of the repo from the live ~/.codex. Read-only on ~/.codex
# except the secret-scrub PREVIEW. Makes NO git commit. Safe to re-run.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CODEX="$HOME/.codex"
DOT="$REPO_ROOT/dotfiles/private_dot_codex"
mkdir -p "$DOT/hooks"

# 1. AGENTS.md — copy, then fix the copy-paste attribution artifact (Codex/OpenAI, dedup)
if [ -f "$CODEX/AGENTS.md" ]; then
  sed -e 's/reference to Codex, Codex, or Anthropic/reference to Codex or OpenAI/g' \
      -e 's/Codex\/Anthropic attribution/OpenAI\/Codex attribution/g' \
      -e 's/or any Codex\/Anthropic/or any OpenAI\/Codex/g' \
      "$CODEX/AGENTS.md" > "$DOT/AGENTS.md"
fi

# 2. hooks.json -> hooks.json.tmpl: replace the literal HOME with a chezmoi template var so the
#    hook-script paths resolve to the real HOME on every device (any username).
[ -f "$CODEX/hooks.json" ] && \
  sed "s|$HOME|{{ .chezmoi.homeDir }}|g" "$CODEX/hooks.json" > "$DOT/hooks.json.tmpl"
if [ -d "$CODEX/hooks" ]; then
  for f in "$CODEX/hooks"/*; do [ -f "$f" ] && cp "$f" "$DOT/hooks/executable_$(basename "$f")"; done
fi

# NOTE: Codex USER skills live in ~/.agents/skills (auto-discovered, shared with ~/.claude), NOT
# ~/.codex/skills (which holds only bundled .system skills). Vendored skills are seeded separately
# into dotfiles/private_dot_agents/skills below.

# 3. secret-scrub PREVIEW (read-only; does not modify ~/.codex)
echo "=== SECRET SCRUB (Codex) ==="
python3 - "$CODEX/config.toml" <<'PY'
import os, sys, tomllib
p = sys.argv[1]
if os.path.isfile(p):
    d = tomllib.loads(open(p, encoding="utf-8").read())
    if (d.get("shell_environment_policy", {}).get("set", {})).get("CLICKUP_API_TOKEN"):
        print("  config.toml CLICKUP_API_TOKEN present -> already in pass; codex-config re-supplies it")
    if "context7" in d.get("mcp_servers", {}):
        print("  context7 MCP (inline ctx7sk key) -> drop: `codex mcp remove context7`; plugin covers it")
PY
echo "=== DONE. Vendor chosen skills into dotfiles/private_dot_agents/skills/ (~/.agents/skills), then commit. ==="
```

- [ ] **Step 2: `chmod +x scripts/import-codex-config.sh`; `bash -n` it; shellcheck if available. Commit the script only.**

```bash
git add scripts/import-codex-config.sh
git commit -m "feat(codex): one-time import script (AGENTS.md, hooks, skills report, secret scrub)"
```

- [ ] **Step 3: Run the import; vendor the same 14 non-lock skills into `~/.agents/skills`**

Run `./scripts/import-codex-config.sh`, then vendor into `private_dot_agents/skills` (Codex
auto-discovers `~/.agents/skills`; SKILL.md format is compatible, reuse the claude content):

```bash
mkdir -p dotfiles/private_dot_agents/skills
for s in agents-sdk cloudflare cloudflare-email-service cloudflare-one cloudflare-one-migrations \
         context7-mcp durable-objects find-docs sandbox-sdk sharpen turnstile-spin web-perf \
         workers-best-practices wrangler; do
  cp -aL "dotfiles/private_dot_claude/skills/$s" "dotfiles/private_dot_agents/skills/$s"
done
```

- [ ] **Step 4: Live migration** — drop the context7 MCP from Codex (the token is already in `pass`):

```bash
codex mcp remove context7 2>/dev/null || true
```

- [ ] **Step 5: Secret-scan the seeded dotfiles (must be clean of REAL secrets)**

```bash
! grep -rniE 'ctx7sk-f4f06e7a|pk_89590270|dits_client|GLBO6ZND' \
    dotfiles/private_dot_codex/ dotfiles/private_dot_agents/ && echo clean
```

- [ ] **Step 6: Verify chezmoi applies (incl. the hooks template) + commit the seeded config**

```bash
DEST=$(mktemp -d); chezmoi apply --force --source "$PWD/dotfiles" --destination "$DEST" >/dev/null 2>&1
ls "$DEST/.codex/AGENTS.md" "$DEST/.codex/hooks.json"   # hooks.json.tmpl -> hooks.json (HOME resolved)
! grep -q '{{' "$DEST/.codex/hooks.json" && echo "hooks template rendered (no raw {{ left)"
ls "$DEST/.agents/skills/" | wc -l                       # vendored skills land in ~/.agents/skills
rm -rf "$DEST"
git add dotfiles/private_dot_codex dotfiles/private_dot_agents
git commit -m "feat(codex): seed managed ~/.codex config (AGENTS.md, hooks.tmpl) + ~/.agents skills"
```

---

## Self-Review

**Spec coverage** (vs `2026-09-07-codex-module-design.md`): dotfiles (AGENTS.md/hooks/vendored skills) → Tasks 1,8; `codex-code`→2; `codex-mcp`→3; `codex-skills`→4; `codex-plugins`→5; `codex-config`→6; profile→1,7; import→8; secrets (pass reuse, CLICKUP→shell_env, context7 dropped)→6,8; TOML merge preserving device state→6.

**Placeholder scan:** no TBD/TODO; complete code per step. The one deferred item (approval_policy/sandbox_mode values) is explicitly recorded in Task 6, not a silent gap.

**Type consistency:** `CODEX_MCP_SERVERS: dict[str,list[str]]`, `CODEX_MARKETPLACES: dict[str,str]`, `CODEX_PREFS: dict[str,str]`, reused `ENABLED_PLUGINS`/`_lock_entries`; `FakeExecutor` `.calls/.scripts/.present` per `exec/executor.py`.

**Verified against source/binary:** `codex plugin marketplace add <source>`, `codex plugin add PLUGIN@MARKETPLACE --json`, `codex plugin list --available --json`, `codex mcp add NAME -- <cmd>` / `--url`, `codex mcp list --json`, `npx skills add … -g` into the shared `~/.agents/skills` (Codex USER scope, auto-discovered — corrected during grilling from the wrong `~/.codex/skills`), `tomli_w` present. Profile-ordering fix (stub in profiles.toml + both test tables) carried over from the `claude` module.
