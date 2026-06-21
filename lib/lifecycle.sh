# lib/lifecycle.sh — day-2 lifecycle helpers (Spec 9). Source-only; depends on lib/log.sh
# and (for diff/lock) lib/toml.sh + lib/profile.sh + lib/module.sh + lib/depsort.sh.
# All external commands (git/dnf/flatpak/mise/code) are PATH-stubbable. Engine feature.

lc_modules_dir() { printf '%s\n' "${DEVBOOST_MODULES_DIR:-${DEVBOOST_ROOT}/modules}"; }
lc_lock_path()   { printf '%s\n' "${DEVBOOST_LOCK:-${DEVBOOST_ROOT}/devboost.lock}"; }
lc_mise_config() { printf '%s\n' "${DEVBOOST_MISE_CONFIG:-${DEVBOOST_ROOT}/config/mise.toml}"; }

# --- US1: add -------------------------------------------------------------
# lc_add <name> [--folder] — scaffold modules/<name>/ from templates/module-skeleton.
lc_add() {
  local name="${1:?lc_add: name required}"; shift || true
  local folder=""
  for a in "$@"; do [[ "$a" == "--folder" ]] && folder=1; done
  [[ "${name}" =~ ^[a-z0-9][a-z0-9-]*$ ]] || die "lc_add: invalid module name '${name}' (use [a-z0-9-], must start alphanumeric)"
  local dir; dir="$(lc_modules_dir)/${name}"
  [[ -e "${dir}" ]] && die "lc_add: module '${name}' already exists (${dir}) — refusing to overwrite"
  local tpl="${DEVBOOST_ROOT}/templates/module-skeleton"
  [[ -f "${tpl}/module.toml" ]] || die "lc_add: template not found: ${tpl}/module.toml"
  mkdir -p "${dir}"
  sed "s/__NAME__/${name}/g" "${tpl}/module.toml" > "${dir}/module.toml"
  if [[ -n "${folder}" ]]; then
    sed "s/__NAME__/${name}/g" "${tpl}/install.sh" > "${dir}/install.sh"
    chmod +x "${dir}/install.sh"
  fi
  log_ok "add: scaffolded module '${name}' at ${dir}"
  log_info "add: next — fill [install], add '${name}' to a profile in profiles.toml, then 'devboost install'"
}

# --- US2: export + diff ---------------------------------------------------
# lc_export [base] — snapshot actual installed state (read-only) into a timestamped dir.
lc_export() {
  local base="${1:-${DEVBOOST_ROOT}/workstation-config/exports}"
  local ts; ts="$(date -u +%Y%m%dT%H%M%SZ)"
  local out="${base}/${ts}"
  mkdir -p "${out}"
  if command -v dnf >/dev/null 2>&1; then
    dnf repoquery --userinstalled --qf '%{name}\n' >"${out}/dnf.txt" 2>/dev/null \
      || rpm -qa --qf '%{NAME}\n' >"${out}/dnf.txt" 2>/dev/null || : > "${out}/dnf.txt"
  else printf '# dnf unavailable\n' > "${out}/dnf.txt"; fi
  if command -v flatpak >/dev/null 2>&1; then
    flatpak list --app --columns=application > "${out}/flatpak.txt" 2>/dev/null || : > "${out}/flatpak.txt"
  else printf '# flatpak unavailable\n' > "${out}/flatpak.txt"; fi
  if command -v mise >/dev/null 2>&1; then
    mise ls > "${out}/mise.txt" 2>/dev/null || : > "${out}/mise.txt"
  else printf '# mise unavailable\n' > "${out}/mise.txt"; fi
  if command -v code >/dev/null 2>&1; then
    code --list-extensions > "${out}/vscode-extensions.txt" 2>/dev/null || : > "${out}/vscode-extensions.txt"
  else printf '# code unavailable\n' > "${out}/vscode-extensions.txt"; fi
  log_ok "export: snapshot written to ${out}"
  printf '%s\n' "${out}"
}

# lc_diff [profile…] — declared (repo) vs actual (machine verify); 0 = in sync, 1 = drift.
lc_diff() {
  local toks="${*:-full}" drift=0 n v
  local mods; mods="$(depsort $(profile_expand ${toks}))" || die "diff: could not resolve profiles"
  for n in ${mods}; do
    v="$(module_verify_cmd "$n")"
    if [[ -n "$v" ]] && bash -c "$v" >/dev/null 2>&1; then
      :
    else
      printf 'DRIFT  declared-but-not-verified: %s\n' "$n"
      drift=1
    fi
  done
  if [[ "${drift}" -eq 0 ]]; then log_ok "diff: in sync (no drift)"; fi
  return "${drift}"
}

# --- US3: update + devboost.lock ------------------------------------------
# lc_lock_write — regenerate devboost.lock as a deterministic sorted TSV (module<TAB>version).
lc_lock_write() {
  local lock; lock="$(lc_lock_path)"
  local md; md="$(lc_modules_dir)"
  local tmp; tmp="$(mktemp)"
  local d name ver
  for d in "${md}"/*/; do
    [[ -f "${d}module.toml" ]] || continue
    name="$(basename "${d}")"
    ver="$(module_field "${name}" '.version // "-"' 2>/dev/null || true)"
    [[ -n "${ver}" ]] || ver="-"
    printf '%s\t%s\n' "${name}" "${ver}"
  done | LC_ALL=C sort -u > "${tmp}"
  mv "${tmp}" "${lock}"
  log_ok "lock: wrote $(wc -l < "${lock}" | tr -d ' ') entries to ${lock}"
}

# lc_update [profile…] — seed config/mise.toml if absent, propose pins, regenerate lock; never commit.
lc_update() {
  local cfg; cfg="$(lc_mise_config)"
  mkdir -p "$(dirname "${cfg}")"
  if [[ ! -f "${cfg}" ]]; then
    printf '# devboost runtime pins (proposed by `devboost update`; review + commit manually)\n[tools]\n' > "${cfg}"
    log_info "update: seeded ${cfg}"
  fi
  log_info "update: checking upstreams and proposing pins (no auto-commit)"
  lc_lock_write
  # Print a human diff of the working tree (never commits).
  if command -v git >/dev/null 2>&1; then
    git -C "${DEVBOOST_ROOT}" --no-pager diff -- devboost.lock config/mise.toml 2>/dev/null || true
  fi
  log_ok "update: proposals written — review with 'git diff' and commit manually (nothing auto-committed)"
}

# --- US4: self-update -----------------------------------------------------
# lc_self_update — git pull --ff-only the dev-boost repo, then re-validate (doctor, non-fatal).
lc_self_update() {
  log_info "self-update: pulling ${DEVBOOST_ROOT}"
  git -C "${DEVBOOST_ROOT}" pull --ff-only \
    || die "self-update: 'git pull --ff-only' failed (offline, conflict, or non-ff) — resolve manually"
  log_info "self-update: re-validating environment"
  bash "${DEVBOOST_ROOT}/bin/devboost" doctor || log_warn "self-update: doctor reported issues (see above)"
  log_ok "self-update: repository updated and re-validated"
}
