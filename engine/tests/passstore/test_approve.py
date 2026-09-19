from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.errors import ConfigError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.passstore import approve
from devboost.passstore.layout import DeviceRecord, Kind, RotationEntry, Store
from tests.passstore.fakes import RuleExecutor, colons

FEDORA = OsInfo("fedora", "fedora", "x86_64")
FP_ME = "A" * 40
FP_NEW = "B" * 40
FP_SRV = "C" * 40
ARMOR = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nx\n"


def _store(tmp_path: Path, root_ids: list[str]) -> Store:
    root = tmp_path / "store"
    (root / ".git").mkdir(parents=True)
    (root / ".gpg-id").write_text("\n".join(root_ids) + "\n", encoding="utf-8")
    s = Store(root)
    s.write_record("devices", DeviceRecord(name="desk", fingerprint=FP_ME, os="fedora"), ARMOR)
    return s


def _ex(*extra: tuple[tuple[str, ...], Result]) -> RuleExecutor:
    return RuleExecutor(rules=[
        *extra,
        (("--list-secret-keys",), Result(0, colons("sec", FP_ME))),
        (("--list-keys",), Result(0, colons("pub", FP_ME))),
        (("--show-keys",), Result(0, colons("pub", FP_NEW))),
        (("diff", "--cached"), Result(1)),
        (("rev-parse", "HEAD"), Result(0, "abc123\n")),
    ])


def _ctx(ex: RuleExecutor) -> Ctx:
    return Ctx(os=FEDORA, ex=ex)


def _pending(s: Store, scope: list[str] | None = None) -> None:
    s.write_record("pending", DeviceRecord(name="lap", fingerprint=FP_NEW, os="ubuntu",
                                           scope=scope), ARMOR)


def test_approve_workstation_reencrypts_to_n_plus_one(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME])
    _pending(s)
    ex = _ex()
    seen: list[str] = []

    def _yes(r: DeviceRecord) -> bool:
        seen.append(r.name)
        return True

    done = approve.approve(_ctx(ex), s, "desk", None, _yes)
    assert done == [approve.Approved("lap", None)] and seen == ["lap"]
    root = str(s.root)
    assert ex.calls[0] == ["git", "-C", root, "pull", "--rebase", "--autostash", "--quiet"]
    assert ["gpg", "--batch", "--import", str(s.key_path("pending", "lap"))] in ex.calls
    i = ex.calls.index(["pass", "init", FP_ME, FP_NEW])
    assert ex.interactive[i] is True and ex.envs[i]["PASSWORD_STORE_DIR"] == root
    rec = s.record("devices", "lap")
    assert rec is not None and rec.enrolled_at and s.record("pending", "lap") is None
    assert s.key_path("devices", "lap").exists()
    assert ["git", "-C", root, "-c", "commit.gpgsign=false", "commit", "--quiet", "-m",
            "devboost: enroll lap"] in ex.calls


def test_approve_refuses_mismatched_key_file(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME])
    _pending(s)
    ex = _ex((("--show-keys",), Result(0, colons("pub", "E" * 40))))
    with pytest.raises(ConfigError, match="does not match"):
        approve.approve(_ctx(ex), s, "desk", "lap", lambda r: True)
    assert not any(c[:2] == ["pass", "init"] for c in ex.calls)


def test_declined_confirmation_changes_nothing(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME])
    _pending(s)
    ex = _ex()
    assert approve.approve(_ctx(ex), s, "desk", "lap", lambda r: False) == []
    assert s.record("pending", "lap") is not None
    assert not any(c[:2] == ["pass", "init"] for c in ex.calls)


def test_scoped_approve_limits_to_folders(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME])
    _pending(s, scope=["harness"])
    ex = _ex()
    done = approve.approve(_ctx(ex), s, "desk", "lap", lambda r: True)
    assert done == [approve.Approved("lap", ["harness"])]
    assert ["pass", "init", "-p", "harness", FP_ME, FP_NEW] in ex.calls
    assert ["pass", "init", FP_ME, FP_NEW] not in ex.calls


def test_scope_override_wins(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME])
    _pending(s, scope=["harness", "web"])
    ex = _ex()
    done = approve.approve(_ctx(ex), s, "desk", "lap", lambda r: True,
                           scope_override=["harness"])
    assert done == [approve.Approved("lap", ["harness"])]
    assert ["pass", "init", "-p", "harness", FP_ME, FP_NEW] in ex.calls
    assert not any("web" in c for c in ex.calls if c[:2] == ["pass", "init"])
    rec = s.record("devices", "lap")
    assert rec is not None and rec.scope == ["harness"]


