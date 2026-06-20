load test_helper
load fixtures/base/stubs

# ---------------------------------------------------------------------------
# Setup / teardown
# ---------------------------------------------------------------------------
setup() {
  load_lib log.sh
  load_lib pkg.sh
  base_setup
}

teardown() {
  base_teardown
}

# ---------------------------------------------------------------------------
# have / need_cmd
# ---------------------------------------------------------------------------
@test "have: returns 0 for a command on PATH (bash)" {
  run have bash
  [ "$status" -eq 0 ]
}

@test "have: returns non-zero for a command not on PATH" {
  run have __no_such_cmd_xyz_devboost
  [ "$status" -ne 0 ]
}

@test "need_cmd: does NOT call dnf when command is already present (bash)" {
  run need_cmd bash bash
  [ "$status" -eq 0 ]
  # dnf log should be empty — no install attempted
  [ ! -s "${STUB_DNF_LOG}" ]
}

@test "need_cmd: calls dnf install when command is absent" {
  # jq is not in the stub bin dir but we alias 'jq' to an absent name
  run need_cmd __absent_tool_xyz some-pkg
  [ "$status" -eq 0 ]
  grep -q "install" "${STUB_DNF_LOG}"
}

# ---------------------------------------------------------------------------
# dnf_install
# ---------------------------------------------------------------------------
@test "dnf_install: invokes sudo dnf install -y with the given package" {
  run dnf_install vim
  [ "$status" -eq 0 ]
  grep -q "dnf install -y vim" "${STUB_DNF_LOG}"
}

@test "dnf_install: passes multiple packages in one call" {
  run dnf_install curl wget jq
  [ "$status" -eq 0 ]
  grep -q "install -y curl wget jq" "${STUB_DNF_LOG}"
}

# ---------------------------------------------------------------------------
# rpm_q
# ---------------------------------------------------------------------------
@test "rpm_q: returns 0 when all packages are installed" {
  export STUB_RPM_INSTALLED="pkgA pkgB"
  run rpm_q pkgA pkgB
  [ "$status" -eq 0 ]
}

@test "rpm_q: returns non-zero when any package is absent" {
  export STUB_RPM_INSTALLED="pkgA"
  run rpm_q pkgA pkgB
  [ "$status" -ne 0 ]
}

@test "rpm_q: returns non-zero when no packages are installed" {
  export STUB_RPM_INSTALLED=""
  run rpm_q pkgA
  [ "$status" -ne 0 ]
}

# ---------------------------------------------------------------------------
# flatpak_remote_add
# ---------------------------------------------------------------------------
@test "flatpak_remote_add: adds remote when not already present" {
  export STUB_FLATPAK_REMOTES=""
  run flatpak_remote_add flathub https://flathub.org/repo/flathub.flatpakrepo
  [ "$status" -eq 0 ]
  grep -q "remote-add" "${STUB_FLATPAK_LOG}"
}

@test "flatpak_remote_add: skips remote-add when remote already present" {
  export STUB_FLATPAK_REMOTES="flathub"
  run flatpak_remote_add flathub https://flathub.org/repo/flathub.flatpakrepo
  [ "$status" -eq 0 ]
  # remote-add must NOT appear in the log
  ! grep -q "remote-add" "${STUB_FLATPAK_LOG}"
}

@test "flatpak_remote_add: skips remote-add when flatpak remotes prints name<TAB>system" {
  # Simulate real `flatpak remotes` output which includes a type column.
  # Override the flatpak stub for this test by writing a custom one.
  cat > "${_base_bin_dir}/flatpak" <<'TABSTUB'
#!/usr/bin/env bash
log_file="${STUB_FLATPAK_LOG:-/tmp/stub-flatpak-calls.log}"
printf 'flatpak %s\n' "$*" >> "${log_file}"
if [[ "$1" == "remotes" ]]; then
  printf 'flathub\tsystem\n'
  exit 0
fi
exit 0
TABSTUB
  chmod +x "${_base_bin_dir}/flatpak"
  run flatpak_remote_add flathub https://flathub.org/repo/flathub.flatpakrepo
  [ "$status" -eq 0 ]
  ! grep -q "remote-add" "${STUB_FLATPAK_LOG}"
}

