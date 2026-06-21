# Implementation Plan: ventoy-kickstart-usb
**Branch**: `011-ventoy-kickstart-usb` | **Date**: 2026-06-21 | **Spec**: [spec.md](./spec.md)

## Summary
Ship the bootable USB layer: `ventoy/make-usb.sh` (safe builder), `ventoy/ventoy.json` (delivery config),
`ventoy/ks.cfg` (zero-touch Fedora install + §10c BTRFS layout), `ventoy/devboost-firstboot.service`
(self-disabling first-boot bootstrap), + a recovery runbook. Artifacts only — NO engine/module/profile
changes (Principle I untouched). Validated hermetically (stub lsblk/ventoy; content asserts; no real disk).

## Technical Context
Bash + Fedora Kickstart + JSON + systemd unit. Deps: ventoy, lsblk (PATH-stubbable), jq (real). Storage:
files under ventoy/. Testing: bats tests/ventoy.bats, stub lsblk/ventoy, no real USB/disk mutation.
Target: the USB build runs on any OS; ks.cfg targets Fedora 44. Constraints: destructive-disk guard;
zero-touch; snapshot-capable layout; secrets/ISOs never committed.

## Constitution Check
- I. Engine+Data Separation — PASS (no engine/module change; pure delivery artifacts).
- II. Idempotent/Verify — PASS (make-usb --update in-place; firstboot self-disables; guarded).
- III. Reproducible — PASS (kickstart pins the layout; secrets/ISOs off-repo, never committed).
- IV. Unattended — PASS (zero-touch; only the one-time NVIDIA MOK screen, by design).
- V. Test-First — PASS (hermetic content/safety tests built first).
- VI. Cross-OS via Data — N/A (USB builder runs anywhere; ks.cfg is Fedora-specific by nature).
Result: PASS.

## Project Structure
```
ventoy/{make-usb.sh, ventoy.json, ks.cfg, devboost-firstboot.service, Docs/recovery-runbook.md}
tests/ventoy.bats ; tests/fixtures/base/stubs.bash (+ lsblk/ventoy stubs, backward-compatible)
```
## Phases
Phase 0 research.md · Phase 1 data-model.md + contracts/usb-artifacts.md + quickstart.md · Phase 2 tasks.
