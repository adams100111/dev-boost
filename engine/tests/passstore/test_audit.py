from __future__ import annotations

from pathlib import Path

from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.passstore import audit
from devboost.passstore.layout import DeviceRecord, Store
from tests.passstore.fakes import RuleExecutor

FEDORA = OsInfo("fedora", "fedora", "x86_64")
FP_A = "A" * 24 + "1111111111111111"
FP_B = "B" * 24 + "2222222222222222"
SUB_A, SUB_B = "AAAA0000AAAA0000", "BBBB0000BBBB0000"
ARMOR = "-----BEGIN PGP PUBLIC KEY BLOCK-----\nx\n"


def _keys(*pairs: tuple[str, str]) -> str:
    out = ""
    for fp, sub in pairs:
        out += (
            f"pub:u:255:22:{fp[-16:]}:1:::u:::scESC:::::ed25519:::0:\n"
            f"fpr:::::::::{fp}:\n"
            f"sub:u:255:18:{sub}:1::::::e:::::cv25519::\n"
            f"fpr:::::::::{'F' * 24}{sub}:\n"
        )
    return out


def _packets(*subs: str) -> Result:
    return Result(0, "".join(
        f":pubkey enc packet: version 3, algo 18, keyid {s}\n" for s in subs
    ))


def _store(tmp_path: Path) -> Store:
    root = tmp_path / "store"
    (root / ".git").mkdir(parents=True)
    (root / "web").mkdir()
    (root / ".gpg-id").write_text(FP_A + "\n", encoding="utf-8")
    for e in ("web/ok", "web/offline"):
        (root / f"{e}.gpg").write_bytes(b"x")
    s = Store(root)
    s.write_record("devices", DeviceRecord(name="alpha", fingerprint=FP_A, os="fedora"), ARMOR)
    s.write_record("revoked", DeviceRecord(name="bravo", fingerprint=FP_B, os="macos"), ARMOR)
    return s


def _ex(store: Store) -> RuleExecutor:
    return RuleExecutor(rules=[
        (("--list-packets", str(store.root / "web/offline.gpg")), _packets(SUB_A, SUB_B)),
        (("--list-packets",), _packets(SUB_A)),
        # bravo's key is gone from the keyring (sync deleted it) — only its store file names it
        (("--show-keys", str(store.key_path("revoked", "bravo"))),
         Result(0, _keys((FP_B, SUB_B)))),
        (("--show-keys",), Result(0, _keys((FP_A, SUB_A)))),
        (("--list-keys",), Result(0, _keys((FP_A, SUB_A)))),
    ])


def test_offline_entry_still_encrypted_to_a_revoked_key_is_flagged(tmp_path: Path) -> None:
    s = _store(tmp_path)
    report = audit.audit(Ctx(os=FEDORA, ex=_ex(s)), s)
    assert report.mismatches == [audit.Mismatch("web/offline", ("bravo (revoked)",), ())]
    assert report.unauditable == []
    hint = audit.fix_hint(s, report.mismatches[0])
    assert "pass init " + FP_A in hint and "pass edit web/offline" in hint


def test_missing_recipient_is_flagged(tmp_path: Path) -> None:
    s = _store(tmp_path)
    (s.root / ".gpg-id").write_text(f"{FP_A}\n{FP_B}\n", encoding="utf-8")
    ex = _ex(s)
    ex.rules.insert(0, (("--list-packets",), _packets(SUB_A)))
    report = audit.audit(Ctx(os=FEDORA, ex=ex), s)
    assert {m.entry for m in report.mismatches} == {"web/ok", "web/offline"}
    # labels name registered keys, even when the name is a revoked record's
    assert all(m.missing == ("bravo (revoked)",) and m.extra == () for m in report.mismatches)


def test_unknown_recipient_stays_a_key_id(tmp_path: Path) -> None:
    s = _store(tmp_path)
    ex = _ex(s)
    ex.rules.insert(0, (("--list-packets",), _packets(SUB_A, "0123456789ABCDEF")))
    report = audit.audit(Ctx(os=FEDORA, ex=ex), s)
    assert report.mismatches[0].extra == ("0123456789ABCDEF",)


def test_forged_key_file_cannot_rename_a_recipient(tmp_path: Path) -> None:
    """A pushed .asc only vouches for its own record's fingerprint (R9)."""
    s = _store(tmp_path)
    ex = _ex(s)
    ex.rules.insert(0, (("--show-keys", str(s.key_path("revoked", "bravo"))),
                        Result(0, _keys((FP_A, SUB_B)))))
    report = audit.audit(Ctx(os=FEDORA, ex=ex), s)
    assert report.mismatches == [audit.Mismatch("web/offline", (SUB_B,), ())]


def test_email_gpg_id_folder_is_unauditable_not_flagged(tmp_path: Path) -> None:
    s = _store(tmp_path)
    (s.root / "web" / ".gpg-id").write_text("me@example.com\n", encoding="utf-8")
    report = audit.audit(Ctx(os=FEDORA, ex=_ex(s)), s)
    assert report.mismatches == [] and report.unauditable == ["web"]


def test_unreadable_entry_is_reported(tmp_path: Path) -> None:
    s = _store(tmp_path)
    ex = _ex(s)
    ex.rules.insert(0, (("--list-packets", str(s.root / "web/ok.gpg")), Result(2)))
    report = audit.audit(Ctx(os=FEDORA, ex=ex), s)
    assert audit.Mismatch("web/ok", ("<unreadable>",), ()) in report.mismatches
