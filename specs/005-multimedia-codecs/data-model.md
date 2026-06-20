# Phase 1 Data Model: multimedia-codecs

No database. "Data" = module manifests, the profile entry, and system package state.

## Module entities
Escape-hatch modules (`modules/<name>/{module.toml,install.sh}`) sourcing `lib/log.sh`+`lib/pkg.sh`:
`ffmpeg-full`, `codecs`, `va-hwaccel`, `openh264`. All `category="multimedia"`, only
`[install].fedora` keys (⇒ unsupported on non-Fedora by data).

## profiles.toml (EDIT — add 1 entry)
```toml
multimedia = ["ffmpeg-full","codecs","va-hwaccel","openh264"]
```
`requires`: ffmpeg-full/codecs/va-hwaccel `requires=["rpmfusion"]`; openh264 `requires=[]`.
`multimedia` is part of the design's `full` set (Spec 12 will assemble `full`).

## GPU → driver map (in va-hwaccel, data)
| lspci vendor | Driver action |
|---|---|
| Intel (recent) | install `intel-media-driver` (older → `libva-intel-driver`) |
| AMD/ATI | swap `mesa-va-drivers`→`mesa-va-drivers-freeworld` + `mesa-vdpau-drivers`→`-freeworld` |
| NVIDIA | install `libva-nvidia-driver` |
| ≥2 vendors (hybrid) | install ALL matched drivers |
| unrecognized | libva-utils only + NAMED failure (not guessed) |

## State / verify per module
| Module | Verify (END state) |
|---|---|
| ffmpeg-full | `rpm -q ffmpeg` present AND `ffmpeg-free` absent |
| codecs | representative `@multimedia` codec component present |
| va-hwaccel | `vainfo` exit 0 + reports a working driver |
| openh264 | `openh264` + `gstreamer1-plugin-openh264` + `mozilla-openh264` present |

## Validation rules (from FRs)
| Rule | Source |
|---|---|
| full ffmpeg replaces ffmpeg-free, idempotent (end-state verify) | FR-001, FR-006 |
| codec set installed, idempotent | FR-002 |
| detect GPU(s) + install matching driver(s), hybrid=both | FR-003, FR-009 |
| vainfo working on end state; else NAMED failure (no silent success) | FR-004 |
| openh264 repo enabled + components installed, idempotent | FR-005 |
| non-Fedora → unsupported failure (by data) | FR-007 |
| ordering via requires (after rpmfusion) | FR-008 |
| failure names module + op | FR-010 |
| no secret in git | FR-011 |

## Ordering (depsort via requires)
```
rpmfusion (base) → ffmpeg-full, codecs, va-hwaccel
openh264: requires=[] (Cisco repo is Fedora's own)
non-Fedora: engine reports each unsupported (no fedora-key match)
```