# ---------------------------------------------------------------------------
# write_kv_conf
# ---------------------------------------------------------------------------
@test "write_kv_conf: adds key=value to an empty file" {
  local conf
  conf="$(base_scratch_dnf_conf)"
  run write_kv_conf "${conf}" max_parallel_downloads 10
  [ "$status" -eq 0 ]
  grep -q "^max_parallel_downloads=10$" "${conf}"
}

@test "write_kv_conf: reconciles an existing key= line (no duplicate)" {
  local conf
  conf="$(base_scratch_dnf_conf)"
  printf 'max_parallel_downloads=3\n' > "${conf}"
  run write_kv_conf "${conf}" max_parallel_downloads 10
  [ "$status" -eq 0 ]
  grep -q "^max_parallel_downloads=10$" "${conf}"
  # Only one occurrence — no duplicate
  [ "$(grep -c "^max_parallel_downloads=" "${conf}")" -eq 1 ]
}

@test "write_kv_conf: preserves unrelated lines" {
  local conf
  conf="$(base_scratch_dnf_conf)"
  printf '[main]\nfastestmirror=True\n' > "${conf}"
  run write_kv_conf "${conf}" max_parallel_downloads 10
  [ "$status" -eq 0 ]
  grep -q "^fastestmirror=True$" "${conf}"
  grep -q "^max_parallel_downloads=10$" "${conf}"
}

@test "write_kv_conf: idempotent — same value written twice is not duplicated" {
  local conf
  conf="$(base_scratch_dnf_conf)"
  write_kv_conf "${conf}" max_parallel_downloads 10
  write_kv_conf "${conf}" max_parallel_downloads 10
  [ "$(grep -c "^max_parallel_downloads=" "${conf}")" -eq 1 ]
}

@test "write_kv_conf: handles value containing | and / without corruption" {
  local conf
  conf="$(base_scratch_dnf_conf)"
  run write_kv_conf "${conf}" proxy "http://proxy.example|corp/mirror"
  [ "$status" -eq 0 ]
  grep -qF 'proxy=http://proxy.example|corp/mirror' "${conf}"
}

@test "write_kv_conf: idempotent when value contains | and / (no duplicate)" {
  local conf
  conf="$(base_scratch_dnf_conf)"
  write_kv_conf "${conf}" proxy "http://proxy.example|corp/mirror"
  run write_kv_conf "${conf}" proxy "http://proxy.example|corp/mirror"
  [ "$status" -eq 0 ]
  [ "$(grep -cF 'proxy=' "${conf}")" -eq 1 ]
}

# ---------------------------------------------------------------------------
# comment_block
# ---------------------------------------------------------------------------
@test "comment_block: comments lines between begin and end markers" {
  local bashrc
  bashrc="$(base_scratch_bashrc)"
  base_add_nvm_block
  run comment_block "${bashrc}" "# BEGIN NVM" "# END NVM"
  [ "$status" -eq 0 ]
  # The interior lines must now be commented
  grep -q "^# export NVM_DIR" "${bashrc}"
  grep -q "^# \[ -s" "${bashrc}"
}

@test "comment_block: is idempotent (already-commented lines not double-commented)" {
  local bashrc
  bashrc="$(base_scratch_bashrc)"
  base_add_nvm_block
  comment_block "${bashrc}" "# BEGIN NVM" "# END NVM"
  comment_block "${bashrc}" "# BEGIN NVM" "# END NVM"
  # Must not have double-comment prefix
  ! grep -q "^# # export NVM_DIR" "${bashrc}"
}

