#!/usr/bin/env bash
# scripts/vm-test-macos.sh — rehearse the macOS `curl | bash` flow in a throwaway tart VM
# (design §9.5 macOS leg; plan D8). Drives the guest entirely with `tart exec` (the Tart
# Guest Agent) — no sshpass, no key setup. `ssh admin@$(tart ip <vm>)` is printed only as
# an interactive hint (admin/admin). tart has no native snapshots, so `snapshot`/`revert`
# fake them with `tart clone` of a stopped VM.
#
# Usage: scripts/vm-test-macos.sh [--dry-run] <verb> [options]
#   create   --os 27|26 [--name N] [--cpu 4] [--memory 8192] [--disk 80] [--recreate]
#   snapshot <snap> [--name N] [--os 27|26]
#   revert   <snap> [--name N] [--os 27|26]
#   list
#   destroy  [--name N] [--os 27|26]
#   run      [--local DIR] [--profiles "macos"] [--name N] [--os 27|26]
#   shell    [--name N] [--os 27|26]
#
# --dry-run prints the exact `tart` argv (one `+ `-prefixed line each) instead of running it,
# so this is safe to preview without tart installed or a Darwin host.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="adams100111/dev-boost"
RAW_BASE="https://raw.githubusercontent.com/${REPO}/main/scripts"
DEFAULT_OS=27

err() { printf 'vm-test-macos: %s\n' "$*" >&2; }
die() { err "$*"; exit 1; }

DRY=0
if [[ "${1:-}" == "--dry-run" ]]; then DRY=1; shift; fi
run() { if [[ ${DRY} -eq 1 ]]; then printf '+ %s\n' "$*"; else "$@"; fi; }

need_host() {
  local kernel machine
  kernel="$(uname -s)"
  machine="$(uname -m)"
  [[ "${kernel}" == "Darwin" ]] || die "requires a Darwin host (got '${kernel}')"
  [[ "${machine}" == "arm64" ]] || die "requires an Apple Silicon (arm64) host (got '${machine}')"
}

need_tart() {
  [[ ${DRY} -eq 1 ]] && return 0
  command -v tart >/dev/null 2>&1 \
    || die "missing 'tart' — install with: brew install cirruslabs/cli/tart"
}

image_for_os() {
  case "$1" in
    27) echo "ghcr.io/cirruslabs/macos-golden-gate-base:latest" ;;
    26) echo "ghcr.io/cirruslabs/macos-tahoe-base:latest" ;;
    *) die "unknown --os '$1' (want 27 or 26)" ;;
  esac
}

# _target OS_DEFAULT "$@" — scans the remaining args for --name/--os, leaves them in place
# (callers re-parse for their own extra flags), and prints "<os> <name>" resolved against
# OS_DEFAULT and the devboost-mac<os> default name.
_target() {
  local os_default="$1" os="" name=""
  shift
  while (($#)); do
    case "$1" in
      --os) os="$2"; shift 2 ;;
      --name) name="$2"; shift 2 ;;
      *) shift ;;
    esac
  done
  [[ -n "${os}" ]] || os="${os_default}"
  [[ -n "${name}" ]] || name="devboost-mac${os}"
  printf '%s %s\n' "${os}" "${name}"
}

vm_exists() { [[ ${DRY} -eq 1 ]] && return 1; tart list 2>/dev/null | awk '{print $NF}' | grep -qx "$1"; }

# --- create -----------------------------------------------------------------
cmd_create() {
  local os="" name="" cpu=4 memory=8192 disk=80 recreate=0
  while (($#)); do
    case "$1" in
      --os) os="$2"; shift 2 ;;
      --name) name="$2"; shift 2 ;;
      --cpu) cpu="$2"; shift 2 ;;
      --memory) memory="$2"; shift 2 ;;
      --disk) disk="$2"; shift 2 ;;
      --recreate) recreate=1; shift ;;
      *) die "create: unknown option '$1'" ;;
    esac
  done
  [[ -n "${os}" ]] || die "create: --os 27|26 is required"
  [[ -n "${name}" ]] || name="devboost-mac${os}"
  local image; image="$(image_for_os "${os}")"

  if vm_exists "${name}"; then
    [[ ${recreate} -eq 1 ]] || die "VM '${name}' already exists — pass --recreate to replace it (DESTROYS it), or use a different --name"
    err "recreating '${name}' (destroying the old one)"
    tart stop "${name}" >/dev/null 2>&1 || true
    tart delete "${name}" || die "recreate: could not delete existing '${name}'"
  fi

  run tart clone "${image}" "${name}"
  run tart set "${name}" --cpu "${cpu}" --memory "${memory}" --disk-size "${disk}"
}

