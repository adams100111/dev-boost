from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.errors import InstallError, NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.modules import ios
from devboost.modules._brew import BrewFormula
from devboost.modules.macos import Homebrew
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")
# `xcodes installed` with captured stdout (XcodesKit XcodeListPresentationService.installedLines,
# non-interactive branch): "<version> (<build>)[ (Selected)]\t<path>".
INSTALLED = (
    "26.4 (17E192)\t/Applications/Xcode-26.4.0.app\n"
    "27.0 (27A266a) (Selected)\t/Applications/Xcode-27.0.0.app\n"
)
RUNTIMES = (
    "== Runtimes ==\n"
    "iOS 27.0 (27.0 - 23A5287e) - com.apple.CoreSimulator.SimRuntime.iOS-27-0\n"
)
PASSWORD = "s3cret-apple-pw"
GIB = 1024**3


@pytest.fixture(autouse=True)
def plenty_of_space(monkeypatch: pytest.MonkeyPatch) -> None:
    # Never read the real disk: the free-space pre-check is patched per test.
    monkeypatch.setattr(ios, "_free_bytes", lambda _path: 500 * GIB)


@pytest.fixture
def creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XCODES_USERNAME", "dev@example.com")
    monkeypatch.setenv("XCODES_PASSWORD", PASSWORD)
    monkeypatch.setattr(ios, "_interactive", lambda: False)


@pytest.fixture
def no_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XCODES_USERNAME", raising=False)
    monkeypatch.delenv("XCODES_PASSWORD", raising=False)
    monkeypatch.setattr(ios, "_interactive", lambda: False)


@pytest.fixture
def tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XCODES_USERNAME", raising=False)
    monkeypatch.delenv("XCODES_PASSWORD", raising=False)
    monkeypatch.setattr(ios, "_interactive", lambda: True)


def test_gated_on_xcodes_minimum_macos() -> None:
    assert ios.Xcode.supported_on(MAC) is True
    assert ios.Xcode.supported_on(OsInfo("macos", "macos", "aarch64", version_id="26.6")) is True
    assert ios.Xcode.supported_on(OsInfo("macos", "macos", "aarch64", version_id="26.3")) is False
    assert ios.IosTooling.supported_on(OsInfo("macos", "macos", "aarch64", version_id="15.6")) \
        is False


def test_xcode_install_is_interactive_then_license_and_first_launch(tty: None) -> None:
    ex = RuleExecutor()
    ios.Xcode().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [
        ["xcodes", "install", "27.0", "--select", "--experimental-unxip", "--empty-trash"],
        ["sudo", "xcodebuild", "-license", "accept"],
        ["sudo", "xcodebuild", "-runFirstLaunch"],
    ]
    assert ex.interactive[0] is True  # never capture xcodes: it may prompt (Apple ID/2FA)


def test_apple_id_secrets_never_reach_argv_env_or_the_error(creds: None) -> None:
    ex = RuleExecutor(rules=[(("xcodes", "install"), Result(1))])
    with pytest.raises(NeedsUser) as err:
        ios.Xcode().install(Ctx(os=MAC, ex=ex))
    assert all(PASSWORD not in arg for argv in ex.calls for arg in argv)
    assert all(PASSWORD not in v for env in ex.envs for v in env.values())
    assert PASSWORD not in str(err.value)
    assert "dev@example.com" not in str(err.value)


def test_xcode_without_credentials_or_terminal_needs_the_user(no_tty: None) -> None:
    ex = RuleExecutor()
    with pytest.raises(NeedsUser, match="Apple ID"):
        ios.Xcode().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == []


