from __future__ import annotations

import os
import plistlib
import stat
import subprocess
from pathlib import Path

import pytest

from devboost.core.errors import InstallError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.exec.primitives import launchd
from devboost.model import Ctx
from devboost.modules import macos_system as ms
from tests.passstore.fakes import RuleExecutor

MAC = OsInfo("macos", "macos", "aarch64", version_id="27.0")


def _ctx(ex: RuleExecutor) -> Ctx:
    return Ctx(os=MAC, ex=ex)


@pytest.fixture(autouse=True)
def _daemons(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launchd, "DAEMONS_DIR", tmp_path / "LaunchDaemons")
    monkeypatch.delenv("COLIMA_HOME", raising=False)


# --- macos-limits -------------------------------------------------------------------------


def test_limits_verify_needs_both_sysctls_and_the_daemon() -> None:
    high = RuleExecutor(rules=[(("sysctl", "-n"), Result(0, "524288\n524288\n"))])
    assert ms.MacosLimits().verify(_ctx(high)) is True
    clamped = RuleExecutor(rules=[(("sysctl", "-n"), Result(0, "184320\n92160\n"))])
    assert ms.MacosLimits().verify(_ctx(clamped)) is False
    unloaded = RuleExecutor(rules=[
        (("sysctl", "-n"), Result(0, "524288\n524288\n")),
        (("launchctl", "print"), Result(113)),
    ])
    assert ms.MacosLimits().verify(_ctx(unloaded)) is False


def test_limits_verify_rejects_unparseable_or_partial_sysctl_output() -> None:
    for out in ("", "524288\n", "abc\n524288\n"):
        ex = RuleExecutor(rules=[(("sysctl", "-n"), Result(0, out))])
        assert ms.MacosLimits().verify(_ctx(ex)) is False, out
    failed = RuleExecutor(rules=[(("sysctl", "-n"), Result(1))])
    assert ms.MacosLimits().verify(_ctx(failed)) is False


def test_limits_install_writes_the_daemon_and_applies_now(tmp_path: Path) -> None:
    ex = RuleExecutor(rules=[(("launchctl", "print"), Result(113))])
    ms.MacosLimits().install(_ctx(ex))
    plist = tmp_path / "LaunchDaemons" / "dev.devboost.maxfiles.plist"
    assert ["sudo", "tee", str(plist)] in ex.calls
    stdin = ex.stdins[ex.calls.index(["sudo", "tee", str(plist)])]
    assert stdin is not None
    body = plistlib.loads(stdin.encode())
    assert body["ProgramArguments"][:2] == ["/bin/sh", "-c"]
    script = body["ProgramArguments"][2]
    assert "sysctl -w kern.maxfiles=524288 kern.maxfilesperproc=524288" in script
    assert "launchctl limit maxfiles 524288 524288 || true" in script
    assert body["RunAtLoad"] is True
    assert ["sudo", "sh", "-c", script] in ex.calls


def test_limits_install_raises_when_the_immediate_apply_fails() -> None:
    ex = RuleExecutor(rules=[(("sh", "-c"), Result(1))])
    with pytest.raises(InstallError):
        ms.MacosLimits().install(_ctx(ex))


def test_limits_daemon_script_references_no_user_writable_path() -> None:
    # A root LaunchDaemon must not run anything a user could replace.
    assert "$HOME" not in ms._LIMITS_SCRIPT and "/Users" not in ms._LIMITS_SCRIPT


# --- macos-firewall -----------------------------------------------------------------------


def test_firewall_state_parsing() -> None:
    on = RuleExecutor(
        rules=[(("--getglobalstate",), Result(0, "Firewall is enabled. (State = 1)\n"))]
    )
    off = RuleExecutor(
        rules=[(("--getglobalstate",), Result(0, "Firewall is disabled. (State = 0)\n"))]
    )
    block_all = RuleExecutor(
        rules=[(("--getglobalstate",), Result(0, "Firewall is blocking all non-essential "
                                                 "incoming connections. (State = 2)\n"))]
    )
    failed = RuleExecutor(rules=[(("--getglobalstate",), Result(1, "Firewall is enabled."))])
    assert ms.firewall_enabled(_ctx(on)) is True
    assert ms.firewall_enabled(_ctx(off)) is False
    assert ms.firewall_enabled(_ctx(block_all)) is True
    assert ms.firewall_enabled(_ctx(failed)) is False
    assert ms.MacosFirewall().verify(_ctx(on)) is True


