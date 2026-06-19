# lib/install.sh — verify-guarded, dependency-ordered install loop. Source-only.
run_install() {
  summary_reset
  local force=0 strict=0
  while [[ "${1:-}" == --* ]]; do
    case "$1" in
      --force) force=1;; --strict) strict=1;; --) shift; break;;
      *) die "run_install: unknown flag $1";;
    esac; shift
  done
  local -a order; mapfile -t order < <(depsort "$@")
  local name vcmd icmd
  for name in "${order[@]}"; do
    vcmd="$(module_verify_cmd "$name")"
    icmd="$(module_install_cmd "$name")"
    # Idempotency guard.
    if [[ "$force" -eq 0 && -n "$vcmd" ]] && bash -c "$vcmd" >/dev/null 2>&1; then
      log_skip "$name (already installed)"; summary_add skip "$name"; continue
    fi
    if [[ -z "$icmd" ]]; then
      log_error "$name: unsupported on $OS_DISTRO/$OS_FAMILY"
      summary_add fail "$name" "unsupported on $OS_DISTRO"
      [[ "$strict" -eq 1 ]] && { summary_print; return 1; }
      continue
    fi
    log_info "$name: installing"
    if ! bash -c "$icmd"; then
      log_error "$name: install failed"; summary_add fail "$name" "install cmd failed"
      [[ "$strict" -eq 1 ]] && { summary_print; return 1; }
      continue
    fi
    if [[ -n "$vcmd" ]] && ! bash -c "$vcmd" >/dev/null 2>&1; then
      log_error "$name: verify failed after install"; summary_add fail "$name" "verify failed"
      [[ "$strict" -eq 1 ]] && { summary_print; return 1; }
      continue
    fi
    log_ok "$name"; summary_add ok "$name"
  done
  summary_print
}
