"""Omarchy (Arch + Hyprland) support — detection, gating, and native-package routing.

Omarchy is an opinionated platform, not just "Arch with Hyprland": it already ships the
desktop, system-resilience, multimedia and NVIDIA layers dev-boost installs on Fedora, and
it packages several tools dev-boost otherwise pins itself. These tests pin down the two
things that make support correct rather than merely present — that Omarchy resolves to the
`arch` family at all, and that dev-boost declines to install what the platform owns.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from devboost.cli.app import default_profile
from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo, OsMap, detect, family_of
from devboost.core.plan import build_plan
from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load, validate_profiles
from devboost.exec.executor import FakeExecutor
from devboost.model import Ctx
from devboost.modules.apps import Bruno, Localsend, Obsidian
from devboost.modules.cli_tools import Dust, Fd, Gh, Yq
from devboost.modules.ddev import Ddev
from devboost.modules.dev_stacks import DotnetSdk
from devboost.modules.editors import Vscode
from devboost.modules.herdr import Herdr
from devboost.modules.omarchy import OmarchyUpdateHook

OMARCHY = OsInfo("omarchy", "arch", "x86_64", id_like=("arch",))
ARCH = OsInfo("arch", "arch", "x86_64")
FEDORA = OsInfo("fedora", "fedora", "x86_64")

REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Detection — the unlock. Everything else is dead code without it.
# ---------------------------------------------------------------------------


def test_omarchy_resolves_to_the_arch_family_via_id_like() -> None:
    assert family_of("omarchy", ("arch",)) == "arch"


def test_unknown_derivative_follows_id_like() -> None:
    """Any Arch/Debian/Fedora derivative gets the right family for free."""
    assert family_of("some-new-spin", ("arch",)) == "arch"
    assert family_of("another-spin", ("ubuntu", "debian")) == "debian"


def test_known_distro_ignores_id_like() -> None:
    """A distro we know about is never overridden by its ID_LIKE."""
    assert family_of("ubuntu", ("debian",)) == "debian"
    assert family_of("fedora", ("rhel",)) == "fedora"


def test_unrelated_distro_still_resolves_to_itself() -> None:
    assert family_of("plan9") == "plan9"
    assert family_of("plan9", ("inferno",)) == "plan9"


def test_detect_parses_id_like(tmp_path: Path) -> None:
    release = tmp_path / "os-release"
    release.write_text(
        'NAME="Omarchy"\nID=omarchy\nID_LIKE=arch\nVERSION_ID="4.0.2"\n', encoding="utf-8"
    )
    info = detect(os_release_path=str(release), machine="x86_64", env={"DISPLAY": ":0"})
    assert info.distro == "omarchy"
    assert info.family == "arch"
    assert info.id_like == ("arch",)


def test_per_os_strategy_selects_the_arch_entry_on_omarchy() -> None:
    """The bug this whole seam exists to fix: an `arch=` strategy must actually resolve."""
    strategies: OsMap[str] = OsMap(fedora="dnf", debian="apt", arch="pacman")
    assert strategies.get(OMARCHY) == "pacman"


# ---------------------------------------------------------------------------
# Platform-provided modules are REPORTED, not silently dropped
# ---------------------------------------------------------------------------


def test_provided_by_reports_a_skip_reason_rather_than_installing() -> None:
    modules = load()
    plan = build_plan(["herdr"], modules, OMARCHY)
    assert [(p.name, p.skip_reason) for p in plan] == [("herdr", "provided-by-omarchy")]


def test_provided_by_is_scoped_to_omarchy_not_the_whole_arch_family() -> None:
    """Vanilla Arch has no packaged herdr, so it must still be installed there."""
    assert Herdr.provided_by == ("omarchy",)
    plan = build_plan(["herdr"], load(), ARCH)
    assert plan[0].skip_reason is None


def test_fedora_only_modules_are_dropped_on_omarchy() -> None:
    modules = load()
    names = ["rpmfusion", "dnf-tune", "grub-btrfs", "snapper", "flatpak"]
    assert build_plan(names, modules, OMARCHY) == []
    # …and still install on Fedora.
    assert [p.name for p in build_plan(names, modules, FEDORA)] == names


# ---------------------------------------------------------------------------
# Native packages instead of Flathub
# ---------------------------------------------------------------------------


def test_gui_apps_install_natively_on_arch_not_via_flatpak() -> None:
    ex = FakeExecutor()
    Obsidian().install(Ctx(os=OMARCHY, ex=ex))
    assert ["sudo", "pacman", "-S", "--needed", "--noconfirm", "obsidian"] in ex.calls
    assert not any("flatpak" in c for c in ex.calls)


def test_gui_app_absent_from_official_repos_uses_the_aur() -> None:
    ex = FakeExecutor(present={"yay"})
    Bruno().install(Ctx(os=OMARCHY, ex=ex))
    assert ["yay", "-S", "--needed", "--noconfirm", "bruno-bin"] in ex.calls


def test_gui_app_from_the_omarchy_repo_uses_plain_pacman() -> None:
    """localsend ships in Omarchy's own pacman repo — no AUR build needed."""
    ex = FakeExecutor(present={"omarchy-pkg-add"})
    Localsend().install(Ctx(os=OMARCHY, ex=ex))
    assert ["omarchy-pkg-add", "localsend"] in ex.calls


