"""Credential fallback when no age bundle is provisioned.

The bundle is the zero-touch (USB/Kickstart) contract and must keep winning outright.
These tests pin the three properties that make the fallback safe: an unattended run never
waits for input, a signed-in `gh` session is offered rather than silently adopted, and
"skip" means skip.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from devboost.core.errors import SecretsError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules import _credentials as creds_src
from devboost.modules.secrets import Secrets

OMARCHY = OsInfo("omarchy", "arch", "x86_64", id_like=("arch",))

_USER_JSON = json.dumps({"login": "octocat", "email": "octocat@example.com"})


def _gh_ready() -> FakeExecutor:
    """A fake where `gh` exists and is signed in."""
    return FakeExecutor(
        present={"gh", "git"},
        scripts={"gh": Result(0, stdout=_USER_JSON)},
    )


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    # Point the bundle at a path that does not exist, so these tests exercise the fallback.
    monkeypatch.setenv("DEVBOOST_BOOTSTRAP_DIR", str(tmp_path / "no-bundle"))


# ---------------------------------------------------------------------------
# Unattended runs must never block
# ---------------------------------------------------------------------------


def test_non_interactive_raises_instead_of_prompting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A firstboot service / curl|bash run has nobody at the keyboard: fail, don't hang."""
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")

    def _explode() -> None:
        raise AssertionError("prompted during a non-interactive run")

    monkeypatch.setattr(
        creds_src, "resolve_interactively", lambda ctx, existing=None: _explode()
    )
    with pytest.raises(SecretsError) as exc:
        Secrets().install(Ctx(os=OMARCHY, ex=FakeExecutor(present={"git"})))
    # The error has to be actionable, not just "file not found".
    assert "gh auth login" in str(exc.value)
    assert "make-secrets.sh" in str(exc.value)


def test_is_interactive_is_forced_off_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")
    assert creds_src.is_interactive() is False


# ---------------------------------------------------------------------------
# An authenticated gh: offered at a terminal, used directly when unattended
# ---------------------------------------------------------------------------


def test_unattended_run_uses_the_signed_in_gh_directly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With nobody to confirm with, using the session beats failing outright."""
    monkeypatch.setenv("DEVBOOST_NONINTERACTIVE", "1")
    ex = _gh_ready()
    Secrets().install(Ctx(os=OMARCHY, ex=ex))

    assert ["gh", "auth", "status"] in ex.calls
    assert ["git", "config", "--global", "user.name", "octocat"] in ex.calls
    assert ["git", "config", "--global", "user.email", "octocat@example.com"] in ex.calls
    assert "@github.com" in (tmp_path / ".git-credentials").read_text(encoding="utf-8")


def test_at_a_terminal_the_signed_in_account_is_offered_not_assumed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gh session on this machine may be a different account than this box should
    commit as. Adopting it silently would write the wrong identity into every commit."""
    seen: dict[str, object] = {}

    def _record(ctx: Ctx, existing: dict[str, str] | None = None) -> dict[str, str] | None:
        seen["existing"] = existing
        return existing

    monkeypatch.setattr(creds_src, "is_interactive", lambda: True)
    monkeypatch.setattr(creds_src, "resolve_interactively", _record)
    Secrets().install(Ctx(os=OMARCHY, ex=_gh_ready()))

    offered = seen["existing"]
    assert isinstance(offered, dict)
    assert offered["GIT_USER"] == "octocat"


def test_choosing_skip_is_respected_even_when_gh_is_signed_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """"Skip" must not be quietly overridden by the gh session we just offered."""
    monkeypatch.setattr(creds_src, "is_interactive", lambda: True)
    monkeypatch.setattr(creds_src, "resolve_interactively", lambda ctx, existing=None: None)
    with pytest.raises(SecretsError):
        Secrets().install(Ctx(os=OMARCHY, ex=_gh_ready()))


def test_menu_offers_the_account_by_name_when_signed_in() -> None:
    keys = [k for k, _ in creds_src.menu_for("octocat")]
    assert keys == ["use-gh", "gh", "manual", "skip"]
    label = dict(creds_src.menu_for("octocat"))["use-gh"]
    assert "octocat" in label, "the operator must see WHICH account they are accepting"


def test_menu_has_no_use_gh_row_when_not_signed_in() -> None:
    keys = [k for k, _ in creds_src.menu_for(None)]
    assert keys == ["gh", "manual", "skip"]


class _Gh(FakeExecutor):
    """FakeExecutor keyed on the gh SUBcommand, so `api user` and `auth token` differ."""

    def __init__(self, responses: dict[str, Result]) -> None:
        super().__init__(present={"gh", "git"})
        self.responses = responses

    def run(self, argv, *, sudo=False, stdin=None, env=None, cwd=None, interactive=False):  # type: ignore[no-untyped-def]  # noqa: E501
        super().run(
            argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd, interactive=interactive
        )
        for prefix, result in self.responses.items():
            if " ".join(argv).startswith(prefix):
                return result
        return Result(0)


