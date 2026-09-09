# Orca module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Two opt-in dev-boost modules — `orca-ide` (install Orca per-OS) and `orca-serve` (headless box via systemd --user) — with `orca`/`orca-box` profiles.

**Architecture:** Per spec `docs/superpowers/specs/2026-09-09-orca-module-design.md`. `orca-ide` installs the latest Orca release per OS (Fedora `.rpm`/dnf, Ubuntu `.deb`/apt via a `sh -c` release-asset fetch; Arch `pkg.install_aur("stably-orca-bin")`). `orca-serve` writes a systemd `--user` unit running `xvfb-run -a <cmd> serve …`, enables linger, derives the pairing address from Tailscale.

**Tech Stack:** typed-Python engine; builds on the landed Omarchy `Pacman`/`install_aur` + `families` scoping.

## Global Constraints

- Gates: `uv run ruff check`, `uv run mypy`, `uv run pytest` green (run from `engine/`); 100-col lines.
- Module names `orca-ide`/`orca-serve`; profiles `orca`/`orca-box` — must differ (collision rule).
- HARD failure = raise `devboost.core.errors.ConfigError`; SOFT = `log.warn` + continue.
- `orca-ide` must **NOT** set `gui=True` (headless boxes skip gui modules → would break `orca-serve`).
- Command name per-OS: `_ORCA_CMD = OsMap(fedora="orca-ide", debian="orca-ide", arch="stably-orca")`.
- `families`: `orca-ide` = `("fedora","debian","arch")`; `orca-serve` = `("fedora","debian")`.
- Version: `DEVBOOST_ORCA_VERSION` (empty = latest → `releases/latest`; set → `releases/tags/v<ver>`).
- No Claude/Anthropic reference in commits.

---

### Task 1: `orca-ide` module + `orca` profile + tests

**Files:**
- Create: `engine/src/devboost/modules/orca.py`
- Modify: `profiles.toml` (add `orca = ["orca-ide"]`)
- Modify: `engine/tests/conftest.py`, `engine/tests/cli/test_lifecycle_devhygiene.py` (add `orca = ["orca-ide"]` stub — required or `validate_profiles` fails load-wide)
- Create: `engine/tests/modules/test_orca.py`

**Interfaces:** Consumes `pkg.install_aur`, `pkg.install`, `OsMap`, `ConfigError`, `Ctx/Module`, `FakeExecutor(present=, scripts=, calls=)` (scripts maps FIRST argv token → Result; env NOT recorded → assert on `sh -c` argv text). Produces module `orca-ide` + `_ORCA_CMD` (reused by Task 2).

- [ ] **Step 1: profile stub first** — add to `profiles.toml`: `orca = ["orca-ide"]` (after the `omarchy` block). Add `'orca = ["orca-ide"]\n'` to the profiles.toml fixture in `engine/tests/conftest.py` and to the inline table in `engine/tests/cli/test_lifecycle_devhygiene.py` (grep `grep -rn 'codex = \["codex-code"\]' engine/tests` for any other inline fixture and add there too).

- [ ] **Step 2: failing tests** — create `engine/tests/modules/test_orca.py`:
```python
from __future__ import annotations

import pytest

from devboost.core.errors import ConfigError
from devboost.core.osinfo import OsInfo
from devboost.exec.executor import FakeExecutor, Result
from devboost.model import Ctx
from devboost.modules.orca import OrcaIde

FEDORA = OsInfo("fedora", "fedora", "x86_64")
FEDORA_ARM = OsInfo("fedora", "fedora", "aarch64")
UBUNTU = OsInfo("ubuntu", "debian", "x86_64")
OMARCHY = OsInfo("omarchy", "arch", "x86_64", id_like=("arch",))
MAC = OsInfo("macos", "macos", "arm64")


def _ctx(os: OsInfo = FEDORA, **kw: object) -> Ctx:
    return Ctx(os=os, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def _joined(ctx: Ctx) -> list[str]:
    return [" ".join(c) for c in ctx.ex.calls]  # type: ignore[attr-defined]


def test_verify_uses_per_os_command() -> None:
    assert OrcaIde().verify(_ctx(FEDORA, present={"orca-ide"})) is True
    assert OrcaIde().verify(_ctx(OMARCHY, present={"stably-orca"})) is True
    assert OrcaIde().verify(_ctx(OMARCHY, present={"orca-ide"})) is False  # wrong name on arch


def test_fedora_fetches_rpm_and_dnf_installs() -> None:
    ctx = _ctx(FEDORA, present={"orca-ide"})
    OrcaIde().install(ctx)
    j = _joined(ctx)
    assert any("api.github.com/repos/stablyai/orca/releases/latest" in c for c in j)
    assert any(r"orca-ide-" in c and "x86_64" in c and ".rpm" in c for c in j)
    assert any("dnf install -y" in c for c in j)


def test_fedora_arm_matches_aarch64() -> None:
    ctx = _ctx(FEDORA_ARM, present={"orca-ide"})
    OrcaIde().install(ctx)
    assert any("aarch64" in c and ".rpm" in c for c in _joined(ctx))


def test_ubuntu_fetches_deb_amd64_and_apt_installs() -> None:
    ctx = _ctx(UBUNTU, present={"orca-ide"})
    OrcaIde().install(ctx)
    j = _joined(ctx)
    assert any("orca-ide_" in c and "amd64" in c and ".deb" in c for c in j)
    assert any("apt install -y" in c for c in j)


def test_arch_installs_via_aur() -> None:
    ctx = _ctx(OMARCHY, present={"stably-orca", "yay"})
    OrcaIde().install(ctx)
    assert any("stably-orca-bin" in c for c in _joined(ctx))


def test_pinned_version_uses_tag() -> None:
    ctx = _ctx(FEDORA, present={"orca-ide"})
    import os as _os
    _os.environ["DEVBOOST_ORCA_VERSION"] = "1.4.198"
    try:
        OrcaIde().install(ctx)
    finally:
        del _os.environ["DEVBOOST_ORCA_VERSION"]
    assert any("releases/tags/v1.4.198" in c for c in _joined(ctx))


def test_unsupported_os_raises() -> None:
    with pytest.raises(ConfigError):
        OrcaIde().install(_ctx(MAC))
```