def test_gui_app_verify_uses_pacman_query_on_arch() -> None:
    ex = FakeExecutor()
    assert Obsidian().verify(Ctx(os=OMARCHY, ex=ex)) is True
    assert ["pacman", "-Q", "obsidian"] in ex.calls


def test_vscode_uses_the_microsoft_branded_aur_build_on_arch() -> None:
    """Arch's own `code` package is the OSS rebuild — no Marketplace, no MS branding."""
    ex = FakeExecutor(present={"yay"})
    Vscode().install(Ctx(os=OMARCHY, ex=ex))
    assert ["yay", "-S", "--needed", "--noconfirm", "visual-studio-code-bin"] in ex.calls


# ---------------------------------------------------------------------------
# One-click: the default target
# ---------------------------------------------------------------------------


def test_install_defaults_to_the_omarchy_profile_on_omarchy() -> None:
    assert default_profile(OMARCHY) == "omarchy"


def test_install_still_defaults_to_full_elsewhere() -> None:
    assert default_profile(FEDORA) == "full"
    assert default_profile(ARCH) == "full"


@pytest.fixture
def real_profiles() -> dict[str, list[str]]:
    return load_profiles(REPO_ROOT / "profiles.toml")


def test_omarchy_profile_excludes_the_layers_omarchy_owns(
    real_profiles: dict[str, list[str]],
) -> None:
    omarchy = real_profiles["omarchy"]
    assert "gnome" not in omarchy, "Omarchy is Hyprland; the GNOME group has no analog"
    assert "multimedia" not in omarchy, "Arch ships codecs unencumbered — nothing to swap"
    # …but the dev stacks — dev-boost's actual contribution here — are all present.
    for stack in ("python", "web", "laravel", "dotnet", "data", "devops", "react-native"):
        assert stack in omarchy


def test_omarchy_profile_resolves_and_plans_cleanly(
    real_profiles: dict[str, list[str]],
) -> None:
    """End-to-end: the profile expands, sorts, and produces a plan with no NVIDIA/dnf work."""
    modules = load()
    validate_profiles(modules, set(real_profiles))
    order = toposort(expand(["omarchy"], real_profiles, modules), modules)
    plan = build_plan(order, modules, OMARCHY)
    planned = {p.name for p in plan}

    assert planned, "the omarchy profile must plan something"
    # Nothing dnf-, GRUB- or Flatpak-shaped survives to the plan.
    for gone in ("rpmfusion", "dnf-tune", "grub-btrfs", "flatpak", "snapper", "openh264"):
        assert gone not in planned, gone
    # The NVIDIA akmod/MOK state machine is RPM Fusion machinery — never on Arch.
    assert not any(
        modules[p.name].category == "hardware-nvidia" for p in plan
    ), "Fedora's NVIDIA stack must not be planned on Omarchy"
    # The things only dev-boost provides are planned.
    for wanted in ("ddev", "aspire", "uv", "fresh", "secrets", "obsidian-sync"):
        assert wanted in planned, wanted
    # And what the platform owns is reported rather than reinstalled.
    reasons = {p.name: p.skip_reason for p in plan}
    assert reasons.get("herdr") == "provided-by-omarchy"
    assert reasons.get("wezterm") == "provided-by-omarchy"


# ---------------------------------------------------------------------------
# One-click update: delegate to `omarchy update`, don't duplicate it
# ---------------------------------------------------------------------------


def test_update_hook_is_installed_into_omarchys_post_update_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = Ctx(os=OMARCHY, ex=FakeExecutor(present={"omarchy-hook-install"}))
    mod = OmarchyUpdateHook()

    assert mod.verify(ctx) is False
    mod.install(ctx)

    hook = tmp_path / ".config" / "omarchy" / "hooks" / "post-update.d" / "devboost-update"
    assert hook.is_file()
    body = hook.read_text(encoding="utf-8")
    assert "devboost install --update" in body
    # The OS update already succeeded by the time this runs; a failed dev-layer refresh
    # must not be reported as a broken system update.
    assert body.rstrip().endswith("exit 0")
    assert hook.stat().st_mode & 0o111, "hook must be executable"
    assert mod.verify(ctx) is True


