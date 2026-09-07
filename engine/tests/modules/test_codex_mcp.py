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