def test_firewall_install_uses_sudo() -> None:
    ex = RuleExecutor()
    ms.MacosFirewall().install(_ctx(ex))
    assert ex.calls == [["sudo", ms.SOCKETFILTERFW, "--setglobalstate", "on"]]


def test_firewall_install_raises_on_failure() -> None:
    ex = RuleExecutor(rules=[(("--setglobalstate",), Result(1))])
    with pytest.raises(InstallError):
        ms.MacosFirewall().install(_ctx(ex))


# --- timemachine-exclusions ---------------------------------------------------------------


def test_tm_paths_match_the_spec_plus_every_vm_home() -> None:
    # M5-D8: every Colima home candidate, OrbStack and Docker Desktop's container.
    assert ms.TM_PATHS == (
        "Library/Caches", ".colima", ".config/colima", ".orbstack",
        "Library/Containers/com.docker.docker", ".gradle", ".npm", ".cache",
        ".nuget/packages", "Library/Developer/Xcode/DerivedData",
    )


def test_tm_candidates_add_colima_home_when_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert ms.tm_candidates() == [tmp_path / rel for rel in ms.TM_PATHS]
    monkeypatch.setenv("COLIMA_HOME", "/Volumes/vm/colima")
    assert ms.tm_candidates()[-1] == Path("/Volumes/vm/colima")
    monkeypatch.setenv("COLIMA_HOME", str(tmp_path / ".colima"))  # already listed
    assert ms.tm_candidates() == [tmp_path / rel for rel in ms.TM_PATHS]


def test_tm_verify_checks_existing_paths_only_and_the_agent(tmp_path: Path) -> None:
    (tmp_path / ".npm").mkdir()
    ms.TimemachineExclusions().install(_ctx(RuleExecutor()))  # the agent plist is current
    excluded = RuleExecutor(rules=[(("tmutil", "isexcluded"), Result(0, "[Excluded]  x\n"))])
    assert ms.TimemachineExclusions().verify(_ctx(excluded)) is True
    checked = [c[2] for c in excluded.calls if c[:2] == ["tmutil", "isexcluded"]]
    assert checked == [str(tmp_path / ".npm")]  # missing paths are not probed
    included = RuleExecutor(rules=[(("tmutil", "isexcluded"), Result(0, "[Included]  x\n"))])
    assert ms.TimemachineExclusions().verify(_ctx(included)) is False
    unloaded = RuleExecutor(rules=[
        (("tmutil", "isexcluded"), Result(0, "[Excluded]  x\n")),
        (("launchctl", "print"), Result(113)),
    ])
    assert ms.TimemachineExclusions().verify(_ctx(unloaded)) is False


def test_tm_verify_is_false_for_a_stale_agent(tmp_path: Path) -> None:
    ms.TimemachineExclusions().install(_ctx(RuleExecutor()))
    plist = tmp_path / "Library" / "LaunchAgents" / "dev.devboost.tm-exclusions.plist"
    plist.write_bytes(plistlib.dumps({"Label": "dev.devboost.tm-exclusions",
                                      "ProgramArguments": ["/bin/sh", "-c", "exit 0"]}))
    assert ms.TimemachineExclusions().verify(_ctx(RuleExecutor())) is False


