from __future__ import annotations

import json

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.claude_plugins import ENABLED_PLUGINS
from devboost.modules.codex_plugins import CODEX_MARKETPLACES, CodexPlugins

FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_every_shipped_marketplace_is_public_and_not_a_local_path() -> None:
    """Shipping the private clickup-flow marketplace made every other install try to
    register a repo it cannot read. Private ones go in `extra_marketplaces`."""
    assert not any(v.startswith("/") for v in CODEX_MARKETPLACES.values())  # no local paths
    assert "adams100111/clickup-flow" not in set(CODEX_MARKETPLACES.values())


def test_a_users_own_marketplace_is_merged_in() -> None:
    from devboost.core.userconfig import UserConfig
    from devboost.modules.codex_plugins import codex_marketplaces

    cfg = UserConfig(extra_marketplaces={"mine": "someone/their-market"})
    assert codex_marketplaces(cfg)["mine"] == "someone/their-market"
    assert set(CODEX_MARKETPLACES) <= set(codex_marketplaces(cfg))


def test_install_adds_missing_marketplaces_and_plugins() -> None:
    # marketplace list empty; plugin list --available --json wraps entries under "installed"
    # (unlike `claude plugin list --json`, which returns a bare list) — reports superpowers
    ctx = _ctx(
        present={"codex"},
        scripts={"codex": Result(
            0, stdout='{"installed":[{"name":"superpowers","installed":true}],"available":[]}'
        )},
    )
    CodexPlugins().install(ctx)
    joined = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    assert any("plugin marketplace add zoom/skills" in j or
               "plugin marketplace add nextlevelbuilder/ui-ux-pro-max-skill" in j
               for j in joined)
    assert any("plugin add ui-ux-pro-max@ui-ux-pro-max-skill" in j for j in joined)
    # superpowers already installed → not re-added
    assert not any("plugin add superpowers@" in j for j in joined)


def test_verify_reads_installed_list_from_wrapped_json_object() -> None:
    # Regression: codex's real --json shape is {"installed": [...], "available": [...]},
    # not a bare list — verify() must not silently see zero plugins as installed.
    names = [p.split("@", 1)[0] for p in ENABLED_PLUGINS]
    entries = [{"name": n, "installed": True} for n in names]
    ctx = _ctx(
        present={"codex"},
        scripts={"codex": Result(
            0, stdout=json.dumps({"installed": entries, "available": []})
        )},
    )
    assert CodexPlugins().verify(ctx) is True


def test_verify_false_when_codex_returns_a_bare_list_missing_entries() -> None:
    ctx = _ctx(present={"codex"}, scripts={"codex": Result(0, stdout="[]")})
    assert CodexPlugins().verify(ctx) is False
