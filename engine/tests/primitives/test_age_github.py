from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from devboost.core.errors import GithubError, SecretsError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import age, github
from devboost.model import Ctx

FEDORA = OsInfo("fedora", "fedora", "x86_64")
_BUNDLE_JSON = json.dumps({"GIT_USER": "u", "GIT_EMAIL": "e@x", "GITHUB_PAT": "ghp_x"})


def _ctx(stdout: str = _BUNDLE_JSON, code: int = 0) -> tuple[Ctx, FakeExecutor]:
    ex = FakeExecutor(scripts={"age": Result(code, stdout=stdout)})
    return Ctx(os=FEDORA, ex=ex), ex


def _bundle(tmp_path: Path) -> Path:
    b = tmp_path / "secrets.age"
    b.write_text("ciphertext", encoding="utf-8")
    return b


def test_age_decrypt_returns_dict(tmp_path: Path) -> None:
    ctx, _ = _ctx()
    data = age.decrypt(ctx, _bundle(tmp_path), tmp_path / "key")
    assert data["GIT_EMAIL"] == "e@x"


def test_age_decrypt_missing_bundle_raises(tmp_path: Path) -> None:
    ctx, _ = _ctx()
    with pytest.raises(SecretsError):
        age.decrypt(ctx, tmp_path / "nope.age", tmp_path / "key")


def test_age_decrypt_bad_cipher_raises(tmp_path: Path) -> None:
    ctx, _ = _ctx(code=1)
    with pytest.raises(SecretsError):
        age.decrypt(ctx, _bundle(tmp_path), tmp_path / "key")


def test_age_doctor_states(tmp_path: Path) -> None:
    ok_ctx, _ = _ctx()
    assert age.doctor_state(ok_ctx, _bundle(tmp_path), tmp_path / "key") == "ok"
    assert age.doctor_state(ok_ctx, tmp_path / "nope.age", tmp_path / "key") == "missing"
    bad_ctx, _ = _ctx(code=1)
    assert age.doctor_state(bad_ctx, _bundle(tmp_path), tmp_path / "key") == "cannot-decrypt"
    incomplete_ctx, _ = _ctx(stdout=json.dumps({"GIT_USER": "u"}))
    assert age.doctor_state(incomplete_ctx, _bundle(tmp_path), tmp_path / "key") == "incomplete"


# --- github primitive (injected fake HTTP) ---------------------------------------------


class FakeHttp:
    def __init__(self, get_body: str, post_status: int = 201) -> None:
        self.get_body = get_body
        self.post_status = post_status
        self.calls: list[tuple[str, str]] = []

    def __call__(
        self, method: str, url: str, headers: Mapping[str, str], body: bytes | None
    ) -> github.HttpResponse:
        self.calls.append((method, url))
        if method == "GET":
            return github.HttpResponse(200, self.get_body)
        return github.HttpResponse(self.post_status, "{}")


def test_github_uploads_new_key() -> None:
    http = FakeHttp(get_body="[]")
    assert github.upload_ssh_key("pat", "ssh-ed25519 AAA", "devboost:host", http=http) is True
    assert ("POST", f"{github.API}/user/keys") in http.calls


def test_github_skips_duplicate_title() -> None:
    http = FakeHttp(get_body=json.dumps([{"title": "devboost:host", "key": "other"}]))
    assert github.upload_ssh_key("pat", "ssh-ed25519 AAA", "devboost:host", http=http) is True
    assert ("POST", f"{github.API}/user/keys") not in http.calls


def test_github_raises_on_post_failure() -> None:
    http = FakeHttp(get_body="[]", post_status=422)
    with pytest.raises(GithubError):
        github.upload_ssh_key("pat", "ssh-ed25519 AAA", "devboost:host", http=http)
