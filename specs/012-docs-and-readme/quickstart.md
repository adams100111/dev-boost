# Quickstart: validate docs-and-readme
```sh
cd /home/dev/repos/dev-boost
bash scripts/gen-profiles-table.sh   # prints the profiles table
bats tests/docs.bats                 # README drift gate + docs presence
```
Green proves: README has quick start + every profile + every verb (SC-001/002); 6 docs files exist; suite green (SC-003).
