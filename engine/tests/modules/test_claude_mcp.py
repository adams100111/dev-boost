from __future__ import annotations

import json

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.claude_mcp import MCP_SERVERS, ClaudeMcp

FEDORA = OsInfo("fedora", "fedora", "x86_64")


def _ctx(**kw: object) -> Ctx:
    return Ctx(os=FEDORA, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def test_manifest_is_google_docs_and_fathom_only() -> None:
    assert set(MCP_SERVERS) == {"google-docs", "fathom"}
    # google-docs resolves its secrets from pass at runtime, not from committed config
    assert "pass google-docs/" in MCP_SERVERS["google-docs"]
    # no plaintext api key anywhere in the manifest
    assert "ctx7sk" not in json.dumps(MCP_SERVERS)


def test_manifest_entries_are_valid_json() -> None:
    # catches any escaping bug in the google-docs bash/pass wrapper
    for spec in MCP_SERVERS.values():
        json.loads(spec)  # must not raise


def test_install_adds_only_missing_servers() -> None:
    # `claude mcp list` reports google-docs already present → only fathom is added.
    ctx = _ctx(present={"claude"}, scripts={"claude": Result(0, stdout="google-docs: connected\n")})
    ClaudeMcp().install(ctx)
    joined = [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]
    add_calls = [j for j in joined if "mcp add-json" in j]
    assert any("fathom" in j and "--scope user" in j for j in add_calls)
    assert not any("google-docs" in j for j in add_calls)  # already present, skipped


def test_verify_true_when_both_present() -> None:
    ctx = _ctx(
        present={"claude"},
        scripts={"claude": Result(0, stdout="google-docs: connected\nfathom: connected\n")},
    )
    assert ClaudeMcp().verify(ctx) is True
