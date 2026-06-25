from devboost.manifest import Module
from devboost.osinfo import OsInfo
from devboost.plan import build_plan, resolve_steps


def _m(name: str, install: dict[str, str], fallback: dict[str, str] = {}, gui: bool = False) -> Module:
    return Module(name, "cli", f"command -v {name}", (), install, fallback, gui)


FEDORA = OsInfo("fedora", "fedora", "x86_64")
UBUNTU = OsInfo("ubuntu", "debian", "x86_64")


def test_resolve_prefers_distro_then_fallback() -> None:
    mod = _m("eza", {"fedora": "dnf eza"}, {"mise": "aqua:eza-community/eza"})
    # On ubuntu there's no apt key -> falls to mise ladder step
    assert resolve_steps(mod, UBUNTU) == ("mise use -g aqua:eza-community/eza",)
    # On fedora the distro install wins, mise still appended as fallback
    assert resolve_steps(mod, FEDORA) == ("dnf eza", "mise use -g aqua:eza-community/eza")


def test_build_plan_skips_gui_when_headless() -> None:
    mods = {"ghostty": _m("ghostty", {"fedora": "echo g"}, gui=True)}
    plan = build_plan(["ghostty"], mods, FEDORA, headless=True)
    assert plan[0].skip_reason == "headless-gui"


def test_build_plan_marks_unsupported() -> None:
    mods = {"x": _m("x", {"fedora": "echo x"})}
    plan = build_plan(["x"], mods, UBUNTU, headless=False)
    assert plan[0].skip_reason == "unsupported-os"
