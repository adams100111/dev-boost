load test_helper

setup() {
  GETSH="${BATS_TEST_DIRNAME}/../scripts/get.sh"
  STUB_DIR="$(mktemp -d)"
  export PATH="${STUB_DIR}:${PATH}"
}
teardown() { rm -rf "${STUB_DIR}"; }

@test "get.sh: gs_arch maps arm64 to aarch64" {
  printf '#!/usr/bin/env bash\necho arm64\n' > "${STUB_DIR}/uname"; chmod +x "${STUB_DIR}/uname"
  source "${GETSH}"
  run gs_arch
  [ "$status" -eq 0 ]
  [ "$output" = "aarch64" ]
}

@test "get.sh: gs_arch maps x86_64" {
  printf '#!/usr/bin/env bash\necho x86_64\n' > "${STUB_DIR}/uname"; chmod +x "${STUB_DIR}/uname"
  source "${GETSH}"
  run gs_arch
  [ "$output" = "x86_64" ]
}

@test "get.sh: gs_arch fails on unknown arch" {
  printf '#!/usr/bin/env bash\necho mips\n' > "${STUB_DIR}/uname"; chmod +x "${STUB_DIR}/uname"
  source "${GETSH}"
  run gs_arch
  [ "$status" -ne 0 ]
}

@test "get.sh: gs_verify fails on checksum mismatch" {
  source "${GETSH}"
  d="$(mktemp -d)"; echo "hello" > "${d}/file"
  echo "0000000000000000000000000000000000000000000000000000000000000000  file" > "${d}/checksums.txt"
  run gs_verify "${d}" file
  [ "$status" -ne 0 ]
  rm -rf "${d}"
}

@test "get.sh: gs_verify passes on matching checksum" {
  source "${GETSH}"
  d="$(mktemp -d)"; echo "hello" > "${d}/file"
  ( cd "${d}" && sha256sum file > checksums.txt )
  run gs_verify "${d}" file
  [ "$status" -eq 0 ]
  rm -rf "${d}"
}

@test "get.sh: gs_verify fails when file has NO checksum entry" {
  source "${GETSH}"
  d="$(mktemp -d)"; echo "hello" > "${d}/file"
  # checksums.txt exists but does NOT list 'file'
  echo "deadbeef  someotherfile" > "${d}/checksums.txt"
  run gs_verify "${d}" file
  [ "$status" -ne 0 ]
  rm -rf "${d}"
}

@test "get.sh: sourcing does not auto-run gs_main" {
  # if gs_main ran on source, it would try to download and fail loudly
  run bash -c "source '${GETSH}'; echo SOURCED_OK"
  [ "$status" -eq 0 ]
  [[ "$output" == *"SOURCED_OK"* ]]
}
