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

## Updating an existing box

Three separate "update" surfaces — do not confuse them:

| Command | Updates | Notes |
|---|---|---|
| `devboost update` | **nothing installed** — regenerates `devboost.lock` | a misnomer, kept for compatibility |
| `devboost self-update` | the **engine binary** | checksummed GitHub-release swap |
| `devboost install --update` | the **CLI tools** in place | force-refreshes every `self_updating` module (all single-package/binary tools); leaves docker/dotfiles/gnome/drivers untouched |
| `dnf-automatic` timer | **OS security** patches only | provisioned by `dnf-automatic-security` |

`install --update` and `install --force` are mutually exclusive: `--update` refreshes only
the refreshable tools, `--force` re-runs *every* module. `--update` lives on `install` only —
"update my terminal tier" is `devboost install --update terminal`.

**Why some tools need `install --update`:** `lazydocker` and `lazygit` install via their
upstream scripts to `~/.local/bin` (no `dnf`/COPR), so they ride neither `dnf upgrade` nor the
`dnf-automatic` security timer. `install --update` re-runs their install-and-update scripts to
pull the latest release. The same applies to the GitHub-release binary tools (eza, atuin, dust,
sd, yq, fastfetch, gh, …).

## Quarterly checklist
1. Refresh the Fedora ISO on the Ventoy USB (`devboost installer --update` (re-stage Ventoy + newest ISO)).
2. `devboost update` → review the proposed pins + `devboost.lock` diff → commit.
3. `devboost install --update` → pick up non-security CLI-tool version bumps
   (`dnf-automatic` covers security patches only).
4. Confirm the vault round-trips (Obsidian Git + the daily `devboost-vault-sync` timer).
5. `devboost verify --profile <selected>` green; re-running install is a no-op.
6. `uv run pytest` (+ `mypy --strict` + ruff) green in `engine/`.

## Cutting a release
The frozen `devboost-<arch>` binaries that `scripts/get.sh` installs come from a GitHub Release.
Bump the version in **both** `engine/pyproject.toml` and `engine/src/devboost/__init__.py` (they must
match — CI and the local script both guard this), then publish either way:

- **CI (multi-arch, recommended):** `git tag vX.Y.Z && git push origin vX.Y.Z` → `.github/workflows/release.yml`
  builds x86_64 + aarch64 on native runners, assembles `checksums.txt`, and publishes the release.
- **Local (`scripts/release.sh`):** builds the **host arch only** (PyInstaller can't cross-compile),
  then creates/updates the `vX.Y.Z` release and regenerates `checksums.txt` from every binary on it.
  Run it on an x86_64 box *and* an aarch64 box for a full release; `--dry-run` prints the steps.

`get.sh` is anonymous `curl … | bash`, so its `releases/latest` only resolves when the **repo is public**.

## Notes
- Nothing auto-commits: `update`/`self-update` only edit the working tree; you review `git diff` and commit.
- Two machines built from the same `devboost.lock` are byte-for-byte identical.