def test_approve_requires_enrolled_workstation(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_NEW])  # this device's key is not in .gpg-id
    _pending(s)
    with pytest.raises(ConfigError, match="enrolled"):
        approve.approve(_ctx(_ex()), s, "desk", None, lambda r: True)


def test_unknown_request_name(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME])
    with pytest.raises(ConfigError, match="no pending request"):
        approve.approve(_ctx(_ex()), s, "desk", "ghost", lambda r: True)


def test_revoke_workstation_reencrypts_moves_and_lists_rotation(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME, FP_NEW])
    s.write_record("devices", DeviceRecord(name="lap", fingerprint=FP_NEW, os="fedora"), ARMOR)
    ex = _ex(
        ((f"-S{FP_NEW}",), Result(0, "c1\nc9\n")),
        (("ls-tree",), Result(0, ".gpg-id\nweb/a.gpg\n.devboost/devices/desk.json\n")),
        (("--diff-filter=A",), Result(0, "web/b.gpg\n")),
    )
    entry = approve.revoke(_ctx(ex), s, "desk", "lap", lambda r: True)
    assert entry is not None
    assert (entry.device, entry.after, entry.entries) == ("lap", "abc123", ["web/a", "web/b"])
    assert ["pass", "init", FP_ME] in ex.calls
    assert s.record("devices", "lap") is None and s.record("revoked", "lap") is not None
    assert s.rotation() == [entry]
    assert ["git", "-C", str(s.root), "-c", "commit.gpgsign=false", "commit", "--quiet", "-m",
            "devboost: revoke lap"] in ex.calls


def test_revoke_refuses_this_device(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME, FP_NEW])
    with pytest.raises(ConfigError, match="another enrolled device"):
        approve.revoke(_ctx(_ex()), s, "desk", "desk", lambda r: True)


def test_revoke_cancelled_returns_none(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME, FP_NEW])
    s.write_record("devices", DeviceRecord(name="lap", fingerprint=FP_NEW, os="fedora"), ARMOR)
    assert approve.revoke(_ctx(_ex()), s, "desk", "lap", lambda r: False) is None
    assert s.record("devices", "lap") is not None


def test_revoke_scoped_server_restores_folder_inheritance(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME])
    (s.root / "harness").mkdir()
    (s.root / "harness" / ".gpg-id").write_text(f"{FP_ME}\n{FP_SRV}\n", encoding="utf-8")
    s.write_record("devices", DeviceRecord(name="srv", fingerprint=FP_SRV, os="ubuntu",
                                           scope=["harness"]), ARMOR)
    ex = _ex((("log", "--name-only", "--format="), Result(0, "harness/tg.gpg\nweb/a.gpg\n")))
    entry = approve.revoke(_ctx(ex), s, "desk", "srv", lambda r: True)
    assert entry is not None and entry.entries == ["harness/tg"]
    assert ["pass", "init", "-p", "harness", ""] in ex.calls
    assert not any(c == ["pass", "init", FP_ME] for c in ex.calls)


def test_unrotated_ignores_automated_reencryptions(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME])
    for e in ("web/a", "web/b"):
        (s.root / "web").mkdir(exist_ok=True)
        (s.root / f"{e}.gpg").write_text("x", encoding="utf-8")
    s.write_rotation([RotationEntry(device="lap", fingerprint=FP_NEW, revoked_at="t",
                                    after="abc", entries=["web/a", "web/b", "web/gone"])])
    ex = RuleExecutor(rules=[
        (("web/a.gpg",), Result(0, "Edit password for web/a using vim.\n"
                                   "Reencrypt password store using new GPG id A.\n")),
        (("web/b.gpg",), Result(0, "Reencrypt password store using new GPG id A.\n"
                                   "devboost: enroll x\n")),
    ])
    assert approve.unrotated(_ctx(ex), s) == [approve.Unrotated("lap", "web/b")]


def _recording(seen: list[str]) -> approve.Confirm:
    def _yes(r: DeviceRecord) -> bool:
        seen.append(r.name)
        return True

    return _yes


def _no_pass_init(ex: RuleExecutor) -> bool:
    return not any(c[:2] == ["pass", "init"] for c in ex.calls)


