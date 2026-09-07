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
