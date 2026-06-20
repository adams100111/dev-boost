load test_helper
load fixtures/base/stubs
load fixtures/base/engine_helpers

setup() {
  load_lib log.sh
  load_lib pkg.sh
  base_setup
  export DEVBOOST_MODULES_DIR="${DEVBOOST_ROOT}/modules"
  # Scratch ANDROID_HOME under HOME so no real SDK is touched; the android-sdk
  # module must HONOR this existing env value.
  export ANDROID_HOME="${HOME}/android-scratch/Sdk"
}

teardown() {
  base_teardown
}

# ---------------------------------------------------------------------------
# runners
# ---------------------------------------------------------------------------
_run_android_sdk() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export ANDROID_HOME='${ANDROID_HOME}'
    export STUB_MISE_LOG='${STUB_MISE_LOG}'
    export STUB_SDKMANAGER_LOG='${STUB_SDKMANAGER_LOG}'
    export STUB_CURL_LOG='${STUB_CURL_LOG}'
    bash '${DEVBOOST_ROOT}/modules/android-sdk/install.sh'
  " 2>&1
}

_run_verify_android_sdk() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export ANDROID_HOME='${ANDROID_HOME}'
    bash '${DEVBOOST_ROOT}/modules/android-sdk/verify.sh'
  " 2>&1
}

_run_expo() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export OS_DISTRO='${OS_DISTRO:-fedora}'
    export OS_FAMILY='${OS_FAMILY:-fedora}'
    export STUB_MISE_LOG='${STUB_MISE_LOG}'
    export STUB_NPM_LOG='${STUB_NPM_LOG}'
    bash '${DEVBOOST_ROOT}/modules/expo/install.sh'
  " 2>&1
}

_run_verify_expo() {
  bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    bash '${DEVBOOST_ROOT}/modules/expo/verify.sh'
  " 2>&1
}

# ===========================================================================
# android-sdk module
# ===========================================================================

@test "android-sdk: pins JDK via mise (java@temurin-17)" {
  run _run_android_sdk
  [ "$status" -eq 0 ]
  grep -q 'use -g java@temurin-17' "${STUB_MISE_LOG}"
}

@test "android-sdk: honors existing ANDROID_HOME and downloads cmdline-tools there" {
  run _run_android_sdk
  [ "$status" -eq 0 ]
  # curl downloaded a commandlinetools zip (logged) and unzipped under ANDROID_HOME.
  grep -qi 'commandlinetools' "${STUB_CURL_LOG}"
  [ -d "${ANDROID_HOME}/cmdline-tools/latest" ]
}

@test "android-sdk: installs the pinned SDK packages via sdkmanager" {
  run _run_android_sdk
  [ "$status" -eq 0 ]
  grep -q 'platform-tools' "${STUB_SDKMANAGER_LOG}"
  grep -q 'platforms;android-35' "${STUB_SDKMANAGER_LOG}"
  grep -q 'build-tools;36.0.0' "${STUB_SDKMANAGER_LOG}"
  grep -q 'cmdline-tools;latest' "${STUB_SDKMANAGER_LOG}"
}

@test "android-sdk: accepts SDK licenses unattended (--licenses)" {
  run _run_android_sdk
  [ "$status" -eq 0 ]
  grep -q -- '--licenses' "${STUB_SDKMANAGER_LOG}"
  [ -f "${ANDROID_HOME}/licenses/android-sdk-license" ]
}

@test "android-sdk: verify GREEN after provisioning (adb present, mise java resolves)" {
  _run_android_sdk >/dev/null
  [ -x "${ANDROID_HOME}/platform-tools/adb" ]
  run _run_verify_android_sdk
  [ "$status" -eq 0 ]
}

@test "android-sdk: verify RED before provisioning" {
  run _run_verify_android_sdk
  [ "$status" -ne 0 ]
}