@pytest.mark.parametrize("scope", [[""], ["."], ["../x"], ["harness/../.."], ["/etc"], []])
def test_approve_rejects_bad_request_scope(tmp_path: Path, scope: list[str]) -> None:
    s = _store(tmp_path, [FP_ME])
    _pending(s, scope=scope)
    ex = _ex()
    with pytest.raises(ConfigError, match="'lap'"):
        approve.approve(_ctx(ex), s, "desk", "lap", lambda r: True)
    assert _no_pass_init(ex) and s.record("pending", "lap") is not None


@pytest.mark.parametrize("scope", [[""], ["."], ["../x"], ["/etc"], [".devboost"], []])
def test_approve_rejects_bad_scope_override(tmp_path: Path, scope: list[str]) -> None:
    s = _store(tmp_path, [FP_ME])
    _pending(s)
    ex = _ex()
    asked: list[str] = []
    with pytest.raises(ConfigError, match="'lap'"):
        approve.approve(_ctx(ex), s, "desk", "lap", _recording(asked),
                        scope_override=scope)
    assert _no_pass_init(ex) and asked == []


@pytest.mark.parametrize("kind", ["devices", "revoked"])
def test_approve_refuses_name_taken_by_other_key(tmp_path: Path, kind: Kind) -> None:
    s = _store(tmp_path, [FP_ME])
    s.write_record("devices", DeviceRecord(name="lap", fingerprint=FP_SRV, os="fedora"), ARMOR)
    if kind == "revoked":
        s.move("devices", "revoked", "lap")
    _pending(s)
    ex = _ex()
    with pytest.raises(ConfigError, match="already belongs"):
        approve.approve(_ctx(ex), s, "desk", "lap", lambda r: True)
    assert _no_pass_init(ex)
    kept = s.record(kind, "lap")
    assert kept is not None and kept.fingerprint == FP_SRV


def test_approve_refuses_name_with_path_separator(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME])
    rec = DeviceRecord(name="../evil", fingerprint=FP_NEW, os="ubuntu")
    (s.meta / "pending").mkdir(parents=True)
    (s.meta / "pending" / "evil.json").write_text(rec.model_dump_json(), encoding="utf-8")
    ex = _ex()
    with pytest.raises(ConfigError, match="path separator"):
        approve.approve(_ctx(ex), s, "desk", "../evil", lambda r: True)
    assert _no_pass_init(ex)


def test_approve_without_name_skips_a_bad_request(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME])
    s.write_record("pending", DeviceRecord(name="bad", fingerprint=FP_NEW, os="ubuntu",
                                           scope=[".."]), ARMOR)
    _pending(s)
    ex = _ex()
    seen: list[str] = []
    done = approve.approve(_ctx(ex), s, "desk", None, _recording(seen))
    assert done == [approve.Approved("lap", None)] and seen == ["lap"]
    assert s.record("pending", "bad") is not None and s.record("devices", "bad") is None


def test_approve_stores_uppercase_fingerprint(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME])
    s.write_record("pending", DeviceRecord(name="lap", fingerprint=FP_NEW.lower(), os="ubuntu"),
                   ARMOR)
    ex = _ex()
    approve.approve(_ctx(ex), s, "desk", "lap", lambda r: True)
    rec = s.record("devices", "lap")
    assert rec is not None and rec.fingerprint == FP_NEW
    assert ["pass", "init", FP_ME, FP_NEW] in ex.calls


def test_approve_and_revoke_import_enrolled_device_keys(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME, FP_SRV])
    s.write_record("devices", DeviceRecord(name="srv", fingerprint=FP_SRV, os="ubuntu"), ARMOR)
    srv_key = str(s.key_path("devices", "srv"))
    _pending(s)
    ex = _ex((("--show-keys", srv_key), Result(0, colons("pub", FP_SRV))))
    approve.approve(_ctx(ex), s, "desk", "lap", lambda r: True)
    imp = ex.calls.index(["gpg", "--batch", "--import", srv_key])
    assert imp < ex.calls.index(["pass", "init", FP_ME, FP_SRV, FP_NEW])

    s.gpg_id_path().write_text(f"{FP_ME}\n{FP_SRV}\n{FP_NEW}\n", encoding="utf-8")  # fake pass
    ex = _ex((("--show-keys", srv_key), Result(0, colons("pub", FP_SRV))))
    approve.revoke(_ctx(ex), s, "desk", "lap", lambda r: True)
    imp = ex.calls.index(["gpg", "--batch", "--import", srv_key])
    assert imp < ex.calls.index(["pass", "init", FP_ME, FP_SRV])