# --- snapshot / revert / destroy / list --------------------------------------
cmd_snapshot() {
  local snap="${1:?snapshot: <snap> name required}"; shift
  read -r _ name <<<"$(_target "${DEFAULT_OS}" "$@")"
  run tart stop "${name}"
  run tart clone "${name}" "${name}--${snap}"
}

cmd_revert() {
  local snap="${1:?revert: <snap> name required}"; shift
  read -r _ name <<<"$(_target "${DEFAULT_OS}" "$@")"
  run tart stop "${name}"
  run tart delete "${name}"
  run tart clone "${name}--${snap}" "${name}"
}

cmd_destroy() {
  read -r _ name <<<"$(_target "${DEFAULT_OS}" "$@")"
  run tart stop "${name}"
  run tart delete "${name}"
}

cmd_list() { run tart list; }

cmd_shell() {
  read -r _ name <<<"$(_target "${DEFAULT_OS}" "$@")"
  # shellcheck disable=SC2016  # literal hint text — $(tart ip ...) is meant for the user to run
  printf 'ssh admin@$(tart ip %s)   # password: admin\n' "${name}"
}

# --- run: boot, wait for the guest agent, drive get.sh, then smoke-assert.sh -----
# The guest mount point tart gives a --dir share. The path has spaces, so it is quoted
# wherever it is a path, and percent-encoded where it is a file:// URL (curl rejects a
# URL with raw spaces).
GUEST_SHARE="/Volumes/My Shared Files/dist"
GUEST_SHARE_URL="file:///Volumes/My%20Shared%20Files/dist"

# What the guest-side smoke verifies. NOT the install profiles: an unattended guest has
# no password, no TCC grants and no GitHub session, so the modules that need a human are
# reported `blocked` by design and `devboost verify macos` can never exit 0 there (see
# docs/vm-testing.md "accepted non-green items"). `cli` is the largest set that a guest
# with nobody at the keyboard CAN have fully green, so a real regression still fails it.
SMOKE_PROFILES_DEFAULT="cli"