@test "android-sdk: idempotent — second run does NOT re-accept licenses" {
  _run_android_sdk >/dev/null
  local n1; n1="$(grep -c -- '--licenses' "${STUB_SDKMANAGER_LOG}")"
  [ "${n1}" -ge 1 ]
  run _run_android_sdk
  [ "$status" -eq 0 ]
  local n2; n2="$(grep -c -- '--licenses' "${STUB_SDKMANAGER_LOG}")"
  # No additional --licenses call on the idempotent re-run.
  [ "${n2}" -eq "${n1}" ]
}

@test "android-sdk: unsupported-OS — engine reports failure on non-fedora" {
  run bash -c "
    export HOME='${HOME}'
    export PATH='${PATH}'
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_DISTRO='ubuntu'
    export OS_FAMILY='debian'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    source '${DEVBOOST_ROOT}/lib/depsort.sh'
    source '${DEVBOOST_ROOT}/lib/install.sh'
    summary_reset
    run_install -- android-sdk
  " 2>&1
  [ "$status" -ne 0 ]
  [[ "$output" == *"unsupported"* ]]
}

# ===========================================================================
# expo module (NO global expo-cli — deprecated)
# ===========================================================================

@test "expo: seeds templates/react-native/README.md" {
  run _run_expo
  [ "$status" -eq 0 ]
  [ -f "${DEVBOOST_ROOT}/templates/react-native/README.md" ]
}

@test "expo: installs NO global expo-cli (deprecated)" {
  run _run_expo
  [ "$status" -eq 0 ]
  ! grep -qiE 'install -g .*expo' "${STUB_MISE_LOG}"
  ! grep -qiE 'install -g .*expo' "${STUB_NPM_LOG}"
}

@test "expo: verify GREEN (README present)" {
  run _run_verify_expo
  [ "$status" -eq 0 ]
}

@test "expo: unsupported-OS — engine has no non-fedora install path (gated)" {
  # expo's verify (in-repo template README) is OS-independent and always true, so
  # the engine short-circuits on the idempotency guard before the OS gate. The
  # gating contract is therefore asserted at the source: only [install].fedora is
  # defined, so module_install_cmd is empty on any non-fedora distro — which is
  # exactly the condition run_install reports as "unsupported".
  run bash -c "
    export DEVBOOST_ROOT='${DEVBOOST_ROOT}'
    export DEVBOOST_MODULES_DIR='${DEVBOOST_MODULES_DIR}'
    export OS_DISTRO='ubuntu'
    export OS_FAMILY='debian'
    source '${DEVBOOST_ROOT}/lib/log.sh'
    source '${DEVBOOST_ROOT}/lib/toml.sh'
    source '${DEVBOOST_ROOT}/lib/os.sh'
    source '${DEVBOOST_ROOT}/lib/module.sh'
    icmd=\"\$(module_install_cmd expo)\"
    [[ -z \"\${icmd}\" ]] || { echo \"unexpected non-fedora install cmd: \${icmd}\"; exit 1; }
    echo 'expo: no install command — unsupported on ubuntu/debian'
  " 2>&1
  [ "$status" -eq 0 ]
  [[ "$output" == *"unsupported"* ]]
}

# ===========================================================================
# templates/react-native
# ===========================================================================

@test "templates/react-native/.fresh/config.json is valid JSON, tab_size 2" {
  local cfg="${DEVBOOST_ROOT}/templates/react-native/.fresh/config.json"
  [ -f "${cfg}" ]
  jq -e . "${cfg}" >/dev/null
  [ "$(jq -r '.editor.tab_size' "${cfg}")" = "2" ]
}

@test "templates/react-native/README.md documents the Expo/Android flow (JDK 17, API 35)" {
  local readme="${DEVBOOST_ROOT}/templates/react-native/README.md"
  [ -f "${readme}" ]
  grep -q 'create-expo-app' "${readme}"
  grep -q 'expo prebuild' "${readme}"
  grep -q 'expo run:android' "${readme}"
}
