"""One shared fake for what the real `voxtype` (and the dotfiles apply) leave on disk.

Used by the voxtype, voxtype-arabic and voxtype-config tests, so the simulated side
effects live in one place (like `macos_fakes.PrefsExecutor` for `defaults`).
"""

from __future__ import annotations

import plistlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from devboost.exec.executor import Result
from devboost.modules import voxtype as vox
from tests.passstore.fakes import RuleExecutor

#: What the Voxtype template renders with the voxtype-arabic marker present.
ARABIC_RENDERED = (
    "# devboost — managed by chezmoi (dotfiles/dot_config/voxtype/config.toml.tmpl)\n"
    '[whisper]\nmodel = "small.en"\nsecondary_model = "large-v3-turbo"\n'
)


def fake_model(name: str) -> bytes:
    """The bytes the fake writes for model *name* (tests pin MODEL_SHA256 to their hash)."""
    return f"lmgg fake {name}".encode()


def write_bundle(version: str) -> None:
    """Voxtype.app at `vox.APP_BUNDLE` (conftest points it under tmp_path) at *version*."""
    contents = vox.APP_BUNDLE / "Contents"
    contents.mkdir(parents=True, exist_ok=True)
    (contents / "Info.plist").write_bytes(
        plistlib.dumps({"CFBundleShortVersionString": version})
    )


def _download_to(env: Mapping[str, str] | None, name: str) -> None:
    """Where voxtype writes a model: $XDG_DATA_HOME/voxtype/models (the env it was given)."""
    base = Path(env["XDG_DATA_HOME"]) if env and "XDG_DATA_HOME" in env else None
    target = (base / "voxtype" / "models" / f"ggml-{name}.bin") if base else vox.model_file(name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(fake_model(name))


@dataclass
class VoxtypeExecutor(RuleExecutor):
    """The real tools' side effects:

    - `voxtype setup --download --model <m>` writes the model under $XDG_DATA_HOME;
    - `voxtype setup app-bundle` writes Voxtype.app at ``version``;
    - `voxtype --version` answers; the pinned macOS binary (by path) only once an
      `install … <bin_path>` call has put it there (``installed``);
    - `chezmoi apply` writes ``rendered`` as the Voxtype config (None: writes nothing).
    """

    version: str = "1.0.1"
    installed: bool = False
    rendered: str | None = ARABIC_RENDERED

    def run(
        self,
        argv: Sequence[str],
        *,
        sudo: bool = False,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
        cwd: Path | None = None,
        interactive: bool = False,
    ) -> Result:
        res = super().run(argv, sudo=sudo, stdin=stdin, env=env, cwd=cwd,
                          interactive=interactive)
        args = list(argv)
        if args and args[0] == "install" and args[-1] == str(vox.bin_path()) and res.ok:
            self.installed = True
        if args[:2] == ["chezmoi", "apply"] and res.ok and self.rendered is not None:
            cfg = vox._config_file()
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_text(self.rendered, encoding="utf-8")
        if not args or args[0] not in {"voxtype", str(vox.bin_path())}:
            return res
        rest = args[1:]
        if rest[:2] == ["setup", "--download"] and res.ok:
            _download_to(env, rest[rest.index("--model") + 1])
        elif rest == ["setup", "app-bundle"]:
            write_bundle(self.version)
        elif rest == ["--version"]:
            if args[0] == "voxtype" or self.installed:
                return Result(0, f"voxtype {self.version}\n")
            return Result(127, "", "no such file")
        return res
