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

**Why some tools need `install --update`:** `lazydocker` always installs via its upstream
`install_update_linux.sh` script to `~/.local/bin` on every OS (no `dnf`/COPR). `lazygit` and the
other GitHub-release binary tools (eza, atuin, dust, sd, yq, fastfetch, gh, …) install the same
way on Debian/Ubuntu, but on Fedora `lazygit` (and friends) come from `dnf`/COPR instead. Either
way, none of them ride the security-only `dnf-automatic` timer, so a plain re-run never bumps them
to a newer non-security release. `install --update` force-refreshes them: it re-runs the
binary-drop scripts on Debian/Ubuntu, and re-runs `dnf`/`apt` install on Fedora, which upgrades
the package in place.

## Quarterly checklist
1. Refresh the Fedora ISO on the Ventoy USB (`devboost installer --update` (re-stage Ventoy + newest ISO)).
2. `devboost update` → review the proposed pins + `devboost.lock` diff → commit.
3. `devboost install --update` → pick up non-security CLI-tool version bumps
   (`dnf-automatic` covers security patches only).
4. Confirm the vault round-trips (Obsidian Git + the daily `devboost-vault-sync` timer).
5. `devboost verify --profile <selected>` green; re-running install is a no-op.
6. `uv run pytest` (+ `mypy --strict` + ruff) green in `engine/`.

## Cutting a release
The frozen binaries `scripts/get.sh` installs — `devboost-x86_64`, `devboost-aarch64` and
`devboost-darwin-arm64` — come from a GitHub Release, alongside the two Linux-only Ventoy
injection archives and **one shared `checksums.txt`** covering all five files. Bump the
version in **both** `engine/pyproject.toml` and `engine/src/devboost/__init__.py` (they
must match — CI and the local script both guard this).

**Before tagging:** rehearse the macOS `curl | bash` path in a tart VM against your own
unpublished build, so a broken install is caught before it ships, not after —
`bash scripts/build-bundle.sh` then `scripts/vm-test-macos.sh run --local dist` (see
[docs/vm-testing.md](vm-testing.md), "macOS (tart)", D9). This needs a Mac; if you're
releasing from Linux, CI's `binary-compat` job below is the equivalent check.

Publish through CI. `release.yml` is the **one canonical release path**; `scripts/release.sh`
is an emergency fallback that refuses to run while the workflow is enabled (below).

- **CI (multi-arch, canonical):** `git tag vX.Y.Z && git push origin vX.Y.Z` →
  `.github/workflows/release.yml`:
  1. `checks` — the full test suite on `ubuntu-24.04` **and** `macos-15`; everything below
     needs this to pass first.
  2. `binary` — builds (and, on macOS, ad-hoc-signs + `codesign --verify --strict`s) all
     three binaries on their native runners (`ubuntu-24.04`, `ubuntu-24.04-arm`,
     `macos-15`). The two Linux legs build inside an `ubuntu:22.04` container, which keeps
     the published binaries' **glibc 2.35 floor** (Ubuntu 22.04+, Debian 12, Fedora 36+)
     now that the `ubuntu-22.04` runner image is deprecated. `scripts/check-glibc-floor.sh`
     fails the leg if any ELF object that ships needs a `GLIBC_` symbol newer than 2.35: it
     runs `objdump -T` over the bootloader stub **and** over every ELF inside the onefile's
     embedded archive — libpython and every extension module / shared library PyInstaller
     collected — which `scripts/pyi_bundle_elfs.py` extracts. (The stub alone can never
     fail: PyInstaller's prebuilt bootloader needs only about `GLIBC_2.14`.) An archive it
     cannot read, or one with no ELF libpython, errors instead of passing.
  3. `binary-compat` — re-runs the **macos-15-built** `devboost-darwin-arm64` unmodified on
     `macos-26` (blocking) and the `xcode-27` preview image (non-blocking): `--version`,
     `list macos`, `codesign --verify --strict` again — proving the oldest-supported-macOS
     build stays forward-compatible on the newer OSes it also targets.
  4. `release` — collects all three binaries and both Ventoy archives (`x86_64`/`aarch64`
     only — Darwin ships none), verifies every one against the per-arch
     `checksums-<arch>.txt` its build runner wrote (`sha256sum -c`) and regenerates the
     single `checksums.txt`. It then creates the release as a **draft** (refusing if the
     tag's release is already published — a re-run reuses its own draft), uploads all six
     files, downloads them back and checks there are exactly those six, that every asset has
     a `checksums.txt` entry and that every hash matches, and only as its **last step**
     publishes the release and marks it latest. Until then `releases/latest` (and so
     `get.sh` / `self-update`) still serves the previous release.
- **Emergency only — local (`scripts/release.sh`):** it **refuses** while
  `.github/workflows/release.yml` exists and is enabled (or its state can't be read), because
  the paths collide: publishing a `release.sh` draft creates the `v*` tag with your own token,
  which starts `release.yml`, which rebuilds every binary (not byte-reproducible) and uploads
  it over the release you just verified. To use it anyway, either disable the workflow
  (`gh workflow disable release.yml`, and re-enable it afterwards), or set
  `DEVBOOST_RELEASE_EMERGENCY=1`: that prints a loud warning and publishes **only if the tag
  already exists on origin** (publishing then pushes no tag, so starts no workflow); for a
  tag not yet pushed it stops at a verified draft. It builds and uploads the **host arch
  only** (PyInstaller can't cross-compile — run it once per arch, one host after another,
  never at the same time: an x86_64 box, an aarch64 box, and a Mac, for a full 3-arch
  release). The first run creates the release as a **draft**, which
  `releases/latest` (and so `get.sh` / `self-update`) never sees. Each run uploads its arch,
  regenerates `checksums.txt` from every binary on the release, downloads everything back
  and verifies it, and only then — once all five assets are there — publishes the release
  and marks it latest; until then it says which assets are still missing. `--publish` ships
  a deliberately partial release; `--dry-run` prints the steps without running them. An
  already-published release never has an existing asset replaced.

`get.sh` is anonymous `curl … | bash`, so its `releases/latest` only resolves when the **repo is public**.

## Notes
- Nothing auto-commits: `update`/`self-update` only edit the working tree; you review `git diff` and commit.
- Two machines built from the same `devboost.lock` are byte-for-byte identical.
