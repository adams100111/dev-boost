#!/usr/bin/env bash
# scripts/vm-kickstart-smoke.sh — boot ventoy/ks.cfg in a real Anaconda and prove it installs.
#
# WHY THIS EXISTS
#   pykickstart parsing (the CI syntax gate) is necessary but not sufficient. Two shipped
#   failures parsed fine and still broke the install:
#     - /dev/zram0 (TYPE=disk RM=0) got picked by %pre  -> "Disk zram0 ... does not exist"
#     - btrfs --fsoptions (accepted by no btrfs command) -> "Unexpected arguments to btrfs"
#     - ESP-only partitioning on BIOS/GPT               -> "Kickstart insufficient" (hang)
#   Only booting the real installer catches these. This drives Anaconda unattended in qemu
#   and passes when it reaches the package phase — i.e. parse + %pre + storage all succeeded.
#
# NO SUDO, NO LIBVIRT: kernel is booted directly and the kickstart is injected into the initrd
# (unlike scripts/vm-test.sh, which uses virt-install). Needs a writable /dev/kvm, qemu, 7z.
#
# Usage:  scripts/vm-kickstart-smoke.sh <fedora-netinst.iso> [--full] [--disk NAME] [--timeout S]
#   --full        run to a completed install + reboot (slow: downloads ~2GB). Default stops at
#                 the package phase, which is enough to prove the kickstart is structurally sound.
#   --disk NAME   guest disk the kickstart should target (default: vda; passed as devboost.disk=).
#   --timeout S   seconds to wait for the milestone (default 600; use 2400 with --full).
set -Eeuo pipefail

ISO="${1:?usage: vm-kickstart-smoke.sh <fedora-netinst.iso> [--full] [--disk NAME] [--timeout S]}"
shift || true
FULL=0; DISK=vda; TIMEOUT=600
while [ $# -gt 0 ]; do
  case "$1" in
    --full) FULL=1; TIMEOUT=2400; shift ;;
    --disk) DISK="${2:?}"; shift 2 ;;
    --timeout) TIMEOUT="${2:?}"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KS="${ROOT}/ventoy/ks.cfg"
[ -f "$ISO" ] || { echo "smoke: ISO not found: $ISO" >&2; exit 2; }
[ -w /dev/kvm ] || { echo "smoke: /dev/kvm not writable — need KVM" >&2; exit 2; }
for t in qemu-system-x86_64 7z qemu-img cpio; do command -v "$t" >/dev/null || { echo "smoke: missing $t" >&2; exit 2; }; done

W="$(mktemp -d)"; trap 'pkill -9 -f "qemu-system-x86_64.*${W}" 2>/dev/null || true; rm -rf "$W"' EXIT
cd "$W"

echo "smoke: extracting kernel + initrd from $(basename "$ISO")"
7z e -y "$ISO" images/pxeboot/vmlinuz images/pxeboot/initrd.img >/dev/null
LABEL="$(isoinfo -d -i "$ISO" 2>/dev/null | sed -n 's/^Volume id: //p' | head -1)"
[ -n "$LABEL" ] || { echo "smoke: could not read ISO volume label" >&2; exit 2; }

# Inject ks.cfg as a trailing gzip cpio member (dracut concatenates initrds).
cp "$KS" ks.cfg
echo ks.cfg | cpio -c -o 2>/dev/null | gzip -9 -c >> initrd.img
qemu-img create -f qcow2 target.qcow2 20G >/dev/null

echo "smoke: booting Anaconda unattended (disk=${DISK}, full=${FULL}, timeout=${TIMEOUT}s)"
setsid qemu-system-x86_64 -accel kvm -m 4096 -smp 2 -cpu host \
  -kernel vmlinuz -initrd initrd.img \
  -append "inst.stage2=hd:LABEL=${LABEL} inst.ks=file:/ks.cfg inst.text devboost.disk=${DISK} console=ttyS0,115200n8 inst.notmux" \
  -drive "file=${W}/target.qcow2,if=virtio,format=qcow2" \
  -drive "file=${ISO},if=ide,media=cdrom,readonly=on" \
  -netdev user,id=n0 -device virtio-net,netdev=n0 \
  -nographic -serial "file:${W}/console.log" -display none </dev/null >/dev/null 2>&1 &

# Terminal signatures. FAIL covers every way the installer can refuse or die — silence must
# never read as success.
fail_re='Unexpected arguments|does not exist|Kickstart insufficient|special partition|installation will now terminate|Traceback \(most recent|Pane is dead|storage configuration failed|kickstart.*error'
if [ "$FULL" -eq 1 ]; then
  pass_re='Performing post-installation setup|Running post-installation scripts|reboot: (Restarting|Power down)|Installation complete'
else
  pass_re='Starting package installation|Downloading [0-9]+ (RPMs|packages)|Performing post-installation|Running post-installation'
fi

deadline=$(( $(date +%s) + TIMEOUT ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  L="$(sed 's/\r$//' console.log 2>/dev/null || true)"
  if echo "$L" | grep -qiE "$fail_re"; then
    echo "smoke: FAIL — installer error:"; echo "$L" | grep -iE "$fail_re|\[pre\]" | tail -8
    exit 1
  fi
  if echo "$L" | grep -qiE "$pass_re"; then
    echo "smoke: PASS — kickstart parsed, %pre selected the disk, storage built:"
    echo "$L" | grep -iE '\[pre\]|Creating (btrfs|biosboot|efi)|Downloading|package installation|post-installation' | tail -8
    exit 0
  fi
  sleep 5
done
echo "smoke: TIMEOUT after ${TIMEOUT}s — last meaningful output:"
sed 's/\r$//' console.log 2>/dev/null | grep -aiE '\[pre\]|anaconda|storage|Creating|error|Downloading' | tail -15
exit 3