- [ ] **Step 3: run → fail** (`cd engine && uv run pytest tests/modules/test_orca.py -q` → ModuleNotFound).

- [ ] **Step 4: implement** — create `engine/src/devboost/modules/orca.py`:
```python
"""orca — install the Orca agent development environment (stablyai/orca)."""

from __future__ import annotations

import os

from devboost.core.errors import ConfigError
from devboost.core.osinfo import OsMap
from devboost.core.registry import register
from devboost.exec.primitives import pkg
from devboost.model import Ctx, Module

_REPO = "stablyai/orca"
#: Linux command differs by distro: .rpm/.deb install `orca-ide`; the AUR `stably-orca-bin`
#: installs `stably-orca` (a pass-through wrapper over the same release binary).
_ORCA_CMD: OsMap[str] = OsMap(fedora="orca-ide", debian="orca-ide", arch="stably-orca")
_RARCH = {"x86_64": "x86_64", "aarch64": "aarch64"}
_DARCH = {"x86_64": "amd64", "aarch64": "arm64"}


def orca_cmd(ctx: Ctx) -> str:
    cmd = _ORCA_CMD.get(ctx.os)
    if cmd is None:
        raise ConfigError(f"orca: unsupported OS {ctx.os.distro!r}")
    return cmd


def _release_ref() -> str:
    ver = os.environ.get("DEVBOOST_ORCA_VERSION", "")
    return f"tags/v{ver}" if ver else "latest"


def _fetch_script(pattern: str, install_cmd: str, suffix: str) -> str:
    api = f"https://api.github.com/repos/{_REPO}/releases/{_release_ref()}"
    return (
        f"set -e; "
        f"url=$(curl -fsSL \"{api}\" | grep -oE 'https://[^\"]*{pattern}' | head -1); "
        f"[ -n \"$url\" ] || {{ echo 'orca-ide: no asset for {pattern}' >&2; exit 1; }}; "
        f"f=$(mktemp --suffix={suffix}); curl -fsSL \"$url\" -o \"$f\"; "
        f"{install_cmd} \"$f\"; rm -f \"$f\""
    )


@register
class OrcaIde(Module):
    name = "orca-ide"
    category = "orca"
    description = "Orca — multi-agent development environment (stablyai/orca)."
    profiles = ("orca",)
    families = ("fedora", "debian", "arch")

    def verify(self, ctx: Ctx) -> bool:
        return ctx.ex.which(orca_cmd(ctx))

    def install(self, ctx: Ctx) -> None:
        if ctx.os.family == "arch":
            # Upstream-recommended AUR build of the release binary (command: `stably-orca`).
            pkg.install_aur(ctx, "stably-orca-bin")
            return
        if ctx.os.family == "fedora":
            rarch = _RARCH.get(ctx.os.arch)
            if rarch is None:
                raise ConfigError(f"orca-ide: no rpm for arch {ctx.os.arch!r}")
            script = _fetch_script(rf"orca-ide-[^\"/]*\.{rarch}\.rpm", "sudo dnf install -y", ".rpm")
        elif ctx.os.family == "debian":
            darch = _DARCH.get(ctx.os.arch)
            if darch is None:
                raise ConfigError(f"orca-ide: no deb for arch {ctx.os.arch!r}")
            script = _fetch_script(rf"orca-ide_[^\"/]*_{darch}\.deb", "sudo apt install -y", ".deb")
        else:
            raise ConfigError(f"orca-ide: unsupported OS family {ctx.os.family!r}")
        res = ctx.ex.run(["sh", "-c", script])
        if not res.ok:
            raise ConfigError(f"orca-ide: install failed (exit {res.code})")
```

