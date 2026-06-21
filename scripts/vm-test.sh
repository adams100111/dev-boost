#!/usr/bin/env bash
# scripts/vm-test.sh — spin up a throwaway Fedora VM to validate dev-boost end-to-end.
#
# Two validation paths (design §9.5):
#   engine  — boot a Fedora Live ISO, install Fedora by hand, then run ./install.sh in the guest.
#             Validates the dev-boost ENGINE. No USB, no root (qemu:///session).
#   usb     — the FULL shippable path. Either:
#               --device /dev/sdX   boot the REAL Ventoy USB via passthrough (qemu:///system, sudo), or
#               --kickstart <iso>   unattended zero-touch via ventoy/ks.cfg + a Fedora netinst/Everything ISO
#                                   (no physical USB; qemu:///session).
#
# Plus lifecycle helpers: snapshot / revert / console / destroy / list.
# Everything routes through libvirt (`virt-install`/`virsh`), Fedora's native KVM stack.
set -Eeuo pipefail

# --- config (overridable via env or flags) ------------------------------------
NAME="${VM_NAME:-devboost-test}"
RAM="${VM_RAM:-8192}"            # MiB
VCPUS="${VM_VCPUS:-4}"
DISK_SIZE="${VM_DISK:-50}"       # GiB
OS_VARIANT="${VM_OS_VARIANT:-detect=on,name=fedora-unknown}"
SESSION_URI="qemu:///session"
SYSTEM_URI="qemu:///system"

err() { printf 'vm-test: %s\n' "$*" >&2; }
die() { err "$*"; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing '$1' — install with: sudo dnf install -y @virtualization virt-manager edk2-ovmf"; }

_disk_path() {  # $1 = uri
  if [[ "$1" == "${SYSTEM_URI}" ]]; then printf '/var/lib/libvirt/images/%s.qcow2\n' "${NAME}"
  else printf '%s/.local/share/libvirt/images/%s.qcow2\n' "${HOME}" "${NAME}"; fi
}

_exists() { virsh --connect "$1" dominfo "${NAME}" >/dev/null 2>&1; }

_recreate_guard() {  # $1=uri $2=recreate?
  if _exists "$1"; then
    [[ "$2" == "1" ]] || die "VM '${NAME}' already exists — pass --recreate to replace it (DESTROYS it), or use a different --name"
    err "recreating '${NAME}' (destroying the old one)"
    virsh --connect "$1" destroy "${NAME}" >/dev/null 2>&1 || true
    virsh --connect "$1" undefine --nvram "${NAME}" >/dev/null 2>&1 || true
    rm -f "$(_disk_path "$1")"
  fi
}

# --- engine mode: Fedora Live ISO → manual install → ./install.sh -------------
cmd_engine() {
  local iso="" recreate=0
  while (($#)); do case "$1" in
    --iso) iso="${2:?--iso requires a path}"; shift 2;;
    --name) NAME="$2"; shift 2;; --ram) RAM="$2"; shift 2;; --vcpus) VCPUS="$2"; shift 2;;
    --disk) DISK_SIZE="$2"; shift 2;; --recreate) recreate=1; shift;;
    *) die "engine: unknown option '$1'";; esac; done
  [[ -n "${iso}" ]] || die "engine: --iso <Fedora-Live.iso> is required"
  [[ -f "${iso}" ]] || die "engine: ISO not found: ${iso}"
  need virt-install
  _recreate_guard "${SESSION_URI}" "${recreate}"
  local disk; disk="$(_disk_path "${SESSION_URI}")"; mkdir -p "$(dirname "${disk}")"
  err "creating engine VM '${NAME}' (Live ISO, UEFI, ${RAM}MiB/${VCPUS}vcpu/${DISK_SIZE}GiB)"
  virt-install --connect "${SESSION_URI}" \
    --name "${NAME}" --memory "${RAM}" --vcpus "${VCPUS}" --cpu host-passthrough \
    --disk "path=${disk},size=${DISK_SIZE},format=qcow2,bus=virtio" \
    --cdrom "${iso}" --os-variant "${OS_VARIANT}" \
    --boot uefi --graphics spice --video qxl --network user --noautoconsole
  cat <<EOF
vm-test: '${NAME}' created (engine mode).
 1) A graphical window opens (or: scripts/vm-test.sh console). Click through the Fedora installer (~10 min), reboot.
 2) In the guest, get dev-boost (git clone, or mount this repo) and run:
       ./install.sh --profile cli,shell      # fast smoke test first
       ./install.sh --profile full           # then the full workstation
 3) Snapshot before each run:  scripts/vm-test.sh snapshot clean
EOF
}

