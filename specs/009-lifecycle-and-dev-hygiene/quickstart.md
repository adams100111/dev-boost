# Quickstart: validate lifecycle-and-dev-hygiene (hermetic)

All validation is offline/stubbed — no real docker, systemd, git, or package tools.

## Run the feature's tests
```sh
cd /home/dev/repos/dev-boost
bats tests/lifecycle.bats     # add / export / diff / update / self-update / devboost.lock
bats tests/devhygiene.bats    # dev status / gc / down (label+PID orphan GC)
bats tests/aspire-gc.bats     # hourly dev gc user timer module
bats tests/cli.bats           # bin/devboost dispatch + usage for new verbs
bats tests/profiles.bats      # dev-hygiene membership + depsort
```

## Manual smoke (stub-safe verbs)
```sh
./bin/devboost add demo                 # → modules/demo/module.toml (refuses if exists)
./bin/devboost add demo --folder        # also scaffolds install.sh
./bin/devboost export                   # → workstation-config/exports/<ts>/*.txt (read-only)
./bin/devboost diff; echo "drift? $?"   # 0 = in sync, non-zero = drift
./bin/devboost update --profile base    # proposes pins + devboost.lock; prints diff; NO commit
./bin/devboost dev status               # AppHosts/ddev/RAM/swap; warns on duplicate AppHost
./bin/devboost dev gc                   # removes only dead-PID session orphans; never persistent/live
```

## What "green" proves
- `add` scaffolds a valid module, refuses overwrite, rejects bad names (SC-001).
- `diff` exits 0 in sync / non-zero on drift — CI-usable (SC-002).
- `update` never commits; pins land as reviewable edits + deterministic `devboost.lock` (SC-003).
- `dev gc` removes 100% dead-PID session orphans, 0% persistent/live containers (SC-004).
- `aspire-gc` timer installed + enabled → hourly reclaim (SC-005).
- existing install/verify/list/doctor unchanged; full suite green (SC-006).

Decisions: [research.md](./research.md). Contracts: [contracts/](./contracts/).
