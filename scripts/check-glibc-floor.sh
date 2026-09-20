#!/usr/bin/env bash
# scripts/check-glibc-floor.sh BUNDLE [MAX] — fail when a Linux PyInstaller onefile bundle,
# or any ELF object inside it, needs a glibc symbol version newer than MAX (default 2.35,
# Ubuntu 22.04's glibc: the floor the published Linux binaries promise — Ubuntu 22.04+,
# Debian 12, Fedora 36+).
#
# What is checked: `objdump -T` over
#   1. the bundle itself — only the PyInstaller bootloader stub, whose prebuilt symbols stop
#      far below the floor, so this alone can never fail; and
#   2. every ELF object in the bundle's embedded archive — libpython and every extension
#      module / shared library PyInstaller collected — extracted by pyi_bundle_elfs.py.
# The highest GLIBC_x.y across all of them is compared with MAX. If the archive cannot be
# read, or it has no ELF libpython, the check errors (exit 2) instead of passing on the stub.
#
# CI builds the Linux binaries inside an ubuntu:22.04 container (ruling C-M6-R1), so this
# should always pass there; it is the guard that fails the release if a build ever picks up
# a newer glibc (a runner/image change, a newer build host, a wheel built for a newer
# manylinux). Needs objdump (binutils) and a Python 3 for the extractor: $GLIBC_FLOOR_PYTHON
# if set, else python3 on PATH, else `uv run --no-project python` (the build container has
# only uv's Python).
#
# Exit 0: within the floor. Exit 1: above it. Exit 2: usage error, missing file, no
# objdump/Python, or not a readable PyInstaller bundle.
set -Eeuo pipefail

bin="${1:-}"
max="${2:-2.35}"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ -n "${bin}" ]] || { echo "usage: check-glibc-floor.sh BUNDLE [MAX]" >&2; exit 2; }
[[ -f "${bin}" ]] || { echo "check-glibc-floor: no such file: ${bin}" >&2; exit 2; }
command -v objdump >/dev/null 2>&1 \
  || { echo "check-glibc-floor: objdump not found — install binutils" >&2; exit 2; }

if [[ -n "${GLIBC_FLOOR_PYTHON:-}" ]]; then
  py=("${GLIBC_FLOOR_PYTHON}")
elif command -v python3 >/dev/null 2>&1; then
  py=(python3)
elif command -v uv >/dev/null 2>&1; then
  py=(uv run --no-project --quiet python)
else
  echo "check-glibc-floor: no python3 or uv to read the bundle's archive" >&2
  exit 2
fi

work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT

# One `<file>\t<label>` line per ELF to check: the stub first, then the bundled objects.
targets="${work}/targets"
printf '%s\t%s\n' "${bin}" "bootloader stub (${bin##*/})" > "${targets}"
if ! "${py[@]}" "${here}/pyi_bundle_elfs.py" "${bin}" "${work}/elfs" >> "${targets}"; then
  echo "check-glibc-floor: could not extract the ELF objects bundled in ${bin}" >&2
  exit 2
fi

# objdump -T lists the dynamic symbols with their version, e.g. `GLIBC_2.34 __libc_start_main`
# or `(GLIBC_2.2.5) memcpy`. Collect `<version>\t<label>\t<symbol line>` for every object.
all="${work}/all"
: > "${all}"
count=0
while IFS=$'\t' read -r file label; do
  [[ -n "${file}" ]] || continue
  count=$((count + 1))
  if ! symbols="$(objdump -T "${file}" 2>&1)"; then
    echo "check-glibc-floor: objdump -T failed on ${label}:" >&2
    printf '  %s\n' "${symbols//$'\n'/$'\n'  }" >&2
    exit 2
  fi
  awk -v l="${label}" 'match($0, /GLIBC_[0-9]+(\.[0-9]+)+/) {
    print substr($0, RSTART + 6, RLENGTH - 6) "\t" l "\t" $0 }' <<<"${symbols}" >> "${all}"
done < "${targets}"

highest="$(cut -f1 "${all}" | sort -u -V | tail -n1)"
if [[ -z "${highest}" ]]; then
  echo "check-glibc-floor: ${bin}: no GLIBC symbol versions in ${count} ELF objects — ok"
  exit 0
fi

newest="$(printf '%s\n%s\n' "${highest}" "${max}" | sort -V | tail -n1)"
if [[ "${newest}" != "${max}" ]]; then
  echo "check-glibc-floor: ${bin} needs GLIBC_${highest}, above the ${max} floor" \
       "(checked ${count} ELF objects):" >&2
  while IFS=$'\t' read -r v label line; do
    [[ "$(printf '%s\n%s\n' "${v}" "${max}" | sort -V | tail -n1)" == "${max}" ]] && continue
    printf '  %s: %s\n' "${label}" "${line}" >&2
  done < "${all}"
  exit 1
fi
echo "check-glibc-floor: ${bin}: highest GLIBC_${highest} <= ${max}" \
     "across ${count} ELF objects (bootloader + $((count - 1)) bundled) — ok"
