from __future__ import annotations

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
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