- [ ] **Step 5: run → pass** (`uv run pytest tests/modules/test_orca.py -q`).
- [ ] **Step 6: gates** (`cd engine && uv run ruff check && uv run mypy && uv run pytest -q`).
- [ ] **Step 7: commit** — `git add engine/src/devboost/modules/orca.py engine/tests/modules/test_orca.py profiles.toml engine/tests/conftest.py engine/tests/cli/test_lifecycle_devhygiene.py` → `feat(orca): orca-ide installs Orca per-OS (Fedora rpm / Ubuntu deb / Arch AUR); opt-in orca profile`.

---

### Task 2: `orca-serve` module + `orca-box` profile + tests

**Files:**
- Modify: `engine/src/devboost/modules/orca.py` (add `OrcaServe`)
- Modify: `profiles.toml` (`orca-box = ["orca-ide", "orca-serve"]`)
- Modify: `engine/tests/conftest.py`, `engine/tests/cli/test_lifecycle_devhygiene.py` (add `orca-box` stub)
- Modify: `engine/tests/modules/test_orca.py` (add OrcaServe tests)

**Interfaces:** Consumes `systemd.write_user_unit/enable_user_unit/is_enabled`, `pkg.install(OsMap)`, `_invoking_user` idiom, `orca_cmd`, `OrcaIde`. `write_user_unit` writes `$HOME/.config/systemd/user/` → tests monkeypatch `HOME` to `tmp_path`.

- [ ] **Step 1: profile stub** — `profiles.toml`: `orca-box = ["orca-ide", "orca-serve"]`. Add `orca-box` stub to both test fixtures (as in Task 1).

- [ ] **Step 2: failing tests** — append to `test_orca.py`:
```python
from pathlib import Path

from devboost.modules.orca import OrcaServe


def _serve_ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, os: OsInfo = FEDORA, **kw: object) -> Ctx:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USER", "dev")
    return Ctx(os=os, ex=FakeExecutor(**kw))  # type: ignore[arg-type]


def _unit_text(tmp_path: Path) -> str:
    return (tmp_path / ".config" / "systemd" / "user" / "orca-serve.service").read_text(encoding="utf-8")


def test_serve_writes_unit_with_env_pairing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVBOOST_ORCA_PAIRING_ADDRESS", "100.64.1.20")
    ctx = _serve_ctx(tmp_path, monkeypatch, FEDORA, present={"orca-ide"})
    OrcaServe().install(ctx)
    u = _unit_text(tmp_path)
    assert "xvfb-run -a orca-ide serve" in u
    assert "--pairing-address 100.64.1.20" in u
    assert "LIBGL_ALWAYS_SOFTWARE=1" in u
    assert "RestartPreventExitStatus=3" in u
    j = _joined(ctx)
    assert any("xorg-x11-server-Xvfb" in c for c in j)              # xvfb on fedora
    assert any("enable-linger dev" in c for c in j)
    assert any("systemctl --user enable --now orca-serve.service" in c for c in j)


def test_serve_derives_tailscale_ip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEVBOOST_ORCA_PAIRING_ADDRESS", raising=False)
    ctx = _serve_ctx(
        tmp_path, monkeypatch, UBUNTU,
        present={"orca-ide", "tailscale"},
        scripts={"tailscale": Result(0, stdout="100.99.1.5\n")},
    )
    OrcaServe().install(ctx)
    u = _unit_text(tmp_path)
    assert "--pairing-address 100.99.1.5" in u
    assert any("xvfb" == c or "install" in c and "xvfb" in c for c in _joined(ctx))  # xvfb on debian


def test_serve_no_pairing_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEVBOOST_ORCA_PAIRING_ADDRESS", raising=False)
    ctx = _serve_ctx(tmp_path, monkeypatch, FEDORA, present={"orca-ide"})  # no tailscale
    with pytest.raises(ConfigError):
        OrcaServe().install(ctx)


def test_serve_custom_port(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVBOOST_ORCA_PAIRING_ADDRESS", "10.0.0.9")
    monkeypatch.setenv("DEVBOOST_ORCA_PORT", "7000")
    ctx = _serve_ctx(tmp_path, monkeypatch, FEDORA, present={"orca-ide"})
    OrcaServe().install(ctx)
    assert "--port 7000" in _unit_text(tmp_path)


def test_serve_verify_uses_is_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ok = _serve_ctx(tmp_path, monkeypatch, FEDORA, present={"orca-ide"})
    assert OrcaServe().verify(ok) is True   # FakeExecutor is-enabled → Result(0)
    bad = _serve_ctx(tmp_path, monkeypatch, FEDORA, scripts={"systemctl": Result(1)})
    assert OrcaServe().verify(bad) is False
```

