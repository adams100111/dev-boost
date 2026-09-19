from __future__ import annotations

from pathlib import Path

import pytest

from devboost.core.errors import InstallError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import Result
from devboost.model import Ctx
from devboost.passstore import gpg
from devboost.passstore.gpg import KeyInfo
from tests.passstore.fakes import RuleExecutor, colons

FEDORA = OsInfo("fedora", "fedora", "x86_64")
FP_A = "A" * 32 + "01BD994F"
FP_B = "B" * 32 + "64F46F56"
UID = "Ada (devboost:lap) <ada@example.com>"


def _ctx(ex: RuleExecutor) -> Ctx:
    return Ctx(os=FEDORA, ex=ex)


def test_parse_colons_primary_fpr_and_uids_not_subkeys() -> None:
    out = colons("sec", FP_A, UID) + colons("sec", FP_B)
    assert gpg.parse_colons(out, "sec") == [KeyInfo(FP_A, (UID,)), KeyInfo(FP_B, ())]


def test_parse_colons_unescapes_uid() -> None:
    """`colons()` escapes `:` as `\\x3a` the way real gpg does; parse_colons must undo it."""
    out = colons("sec", FP_A, UID)
    assert "\\x3a" in out  # the fake really emits the escaped form
    assert gpg.parse_colons(out, "sec") == [KeyInfo(FP_A, (UID,))]


def test_matches_fingerprint_keyid_0x_and_email() -> None:
    key = KeyInfo(FP_A, (UID,))
    assert gpg.matches(FP_A.lower(), key)
    assert gpg.matches("0x" + FP_A[-16:], key)
    assert gpg.matches("ada@example.com", key)
    assert not gpg.matches(FP_B, key)
    assert not gpg.matches("", key)
    assert not gpg.matches("994F", key)  # too short to be a key id


def test_device_uid_and_device_key() -> None:
    assert gpg.device_uid("Ada", "ada@example.com", "lap") == UID
    keys = [KeyInfo(FP_B, ("Other <o@x>",)), KeyInfo(FP_A, (UID,))]
    assert gpg.device_key(keys, "lap") == keys[1]
    assert gpg.device_key(keys, "desk") is None


def test_generate_runs_keygen_then_encryption_subkey_via_pinentry() -> None:
    ex = RuleExecutor(rules=[(("--list-secret-keys",), Result(0, colons("sec", FP_A, UID)))])
    assert gpg.generate(_ctx(ex), UID) == FP_A
    expected = ["gpg", "--batch", "--quick-gen-key", UID, "ed25519", "cert,sign", "never"]
    assert ex.calls[0] == expected
    assert ex.calls[-1] == ["gpg", "--batch", "--quick-add-key", FP_A, "cv25519", "encr", "never"]
    assert ex.interactive[0] is True and ex.interactive[-1] is True


def test_generate_loopback_passphrase_for_tests() -> None:
    ex = RuleExecutor(rules=[(("--list-secret-keys",), Result(0, colons("sec", FP_A, UID)))])
    gpg.generate(_ctx(ex), UID, passphrase="")
    assert ex.calls[0][:5] == ["gpg", "--batch", "--pinentry-mode", "loopback", "--passphrase"]
    assert ex.interactive[0] is False


def test_generate_failure_raises() -> None:
    ex = RuleExecutor(rules=[(("--quick-gen-key",), Result(2))])
    with pytest.raises(InstallError, match="quick-gen-key"):
        gpg.generate(_ctx(ex), UID)


def test_export_armored_requires_output() -> None:
    armored = "-----BEGIN PGP PUBLIC KEY BLOCK-----\n"
    ex = RuleExecutor(rules=[(("--export",), Result(0, armored))])
    assert gpg.export_armored(_ctx(ex), FP_A) == armored
    with pytest.raises(InstallError):
        gpg.export_armored(_ctx(RuleExecutor()), FP_A)


def test_import_trusted_sets_ultimate_ownertrust(tmp_path: Path) -> None:
    ex = RuleExecutor()
    gpg.import_trusted(_ctx(ex), tmp_path / "k.asc", FP_A)
    assert ex.calls == [
        ["gpg", "--batch", "--import", str(tmp_path / "k.asc")],
        ["gpg", "--batch", "--import-ownertrust"],
    ]
    assert ex.stdins[1] == f"{FP_A}:6:\n"


def test_show_key_file_and_public_fingerprints(tmp_path: Path) -> None:
    ex = RuleExecutor(rules=[
        (("--show-keys",), Result(0, colons("pub", FP_B))),
        (("--list-keys",), Result(0, colons("pub", FP_A) + colons("pub", FP_B))),
    ])
    assert gpg.show_key_file(_ctx(ex), tmp_path / "b.asc") == [KeyInfo(FP_B, ())]
    assert gpg.public_fingerprints(_ctx(ex)) == {FP_A, FP_B}
