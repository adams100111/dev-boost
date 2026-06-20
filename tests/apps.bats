load test_helper
load fixtures/base/stubs
load fixtures/base/engine_helpers

# US1 — the `apps` profile: six Flathub GUI apps. App IDs are registry-verified (research.md).

setup() {
  load_lib log.sh
  load_lib pkg.sh
  base_setup
  export DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules"
  # Dynamic install tracking so `flatpak info` (verify) reflects an actual install.
  export STUB_FLATPAK_INSTALLED_FILE="${BATS_TEST_TMPDIR}/flatpak-installed.txt"
  : > "${STUB_FLATPAK_INSTALLED_FILE}"
  # Flathub remote present (base profile precondition).
  export STUB_FLATPAK_REMOTES="flathub"
}

teardown() { base_teardown; }

# install + post-verify GREEN, per app (id verified in research.md).
@test "apps/obsidian: installs md.obsidian.Obsidian and verifies" {
  run _engine_install obsidian
  [ "$status" -eq 0 ]
  grep -q 'install -y flathub md.obsidian.Obsidian' "${STUB_FLATPAK_LOG}"
}
@test "apps/bruno: installs com.usebruno.Bruno and verifies" {
  run _engine_install bruno
  [ "$status" -eq 0 ]
  grep -q 'install -y flathub com.usebruno.Bruno' "${STUB_FLATPAK_LOG}"
}
@test "apps/bitwarden: installs com.bitwarden.desktop and verifies" {
  run _engine_install bitwarden
  [ "$status" -eq 0 ]
  grep -q 'install -y flathub com.bitwarden.desktop' "${STUB_FLATPAK_LOG}"
}
@test "apps/flameshot: installs org.flameshot.Flameshot and verifies" {
  run _engine_install flameshot
  [ "$status" -eq 0 ]
  grep -q 'install -y flathub org.flameshot.Flameshot' "${STUB_FLATPAK_LOG}"
}
@test "apps/localsend: installs org.localsend.localsend_app and verifies" {
  run _engine_install localsend
  [ "$status" -eq 0 ]
  grep -q 'install -y flathub org.localsend.localsend_app' "${STUB_FLATPAK_LOG}"
}
@test "apps/vlc: installs org.videolan.VLC and verifies" {
  run _engine_install vlc
  [ "$status" -eq 0 ]
  grep -q 'install -y flathub org.videolan.VLC' "${STUB_FLATPAK_LOG}"
}

@test "apps/obsidian: idempotent — skips install when already present (verify GREEN pre-install)" {
  export STUB_FLATPAK_INSTALLED="md.obsidian.Obsidian"
  run _engine_install obsidian
  [ "$status" -eq 0 ]
  ! grep -q 'install -y flathub md.obsidian.Obsidian' "${STUB_FLATPAK_LOG}"
}

@test "apps/vlc: unsupported-OS — engine reports failure on non-fedora" {
  run _engine_install vlc ubuntu debian
  [ "$status" -ne 0 ]
  [[ "$output" == *"unsupported"* ]]
}

@test "apps: no dbgate flatpak module exists (dbgate is the data-stack container)" {
  [ ! -d "${DEVBOOST_ROOT}/modules/dbgate" ]
  ! grep -qE '"dbgate"' "${DEVBOOST_ROOT}/profiles.toml"
}

@test "apps: every app module is category=apps, requires flatpak, fedora-only install" {
  for m in obsidian bruno bitwarden flameshot localsend vlc; do
    grep -q 'category    = "apps"' "${DEVBOOST_ROOT}/modules/$m/module.toml" || { echo "$m not category apps"; return 1; }
    grep -q 'requires    = \["flatpak"\]' "${DEVBOOST_ROOT}/modules/$m/module.toml" || { echo "$m wrong requires"; return 1; }
    grep -q '^fedora = ' "${DEVBOOST_ROOT}/modules/$m/module.toml" || { echo "$m missing fedora install"; return 1; }
    grep -qE '^(default|ubuntu|debian|arch|macos) = ' "${DEVBOOST_ROOT}/modules/$m/module.toml" && { echo "$m has non-fedora key"; return 1; }
    true
  done
}