@test "comment_block: preserves lines outside the delimited block" {
  local bashrc
  bashrc="$(base_scratch_bashrc)"
  printf '# unrelated line before\n' > "${bashrc}"
  base_add_nvm_block
  printf '# unrelated line after\n' >> "${bashrc}"
  run comment_block "${bashrc}" "# BEGIN NVM" "# END NVM"
  [ "$status" -eq 0 ]
  grep -q "^# unrelated line before$" "${bashrc}"
  grep -q "^# unrelated line after$" "${bashrc}"
}

@test "comment_block: handles sdkman block" {
  local bashrc
  bashrc="$(base_scratch_bashrc)"
  base_add_sdkman_block
  run comment_block "${bashrc}" "# BEGIN SDKMAN" "# END SDKMAN"
  [ "$status" -eq 0 ]
  grep -q "^# export SDKMAN_DIR" "${bashrc}"
}

@test "comment_block: correctly processes file with no trailing newline (end marker on last line)" {
  local bashrc
  bashrc="$(base_scratch_bashrc)"
  # Write block with NO trailing newline after the END marker.
  printf '# BEGIN NVM\nexport NVM_DIR="$HOME/.nvm"\n# END NVM' > "${bashrc}"
  run comment_block "${bashrc}" "# BEGIN NVM" "# END NVM"
  [ "$status" -eq 0 ]
  # Interior line must be commented.
  grep -q '^# export NVM_DIR' "${bashrc}"
  # End marker must be present (not swallowed).
  grep -q '^# END NVM$' "${bashrc}"
}

# ---------------------------------------------------------------------------
# mise_drift
# ---------------------------------------------------------------------------
@test "mise_drift: returns 'both' when mise present and nvm hook uncommented in bashrc" {
  # mise stub is on PATH (installed by base_setup).
  # Seed an UNCOMMENTED nvm init block in the scratch ~/.bashrc.
  base_add_nvm_block
  run mise_drift
  [ "$status" -eq 0 ]
  [[ "$output" == "both" ]]
}

@test "mise_drift: returns 'both' when mise present and sdkman hook uncommented in bashrc" {
  base_add_sdkman_block
  run mise_drift
  [ "$status" -eq 0 ]
  [[ "$output" == "both" ]]
}

@test "mise_drift: returns 'mise-only' when mise present but no legacy hook in bashrc" {
  # mise stub is on PATH; ~/.bashrc has no nvm/sdkman hook lines.
  run mise_drift
  [ "$status" -eq 0 ]
  [[ "$output" == "mise-only" ]]
}

@test "mise_drift: returns 'mise-only' when mise present and legacy dirs exist but hooks are commented (post-migration)" {
  # SC-004 regression guard: after migration, ~/.nvm / ~/.sdkman dirs still exist
  # but their bashrc init blocks have been commented out by comment_block.
  # mise_drift MUST return 'mise-only' — no false drift report.
  mkdir -p "${HOME}/.nvm"
  mkdir -p "${HOME}/.sdkman"
  base_add_nvm_block
  base_add_sdkman_block
  local bashrc
  bashrc="$(base_scratch_bashrc)"
  comment_block "${bashrc}" "# BEGIN NVM" "# END NVM"
  comment_block "${bashrc}" "# BEGIN SDKMAN" "# END SDKMAN"
  run mise_drift
  [ "$status" -eq 0 ]
  [[ "$output" == "mise-only" ]]
}

@test "mise_drift: returns 'neither' when mise is absent and no legacy hook in bashrc" {
  base_remove_mise
  run mise_drift
  [ "$status" -eq 0 ]
  [[ "$output" == "neither" ]]
}

@test "mise_drift: returns 'neither' when mise is absent even if legacy dirs exist" {
  base_remove_mise
  mkdir -p "${HOME}/.nvm"
  base_add_nvm_block
  run mise_drift
  [ "$status" -eq 0 ]
  [[ "$output" == "neither" ]]
}
