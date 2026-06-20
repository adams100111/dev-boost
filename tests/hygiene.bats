load test_helper

# T019 — repo hygiene: no secret/key/credential files must be tracked by git.
# Asserts git ls-files matches none of: *.age, id_ed25519*, *.git-credentials,
# age identity files (age-key.txt). SC-005, FR-012.

@test "hygiene: no *.age files tracked by git" {
  run git -C "${DEVBOOST_ROOT}" ls-files --error-unmatch '*.age' 2>&1
  # ls-files --error-unmatch exits non-zero when no match → that's the PASS condition
  [ "$status" -ne 0 ]
}

@test "hygiene: no id_ed25519* files tracked by git" {
  run git -C "${DEVBOOST_ROOT}" ls-files --error-unmatch 'id_ed25519' 'id_ed25519.pub' 2>&1
  [ "$status" -ne 0 ]
}

@test "hygiene: no *.git-credentials files tracked by git" {
  # Check both bare and prefixed forms.
  run bash -c "
    git -C '${DEVBOOST_ROOT}' ls-files | grep -E '\.git-credentials$'
  " 2>&1
  # grep exits non-zero when no match → pass
  [ "$status" -ne 0 ]
}

@test "hygiene: no age-key.txt tracked by git" {
  run git -C "${DEVBOOST_ROOT}" ls-files --error-unmatch 'age-key.txt' 2>&1
  [ "$status" -ne 0 ]
}
