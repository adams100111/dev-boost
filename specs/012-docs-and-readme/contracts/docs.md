# Contract: docs + generator (tests/docs.bats)
- gen-profiles-table.sh: prints a markdown table; one row per profile in profiles.toml; cell lists modules.
- README.md: contains quick-start command; every profile name from profiles.toml; every verb
  (install verify list doctor add export diff update self-update dev); recovery + add-a-module sections.
- drift gate: every profile in profiles.toml appears in README (test greps each); generator runs exit 0.
- docs/: the 6 files exist and are non-trivial (>20 lines each).
