# Data Model: docs-and-readme
| artifact | content |
|---|---|
| README.md | what-it-is + recovery promise; quick start (install.sh/curl + --profile); profiles table (generated); commands (all verbs); recovery walkthrough; add-a-tool example; requirements/OS matrix |
| scripts/gen-profiles-table.sh | reads profiles.toml via lib/toml.sh+profile.sh → markdown table (profile \| modules) |
| docs/architecture.md | engine+data model, lib map, depsort, profiles |
| docs/recovery-runbook.md | USB build + boot paths + snapshot rollback + GPU recovery (links ventoy/Docs) |
| docs/adding-a-module.md | `devboost add` + module.toml shape + profile wiring |
| docs/maintenance.md | quarterly cadence: update/export/diff, ISO refresh, vault push |
| docs/obsidian-sync.md | §7.1 deploy key + Obsidian Git + daily timer |
| docs/ventoy.md | §9 Ventoy/Kickstart USB |
| tests/docs.bats | README lists every profile + verb; table in sync with generator; 6 docs files exist |