def test_unscoped_approve_adds_key_to_scoped_folders(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME])
    (s.root / "harness").mkdir()
    (s.root / "harness" / ".gpg-id").write_text(f"{FP_ME}\n{FP_SRV}\n", encoding="utf-8")
    ex = _ex()
    _pending(s)
    approve.approve(_ctx(ex), s, "desk", "lap", lambda r: True)
    assert ["pass", "init", FP_ME, FP_NEW] in ex.calls
    assert ["pass", "init", "-p", "harness", FP_ME, FP_SRV, FP_NEW] in ex.calls


@pytest.mark.parametrize("folder", ["", "harness"])
def test_revoke_refuses_email_ids(tmp_path: Path, folder: str) -> None:
    s = _store(tmp_path, [FP_ME, FP_NEW])
    s.write_record("devices", DeviceRecord(name="lap", fingerprint=FP_NEW, os="fedora"), ARMOR)
    ids = s.gpg_id_path(folder)
    ids.parent.mkdir(exist_ok=True)
    ids.write_text(f"{FP_ME}\n{FP_NEW}\nme@example.com\n", encoding="utf-8")
    ex = _ex()
    with pytest.raises(ConfigError, match="replace the email ids in") as err:
        approve.revoke(_ctx(ex), s, "desk", "lap", lambda r: True)
    assert str(ids) in str(err.value)
    assert _no_pass_init(ex) and s.record("devices", "lap") is not None


def test_revoke_refuses_this_device_stored_lowercase(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME, FP_NEW])
    s.write_record("devices", DeviceRecord(name="desk", fingerprint=FP_ME.lower(), os="fedora"),
                   ARMOR)
    ex = _ex()
    with pytest.raises(ConfigError, match="another enrolled device"):
        approve.revoke(_ctx(ex), s, "desk", "desk", lambda r: True)
    assert _no_pass_init(ex)


def test_revoke_scoped_folder_same_ids_in_other_order_inherits(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME, FP_NEW])
    (s.root / "harness").mkdir()
    (s.root / "harness" / ".gpg-id").write_text(f"{FP_NEW}\n{FP_SRV}\n{FP_ME}\n",
                                                encoding="utf-8")
    s.write_record("devices", DeviceRecord(name="srv", fingerprint=FP_SRV, os="ubuntu",
                                           scope=["harness"]), ARMOR)
    ex = _ex()
    approve.revoke(_ctx(ex), s, "desk", "srv", lambda r: True)
    assert ["pass", "init", "-p", "harness", ""] in ex.calls


def test_approve_unreadable_key_file_is_a_refusal_not_a_crash(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME])
    _pending(s)
    ex = _ex((("--show-keys", str(s.key_path("pending", "lap"))), Result(2)))
    with pytest.raises(ConfigError, match="does not match"):
        approve.approve(_ctx(ex), s, "desk", "lap", lambda r: True)
    assert _no_pass_init(ex)


def test_revoke_with_malformed_rotation_json_changes_nothing(tmp_path: Path) -> None:
    s = _store(tmp_path, [FP_ME, FP_NEW])
    s.write_record("devices", DeviceRecord(name="lap", fingerprint=FP_NEW, os="fedora"), ARMOR)
    (s.meta / "rotation.json").write_text("{oops", encoding="utf-8")
    ex = _ex()
    with pytest.raises(ConfigError, match="rotation.json"):
        approve.revoke(_ctx(ex), s, "desk", "lap", lambda r: True)
    assert _no_pass_init(ex) and s.record("devices", "lap") is not None


def test_approve_refuses_a_revoked_key_under_any_name(tmp_path: Path) -> None:
    """I1: a revoked device must not come back by re-requesting under a fresh name."""
    s = _store(tmp_path, [FP_ME])
    s.write_record("devices", DeviceRecord(name="old", fingerprint=FP_NEW, os="fedora"), ARMOR)
    s.move("devices", "revoked", "old")
    s.write_record("pending", DeviceRecord(name="fresh", fingerprint=FP_NEW.lower(), os="x"),
                   ARMOR)
    ex = _ex()
    with pytest.raises(ConfigError, match="revoked"):
        approve.approve(_ctx(ex), s, "desk", "fresh", lambda r: True)
    assert _no_pass_init(ex) and s.record("devices", "fresh") is None
