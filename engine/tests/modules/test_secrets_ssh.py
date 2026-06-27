from __future__ import annotations

import json
from pathlib import Path

import pytest

from devboost.core.errors import GithubError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.exec.primitives import github
from devboost.model import Ctx
from devboost.modules.secrets import Secrets, _bootstrap_root
from devboost.modules.ssh_setup import SshSetup

FEDORA = OsInfo("fedora", "fedora", "x86_64")
_JSON = json.dumps({"GIT_USER": "alice", "GIT_EMAIL": "a@x", "GITHUB_PAT": "ghp_x"})


@pytest.fixture
def home_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bundle = tmp_path / "secrets.age"
    bundle.write_text("cipher", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("DEVBOOST_SECRETS", str(bundle))
    monkeypatch.setenv("DEVBOOST_SECRETS_KEY", str(tmp_path / "key"))
    return tmp_path


def _ctx(present: set[str]) -> Ctx:
    ex = FakeExecutor(scripts={"age": Result(0, stdout=_JSON)}, present=present)
    return Ctx(os=FEDORA, ex=ex)


def test_bootstrap_root_uses_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVBOOST_BOOTSTRAP_DIR", "/mnt/usb/devboost")
    assert str(_bootstrap_root()) == "/mnt/usb/devboost"


def test_bootstrap_root_falls_back_to_opt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEVBOOST_BOOTSTRAP_DIR", raising=False)
    assert str(_bootstrap_root()) == "/opt/dev-boost"


def test_bootstrap_root_never_returns_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEVBOOST_BOOTSTRAP_DIR", raising=False)
    root = _bootstrap_root()
    assert str(root) != ".", "bootstrap root must never fall back to CWD"
    assert root.is_absolute(), "bootstrap root must be an absolute path"


def test_secrets_install_configures_git_and_credentials(home_env: Path) -> None:
    ctx = _ctx(present={"age"})
    Secrets().install(ctx)
    calls = ctx.ex.calls  # type: ignore[attr-defined]
    assert ["git", "config", "--global", "user.email", "a@x"] in calls
    assert ["git", "config", "--global", "credential.helper", "store"] in calls
    creds = home_env / ".git-credentials"
    assert creds.read_text(encoding="utf-8").strip() == "https://alice:ghp_x@github.com"
    assert (creds.stat().st_mode & 0o777) == 0o600


def test_secrets_verify_true_after_install(home_env: Path) -> None:
    ctx = _ctx(present={"age"})
    Secrets().install(ctx)
    # verify: git config user.email ok (FakeExecutor returns 0) + creds has github line
    assert Secrets().verify(ctx) is True


def test_ssh_setup_requires_secrets() -> None:
    assert Secrets in SshSetup.requires


def test_ssh_setup_install_hardens_config_and_writes_marker(
    home_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Pre-create the keypair so keygen is skipped and the pubkey exists.
    ssh = home_env / ".ssh"
    ssh.mkdir(mode=0o700)
    (ssh / "id_ed25519").write_text("priv", encoding="utf-8")
    (ssh / "id_ed25519.pub").write_text("ssh-ed25519 AAA", encoding="utf-8")
    monkeypatch.setattr(github, "upload_ssh_key", lambda *a, **k: True)

    ctx = _ctx(present={"age"})
    SshSetup().install(ctx)

    cfg = (ssh / "config").read_text(encoding="utf-8")
    assert "# BEGIN devboost-managed" in cfg and "IdentityFile ~/.ssh/id_ed25519" in cfg
    assert SshSetup().verify(ctx) is True


def test_ssh_setup_marker_absent_when_upload_fails(
    home_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ssh = home_env / ".ssh"
    ssh.mkdir(mode=0o700)
    (ssh / "id_ed25519").write_text("priv", encoding="utf-8")
    (ssh / "id_ed25519.pub").write_text("ssh-ed25519 AAA", encoding="utf-8")

    def _boom(*a: object, **k: object) -> bool:
        raise GithubError("nope")

    monkeypatch.setattr(github, "upload_ssh_key", _boom)
    ctx = _ctx(present={"age"})
    SshSetup().install(ctx)  # non-blocking
    assert SshSetup().verify(ctx) is False  # no marker