cmd_run() {
  local os="" name="" local_dir="" profiles="macos" smoke_profiles=""
  while (($#)); do
    case "$1" in
      --os) os="$2"; shift 2 ;;
      --name) name="$2"; shift 2 ;;
      --local) local_dir="$2"; shift 2 ;;
      --profiles) profiles="$2"; shift 2 ;;
      --smoke-profiles) smoke_profiles="$2"; shift 2 ;;
      *) die "run: unknown option '$1'" ;;
    esac
  done
  [[ -n "${os}" ]] || os="${DEFAULT_OS}"
  [[ -n "${name}" ]] || name="devboost-mac${os}"

  local dir_arg="" install_cmd smoke_cmd share_dir=""
  if [[ -n "${local_dir}" ]]; then
    [[ -f "${local_dir}/checksums.txt" || -f "${local_dir}/checksums-darwin-arm64.txt" ]] \
      || die "--local ${local_dir}: missing checksums.txt (or checksums-darwin-arm64.txt)"
    [[ -f "${local_dir}/devboost-darwin-arm64" ]] \
      || die "--local ${local_dir}: missing devboost-darwin-arm64"
    if [[ ${DRY} -eq 1 ]]; then
      share_dir="<staging-dir>"  # nothing is staged in a preview
    else
      share_dir="$(mktemp -d)"
      # shellcheck disable=SC2064  # share_dir must expand now, not at trap time
      trap "rm -rf '${share_dir}'" EXIT
      cp "${ROOT}/scripts/get.sh" "${ROOT}/scripts/smoke-assert.sh" "${share_dir}/"
      cp "${local_dir}/devboost-darwin-arm64" "${share_dir}/"
      if [[ -f "${local_dir}/checksums.txt" ]]; then
        cp "${local_dir}/checksums.txt" "${share_dir}/checksums.txt"
      else
        # a raw dist/ only carries the per-arch file — stage the rename, never in dist/.
        cp "${local_dir}/checksums-darwin-arm64.txt" "${share_dir}/checksums.txt"
      fi
    fi
    dir_arg="--dir=dist:${share_dir}"
    # A script FILE operand: its arguments are the profiles, with no `-s --` (that form is
    # only for bash reading the script from stdin, as in `curl | bash -s -- …`).
    install_cmd="DEVBOOST_RELEASE_BASE=${GUEST_SHARE_URL} bash \"${GUEST_SHARE}/get.sh\" ${profiles}"
    smoke_cmd="sh \"${GUEST_SHARE}/smoke-assert.sh\" ${smoke_profiles:-${SMOKE_PROFILES_DEFAULT}}"
  else
    install_cmd="curl -fsSL ${RAW_BASE}/smoke-assert.sh -o \"\$HOME/smoke-assert.sh\""
    install_cmd+=" && curl -fsSL ${RAW_BASE}/get.sh | bash -s -- ${profiles}"
    smoke_cmd="sh \"\$HOME/smoke-assert.sh\" ${smoke_profiles:-${SMOKE_PROFILES_DEFAULT}}"
  fi
  # The smoke runs in a SECOND exec: a brand-new zsh login shell (the user's real macOS
  # shell) started after the install returned, so it sees the PATH the install wired up
  # (~/.local/bin, Homebrew, mise) — not the PATH of the shell that ran get.sh.

  if [[ ${DRY} -eq 1 ]]; then
    if [[ -n "${dir_arg}" ]]; then
      printf '+ tart run --no-graphics %s %s\n' "${dir_arg}" "${name}"
    else
      printf '+ tart run --no-graphics %s\n' "${name}"
    fi
    run tart ip --wait 120 "${name}"
    printf '+ tart exec -i %s /bin/bash -lc '\''%s'\''\n' "${name}" "${install_cmd}"
    printf '+ tart exec -i %s /bin/zsh -lc '\''%s'\''\n' "${name}" "${smoke_cmd}"
    return 0
  fi

  need_tart
  local log; log="$(mktemp)"
  if [[ -n "${dir_arg}" ]]; then
    tart run --no-graphics "${dir_arg}" "${name}" >"${log}" 2>&1 &
  else
    tart run --no-graphics "${name}" >"${log}" 2>&1 &
  fi
  local run_pid=$!
  # shellcheck disable=SC2064  # run_pid/log/share_dir must expand now, not at trap time
  trap "kill ${run_pid} >/dev/null 2>&1 || true; rm -rf '${log}' ${share_dir:+'${share_dir}'}" EXIT

  if ! tart ip --wait 120 "${name}"; then
    err "the VM never came up — tart run said:"
    cat "${log}" >&2
    exit 1
  fi
  local rc=0
  tart exec -i "${name}" /bin/bash -lc "${install_cmd}" || rc=$?
  if [[ ${rc} -eq 0 ]]; then
    tart exec -i "${name}" /bin/zsh -lc "${smoke_cmd}" || rc=$?
  fi
  tart stop "${name}" >/dev/null 2>&1 || true
  exit "${rc}"
}

usage() {
  cat <<EOF
Usage: scripts/vm-test-macos.sh [--dry-run] <verb> [options]

  create   --os 27|26 [--name N] [--cpu 4] [--memory 8192] [--disk 80] [--recreate]
  snapshot <snap> [--name N] [--os 27|26]
  revert   <snap> [--name N] [--os 27|26]
  list
  destroy  [--name N] [--os 27|26]
  run      [--local DIR] [--profiles "macos"] [--name N] [--os 27|26]
  shell    [--name N] [--os 27|26]

27 = macOS 27 Golden Gate (primary); 26 = macOS 26 Tahoe (supported). VM name default:
devboost-mac<os>. --dry-run previews the \`tart\` argv without running it or needing tart.
EOF
}

main() {
  need_host
  local verb="${1:-help}"; shift || true
  case "${verb}" in
    create) need_tart; cmd_create "$@" ;;
    snapshot) need_tart; cmd_snapshot "$@" ;;
    revert) need_tart; cmd_revert "$@" ;;
    destroy) need_tart; cmd_destroy "$@" ;;
    list) need_tart; cmd_list "$@" ;;
    run) cmd_run "$@" ;;
    shell) cmd_shell "$@" ;;
    help|-h|--help) usage ;;
    *) usage; exit 1 ;;
  esac
}
main "$@"
