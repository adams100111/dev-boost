from __future__ import annotations

from collections.abc import Mapping

import pytest
import typer

from devboost.cli.selection import group_choices, resolve_apps, select_modules
from devboost.core import log
from devboost.model import Module


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


class _Cli(Module):
    name = "git"
    category = "Terminal tools"


class _Gui(Module):
    name = "obsidian"
    category = "GUI apps"


class _Bare(Module):
    name = "mystery"
    category = ""


_MODS: Mapping[str, type[Module]] = {"git": _Cli, "obsidian": _Gui, "mystery": _Bare}


def test_group_choices_groups_by_category_sorted_with_other_bucket() -> None:
    rows = group_choices(["git", "obsidian", "mystery"], _MODS)
    assert rows == [
        ("GUI apps", None),
        (None, "obsidian"),
        ("Other", None),
        (None, "mystery"),
        ("Terminal tools", None),
        (None, "git"),
    ]


def test_select_modules_all_returns_expanded() -> None:
    assert select_modules(["git", "obsidian"], _MODS, all_=True, apps=[]) == ["git", "obsidian"]


def test_select_modules_apps_takes_precedence_over_all() -> None:
    assert select_modules(["git", "obsidian"], _MODS, all_=True, apps=["obsidian"]) == ["obsidian"]


def test_select_modules_no_all_uses_injected_checklist() -> None:
    captured: dict[str, object] = {}

    def fake_checklist(expanded: list[str], modules: Mapping[str, type[Module]]) -> list[str]:
        captured["expanded"] = list(expanded)
        return ["git"]

    out = select_modules(["git", "obsidian"], _MODS, all_=False, apps=[], checklist=fake_checklist)
    assert out == ["git"]
    assert captured["expanded"] == ["git", "obsidian"]
