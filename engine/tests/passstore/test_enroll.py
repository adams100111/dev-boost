from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from devboost.core import log
from devboost.core.errors import ConfigError, NeedsUser
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.passstore import enroll
from devboost.passstore.gpg import KeyInfo
from devboost.passstore.layout import DeviceRecord, Store
from tests.passstore.fakes import RuleExecutor, colons

FEDORA = OsInfo("fedora", "fedora", "x86_64")
FP_OLD = "C" * 24 + "01BD994F01BD994F"
FP_NEW = "D" * 40
ARMOR = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nx\n"
UID_NEW = "Ada (devboost:lap) <ada@example.com>"


def _store(tmp_path: Path, gpg_id: str | None = FP_OLD) -> Store:
    root = tmp_path / "store"
    (root / ".git").mkdir(parents=True)
    if gpg_id is not None:
        (root / ".gpg-id").write_text(gpg_id + "\n", encoding="utf-8")
    return Store(root)


def _ex(secret: str = "", *extra: tuple[tuple[str, ...], Result]) -> RuleExecutor:
    return RuleExecutor(rules=[
        *extra,
        (("--list-secret-keys",), Result(0, secret)),
        (("--export",), Result(0, ARMOR)),
        (("diff", "--cached"), Result(1)),  # something is staged → commit happens
        (("user.name",), Result(0, "Ada\n")),
        (("user.email",), Result(0, "ada@example.com\n")),
    ])


def _ctx(ex: RuleExecutor) -> Ctx:
    return Ctx(os=FEDORA, ex=ex)


def test_classify_genesis_when_no_root_gpg_id(tmp_path: Path) -> None:
    acc = enroll.local_access(_ctx(_ex()), _store(tmp_path, None), "lap")
    assert acc.state == "genesis"


def test_classify_enrolled_unregistered_key_by_short_id(tmp_path: Path) -> None:
    store = _store(tmp_path, gpg_id="0x01BD994F01BD994F")  # long key id, as in the real store
    acc = enroll.local_access(_ctx(_ex(colons("sec", FP_OLD, "Me <me@x>"))), store, "lap")
    assert acc.state == "enrolled" and acc.record is None and acc.key is not None


def test_classify_pending_and_new(tmp_path: Path) -> None:
    store = _store(tmp_path)
    ex = _ex(colons("sec", FP_NEW, UID_NEW))
    assert enroll.local_access(_ctx(ex), store, "lap").state == "new"
    pending = DeviceRecord(name="lap", fingerprint=FP_NEW, os="fedora")
    store.write_record("pending", pending, ARMOR)
    assert enroll.local_access(_ctx(ex), store, "lap").state == "pending"


def test_adopt_registers_existing_key_without_approval(tmp_path: Path) -> None:
    store = _store(tmp_path)
    ex = _ex(colons("sec", FP_OLD, "Me <me@x>"))
    acc = enroll.ensure_access(_ctx(ex), store, "desk", interactive=False)
    assert acc.state == "enrolled"
    rec = store.record("devices", "desk")
    assert rec is not None and rec.fingerprint == FP_OLD and rec.enrolled_at
    git_c = ["git", "-C", str(store.root)]
    assert [*git_c, "-c", "commit.gpgsign=false", "commit", "--quiet", "-m",
            "devboost: adopt desk"] in ex.calls
    assert [*git_c, "push", "--quiet", "--set-upstream", "origin", "HEAD"] in ex.calls


def test_new_device_interactive_generates_key_writes_pending_and_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEVBOOST_NTFY_URL", "https://ntfy.sh/t")
    store = _store(tmp_path)
    ex = _ex("")  # no key yet; after keygen the new key lists
    ex.on_call.append(
        ("--quick-gen-key", (("--list-secret-keys",), Result(0, colons("sec", FP_NEW, UID_NEW))))
    )
    with pytest.raises(NeedsUser) as err:
        enroll.ensure_access(_ctx(ex), store, "lap", interactive=True)
    assert err.value.how_to_fix == "devboost pass approve lap"
    gen = ["gpg", "--batch", "--quick-gen-key", UID_NEW, "ed25519", "cert,sign", "never"]
    assert gen in ex.calls
    rec = store.record("pending", "lap")
    assert rec is not None and rec.fingerprint == FP_NEW and rec.requested_at
    assert store.key_path("pending", "lap").read_text(encoding="utf-8") == ARMOR
    assert any(c[0] == "curl" for c in ex.calls)  # one ntfy from the enrolling device


