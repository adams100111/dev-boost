from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core import log
from devboost.core.errors import NeedsUser
from devboost.core.graph import toposort
from devboost.core.osinfo import OsInfo
from devboost.core.plan import PlannedModule
from devboost.core.profiles import load_profiles
from devboost.core.registry import load
from devboost.core.runner import run_plan
from devboost.exec.executor import Result
from devboost.model import Ctx, Module
from devboost.modules._pass import pass_fields, pass_line, pass_show
from devboost.modules.pass_store import Pass, PassStore
from devboost.passstore import paths, sync
from devboost.passstore.layout import DeviceRecord, Store
from tests.passstore.fakes import RuleExecutor, colons

REPO_ROOT = Path(__file__).resolve().parents[3]
FEDORA = OsInfo("fedora", "fedora", "x86_64")
UBUNTU = OsInfo("ubuntu", "debian", "x86_64")
MAC = OsInfo("macos", "macos", "aarch64")
MAC_INTEL = OsInfo("macos", "macos", "x86_64")
FP_ME = "A" * 40
ARMOR = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nx\n"


@pytest.fixture(autouse=True)
def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("PASSWORD_STORE_DIR", str(tmp_path / "store"))
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")
    monkeypatch.delenv("GNUPGHOME", raising=False)
    monkeypatch.delenv("DEVBOOST_PASS_REPO", raising=False)
    cfg = tmp_path / "cfg" / "devboost" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('device_name = "desk"\n', encoding="utf-8")


def _seed(tmp_path: Path, gpg_id: str = FP_ME) -> Store:
    root = tmp_path / "store"
    (root / ".git" / "hooks").mkdir(parents=True)
    (root / ".gpg-id").write_text(gpg_id + "\n", encoding="utf-8")
    return Store(root)


def _ex(secret: str = colons("sec", FP_ME)) -> RuleExecutor:
    return RuleExecutor(present={"pass"}, rules=[
        (("--list-secret-keys",), Result(0, secret)),
        (("--export",), Result(0, ARMOR)),
        (("diff", "--cached"), Result(1)),
    ])


# --- Pass -----------------------------------------------------------------------------


def test_pass_is_base() -> None:
    assert (Pass.category, Pass.profiles) == ("base", ("base",))


def test_pass_sets_agent_cache_ttls_and_reloads(tmp_path: Path) -> None:
    conf = tmp_path / "home" / ".gnupg" / "gpg-agent.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text("pinentry-program /usr/bin/pinentry-gnome3\ndefault-cache-ttl 600\n",
                    encoding="utf-8")
    ex = RuleExecutor(present={"pass"})
    Pass().install(Ctx(os=FEDORA, ex=ex))
    assert conf.read_text(encoding="utf-8") == (
        "pinentry-program /usr/bin/pinentry-gnome3\n"
        "default-cache-ttl 28800\nmax-cache-ttl 86400\n"
    )
    assert ex.calls == [["gpgconf", "--reload", "gpg-agent"]]
    assert Pass().verify(Ctx(os=FEDORA, ex=RuleExecutor(present={"pass"})))
    again = RuleExecutor(present={"pass"})
    Pass().install(Ctx(os=FEDORA, ex=again))
    assert again.calls == []  # unchanged conf → no reload


def test_pass_warns_when_the_agent_reload_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    warned: list[str] = []
    monkeypatch.setattr(log, "warn", warned.append)
    ex = RuleExecutor(present={"pass"}, rules=[(("gpgconf",), Result(2))])
    Pass().install(Ctx(os=FEDORA, ex=ex))
    assert ["gpgconf", "--reload", "gpg-agent"] in ex.calls
    assert len(warned) == 1 and "gpgconf --reload" in warned[0]


def test_pass_installs_package_via_apt_on_ubuntu() -> None:
    ex = RuleExecutor()
    Pass().install(Ctx(os=UBUNTU, ex=ex))
    assert ["sudo", "apt-get", "install", "-y", "pass"] in ex.calls


def test_agent_settings_per_os() -> None:
    from devboost.modules.pass_store import agent_settings

    ttls = {"default-cache-ttl": "28800", "max-cache-ttl": "86400"}
    assert agent_settings(FEDORA) == ttls
    assert agent_settings(MAC) == {**ttls, "pinentry-program": "/opt/homebrew/bin/pinentry-mac"}
    assert agent_settings(MAC_INTEL)["pinentry-program"] == "/usr/local/bin/pinentry-mac"


