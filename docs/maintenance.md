# Maintenance (quarterly cadence)

The git repo is the single source of truth; machines are disposable projections.

## Day-2 commands
- `devboost update [--profile X]` — propose pinned bumps into `config/mise.toml` + regenerate
  `devboost.lock`; prints a diff; **never auto-commits** (you review + commit).
- `devboost export` — snapshot actual state into `workstation-config/exports/<ts>/`.
- `devboost diff` — declared (repo) vs actual (machine) drift; exit ≠ 0 on drift (CI-usable).
- `devboost self-update` — `git pull` dev-boost then re-validate; other machines then `devboost install`.
- `devboost dev gc` / `dev down` — reclaim memory from orphan/duplicate Aspire AppHosts (the `aspire-gc`
  user timer runs `dev gc` hourly).

## Quarterly checklist
1. Refresh the Fedora ISO on the Ventoy USB (`devboost usb --update` (re-stage Ventoy + newest ISO)).
2. `devboost update` → review the proposed pins + `devboost.lock` diff → commit.
3. Confirm the vault round-trips (Obsidian Git + the daily `devboost-vault-sync` timer).
4. `devboost verify --profile <selected>` green; re-running install is a no-op.
5. `uv run pytest` (+ `mypy --strict` + ruff) green in `engine/`.

## Notes
- Nothing auto-commits: `update`/`self-update` only edit the working tree; you review `git diff` and commit.
- Two machines built from the same `devboost.lock` are byte-for-byte identical.
