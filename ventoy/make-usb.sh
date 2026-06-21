#!/usr/bin/env bash
# ventoy/make-usb.sh — build the dev-boost Ventoy USB (design §9).
# Installs Ventoy onto a REMOVABLE USB and lays out the USB tree, then copies
# ventoy.json + ks.cfg into place. The single destructive step in the platform —
# heavily guarded: refuses non-removable/system/partition/loop targets and requires
# explicit confirmation.
#
# Usage: make-usb.sh <device> [--update] [--yes]
#   <device>   whole removable block device, e.g. /dev/sdX
#   --update   update Ventoy in place (no wipe)   (ventoy -u)
#   --yes      non-interactive confirm (skip the y/N prompt)
set -Eeuo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

err() { printf 'make-usb: %s\n' "$*" >&2; }
die() { err "$*"; exit 1; }

dev=""; update=""; assume_yes=""
for a in "$@"; do
  case "$a" in
    --update) update=1;;
    --yes|-y) assume_yes=1;;
    -*)       die "unknown option: $a";;
    *)        dev="$a";;
  esac
done
[[ -n "${dev}" ]] || die "usage: make-usb.sh <device> [--update] [--yes]"
[[ -b "${dev}" ]] || die "not a block device: ${dev}"

# --- Safety guard: only a whole, removable, unmounted disk is acceptable. -----
# lsblk columns: NAME TYPE RM MOUNTPOINT
read -r _name _type _rm _mount < <(lsblk -dno NAME,TYPE,RM,MOUNTPOINT "${dev}")
[[ "${_type}" == "disk" ]] || die "refusing: ${dev} is type '${_type}', not a whole disk (no partitions/loop devices)"
[[ "${_rm}" == "1" ]]      || die "refusing: ${dev} is not a removable device (RM=${_rm}) — will not touch a fixed/system disk"
[[ -z "${_mount}" ]]       || die "refusing: ${dev} is mounted at '${_mount}' — unmount or pick the USB"

# --- Confirm before any destructive action. -----------------------------------
if [[ -z "${update}" ]]; then
  printf 'About to INSTALL Ventoy on %s — THIS WIPES THE DEVICE.\n' "${dev}" >&2
  if [[ -z "${assume_yes}" ]]; then
    read -r -p "Type 'yes' to continue: " ans
    [[ "${ans}" == "yes" ]] || die "aborted (no confirmation)"
  fi
  ventoy -i "${dev}"
else
  ventoy -u "${dev}"
fi

# --- Lay out the USB tree on the exFAT VTOY data partition. --------------------
# Resolve the VTOY mountpoint (Ventoy labels the data partition 'VTOY'); allow override.
vtoy="${VTOY_MOUNT:-/run/media/${USER:-root}/VTOY}"
mkdir -p "${vtoy}/ISO" "${vtoy}/Bootstrap" "${vtoy}/Installers" "${vtoy}/Backups" "${vtoy}/ventoy"
cp "${HERE}/ventoy.json" "${vtoy}/ventoy/ventoy.json"
cp "${HERE}/ks.cfg"      "${vtoy}/Bootstrap/ks.cfg"

printf 'make-usb: done. Copy ISOs into %s/ISO and your secrets.age + devboost.tar.gz into %s/Bootstrap.\n' \
  "${vtoy}" "${vtoy}"