def test_new_device_unattended_never_prompts(tmp_path: Path) -> None:
    ex = _ex("")  # no local key at all
    with pytest.raises(NeedsUser, match="devboost pass enroll"):
        enroll.ensure_access(_ctx(ex), _store(tmp_path), "lap", interactive=False)
    assert not any("--quick-gen-key" in c for c in ex.calls)


def test_pending_device_reports_approve_command(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write_record("pending", DeviceRecord(name="lap", fingerprint=FP_NEW, os="fedora"), ARMOR)
    with pytest.raises(NeedsUser) as err:
        enroll.ensure_access(_ctx(_ex(colons("sec", FP_NEW, UID_NEW))), store, "lap",
                             interactive=True)
    assert err.value.how_to_fix == "devboost pass approve lap"


def test_name_collision_refused(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write_record("devices", DeviceRecord(name="lap", fingerprint=FP_OLD, os="fedora"), ARMOR)
    with pytest.raises(ConfigError, match="already used"):
        enroll.ensure_access(_ctx(_ex(colons("sec", FP_NEW, UID_NEW))), store, "lap",
                             interactive=True)


class _PassInitWrites(RuleExecutor):
    """`pass init <fp>…` writes the root .gpg-id, as the real one does."""

    def run(self, argv: Sequence[str], **kw: Any) -> Result:
        if list(argv[:2]) == ["pass", "init"] and "-p" not in argv:
            root = Path(kw["env"]["PASSWORD_STORE_DIR"])
            (root / ".gpg-id").write_text("\n".join(argv[2:]) + "\n", encoding="utf-8")
        return super().run(argv, **kw)


def test_genesis_initialises_store_to_this_device(tmp_path: Path) -> None:
    store = _store(tmp_path, None)
    ex = _PassInitWrites(rules=_ex(colons("sec", FP_NEW, UID_NEW)).rules)
    acc = enroll.ensure_access(_ctx(ex), store, "lap", interactive=True)
    assert acc.state == "enrolled"
    i = ex.calls.index(["pass", "init", FP_NEW])
    assert ex.envs[i]["PASSWORD_STORE_DIR"] == str(store.root)
    assert ex.envs[i]["DEVBOOST_PASS_HOOK"] == "off"
    assert {k: ex.envs[i][k] for k in (
        "GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0",
        "GIT_TERMINAL_PROMPT", "GIT_ASKPASS", "SSH_ASKPASS",
    )} == {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "commit.gpgsign",
           "GIT_CONFIG_VALUE_0": "false", "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "",
           "SSH_ASKPASS": ""}  # pass's own commits: unsigned, never prompting (D6)
    assert list(ex.envs[i]).count("GIT_CONFIG_COUNT") == 1
    assert store.record("devices", "lap") is not None


def test_ensure_clone_needs_gh_when_unauthenticated(tmp_path: Path) -> None:
    store = Store(tmp_path / "store")
    ex = RuleExecutor(rules=[(("clone",), Result(128))])  # gh absent → not authenticated
    with pytest.raises(NeedsUser, match="gh auth login"):
        enroll.ensure_clone(_ctx(ex), store, "me/store")
    assert ex.calls[0] == ["git", "clone", "--quiet", "https://github.com/me/store.git",
                           str(store.root)]
    assert ex.envs[0]["GIT_TERMINAL_PROMPT"] == "0"  # fail fast, never block on a prompt
    assert ex.envs[0]["GIT_ASKPASS"] == "" and ex.envs[0]["SSH_ASKPASS"] == ""


def test_ensure_clone_config_error_when_authenticated(tmp_path: Path) -> None:
    ex = RuleExecutor(rules=[(("clone",), Result(128))], present={"gh"})
    with pytest.raises(ConfigError, match="me/store"):
        enroll.ensure_clone(_ctx(ex), Store(tmp_path / "store"), "me/store")


def test_ensure_clone_refuses_non_git_dir(tmp_path: Path) -> None:
    root = tmp_path / "store"
    root.mkdir()
    (root / "x.gpg").write_text("x", encoding="utf-8")
    with pytest.raises(NeedsUser, match="not a git clone") as err:
        enroll.ensure_clone(_ctx(RuleExecutor()), Store(root), "me/store")
    assert err.value.how_to_fix == "move it aside and re-run"


def test_import_device_keys_only_verified_and_listed(tmp_path: Path) -> None:
    store = _store(tmp_path, gpg_id=f"{FP_OLD}\n{FP_NEW}")
    store.write_record("devices", DeviceRecord(name="a", fingerprint=FP_NEW, os="fedora"), ARMOR)
    store.write_record("devices", DeviceRecord(name="evil", fingerprint="E" * 40, os="x"), ARMOR)
    ex = RuleExecutor(rules=[
        (("--show-keys", str(store.key_path("devices", "a"))), Result(0, colons("pub", FP_NEW))),
        (("--show-keys",), Result(0, colons("pub", "F" * 40))),  # mismatching file
    ])
    assert enroll.import_device_keys(_ctx(ex), store) == ["a"]
    assert ["gpg", "--batch", "--import", str(store.key_path("devices", "a"))] in ex.calls
    assert not any(str(store.key_path("devices", "evil")) in c and "--import" in c
                   for c in ex.calls)


def test_is_workstation_only_for_whole_store_enrolled_devices() -> None:
    key = KeyInfo(FP_OLD, ())
    whole = DeviceRecord(name="desk", fingerprint=FP_OLD, os="fedora")
    scoped = DeviceRecord(name="srv", fingerprint=FP_OLD, os="fedora", scope=["infra"])
    assert enroll.is_workstation(enroll.Access("enrolled", key, whole))
    assert enroll.is_workstation(enroll.Access("enrolled", key, None))  # not yet adopted
    assert not enroll.is_workstation(enroll.Access("enrolled", key, scoped))
    for state in ("no-store", "genesis", "pending", "new"):
        assert not enroll.is_workstation(enroll.Access(state, key, whole))


def test_email_in_gpg_id_never_grants_access_or_adoption(tmp_path: Path) -> None:
    store = _store(tmp_path, gpg_id="ada@example.com")  # UID_NEW carries this email
    ex = _ex(colons("sec", FP_NEW, UID_NEW))
    assert enroll.local_access(_ctx(ex), store, "lap").state == "new"
    with pytest.raises(NeedsUser) as err:
        enroll.ensure_access(_ctx(ex), store, "lap", interactive=False)
    assert err.value.how_to_fix == "devboost pass approve lap"  # a request, not an adoption
    assert store.record("devices", "lap") is None
    assert store.record("pending", "lap") is not None


def test_import_rejects_email_only_listing(tmp_path: Path) -> None:
    store = _store(tmp_path, gpg_id="ada@example.com")
    store.write_record("devices", DeviceRecord(name="a", fingerprint=FP_NEW, os="fedora"), ARMOR)
    ex = RuleExecutor(rules=[(("--show-keys",), Result(0, colons("pub", FP_NEW, UID_NEW)))])
    assert enroll.import_device_keys(_ctx(ex), store) == []
    assert not any("--import" in c for c in ex.calls)


def test_adopt_ignores_local_key_not_in_gpg_id(tmp_path: Path) -> None:
    store = _store(tmp_path)  # .gpg-id lists FP_OLD only
    ex = _ex(colons("sec", FP_NEW, "Me <me@x>"))  # unrelated personal key
    with pytest.raises(NeedsUser, match="devboost pass enroll"):
        enroll.ensure_access(_ctx(ex), store, "desk", interactive=False)
    assert store.record("devices", "desk") is None and store.record("pending", "desk") is None
    assert not any("commit" in c for c in ex.calls)


def test_unattended_genesis_without_key_needs_user(tmp_path: Path) -> None:
    ex = _ex("")
    with pytest.raises(NeedsUser, match="devboost pass enroll"):
        enroll.ensure_access(_ctx(ex), _store(tmp_path, None), "lap", interactive=False)
    assert not any(c[:2] == ["pass", "init"] or "--quick-gen-key" in c for c in ex.calls)


def test_failed_push_only_warns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    warned: list[str] = []
    monkeypatch.setattr(log, "warn", warned.append)
    store = _store(tmp_path)
    ex = _ex(colons("sec", FP_OLD, "Me <me@x>"), (("push",), Result(1)))
    assert enroll.ensure_access(_ctx(ex), store, "desk", interactive=False).state == "enrolled"
    assert len(warned) == 1 and "push failed" in warned[0]


def test_taken_name_refused_before_generating_a_key(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write_record("devices", DeviceRecord(name="lap", fingerprint=FP_OLD, os="fedora"), ARMOR)
    ex = _ex("")  # no local key: a new one would be generated
    with pytest.raises(ConfigError, match="already used"):
        enroll.ensure_access(_ctx(ex), store, "lap", interactive=True)
    assert not any("--quick-gen-key" in c for c in ex.calls)


def test_ensure_clone_refuses_a_file_path(tmp_path: Path) -> None:
    root = tmp_path / "store"
    root.write_text("x", encoding="utf-8")
    with pytest.raises(NeedsUser, match="not a git clone"):
        enroll.ensure_clone(_ctx(RuleExecutor()), Store(root), "me/store")


def test_import_device_keys_skips_an_unreadable_key_file(tmp_path: Path) -> None:
    store = _store(tmp_path, gpg_id=f"{FP_OLD}\n{FP_NEW}")
    store.write_record("devices", DeviceRecord(name="a", fingerprint=FP_NEW, os="fedora"), ARMOR)
    store.write_record("devices", DeviceRecord(name="b", fingerprint=FP_OLD, os="fedora"), ARMOR)
    ex = RuleExecutor(rules=[
        (("--show-keys", str(store.key_path("devices", "a"))), Result(2)),
        (("--show-keys",), Result(0, colons("pub", FP_OLD))),
    ])
    assert enroll.import_device_keys(_ctx(ex), store) == ["b"]


def _revoked(store: Store, name: str, fp: str) -> None:
    store.write_record("devices", DeviceRecord(name=name, fingerprint=fp, os="fedora"), ARMOR)
    store.move("devices", "revoked", name)


def test_import_device_keys_skips_revoked_fingerprints(tmp_path: Path) -> None:
    store = _store(tmp_path, gpg_id=f"{FP_OLD}\n{FP_NEW}")
    _revoked(store, "old", FP_NEW)
    store.write_record("devices", DeviceRecord(name="again", fingerprint=FP_NEW, os="x"), ARMOR)
    ex = RuleExecutor(rules=[(("--show-keys",), Result(0, colons("pub", FP_NEW)))])
    assert enroll.import_device_keys(_ctx(ex), store) == []
    assert not any("--import" in c for c in ex.calls)


def test_request_with_a_revoked_key_is_refused(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _revoked(store, "lap-old", FP_NEW)
    ex = _ex(colons("sec", FP_NEW, UID_NEW))
    with pytest.raises(ConfigError, match="revoked") as err:
        enroll.ensure_access(_ctx(ex), store, "lap", interactive=True)
    assert "--name" in str(err.value)
    assert store.record("pending", "lap") is None
    assert not any("commit" in c for c in ex.calls)


def test_adopt_refuses_a_key_registered_under_another_name(tmp_path: Path) -> None:
    """Minor (a): one key, one device name."""
    store = _store(tmp_path)  # root .gpg-id lists FP_OLD
    store.write_record("pending", DeviceRecord(name="old", fingerprint=FP_OLD, os="x"), ARMOR)
    ex = _ex(colons("sec", FP_OLD, "Me <me@x>"))
    with pytest.raises(ConfigError, match="'old'"):
        enroll.ensure_access(_ctx(ex), store, "desk", interactive=False)
    assert store.record("devices", "desk") is None


@pytest.mark.parametrize("what", ["entry", "device"])
def test_no_root_gpg_id_is_genesis_only_on_an_empty_store(tmp_path: Path, what: str) -> None:
    """I6: a store with entries or devices but no .gpg-id is broken, not new."""
    store = _store(tmp_path, None)
    if what == "entry":
        (store.root / "web").mkdir()
        (store.root / "web" / "a.gpg").write_text("x", encoding="utf-8")
    else:
        store.write_record("devices", DeviceRecord(name="desk", fingerprint=FP_OLD, os="x"),
                           ARMOR)
    ex = _ex(colons("sec", FP_NEW, UID_NEW))
    with pytest.raises(ConfigError, match="devboost pass sync --resolve"):
        enroll.ensure_access(_ctx(ex), store, "lap", interactive=True)
    assert not any(c[:2] == ["pass", "init"] for c in ex.calls)


def test_a_revoked_name_is_never_reused(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _revoked(store, "lap", FP_OLD)
    ex = _ex(colons("sec", FP_NEW, UID_NEW))  # a fresh key, but the old name
    with pytest.raises(ConfigError, match="'lap'"):
        enroll.ensure_access(_ctx(ex), store, "lap", interactive=True)
    assert store.record("pending", "lap") is None
