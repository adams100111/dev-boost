#!/usr/bin/env bash
# scripts/check-glibc-floor.sh BINARY [MAX] — fail when a Linux ELF binary needs a glibc
# symbol version newer than MAX (default 2.35, Ubuntu 22.04's glibc: the floor the
# published Linux binaries promise — Ubuntu 22.04+, Debian 12, Fedora 36+).
#
# CI builds the Linux binaries inside an ubuntu:22.04 container (ruling C-M6-R1), so this
# should always pass there; it is the guard that fails the release if a build ever picks
# up a newer glibc (a runner/image change, a newer build host). Needs objdump (binutils).
#
# Exit 0: within the floor (or no GLIBC versions at all, e.g. static). Exit 1: above it.
# Exit 2: usage error, missing file, or no objdump.
set -Eeuo pipefail

bin="${1:-}"
max="${2:-2.35}"
[[ -n "${bin}" ]] || { echo "usage: check-glibc-floor.sh BINARY [MAX]" >&2; exit 2; }
[[ -f "${bin}" ]] || { echo "check-glibc-floor: no such file: ${bin}" >&2; exit 2; }
command -v objdump >/dev/null 2>&1 \
  || { echo "check-glibc-floor: objdump not found — install binutils" >&2; exit 2; }

# objdump -T lists the dynamic symbols with their version, e.g. `GLIBC_2.34 __libc_start_main`
# or `(GLIBC_2.2.5) memcpy`.
symbols="$(objdump -T "${bin}")"
versions="$(sed -nE 's/.*GLIBC_([0-9]+(\.[0-9]+)+).*/\1/p' <<<"${symbols}" | sort -u -V)"
highest="$(tail -n1 <<<"${versions}")"
if [[ -z "${highest}" ]]; then
  echo "check-glibc-floor: ${bin}: no GLIBC symbol versions — ok"
  exit 0
fi

newest="$(printf '%s\n%s\n' "${highest}" "${max}" | sort -V | tail -n1)"
if [[ "${newest}" != "${max}" ]]; then
  echo "check-glibc-floor: ${bin} needs GLIBC_${highest}, above the ${max} floor:" >&2
  while IFS= read -r v; do
    [[ -n "${v}" ]] || continue
    [[ "$(printf '%s\n%s\n' "${v}" "${max}" | sort -V | tail -n1)" == "${max}" ]] && continue
    grep -E "GLIBC_${v//./\\.}([^0-9.]|\$)" <<<"${symbols}" | sed 's/^/  /' >&2 || true
  done <<<"${versions}"
  exit 1
fi
echo "check-glibc-floor: ${bin}: highest GLIBC_${highest} <= ${max} — ok"