def test_half_the_credentials_is_not_enough(
    no_tty: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XCODES_USERNAME", "dev@example.com")
    ex = RuleExecutor()
    with pytest.raises(NeedsUser, match="Apple ID"):
        ios.Xcode().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == []


def test_a_terminal_alone_is_enough_to_let_xcodes_prompt(tty: None) -> None:
    ex = RuleExecutor()
    ios.Xcode().install(Ctx(os=MAC, ex=ex))
    assert ex.calls[0][:2] == ["xcodes", "install"]
    assert ex.interactive[0] is True


def test_unattended_xcodes_runs_detached_from_stdin(creds: None) -> None:
    # No human: xcodes gets no terminal and an empty stdin, so a 2FA or password prompt
    # reads EOF at once instead of waiting on an inherited pipe or tty.
    ex = RuleExecutor()
    ios.Xcode().install(Ctx(os=MAC, ex=ex))
    assert ex.calls[0][:2] == ["xcodes", "install"]
    assert ex.interactive[0] is False
    assert ex.stdins[0] == ""


def test_unattended_xcodes_failure_is_blocked_not_failed(creds: None) -> None:
    secret_echo = f"Apple ID dev@example.com password {PASSWORD}"
    ex = RuleExecutor(rules=[(("xcodes", "install"), Result(1, secret_echo, secret_echo))])
    with pytest.raises(NeedsUser, match="could not finish unattended") as err:
        ios.Xcode().install(Ctx(os=MAC, ex=ex))
    assert "2FA, network or disk" in str(err.value)
    assert "terminal" in err.value.how_to_fix
    assert "dev@example.com" not in str(err.value)  # xcodes' output is never copied
    assert PASSWORD not in str(err.value)
    assert ex.interactive == [False] and ex.stdins == [""]
    assert len(ex.calls) == 1  # no sudo steps after a failed download


def test_unattended_runtime_install_runs_detached_from_stdin(creds: None) -> None:
    ex = RuleExecutor(rules=[(("runtimes", "install"), Result(1, "x", "y"))])
    with pytest.raises(NeedsUser, match="could not finish unattended"):
        ios.IosTooling().install(Ctx(os=MAC, ex=ex))
    assert ex.calls[-1] == ["xcodes", "runtimes", "install", "iOS 27.0"]
    assert ex.interactive[-1] is False and ex.stdins[-1] == ""


def test_xcode_needs_40_gib_free_in_home(tty: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ios, "_free_bytes", lambda _path: 39 * GIB)
    ex = RuleExecutor()
    with pytest.raises(NeedsUser, match="40 GiB"):
        ios.Xcode().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == []


def test_xcode_proceeds_with_exactly_40_gib_free(
    tty: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Path] = []

    def free(path: Path) -> int:
        seen.append(path)
        return 40 * GIB

    monkeypatch.setattr(ios, "_free_bytes", free)
    ex = RuleExecutor()
    ios.Xcode().install(Ctx(os=MAC, ex=ex))
    assert ex.calls[0][:2] == ["xcodes", "install"]
    assert seen == [Path.home()]


def test_attended_xcodes_failure_is_an_install_error(tty: None) -> None:
    ex = RuleExecutor(rules=[(("xcodes", "install"), Result(1))])
    with pytest.raises(InstallError):
        ios.Xcode().install(Ctx(os=MAC, ex=ex))


def test_license_failure_is_an_install_error(tty: None) -> None:
    ex = RuleExecutor(rules=[(("-license", "accept"), Result(1))])
    with pytest.raises(InstallError, match="license"):
        ios.Xcode().install(Ctx(os=MAC, ex=ex))


def test_xcode_verify_needs_the_pin_selected_and_the_license() -> None:
    ok = RuleExecutor(rules=[(("xcodes", "installed"), Result(0, INSTALLED))])
    assert ios.Xcode().verify(Ctx(os=MAC, ex=ok)) is True
    other = RuleExecutor(rules=[(("xcodes", "installed"), Result(0, "26.4 (17E192) (Selected)\n"))])
    assert ios.Xcode().verify(Ctx(os=MAC, ex=other)) is False
    unlicensed = RuleExecutor(rules=[
        (("xcodes", "installed"), Result(0, INSTALLED)),
        (("-license", "check"), Result(1)),
    ])
    assert ios.Xcode().verify(Ctx(os=MAC, ex=unlicensed)) is False


def test_xcode_verify_rejects_a_selected_beta_of_the_same_version() -> None:
    beta = "27.0 Beta 3 (27A5218g) (Selected)\t/Applications/Xcode-27.0.0-Beta.3.app\n"
    ex = RuleExecutor(rules=[(("xcodes", "installed"), Result(0, beta))])
    assert ios.Xcode().verify(Ctx(os=MAC, ex=ex)) is False


def test_xcode_verify_is_false_without_xcodes() -> None:
    ex = RuleExecutor(rules=[(("xcodes", "installed"), Result(127))])
    assert ios.Xcode().verify(Ctx(os=MAC, ex=ex)) is False


def test_ios_tooling_installs_formulae_then_the_runtime(tty: None) -> None:
    ex = RuleExecutor()
    ios.IosTooling().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [
        ["brew", "install", "--formula", "-y", "cocoapods", "watchman"],
        ["xcodes", "runtimes", "install", "iOS 27.0"],
    ]
    assert ex.interactive[-1] is True


def test_ios_tooling_without_credentials_or_terminal_needs_the_user(no_tty: None) -> None:
    ex = RuleExecutor()
    with pytest.raises(NeedsUser, match="Apple ID"):
        ios.IosTooling().install(Ctx(os=MAC, ex=ex))
    assert not any(argv[0] == "xcodes" for argv in ex.calls)


def test_ios_tooling_verify_reads_simctl() -> None:
    ok = RuleExecutor(rules=[(("simctl", "list"), Result(0, RUNTIMES))])
    assert ios.IosTooling().verify(Ctx(os=MAC, ex=ok)) is True
    none = RuleExecutor(rules=[(("simctl", "list"), Result(0, "== Runtimes ==\n"))])
    assert ios.IosTooling().verify(Ctx(os=MAC, ex=none)) is False


def test_ios_tooling_verify_ignores_an_unavailable_runtime() -> None:
    gone = RUNTIMES.rstrip("\n") + " (unavailable, runtime profile not found)\n"
    ex = RuleExecutor(rules=[(("simctl", "list"), Result(0, gone))])
    assert ios.IosTooling().verify(Ctx(os=MAC, ex=ex)) is False


def test_ios_tooling_verify_needs_the_formulae() -> None:
    ex = RuleExecutor(rules=[
        (("simctl", "list"), Result(0, RUNTIMES)),
        (("list", "--formula", "watchman"), Result(1)),
    ])
    assert ios.IosTooling().verify(Ctx(os=MAC, ex=ex)) is False


def test_profile_and_order() -> None:
    assert ios.Xcode.profiles == ios.IosTooling.profiles == ("ios",)
    assert [c.name for c in ios.IosTooling.requires] == ["xcode"]
    assert ios.Xcode.requires == (Homebrew, ios.Xcodes)


def test_xcode_is_flagged_for_the_macos_sudo_precheck() -> None:
    # M5-D5: license accept / runFirstLaunch run under sudo.
    assert ios.Xcode.needs_sudo_on_macos is True
    assert ios.IosTooling.needs_sudo_on_macos is False


def test_xcodes_is_a_macos_homebrew_formula() -> None:
    assert ios.Xcodes.name == "xcodes"
    assert ios.Xcodes.families == ("macos",)
    assert ios.Xcodes.requires == (Homebrew,)
    assert ios.Xcodes.per_os.macos == BrewFormula("xcodes")
    ex = RuleExecutor()
    ios.Xcodes().install(Ctx(os=MAC, ex=ex))
    assert ex.calls == [["brew", "install", "--formula", "-y", "xcodes"]]


def test_unattended_mode_turns_the_terminal_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")
    assert ios._interactive() is False