# --- usb mode: real Ventoy USB passthrough OR device-less Kickstart -----------
cmd_usb() {
  local device="" ks_iso="" recreate=0
  while (($#)); do case "$1" in
    --device) device="${2:?--device requires /dev/sdX}"; shift 2;;
    --kickstart) ks_iso="${2:?--kickstart requires a netinst/Everything ISO}"; shift 2;;
    --name) NAME="$2"; shift 2;; --ram) RAM="$2"; shift 2;; --vcpus) VCPUS="$2"; shift 2;;
    --disk) DISK_SIZE="$2"; shift 2;; --recreate) recreate=1; shift;;
    *) die "usb: unknown option '$1'";; esac; done
  need virt-install

  if [[ -n "${device}" ]]; then
    # FULL path: boot the physical Ventoy USB exactly as real hardware would.
    [[ -b "${device}" ]] || die "usb: not a block device: ${device} (run 'lsblk' to find the USB)"
    _recreate_guard "${SYSTEM_URI}" "${recreate}"
    local disk; disk="$(_disk_path "${SYSTEM_URI}")"
    err "creating usb VM '${NAME}' booting the Ventoy USB ${device} (qemu:///system needs sudo)"
    sudo virt-install --connect "${SYSTEM_URI}" \
      --name "${NAME}" --memory "${RAM}" --vcpus "${VCPUS}" --cpu host-passthrough \
      --disk "path=${device},format=raw,bus=usb,boot.order=1" \
      --disk "path=${disk},size=${DISK_SIZE},format=qcow2,bus=virtio,boot.order=2" \
      --os-variant "${OS_VARIANT}" --boot uefi --graphics spice --network default --noautoconsole
    echo "vm-test: '${NAME}' boots the real USB → Ventoy menu → pick Fedora (manual) or the auto-install entry (zero-touch)."
  elif [[ -n "${ks_iso}" ]]; then
    # DEVICE-LESS zero-touch: drive ventoy/ks.cfg directly. SATA disk ⇒ guest sees /dev/sda (matches ks.cfg).
    [[ -f "${ks_iso}" ]] || die "usb: netinst/Everything ISO not found: ${ks_iso} (the Live ISO does NOT support Kickstart %packages)"
    local ks="${DEVBOOST_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}/ventoy/ks.cfg"
    [[ -f "${ks}" ]] || die "usb: ${ks} missing"
    _recreate_guard "${SESSION_URI}" "${recreate}"
    local disk; disk="$(_disk_path "${SESSION_URI}")"; mkdir -p "$(dirname "${disk}")"
    err "creating usb/kickstart VM '${NAME}' (unattended via ventoy/ks.cfg; SATA disk → /dev/sda)"
    virt-install --connect "${SESSION_URI}" \
      --name "${NAME}" --memory "${RAM}" --vcpus "${VCPUS}" --cpu host-passthrough \
      --disk "path=${disk},size=${DISK_SIZE},format=qcow2,bus=sata" \
      --location "${ks_iso}" --initrd-inject "${ks}" \
      --extra-args "inst.ks=file:/ks.cfg console=tty0 console=ttyS0,115200n8" \
      --os-variant "${OS_VARIANT}" --boot uefi --graphics spice --network user --noautoconsole
    echo "vm-test: '${NAME}' installing unattended from ks.cfg; watch with: scripts/vm-test.sh console"
  else
    die "usb: pass --device /dev/sdX (boot the real Ventoy USB) OR --kickstart <netinst.iso> (device-less zero-touch)"
  fi
}

# --- lifecycle helpers (try session first, then system) -----------------------
_uri_of() { _exists "${SESSION_URI}" && printf '%s' "${SESSION_URI}" || printf '%s' "${SYSTEM_URI}"; }
cmd_snapshot() { local u; u="$(_uri_of)"; virsh --connect "$u" snapshot-create-as --domain "${NAME}" --name "${1:?snapshot name required}"; }
cmd_revert()   { local u; u="$(_uri_of)"; virsh --connect "$u" snapshot-revert --domain "${NAME}" --snapshotname "${1:?snapshot name required}"; }
cmd_console()  { need virt-viewer; virt-viewer --connect "$(_uri_of)" "${NAME}" & }
cmd_list()     { virsh --connect "${SESSION_URI}" list --all 2>/dev/null; virsh --connect "${SYSTEM_URI}" list --all 2>/dev/null || true; }
cmd_destroy()  {
  local u; u="$(_uri_of)"
  virsh --connect "$u" destroy "${NAME}" >/dev/null 2>&1 || true
  virsh --connect "$u" undefine --nvram --remove-all-storage "${NAME}" || die "destroy failed"
  echo "vm-test: '${NAME}' destroyed."
}

usage() {
  cat <<EOF
Usage: scripts/vm-test.sh <command> [options]

  engine  --iso <Fedora-Live.iso> [--name N --ram MiB --vcpus N --disk GiB --recreate]
          Validate the dev-boost ENGINE: boot Fedora Live, install by hand, run ./install.sh. (no sudo)

  usb     --device /dev/sdX                  boot the REAL Ventoy USB (full path; sudo / qemu:///system)
          --kickstart <Fedora-netinst.iso>   device-less zero-touch via ventoy/ks.cfg (no sudo)
          [--name N --ram MiB --vcpus N --disk GiB --recreate]

  snapshot <name> | revert <name> | console | list | destroy

Find your USB with:  lsblk -o NAME,SIZE,TYPE,RM,MOUNTPOINT,MODEL
Prereqs:             sudo dnf install -y @virtualization virt-manager edk2-ovmf
EOF
}

main() {
  local cmd="${1:-help}"; shift || true
  case "${cmd}" in
    engine)   cmd_engine "$@";;
    usb)      cmd_usb "$@";;
    snapshot) cmd_snapshot "$@";;
    revert)   cmd_revert "$@";;
    console)  cmd_console "$@";;
    list)     cmd_list "$@";;
    destroy)  cmd_destroy "$@";;
    help|-h|--help) usage;;
    *) usage; exit 1;;
  esac
}
main "$@"
