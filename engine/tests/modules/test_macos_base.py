"""The macOS foundation: Command Line Tools, Homebrew, Rosetta 2 (spec §0, §2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from devboost.core import log
from devboost.core.errors import InstallError, NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.core.plan import build_plan
from devboost.core.profiles import load_profiles
from devboost.core.registry import load
from devboost.exec.executor import Result
from devboost.exec.primitives import remote_script
from devboost.model import Ctx
from devboost.modules import macos
from devboost.modules.macos import Homebrew, Rosetta, XcodeClt, clt_label
from tests.scripted import Scripted

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
MAC28 = OsInfo("macos", "macos", "aarch64", version_id="28.0")
FEDORA = OsInfo("fedora", "fedora", "x86_64")
REPO_ROOT = Path(__file__).resolve().parents[3]

LISTING = (
    "Software Update Tool\n\nFinding available software\n"
    "Software Update found the following new or updated software:\n"
    "* Label: Command Line Tools for Xcode 26.4-26.4\n"
    "\tTitle: Command Line Tools for Xcode 26.4, Version: 26.4, Size: 900000KiB,\n"
    "* Label: Command Line Tools for Xcode 27.0-27.0\n"
    "\tTitle: Command Line Tools for Xcode 27.0, Version: 27.0, Size: 912000KiB,\n"
    "* Label: macOS Golden Gate 27.0.1-26A500\n"
)


#: `softwareupdate --list` as a beta macOS prints it: the beta is the highest number
#: (27.1), and its "beta 2" would win a naive all-digits comparison against 26.4.
BETA_LISTING = (
    "Software Update Tool\n\nFinding available software\n"
    "Software Update found the following new or updated software:\n"
    "* Label: Command Line Tools beta 2 for Xcode 27.1-27.1\n"
    "\tTitle: Command Line Tools beta 2 for Xcode 27.1, Version: 27.1, Size: 915000KiB, "
    "Recommended: YES, \n"
    "* Label: Command Line Tools for Xcode 26.4-26.4\n"
    "\tTitle: Command Line Tools for Xcode 26.4, Version: 26.4, Size: 900000KiB, "
    "Recommended: YES, \n"
    "* Label: Command Line Tools for Xcode 26.10-26.10\n"
    "\tTitle: Command Line Tools for Xcode 26.10, Version: 26.10, Size: 901000KiB, "
    "Recommended: YES, \n"
)
#: The CLT is absent until installed: `xcode-select -p` fails.
_NO_CLT: dict[tuple[str, ...], Result] = {
    ("xcode-select", "-p"): Result(
        2, stderr="xcode-select: error: unable to get active developer directory"
    ),
}


def test_clt_label_picks_the_newest_command_line_tools() -> None:
    assert clt_label(LISTING) == "Command Line Tools for Xcode 27.0-27.0"
    assert clt_label("No new software available.") is None


def test_clt_label_picks_the_highest_non_beta_by_version() -> None:
    # 26.10 > 26.4 numerically; the 27.1 beta is never picked unasked.
    assert clt_label(BETA_LISTING) == "Command Line Tools for Xcode 26.10-26.10"
    only_beta = "* Label: Command Line Tools beta 3 for Xcode 27.1-27.1\n"
    assert clt_label(only_beta) is None


def test_xcode_clt_installs_the_offered_label_and_cleans_up() -> None:
    ex = Scripted(answers={
        **_NO_CLT, ("softwareupdate", "--list"): Result(0, stdout=LISTING),
    })
    XcodeClt().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [
        ["xcode-select", "-p"],
        ["sudo", "touch", macos.CLT_PLACEHOLDER],
        ["softwareupdate", "--list"],
        ["sudo", "softwareupdate", "--install", "Command Line Tools for Xcode 27.0-27.0"],
        ["sudo", "xcode-select", "--switch", macos.CLT_DIR],
        ["sudo", "rm", "-f", macos.CLT_PLACEHOLDER],
    ]


def test_xcode_clt_without_an_offer_needs_the_user() -> None:
    ex = Scripted(answers={
        **_NO_CLT, ("softwareupdate", "--list"): Result(0, stdout="No new software"),
    })
    with pytest.raises(NeedsUser, match="xcode-select --install"):
        XcodeClt().install(Ctx(os=MAC, ex=ex))
    assert ex.calls[-1] == ["sudo", "rm", "-f", macos.CLT_PLACEHOLDER]


def test_xcode_clt_a_failing_softwareupdate_list_is_an_install_error() -> None:
    ex = Scripted(answers={**_NO_CLT, ("softwareupdate", "--list"): Result(1)})
    with pytest.raises(InstallError, match="softwareupdate --list"):
        XcodeClt().install(Ctx(os=MAC, ex=ex))
    assert ex.calls[-1] == ["sudo", "rm", "-f", macos.CLT_PLACEHOLDER]


def test_xcode_clt_warns_when_the_switch_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    warned: list[str] = []
    monkeypatch.setattr(log, "warn", warned.append)
    ex = Scripted(answers={
        **_NO_CLT,
        ("softwareupdate", "--list"): Result(0, stdout=LISTING),
        ("xcode-select", "--switch"): Result(1),
    })
    XcodeClt().install(Ctx(os=MAC, ex=ex))  # the CLT is installed; the switch is advisory
    assert len(warned) == 1 and "xcode-select --switch" in warned[0]
    assert ex.calls[-1] == ["sudo", "rm", "-f", macos.CLT_PLACEHOLDER]


@pytest.mark.parametrize("force", [False, True])
def test_xcode_clt_install_is_a_no_op_when_present(force: bool) -> None:
    # --force on a set-up Mac: softwareupdate offers no CLT, which must not block the run.
    ex = Scripted(answers={("softwareupdate", "--list"): Result(0, stdout="No new software")})
    XcodeClt().install(Ctx(os=MAC, ex=ex, force=force))
    assert ex.calls == [["xcode-select", "-p"]]


def test_xcode_clt_sudo_needed_only_when_absent() -> None:
    assert XcodeClt().sudo_needed(Ctx(os=MAC, ex=Scripted(), force=True)) is False
    assert XcodeClt().sudo_needed(Ctx(os=MAC, ex=Scripted(answers=dict(_NO_CLT)))) is True


def test_xcode_clt_verify_asks_xcode_select() -> None:
    assert XcodeClt().verify(Ctx(os=MAC, ex=Scripted())) is True
    missing = Scripted(answers={("xcode-select", "-p"): Result(2)})
    assert XcodeClt().verify(Ctx(os=MAC, ex=missing)) is False


def _brew(prefix: str = "/opt/homebrew", state: str = "disabled") -> Scripted:
    return Scripted(answers={
        ("brew", "--prefix"): Result(0, stdout=f"{prefix}\n"),
        ("brew", "analytics", "state"): Result(0, stdout=f"InfluxDB analytics are {state}.\n"),
    })


def test_homebrew_verify_needs_the_prefix_and_analytics_off() -> None:
    assert Homebrew().verify(Ctx(os=MAC, ex=_brew())) is True
    assert Homebrew().verify(Ctx(os=MAC, ex=_brew(state="enabled"))) is False
    assert Homebrew().verify(Ctx(os=MAC, ex=_brew(prefix="/usr/local"))) is False
    none = Scripted(answers={("brew",): Result(127)})
    assert Homebrew().verify(Ctx(os=MAC, ex=none)) is False


def test_homebrew_sudo_needed_only_when_brew_is_absent() -> None:
    # analytics on is fixed without root: no reason to ask for the password.
    assert Homebrew().sudo_needed(Ctx(os=MAC, ex=_brew(state="enabled"))) is False
    assert Homebrew().sudo_needed(Ctx(os=MAC, ex=_brew(), force=True)) is False
    none = Scripted(answers={("brew",): Result(127)})
    assert Homebrew().sudo_needed(Ctx(os=MAC, ex=none)) is True


def test_existing_homebrew_only_gets_analytics_turned_off() -> None:
    ex = _brew(state="enabled")
    Homebrew().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [["brew", "--prefix"], ["brew", "analytics", "off"]]


def test_missing_homebrew_runs_the_official_installer_noninteractively() -> None:
    ex = Scripted(answers={
        ("brew", "--prefix"): Result(127),
        ("mktemp", "-d"): Result(0, stdout="/tmp/db.1\n"),
    })
    Homebrew().install(Ctx(os=MAC, ex=ex))
    download = ["curl", "-fsSL", "--proto", "=https", "--tlsv1.2", "-o", "/tmp/db.1/install.sh",
                macos.BREW_INSTALLER]
    assert download in ex.calls
    run = ex.calls.index(["/bin/bash", "/tmp/db.1/install.sh"])
    assert ex.envs[run] == {"NONINTERACTIVE": "1"}
    assert ex.calls[-2:] == [["rm", "-rf", "/tmp/db.1"], ["brew", "analytics", "off"]]
    assert not any(c[0] == "sudo" for c in ex.calls)  # brew refuses root; never sudo


def test_run_script_cleans_up_after_a_failed_download() -> None:
    ex = Scripted(answers={
        ("mktemp", "-d"): Result(0, stdout="/tmp/db.2\n"),
        ("curl",): Result(22),
    })
    with pytest.raises(InstallError, match="curl"):
        remote_script.run_script(Ctx(os=MAC, ex=ex), "probe", "https://x/i.sh", "sh")
    assert ex.calls[-1] == ["rm", "-rf", "/tmp/db.2"]
    assert not any(c[0] == "sh" for c in ex.calls)


def test_rosetta_on_27_verifies_by_running_an_intel_binary() -> None:
    absent = Scripted(answers={("arch",): Result(1, stderr="Bad CPU type in executable")})
    assert Rosetta().verify(Ctx(os=MAC, ex=absent)) is False
    assert Rosetta().verify(Ctx(os=MAC, ex=Scripted())) is True


def test_rosetta_from_28_has_nothing_to_install() -> None:
    ex = Scripted()
    assert Rosetta().verify(Ctx(os=MAC28, ex=ex)) is True
    assert ex.calls == []


_NO_ROSETTA: dict[tuple[str, ...], Result] = {
    ("arch",): Result(1, stderr="Bad CPU type in executable"),
}


def test_rosetta_install_accepts_the_licence_with_sudo() -> None:
    ex = Scripted(answers=dict(_NO_ROSETTA))
    Rosetta().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [
        ["arch", "-x86_64", "/usr/bin/true"],
        ["sudo", "softwareupdate", "--install-rosetta", "--agree-to-license"],
    ]
    failing = Scripted(answers={**_NO_ROSETTA, ("softwareupdate",): Result(1)})
    with pytest.raises(InstallError):
        Rosetta().install(Ctx(os=MAC, ex=failing))


def test_intel_only_apps_come_from_system_profiler() -> None:
    body = {"SPApplicationsDataType": [
        {"_name": "OldApp", "arch_kind": "arch_i64"},
        {"_name": "Safari", "arch_kind": "arch_arm"},
        {"_name": "Universal", "arch_kind": "arch_arm_i64"},
    ]}
    ex = Scripted(answers={("system_profiler",): Result(0, stdout=json.dumps(body))})
    assert macos.intel_only_apps(Ctx(os=MAC28, ex=ex)) == ["OldApp"]
    bad = Scripted(answers={("system_profiler",): Result(0, stdout="nope")})
    assert macos.intel_only_apps(Ctx(os=MAC28, ex=bad)) is None  # could not list
    failed = Scripted(answers={("system_profiler",): Result(1)})
    assert macos.intel_only_apps(Ctx(os=MAC28, ex=failed)) is None
    empty = Scripted(answers={("system_profiler",): Result(0, stdout='{"x": 1}')})
    assert macos.intel_only_apps(Ctx(os=MAC28, ex=empty)) == []


@pytest.mark.parametrize("force", [False, True])
def test_rosetta_install_is_a_no_op_when_present(force: bool) -> None:
    ex = Scripted()  # `arch -x86_64 /usr/bin/true` succeeds: Rosetta runs Intel binaries
    Rosetta().install(Ctx(os=MAC, ex=ex, force=force))
    assert ex.calls == [["arch", "-x86_64", "/usr/bin/true"]]


def test_rosetta_sudo_needed_only_when_absent() -> None:
    assert Rosetta().sudo_needed(Ctx(os=MAC, ex=Scripted(), force=True)) is False
    assert Rosetta().sudo_needed(Ctx(os=MAC, ex=Scripted(answers=dict(_NO_ROSETTA)))) is True
    assert Rosetta().sudo_needed(Ctx(os=MAC28, ex=Scripted(answers=dict(_NO_ROSETTA)))) is False


def test_mac_major() -> None:
    assert macos.mac_major(MAC) == 27
    assert macos.mac_major(OsInfo("macos", "macos", "aarch64", version_id="26")) == 26
    assert macos.mac_major(OsInfo("macos", "macos", "aarch64")) == 0
    assert macos.rosetta_supported(MAC) and not macos.rosetta_supported(MAC28)


def test_the_foundation_is_macos_only_and_in_base(tmp_path: Path) -> None:
    for cls in (XcodeClt, Homebrew, Rosetta):
        assert cls.families == ("macos",) and cls.profiles == ("base",)
    assert XcodeClt in Homebrew.requires
    names = ["xcode-clt", "homebrew", "rosetta"]
    assert build_plan(names, load(), FEDORA, gpu_marker=tmp_path / "x") == []
    base = load_profiles(REPO_ROOT / "profiles.toml")["base"]
    assert set(names) <= set(base)
