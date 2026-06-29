from __future__ import annotations

import pytest
import typer

from devboost.cli.selection import resolve_apps
from devboost.core import log


def test_resolve_apps_returns_requested_when_all_known() -> None:
    assert resolve_apps(["git", "fzf", "bat"], ["fzf", "git"]) == ["fzf", "git"]


def test_resolve_apps_dedupes_preserving_order() -> None:
    assert resolve_apps(["git", "fzf"], ["git", "git", "fzf"]) == ["git", "fzf"]


def test_resolve_apps_unknown_raises_exit_with_suggestion(monkeypatch: pytest.MonkeyPatch) -> None:
    errors: list[str] = []

    def capture_error(msg: str) -> None:
        errors.append(msg)

    monkeypatch.setattr(log, "error", capture_error)
    with pytest.raises(typer.Exit) as exc:
        resolve_apps(["git", "fzf", "bat"], ["gti"])
    assert exc.value.exit_code == 2
    assert len(errors) == 1
    assert "unknown app 'gti'" in errors[0]
    assert "git" in errors[0]  # suggestion