def test_tm_install_registers_the_sweep_agent_and_runs_it(tmp_path: Path) -> None:
    ex = RuleExecutor(rules=[(("launchctl", "print"), Result(113))])
    ms.TimemachineExclusions().install(_ctx(ex))
    plist = tmp_path / "Library" / "LaunchAgents" / "dev.devboost.tm-exclusions.plist"
    body = plistlib.loads(plist.read_bytes())
    assert body["ProgramArguments"] == ["/bin/sh", "-c", ms.tm_sweep_script()]
    assert body["StartInterval"] == 21600
    assert body["RunAtLoad"] is True
    assert ["/bin/sh", "-c", ms.tm_sweep_script()] in ex.calls
    assert not any(c[0] == "sudo" for c in ex.calls)  # sticky exclusions need no root


def test_tm_install_raises_when_the_sweep_fails() -> None:
    ex = RuleExecutor(rules=[(("/bin/sh", "-c"), Result(1))])
    with pytest.raises(InstallError):
        ms.TimemachineExclusions().install(_ctx(ex))


def _fake_tmutil(tmp_path: Path) -> tuple[Path, Path]:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "tmutil.log"
    fake = bindir / "tmutil"
    fake.write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> "{log}"\n'
        'if [ "$1" = isexcluded ]; then echo "[Included]  $2"; fi\n',
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    return bindir, log


def _added(log: Path) -> list[str]:
    return [ln.split(" ", 1)[1] for ln in log.read_text().splitlines()
            if ln.startswith("addexclusion ")]


def test_tm_sweep_script_excludes_existing_paths_and_prunes_repos(tmp_path: Path) -> None:
    """Run the real POSIX script against a fake `tmutil` (never the real one)."""
    home = tmp_path
    (home / ".npm").mkdir()
    (home / ".config" / "colima").mkdir(parents=True)
    (home / "repos" / "app" / "node_modules" / "dep" / "node_modules").mkdir(parents=True)
    (home / "repos" / "app" / "vendor").mkdir(parents=True)
    bindir, log = _fake_tmutil(tmp_path)
    env = {**os.environ, "HOME": str(home), "PATH": f"{bindir}:/usr/bin:/bin"}
    subprocess.run(["/bin/sh", "-c", ms.tm_sweep_script()], env=env, check=True)
    added = _added(log)
    # fixed paths are swept first, in TM_PATHS order
    assert added[:2] == [str(home / ".config" / "colima"), str(home / ".npm")]
    assert sorted(added) == sorted([
        str(home / ".config" / "colima"),
        str(home / ".npm"),
        str(home / "repos" / "app" / "node_modules"),  # find order is unspecified
        str(home / "repos" / "app" / "vendor"),
    ])
    assert not any(a.endswith("/.colima") for a in added)  # missing → skipped
    assert not any("dep/node_modules" in a for a in added)  # pruned


def test_tm_sweep_script_bakes_in_a_quoted_colima_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """launchd gives the agent no COLIMA_HOME, so the install-time value is literal."""
    odd = tmp_path / "vm's colima $(touch pwned)"
    odd.mkdir()
    monkeypatch.setenv("COLIMA_HOME", str(odd))
    script = ms.tm_sweep_script()
    bindir, log = _fake_tmutil(tmp_path)
    env = {k: v for k, v in os.environ.items() if k != "COLIMA_HOME"}
    env |= {"HOME": str(tmp_path), "PATH": f"{bindir}:/usr/bin:/bin"}
    subprocess.run(["/bin/sh", "-c", script], env=env, check=True, cwd=tmp_path)
    assert _added(log) == [str(odd)]
    assert not (tmp_path / "pwned").exists()


def test_modules_are_macos_only_and_in_macos_desktop() -> None:
    for cls in (ms.MacosLimits, ms.MacosFirewall, ms.TimemachineExclusions):
        assert cls.families == ("macos",)
        assert cls.profiles == ("macos-desktop",)
        assert cls.portable is True


def test_only_limits_and_firewall_need_sudo_on_macos() -> None:
    # M5-D5: the LaunchDaemon and socketfilterfw run sudo; sticky tmutil does not.
    assert ms.MacosLimits.needs_sudo_on_macos is True
    assert ms.MacosFirewall.needs_sudo_on_macos is True
    assert ms.TimemachineExclusions.needs_sudo_on_macos is False