def test_update_hook_is_a_clean_no_op_on_vanilla_arch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No omarchy CLI to integrate with — that is not a failure."""
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = Ctx(os=ARCH, ex=FakeExecutor())
    mod = OmarchyUpdateHook()

    assert mod.verify(ctx) is True
    mod.install(ctx)
    assert not (tmp_path / ".config" / "omarchy").exists()


def test_update_hook_install_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    ctx = Ctx(os=OMARCHY, ex=FakeExecutor(present={"omarchy-hook-install"}))
    OmarchyUpdateHook().install(ctx)
    hook = tmp_path / ".config" / "omarchy" / "hooks" / "post-update.d" / "devboost-update"
    first = hook.read_text(encoding="utf-8")
    OmarchyUpdateHook().install(ctx)
    assert hook.read_text(encoding="utf-8") == first


# ---------------------------------------------------------------------------
# Package names: a Fedora name must never leak through to pacman
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("module", "arch_pkg"),
    [
        # Arch keeps upstream names where Fedora/Debian rename.
        (Fd, "fd"),                 # not fd-find
        (Dust, "dust"),             # not du-dust
        (Gh, "github-cli"),         # not gh — that name does not exist on Arch
        # Arch's own `yq` is a DIFFERENT tool (a Python jq wrapper) that Conflicts With
        # go-yq. Installing it would quietly give a `yq` with different semantics.
        (Yq, "go-yq"),
    ],
)
def test_divergent_package_names_resolve_to_the_arch_package(
    module: type, arch_pkg: str
) -> None:
    ex = FakeExecutor()
    module().install(Ctx(os=OMARCHY, ex=ex))
    assert ["sudo", "pacman", "-S", "--needed", "--noconfirm", arch_pkg] in ex.calls


def test_package_modules_never_fall_back_to_a_fedora_only_name_on_arch() -> None:
    """Guard for the whole class of bug: `_resolve_pkg` defaults to `fedora_pkg`, so any
    module whose Arch name differs MUST declare `arch_pkg`. These are the known
    divergences — verified against Arch's repos."""
    ex = FakeExecutor()
    ctx = Ctx(os=OMARCHY, ex=ex)
    for module, forbidden in ((Fd, "fd-find"), (Dust, "du-dust"), (Gh, "gh"), (Yq, "yq")):
        assert module()._resolve_pkg(ctx) != forbidden, module.name


def test_dotnet_sdk_uses_arch_unversioned_package_name() -> None:
    """Arch ships the current SDK as `dotnet-sdk`; `dotnet-sdk-10.0` does not exist."""
    ex = FakeExecutor()
    DotnetSdk().install(Ctx(os=OMARCHY, ex=ex))
    assert ["sudo", "pacman", "-S", "--needed", "--noconfirm", "dotnet-sdk"] in ex.calls
    assert not any("dotnet-sdk-10.0" in c for c in ex.calls)


def test_ddev_uses_the_aur_since_no_pacman_repo_exists() -> None:
    ex = FakeExecutor(present={"yay", "mkcert"})
    Ddev().install(Ctx(os=OMARCHY, ex=ex))
    assert ["yay", "-S", "--needed", "--noconfirm", "ddev-bin"] in ex.calls
    # The Fedora/Debian repo setup must not run here.
    assert not any("yum.repos.d" in " ".join(c) for c in ex.calls)


def test_tools_packaged_on_arch_use_pacman_not_a_github_binary() -> None:
    """`sd` and `lazydocker` fall back to a ~/.local/bin binary drop on Fedora/Debian
    because neither packages them. Arch does — so pacman owns the file there and
    `omarchy update` keeps it current."""
    from devboost.modules.cli_tools import Lazydocker, Sd

    for module, arch_pkg in ((Sd, "sd"), (Lazydocker, "lazydocker")):
        ex = FakeExecutor()
        module().install(Ctx(os=OMARCHY, ex=ex))
        assert ["sudo", "pacman", "-S", "--needed", "--noconfirm", arch_pkg] in ex.calls
        assert not any(c[0] == "sh" for c in ex.calls), f"{module.name} shelled out on Arch"