def test_pass_on_macos_brews_missing_formulae_and_sets_pinentry(tmp_path: Path) -> None:
    conf = tmp_path / "home" / ".gnupg" / "gpg-agent.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text("pinentry-program /usr/local/bin/pinentry-tty\n", encoding="utf-8")
    ex = RuleExecutor(present={"gpg"})  # pass + pinentry-mac missing
    Pass().install(Ctx(os=MAC, ex=ex))
    brew = [c for c in ex.calls if c[0] == "brew" and "install" in c]
    assert brew and brew[0][-2:] == ["pass", "pinentry-mac"]
    assert "gnupg" not in brew[0]
    assert conf.read_text(encoding="utf-8") == (
        "pinentry-program /opt/homebrew/bin/pinentry-mac\n"
        "default-cache-ttl 28800\nmax-cache-ttl 86400\n"
    )
    assert ["gpgconf", "--reload", "gpg-agent"] in ex.calls
    ready = RuleExecutor(present={"pass", "gpg", "pinentry-mac"})
    assert Pass().verify(Ctx(os=MAC, ex=ready))
    assert not Pass().verify(Ctx(os=MAC, ex=RuleExecutor(present={"pass", "gpg"})))


def test_pass_on_linux_still_installs_only_pass(tmp_path: Path) -> None:
    ex = RuleExecutor(present=set())
    Pass().install(Ctx(os=FEDORA, ex=ex))
    installs = [c for c in ex.calls if "install" in c]
    assert installs and installs[0][-1] == "pass" and "pinentry-mac" not in installs[0]


def test_pass_store_runs_on_macos() -> None:
    assert "macos" in PassStore.families and PassStore.portable and Pass.portable


# --- PassStore ------------------------------------------------------------------------


def test_pass_store_metadata() -> None:
    assert (PassStore.category, PassStore.profiles) == ("base", ("base",))
    assert PassStore.families == ("fedora", "debian", "arch", "macos")
    assert {m.name for m in PassStore.requires} == {"pass", "secrets", "git"}


def test_install_enrolled_device_adopts_and_wires_sync(tmp_path: Path) -> None:
    store = _seed(tmp_path)
    ctx = Ctx(os=FEDORA, ex=_ex())
    PassStore().install(ctx)
    assert store.record("devices", "desk") is not None
    assert (store.root / ".git" / "hooks" / "post-commit").exists()
    units = tmp_path / "home" / ".config" / "systemd" / "user"
    assert (units / "devboost-pass-sync.timer").exists()
    assert PassStore().verify(Ctx(os=FEDORA, ex=_ex()))


def test_verify_false_until_device_is_registered(tmp_path: Path) -> None:
    _seed(tmp_path)
    ctx = Ctx(os=FEDORA, ex=_ex())
    PassStore().install(ctx)
    (tmp_path / "store" / ".devboost" / "devices" / "desk.json").unlink()
    assert PassStore().verify(ctx) is False


def test_install_new_device_unattended_blocks_but_still_syncs(tmp_path: Path) -> None:
    store = _seed(tmp_path, gpg_id="B" * 40)
    with pytest.raises(NeedsUser, match="devboost pass enroll"):
        PassStore().install(Ctx(os=FEDORA, ex=_ex(secret="")))
    # the timer must be in place so the approval arrives by itself
    assert (store.root / ".git" / "hooks" / "post-commit").exists()


def test_pending_device_blocks_with_approve_command(tmp_path: Path) -> None:
    store = _seed(tmp_path, gpg_id="B" * 40)
    store.write_record("pending", DeviceRecord(name="desk", fingerprint=FP_ME, os="fedora"), ARMOR)
    with pytest.raises(NeedsUser) as err:
        PassStore().install(Ctx(os=FEDORA, ex=_ex()))
    assert err.value.how_to_fix == "devboost pass approve desk"


def test_missing_store_clones_default_repo_or_asks_for_gh(tmp_path: Path) -> None:
    ex = RuleExecutor(rules=[(("clone",), Result(128))])
    with pytest.raises(NeedsUser, match="gh auth login"):
        PassStore().install(Ctx(os=FEDORA, ex=ex))
    assert ex.calls[0] == ["git", "clone", "--quiet",
                           "https://github.com/adams100111/password-store.git",
                           str(tmp_path / "store")]


# --- profiles + ordering ----------------------------------------------------------------


def test_base_profile_carries_pass_and_security_cli_is_an_alias() -> None:
    profiles = load_profiles(REPO_ROOT / "profiles.toml")
    assert {"pass", "pass-store"} <= set(profiles["base"])
    assert profiles["security-cli"] == ["pass", "pass-store"]