- [ ] **Step 3: run → fail**, then **Step 4: implement** — append to `orca.py`:
```python
from devboost.core import log
from devboost.exec.primitives import systemd

_ORCA_UNIT = """\
[Unit]
Description=Orca headless serve

[Service]
Type=simple
Environment=LIBGL_ALWAYS_SOFTWARE=1
ExecStart=/usr/bin/xvfb-run -a {cmd} serve --port {port} --pairing-address {addr}
Restart=on-failure
RestartPreventExitStatus=3

[Install]
WantedBy=default.target
"""


def _invoking_user() -> str:
    return os.environ.get("SUDO_USER") or os.environ.get("USER") or ""


@register
class OrcaServe(Module):
    name = "orca-serve"
    category = "orca"
    description = "Run Orca headless (orca-ide serve) as a systemd --user service."
    requires = (OrcaIde,)
    profiles = ("orca-box",)
    families = ("fedora", "debian")

    def verify(self, ctx: Ctx) -> bool:
        return systemd.is_enabled(ctx, "orca-serve.service", user=True)

    def _pairing_address(self, ctx: Ctx) -> str:
        env = os.environ.get("DEVBOOST_ORCA_PAIRING_ADDRESS")
        if env:
            return env
        if ctx.ex.which("tailscale"):
            res = ctx.ex.run(["tailscale", "ip", "-4"])
            lines = res.stdout.strip().splitlines()
            if res.ok and lines:
                return lines[0].strip()
        return ""

    def install(self, ctx: Ctx) -> None:
        pkg.install(ctx, OsMap(fedora="xorg-x11-server-Xvfb", debian="xvfb"))
        addr = self._pairing_address(ctx)
        if not addr:
            raise ConfigError(
                "orca-serve: no pairing address — set DEVBOOST_ORCA_PAIRING_ADDRESS or bring up "
                "Tailscale (`tailscale up`) on this box"
            )
        port = os.environ.get("DEVBOOST_ORCA_PORT", "6768")
        unit = _ORCA_UNIT.format(cmd=orca_cmd(ctx), port=port, addr=addr)
        systemd.write_user_unit(ctx, "orca-serve.service", unit)
        user = _invoking_user()
        if user:
            ctx.ex.run(["loginctl", "enable-linger", user], sudo=True)
        systemd.enable_user_unit(ctx, "orca-serve.service", now=True)
        log.info("orca-serve enabled; first pairing prints an orca://pair code in its journal")
```

- [ ] **Step 5–6: run tests + gates green.**
- [ ] **Step 7: commit** — `feat(orca): orca-serve runs headless orca-ide serve via systemd --user + linger; orca-box profile`.

---

### Task 3: profile-expansion lock + README regen

**Files:** Create `engine/tests/cli/test_orca_profile.py`; Modify `README.md`.

- [ ] **Step 1: lock test** (mirror `test_pi_profile.py` imports/`REPO_ROOT`):
```python
from pathlib import Path
from devboost.core.profiles import expand, load_profiles
from devboost.core.registry import load

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_orca_profiles_expand() -> None:
    p = load_profiles(REPO_ROOT / "profiles.toml"); m = load()
    assert expand(["orca"], p, m) == ["orca-ide"]
    assert expand(["orca-box"], p, m) == ["orca-ide", "orca-serve"]
```
- [ ] **Step 2: run → pass** (`uv run pytest tests/cli/test_orca_profile.py -q`).
- [ ] **Step 3: regenerate README** — `uv run --project engine python scripts/gen_profiles_table.py` and splice its output between the `<!-- BEGIN/END generated profiles table -->` markers in `README.md` (replace the block; keep surrounding prose). Confirm `orca`, `orca-box`, `orca-ide`, `orca-serve` rows appear.
- [ ] **Step 4: gates + commit** — `git add engine/tests/cli/test_orca_profile.py README.md` → `test(orca): lock orca/orca-box profile expansion; regen README tables`.

---

## Self-review notes

- Spec coverage: `orca-ide` per-OS install + per-OS command + version pin → Task 1; `orca-serve`
  headless (xvfb-run, linger, tailscale pairing) → Task 2; profile locks + README → Task 3.
- No placeholders. `families` scoping present on both modules; `orca-ide` deliberately not `gui=True`.
- FakeExecutor caveat: `env` not recorded → release-fetch details asserted via the `sh -c` argv text;
  guarded/branch behavior via `scripts={token: Result(...)}` and `present`.
- Types: `verify→bool`, `install→None`, `orca_cmd→str`, `_pairing_address→str`; module/profile names
  consistent across module, `profiles.toml`, and both fixtures.
