# Quickstart / Validation: multimedia-codecs

Proves the `multimedia` profile end-to-end **hermetically** (no real installs/GPU/network)
via the bats stub harness. See `contracts/` for exact interfaces.

## Prerequisites
- Repo checked out; `bats`, `jq`, `python3`. Specs 1–4 merged (base/rpmfusion on `main`).
- Package/GPU tooling (`dnf`, `rpm`, `lspci`, `vainfo`, `dnf config-manager`) is **stubbed**
  by `tests/fixtures/base/`. No root, no real GPU, no network.

## Run the tests (primary validation)
```bash
bats tests/ffmpeg-codecs.bats tests/va-hwaccel.bats tests/openh264.bats tests/profiles.bats
# or the whole suite:
bats tests/
```
Expected: all green — ffmpeg swap + end-state verify; codec install; per-GPU-vendor driver
(intel/amd/nvidia/hybrid), unrecognized→named-fail, vainfo-fails→named-fail; openh264; the
unsupported-OS path. No real installs/GPU.

## Resolution smoke (list only)
```bash
DEVBOOST_MODULES_DIR="$PWD/modules" DEVBOOST_PROFILES="$PWD/profiles.toml" \
  ./bin/devboost list --profile multimedia
```
Expected: `ffmpeg-full`/`codecs`/`va-hwaccel`/`openh264` (+ transitive `rpmfusion`), no cycle.

## Manual smoke (optional, real Fedora-Workstation VM with RPM Fusion)
```bash
DEVBOOST_MODULES_DIR="$PWD/modules" DEVBOOST_PROFILES="$PWD/profiles.toml" \
  ./bin/devboost install --profile multimedia
```
Expected: full `ffmpeg` (ffmpeg-free gone); `@multimedia` codecs; `vainfo` reports a working
driver for the machine's GPU; Firefox plays H.264 (openh264 installed); re-run reports every
module skipped; `git ls-files` shows no secrets.

## Tear down
Throwaway VM only; no host changes via the test stubs.