def test_readers_order_after_pass_store_without_requiring_it() -> None:
    modules = load()
    for name in ("claude-plugins", "codex-config", "pi-harness", "herdr-plugins"):
        cls = modules[name]
        assert PassStore in cls.after and PassStore not in cls.requires, name
    order = toposort(["claude-plugins", "pass-store"], modules)
    assert order.index("pass-store") < order.index("claude-plugins")
    assert "pass-store" not in toposort(["herdr-plugins"], modules)


# --- _pass helpers ----------------------------------------------------------------------


def test_pass_show_degrades_and_reads() -> None:
    assert pass_show(Ctx(os=FEDORA, ex=RuleExecutor()), "x/y", who="t") is None  # no pass
    failing = RuleExecutor(present={"pass"}, rules=[(("show",), Result(2))])
    assert pass_show(Ctx(os=FEDORA, ex=failing), "x/y", who="t") is None
    ok = RuleExecutor(present={"pass"}, rules=[(("show",), Result(0, "s3cret\nuser: me\n"))])
    assert pass_show(Ctx(os=FEDORA, ex=ok), "x/y", who="t") == "s3cret\nuser: me\n"
    assert ok.calls == [["pass", "show", "x/y"]]


def test_pass_fields_parses_key_value_lines() -> None:
    assert pass_fields("tok\ntoken: T1\nChat_ID:  C1 \nnoise\n") == {"token": "T1", "chat_id": "C1"}


def test_pass_line_is_the_first_line_or_none() -> None:
    ok = RuleExecutor(present={"pass"}, rules=[(("show",), Result(0, "  tok  \nuser: me\n"))])
    assert pass_line(Ctx(os=FEDORA, ex=ok), "x/y", who="t") == "tok"
    assert pass_line(Ctx(os=FEDORA, ex=RuleExecutor()), "x/y", who="t") is None  # no pass
    blank = RuleExecutor(present={"pass"}, rules=[(("show",), Result(0, "\nuser: me\n"))])
    assert pass_line(Ctx(os=FEDORA, ex=blank), "x/y", who="t") is None


# --- a bad config never crashes the run (I4) ---------------------------------------------


def _wired(tmp_path: Path) -> Store:
    """A clone whose hook, scheduler and device enrollment are wired for real (via the
    same `sync.install_hook` / `sync.install_scheduler` the real install path uses, plus
    an enrolled device record), so `verify()` would pass if not for whatever fault the
    test injects on top."""
    store = _seed(tmp_path)
    ctx = Ctx(os=FEDORA, ex=RuleExecutor())  # is-enabled / is-active succeed by default
    bin_ = paths.devboost_bin()
    sync.install_hook(ctx, store, bin_)
    sync.install_scheduler(ctx, bin_)
    store.write_record("devices", DeviceRecord(name="desk", fingerprint=FP_ME, os="fedora"), "K")
    return store


def _bad_toml(tmp_path: Path) -> None:
    (tmp_path / "cfg" / "devboost" / "config.toml").write_text("device_name = [\n",
                                                                encoding="utf-8")


def test_wired_alone_passes_verify(tmp_path: Path) -> None:
    """Positive control for `_wired()`: absent any injected fault, verify() is True — so
    the two tests below fail for their named reason, not because the scheduler/hook are
    unwired."""
    _wired(tmp_path)
    assert PassStore().verify(Ctx(os=FEDORA, ex=_ex())) is True


def test_verify_is_false_not_raising_on_invalid_config(tmp_path: Path) -> None:
    _wired(tmp_path)
    _bad_toml(tmp_path)
    assert PassStore().verify(Ctx(os=FEDORA, ex=_ex())) is False


def test_verify_is_false_not_raising_when_gpg_fails(tmp_path: Path) -> None:
    _wired(tmp_path)
    ex = RuleExecutor(present={"pass"}, rules=[(("--list-secret-keys",), Result(2))])
    assert PassStore().verify(Ctx(os=FEDORA, ex=ex)) is False


def test_invalid_config_fails_pass_store_but_later_modules_still_run(tmp_path: Path) -> None:
    ran: list[str] = []

    class Later(Module):
        name = "t-later"
        category = "base"
        description = "runs after pass-store"

        def verify(self, ctx: Ctx) -> bool:
            return False

        def install(self, ctx: Ctx) -> None:
            ran.append(self.name)

    _wired(tmp_path)
    _bad_toml(tmp_path)
    mods = {"pass-store": PassStore, "t-later": Later}
    plan = [PlannedModule("pass-store"), PlannedModule("t-later")]
    res = {r.name: r for r in run_plan(plan, mods, Ctx(os=FEDORA, ex=_ex()))}
    assert res["pass-store"].status == "fail" and "invalid TOML" in res["pass-store"].detail
    assert ran == ["t-later"]