def test_gh_credentials_are_dropped_when_the_token_is_unavailable() -> None:
    """Signed in but no usable token (revoked session) must not yield partial creds —
    a half-filled dict would configure git with an identity that cannot authenticate."""
    ex = _Gh({
        "gh api user": Result(0, stdout=_USER_JSON),
        "gh auth token": Result(1, stderr="no oauth token"),
    })
    assert creds_src.from_gh(Ctx(os=OMARCHY, ex=ex)) is None


def test_gh_credentials_are_dropped_when_the_token_is_empty() -> None:
    ex = _Gh({
        "gh api user": Result(0, stdout=_USER_JSON),
        "gh auth token": Result(0, stdout="   \n"),
    })
    assert creds_src.from_gh(Ctx(os=OMARCHY, ex=ex)) is None


def test_gh_falls_back_to_the_primary_email_when_the_profile_hides_it() -> None:
    """A GitHub profile with a private email returns null — use the account's primary."""
    ex = _Gh({
        "gh api user/emails": Result(
            0, stdout=json.dumps([
                {"email": "alt@example.com", "primary": False},
                {"email": "primary@example.com", "primary": True},
            ]),
        ),
        "gh api user": Result(0, stdout=json.dumps({"login": "octocat"})),
        "gh auth token": Result(0, stdout="ghp_realtoken"),
    })
    got = creds_src.from_gh(Ctx(os=OMARCHY, ex=ex))
    assert got == {
        "GIT_USER": "octocat",
        "GIT_EMAIL": "primary@example.com",
        "GITHUB_PAT": "ghp_realtoken",
    }


def test_from_gh_returns_none_without_a_login() -> None:
    ex = FakeExecutor(present={"gh"}, scripts={"gh": Result(0, stdout="{}")})
    assert creds_src.from_gh(Ctx(os=OMARCHY, ex=ex)) is None


def test_gh_is_authenticated_is_false_when_gh_is_absent() -> None:
    assert creds_src.gh_is_authenticated(Ctx(os=OMARCHY, ex=FakeExecutor())) is False


def test_gh_is_authenticated_is_false_when_signed_out() -> None:
    ex = FakeExecutor(present={"gh"}, scripts={"gh": Result(1, stderr="not logged in")})
    assert creds_src.gh_is_authenticated(Ctx(os=OMARCHY, ex=ex)) is False


# ---------------------------------------------------------------------------
# The bundle still wins outright — zero-touch behaviour is unchanged
# ---------------------------------------------------------------------------


def test_provisioned_bundle_takes_precedence_over_gh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    boot = tmp_path / "boot"
    boot.mkdir()
    (boot / "secrets.age").write_text("ciphertext", encoding="utf-8")
    (boot / "age-key.txt").write_text("key", encoding="utf-8")
    monkeypatch.setenv("DEVBOOST_BOOTSTRAP_DIR", str(boot))

    bundle = json.dumps(
        {"GIT_USER": "from-bundle", "GIT_EMAIL": "b@example.com", "GITHUB_PAT": "tok"}
    )
    ex = FakeExecutor(present={"age", "gh", "git"}, scripts={"age": Result(0, stdout=bundle)})
    monkeypatch.setattr(
        creds_src, "from_gh", lambda ctx: pytest.fail("consulted gh despite a bundle")
    )
    Secrets().install(Ctx(os=OMARCHY, ex=ex))
    assert ["git", "config", "--global", "user.name", "from-bundle"] in ex.calls


def test_incomplete_bundle_still_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    boot = tmp_path / "boot"
    boot.mkdir()
    (boot / "secrets.age").write_text("ciphertext", encoding="utf-8")
    monkeypatch.setenv("DEVBOOST_BOOTSTRAP_DIR", str(boot))
    partial = json.dumps({"GIT_USER": "x", "GIT_EMAIL": "y@example.com"})  # no PAT
    ex = FakeExecutor(present={"age"}, scripts={"age": Result(0, stdout=partial)})
    with pytest.raises(SecretsError, match="GITHUB_PAT"):
        Secrets().install(Ctx(os=OMARCHY, ex=ex))


# ---------------------------------------------------------------------------
# verify() accepts either credential source
# ---------------------------------------------------------------------------


def test_verify_accepts_an_authenticated_gh_with_no_credentials_file(
    tmp_path: Path,
) -> None:
    """`gh auth setup-git` stores no plaintext token — that box is configured, not broken."""
    ex = _gh_ready()
    assert not (tmp_path / ".git-credentials").exists()
    assert Secrets().verify(Ctx(os=OMARCHY, ex=ex)) is True


def test_verify_is_false_without_any_credential_source(tmp_path: Path) -> None:
    ex = FakeExecutor(present={"git"})
    assert Secrets().verify(Ctx(os=OMARCHY, ex=ex)) is False
