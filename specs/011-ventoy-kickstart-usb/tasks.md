# Tasks: ventoy-kickstart-usb
Artifacts only; hermetic TDD. Keep 1080 suite green.
## Phase 1: Setup
- [X] T001 [P] Create `ventoy/Docs/` dir.
## Phase 2: Foundational
- [X] T002 Extend tests/fixtures/base/stubs.bash (backward-compatible): add `lsblk` stub (STUB_LSBLK_TYPE/RM/MOUNT) + `ventoy` stub (STUB_VENTOY_LOG), NOT auto-installed (ventoy.bats calls base_install_usb_stubs). Run bats tests/ → 1080 green.
## Phase 3: US1 — make-usb.sh (P1)
- [X] T003 [US1] Write tests/ventoy.bats (RED) make-usb cases per contracts: refuse non-removable/partition/loop/mounted (no ventoy call); happy path removable+--yes → ventoy -i + USB tree + copies.
- [X] T004 [US1] Implement ventoy/make-usb.sh. GREEN.
## Phase 4: US2 — ks.cfg + ventoy.json (P2)
- [X] T005 [US2] Add ks.cfg + ventoy.json cases to tests/ventoy.bats (RED): §10c subvols + var/lib/gdm + compress=zstd:1 + no swap + minimal %packages; ventoy.json valid JSON + bindings.
- [X] T006 [US2] Author ventoy/ks.cfg + ventoy/ventoy.json. GREEN.
## Phase 5: US3 — first-boot service (P3)
- [X] T007 [US3] Add devboost-firstboot.service cases to tests/ventoy.bats (RED): oneshot, install.sh --profile full --secrets, log path, self-disable; %post in ks.cfg installs+enables it.
- [X] T008 [US3] Author ventoy/devboost-firstboot.service + wire %post in ks.cfg. GREEN.
## Phase 6: Polish
- [X] T009 [P] Write ventoy/Docs/recovery-runbook.md; reconcile quickstart/research.
- [X] T010 [P] Update docs/roadmap.md row 11 done. Full bats tests/ green.
**Total: 10 tasks.**
