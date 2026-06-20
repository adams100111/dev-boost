# Contract: `openh264` (US3) + `profiles.toml`

## openh264 module
Escape-hatch, `category="multimedia"`, `requires=[]` (Cisco repo is Fedora's own),
only `[install].fedora`.
- `verify`: `rpm -q openh264 gstreamer1-plugin-openh264 mozilla-openh264` (all present).
- `install.sh`: `sudo dnf config-manager setopt fedora-cisco-openh264.enabled=1` (enable,
  add-if-not-enabled) then `sudo dnf install -y openh264 gstreamer1-plugin-openh264 mozilla-openh264`.

## profiles.toml (add 1 entry, do NOT touch base/cli/shell/gnome)
```toml
multimedia = ["ffmpeg-full","codecs","va-hwaccel","openh264"]
```

## Tests (`tests/openh264.bats` + extend `tests/profiles.bats`)
- openh264: config-manager enable attempted; the 3 packages installed; verify maps to `rpm -q` of all 3; idempotent skip; unsupported-OS → engine failure.
- profiles: `profile_expand multimedia` → those 4 modules (membership/count). Full `list --profile multimedia` depsort-without-cycle DEFERRED to the polish task (after modules exist).
