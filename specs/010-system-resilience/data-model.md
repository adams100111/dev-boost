# Phase 1 Data Model: system-resilience

Data = modules + profiles + the `doctor --gpu` engine flag + stub-harness extensions.

## Profiles (profiles.toml)
```toml
system          = ["snapper","snapper-dnf-hook","grub-btrfs","btrfs-assistant","btrfsmaintenance",
                   "fwupd","power-profiles-daemon","thermald","smartmontools","dnf-automatic-security",
                   "restic-backup","earlyoom"]
hardware-nvidia = ["nvidia-akmod","cuda","libva-nvidia-driver","secureboot-mok",
                   "nvidia-resign-service","nvidia-container-toolkit"]   # rpmfusion reused (base)
optional-editors = ["neovim","jetbrains-toolbox"]
```
- `full` gains `system` + `gpu-detect` (gpu-detect lives in `full` membership, detects + composes).

## Modules
| module | category | requires | install (fedora) | verify |
|---|---|---|---|---|
| snapper | system | [] | dnf install snapper; `snapper -c root create-config /` if absent | `snapper list-configs \| grep -qw root` |
| snapper-dnf-hook | system | ["snapper"] | dnf install python3-dnf-plugin-snapper | `rpm -q python3-dnf-plugin-snapper` |
| grub-btrfs | system | ["snapper"] | dnf install grub-btrfs; enable grub-btrfsd; regen grub | `systemctl is-enabled grub-btrfsd` |
| btrfs-assistant | system | [] | dnf install btrfs-assistant | `rpm -q btrfs-assistant` |
| btrfsmaintenance | system | [] | dnf install btrfsmaintenance; enable scrub/balance timers | `rpm -q btrfsmaintenance` |
| fwupd | system | [] | dnf install fwupd; enable fwupd.service | `command -v fwupdmgr` |
| power-profiles-daemon | system | [] | dnf install power-profiles-daemon; enable | `systemctl is-enabled power-profiles-daemon` |
| thermald | system | [] | dnf install thermald; enable | `systemctl is-enabled thermald` |
| smartmontools | system | [] | dnf install smartmontools; enable smartd | `systemctl is-enabled smartd` |
| dnf-automatic-security | system | [] | dnf install dnf-automatic; write automatic.conf upgrade_type=security; enable dnf-automatic.timer | `grep -q 'upgrade_type = security' /etc/dnf/automatic.conf` |
| restic-backup | system | [] | dnf install restic; install sample repo conf + restic-backup.{service,timer}; enable timer | unit files present |
| earlyoom | system | [] | dnf install earlyoom; write /etc/default/earlyoom (avoid/prefer); enable | `systemctl is-enabled earlyoom` + config has --avoid/--prefer |
| gpu-detect | hardware | ["rpmfusion"] | bash install.sh (lspci select; NVIDIA→note hardware-nvidia) | bash verify.sh (vendor detected) |
| nvidia-akmod | hardware | ["rpmfusion"] | bash install.sh (akmod+cuda+vaapi, akmods --force, nouveau blacklist, CRC32, dracut) | `[ -e /lib/modules/$(uname -r)/.../nvidia.ko* ]` (stub-checked) |
| cuda | hardware | ["nvidia-akmod"] | dnf install xorg-x11-drv-nvidia-cuda | `rpm -q xorg-x11-drv-nvidia-cuda` |
| libva-nvidia-driver | hardware | ["nvidia-akmod"] | dnf install libva-nvidia-driver | `rpm -q libva-nvidia-driver` |
| secureboot-mok | hardware | ["nvidia-akmod"] | bash install.sh (MOK state machine) | bash verify.sh (sb-off OR enrolled OR queued) |
| nvidia-resign-service | hardware | ["nvidia-akmod"] | bash install.sh (sign script + oneshot unit, enable) | unit + script present |
| nvidia-container-toolkit | hardware | ["docker","nvidia-akmod"] | dnf install nvidia-container-toolkit; nvidia-ctk runtime configure | `command -v nvidia-ctk` |
| neovim | system | [] | dnf install neovim; LazyVim bootstrap (clone starter if absent) | `command -v nvim` |
| jetbrains-toolbox | system | [] | download+install JetBrains Toolbox (or flatpak) | toolbox binary/app present |

## Engine extension
- `bin/devboost cmd_doctor`: parse `--gpu`; when set, run `lib/gpu.sh` `gpu_doctor` (modprobe/nouveau/
  initramfs/signature/dmesg checks) and return its status; plain `doctor` path unchanged.
- NEW `lib/gpu.sh` (feature-local): `gpu_doctor` + shared detection helpers (reused by gpu-detect).

## FR traceability
FR-001 snapshot stack · FR-002 maintenance modules · FR-003 system profile ∈ full · FR-004 earlyoom ·
FR-005 gpu-detect · FR-006 hardware-nvidia profile · FR-007 nvidia-akmod fixes · FR-008 secureboot-mok ·
FR-009 nvidia-resign-service · FR-010 nvidia-container-toolkit · FR-011 doctor --gpu · FR-012
optional-editors ∉ full · FR-013 unattended/idempotent/fedora-only · FR-014 test-first stubs.
