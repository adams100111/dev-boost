# lib/devhygiene.sh — dev-environment resource hygiene (Spec 9 §8b). Source-only; depends on
# lib/log.sh. All external commands (docker/ddev) PATH-stubbable. Engine feature.
#
# Container model: `docker ps -a` is read as a TSV of
#   <id>\t<persistent:true|false>\t<creator-pid>\t<project-path>
# (persistent = label com.microsoft.developer.usvc-dev.persistent; creator-pid + project from
# DCP labels). A container is an ORPHAN iff persistent==false AND its creator PID is dead.

dh_pid_alive() { local pid="$1"; [[ -n "${pid}" && "${pid}" != "-" ]] && kill -0 "${pid}" 2>/dev/null; }

_dh_ps() {
  docker ps -a --format '{{.ID}}\t{{.Label "com.microsoft.developer.usvc-dev.persistent"}}\t{{.Label "com.microsoft.developer.usvc-dev.creator-pid"}}\t{{.Label "com.microsoft.developer.usvc-dev.project"}}' 2>/dev/null
}

# dh_report_duplicates — warn when >1 LIVE (creator-PID-alive) session container shares a project.
dh_report_duplicates() {
  local id persistent pid project
  local -A live_by_project=()
  while IFS=$'\t' read -r id persistent pid project; do
    [[ -z "${id}" ]] && continue
    if [[ "${persistent}" == "false" ]] && dh_pid_alive "${pid}"; then
      live_by_project["${project}"]=$(( ${live_by_project["${project}"]:-0} + 1 ))
    fi
  done < <(_dh_ps)
  local p
  for p in "${!live_by_project[@]}"; do
    if (( ${live_by_project[$p]} > 1 )); then
      log_warn "dev: ${live_by_project[$p]} live AppHosts for the same project '${p}' — duplicate orchestration (consider stopping the stale one)"
    fi
  done
}

# dh_status — list AppHosts/containers, per-container RAM, swap pressure; warn on duplicates. Read-only.
dh_status() {
  if ! command -v docker >/dev/null 2>&1; then log_info "dev status: docker not present"; return 0; fi
  log_info "dev status: containers (id / persistent / creator-pid / project)"
  local id persistent pid project alive
  while IFS=$'\t' read -r id persistent pid project; do
    [[ -z "${id}" ]] && continue
    alive="dead"; dh_pid_alive "${pid}" && alive="alive"
    printf '  %s  persistent=%s  pid=%s(%s)  %s\n' "${id}" "${persistent}" "${pid}" "${alive}" "${project}"
  done < <(_dh_ps)
  # per-container RAM
  docker stats --no-stream --format '  {{.Name}}\t{{.MemUsage}}' 2>/dev/null || true
  # ddev projects (best-effort)
  command -v ddev >/dev/null 2>&1 && { ddev list 2>/dev/null || true; }
  # swap pressure
  if [[ -r /proc/meminfo ]]; then
    local st sf
    st="$(awk '/^SwapTotal:/{print $2}' /proc/meminfo)"; sf="$(awk '/^SwapFree:/{print $2}' /proc/meminfo)"
    [[ -n "${st}" && "${st}" -gt 0 ]] && printf '  swap: %s/%s kB free\n' "${sf}" "${st}"
  fi
  dh_report_duplicates
  log_ok "dev status: reported"
}

# dh_gc — remove ONLY persistent==false containers whose creator PID is dead; prune exited; report dups.
dh_gc() {
  if ! command -v docker >/dev/null 2>&1; then log_info "dev gc: docker not present — nothing to do"; return 0; fi
  local id persistent pid project removed=0
  while IFS=$'\t' read -r id persistent pid project; do
    [[ -z "${id}" ]] && continue
    if [[ "${persistent}" == "false" ]] && ! dh_pid_alive "${pid}"; then
      log_info "dev gc: removing orphan session container ${id} (creator PID ${pid:-?} dead, project ${project})"
      docker rm -f "${id}" >/dev/null 2>&1 || true
      removed=$(( removed + 1 ))
    fi
  done < <(_dh_ps)
  docker container prune -f >/dev/null 2>&1 || true
  dh_report_duplicates
  log_ok "dev gc: removed ${removed} orphan session container(s); pruned exited; persistent + live untouched"
}

# dh_down — end-of-day reclaim: ddev poweroff + stop stale AppHosts + prune + gc.
dh_down() {
  command -v ddev >/dev/null 2>&1 && { log_info "dev down: ddev poweroff"; ddev poweroff >/dev/null 2>&1 || true; }
  if command -v docker >/dev/null 2>&1; then
    # stop stale (dead-PID session) containers before pruning, then GC.
    local id persistent pid project
    while IFS=$'\t' read -r id persistent pid project; do
      [[ -z "${id}" ]] && continue
      if [[ "${persistent}" == "false" ]] && ! dh_pid_alive "${pid}"; then
        docker stop "${id}" >/dev/null 2>&1 || true
      fi
    done < <(_dh_ps)
    docker container prune -f >/dev/null 2>&1 || true
  fi
  dh_gc
  log_ok "dev down: reclaimed"
}