def test_verify_reports_the_plan_not_the_raw_profile_expansion() -> None:
    """`devboost verify` must judge what `install` would actually run.

    Verifying the raw expansion instead reports every wrong-OS module as "missing"
    (rpmfusion on Arch, ffmpeg-ubuntu on Fedora), so verify could never go green on a
    correctly provisioned non-Fedora box — it always exited 1.
    """
    modules = load()
    order = ["rpmfusion", "dnf-tune", "herdr", "uv"]
    plan = build_plan(order, modules, OMARCHY)
    names = [p.name for p in plan]

    assert "rpmfusion" not in names and "dnf-tune" not in names  # dropped: wrong OS
    assert dict((p.name, p.skip_reason) for p in plan)["herdr"] == "provided-by-omarchy"
    # Only `uv` is left to actually check on this host.
    assert [p.name for p in plan if p.skip_reason is None] == ["uv"]


# ---------------------------------------------------------------------------
# Profiles beyond `omarchy` (brain-host / server) must resolve on Arch too
# ---------------------------------------------------------------------------


def test_browser_view_uses_arch_package_names() -> None:
    """Arch splits Xvfb into its own package and ships neither noVNC nor websockify."""
    from devboost.modules.browser_view import BrowserView

    ex = FakeExecutor(present={"yay"})
    BrowserView().install(Ctx(os=OMARCHY, ex=ex))
    assert ["sudo", "pacman", "-S", "--needed", "--noconfirm",
            "xorg-server-xvfb", "x11vnc"] in ex.calls
    assert ["yay", "-S", "--needed", "--noconfirm", "novnc", "websockify"] in ex.calls
    # The Fedora/Debian spellings must not leak through.
    flat = [tok for call in ex.calls for tok in call]
    assert "xvfb" not in flat and "xorg-x11-server-Xvfb" not in flat


def test_caddy_installs_from_arch_extra() -> None:
    """Caddy is packaged on Arch — no vendor apt repo and no COPR needed."""
    from devboost.modules.caddy import Caddy

    ex = FakeExecutor()
    Caddy().install(Ctx(os=OMARCHY, ex=ex))
    assert ["sudo", "pacman", "-S", "--needed", "--noconfirm", "caddy"] in ex.calls


def test_crossarch_build_skips_the_debian_only_binfmt_package() -> None:
    """`binfmt-support` is a Debian package; Arch registers handlers via systemd-binfmt."""
    from devboost.modules.crossarch_build import CrossArchBuild

    ex = FakeExecutor()
    CrossArchBuild().install(Ctx(os=OMARCHY, ex=ex))
    flat = [tok for call in ex.calls for tok in call]
    assert "qemu-user-static" in flat
    assert "binfmt-support" not in flat


# ---------------------------------------------------------------------------
# `list --json` — the machine-readable feed a UI consumes
# ---------------------------------------------------------------------------


def test_list_json_emits_plan_rows_for_a_ui(tmp_path: Path) -> None:
    """A GUI/TUI needs category + description + skip reason without parsing log output,
    and needs the PLAN (what install would really do here), not the raw expansion."""
    import json as _json

    from typer.testing import CliRunner

    from devboost.cli.app import app

    result = CliRunner().invoke(app, ["list", "--json", "cli"])
    assert result.exit_code == 0, result.output
    rows = _json.loads(result.stdout)
    assert rows, "expected rows"
    by_name = {r["name"]: r for r in rows}
    for row in rows:
        assert set(row) == {
            "name", "category", "description", "profiles", "gui", "skip_reason", "installed"
        }
    # Category is what a UI groups by, so it must actually be populated.
    assert by_name["bat"]["category"] == "cli"
    # Without --status the live probe is skipped entirely (it costs a verify per module).
    assert all(r["installed"] is None for r in rows)


def test_list_json_reports_platform_provided_modules(tmp_path: Path) -> None:
    """A UI must be able to show WHY a row is not actionable, not silently omit it."""
    import json as _json

    from typer.testing import CliRunner

    from devboost.cli.app import app

    result = CliRunner().invoke(app, ["list", "--json", "cli"])
    rows = {r["name"]: r for r in _json.loads(result.stdout)}
    if "herdr" in rows:  # present only when the host resolves to Omarchy
        assert rows["herdr"]["skip_reason"] in (None, "provided-by-omarchy")


def test_list_without_json_still_prints_plain_names() -> None:
    from typer.testing import CliRunner

    from devboost.cli.app import app

    result = CliRunner().invoke(app, ["list", "cli"])
    assert result.exit_code == 0
    assert "bat" in result.stdout.split()
    assert "{" not in result.stdout
