# Contract: `ffmpeg-full` + `codecs` (US1)

Escape-hatch modules sourcing `lib/log.sh`+`lib/pkg.sh`. `category="multimedia"`,
`requires=["rpmfusion"]`, only `[install].fedora`.

## ffmpeg-full
- `verify`: `rpm -q ffmpeg >/dev/null 2>&1 && ! rpm -q ffmpeg-free >/dev/null 2>&1`
  (the full build present AND the limited one gone — END state ⇒ idempotent skip).
- `install.sh`: `sudo dnf swap ffmpeg-free ffmpeg --allowerasing -y`.

## codecs
- `verify`: a representative `@multimedia` codec component present (e.g.
  `rpm -q gstreamer1-plugins-bad-freeworld`).
- `install.sh`: `sudo dnf update @multimedia --setopt="install_weak_deps=False" --exclude=PackageKit-gstreamer-plugin -y`.

## Tests (`tests/ffmpeg-codecs.bats`) — stubbed dnf/rpm
- ffmpeg-full: dnf swap attempted; verify GREEN when `rpm -q ffmpeg` present & `ffmpeg-free` absent (via `STUB_RPM_INSTALLED`); verify RED when ffmpeg-free still present; idempotent skip on re-run.
- codecs: dnf update @multimedia attempted; verify maps to the codec component; idempotent.
- unsupported-OS: non-fedora `OS_DISTRO` (no fedora-key match) → engine reports unsupported (failure), not skip.
