# Phase 1 Data Model: lifecycle-and-dev-hygiene

Engine feature. "Data" = new lib functions, new `bin/devboost` verbs, the `devboost.lock` + export
artifacts, the module skeleton template, and the `aspire-gc` module.

## New libraries (source-only, PATH-stubbable; depend on lib/log.sh)

### lib/lifecycle.sh
| function | responsibility |
|---|---|
| `lc_add <name> [--folder]` | scaffold `modules/<name>/module.toml` from template (subst name); `--folder`→`install.sh` skeleton; refuse overwrite; validate name `^[a-z0-9][a-z0-9-]*$` |
| `lc_export [dir]` | write `workstation-config/exports/<UTC-ts>/{dnf,flatpak,mise,vscode-extensions}.txt`; gap-marker on missing tool; no mutation |
| `lc_diff` | declared closure (`profile_expand full`→`depsort`→`verify`) vs actual; print drift; return 0 sync / 1 drift |
| `lc_lock_write` | regenerate `devboost.lock` (sorted TSV module<TAB>resolved-version) from resolved state |
| `lc_lock_path` | echo `$DEVBOOST_ROOT/devboost.lock` |
| `lc_update [profile]` | propose pins into `config/mise.toml` (seed if absent) + `lc_lock_write`; print diff; never commit |
| `lc_self_update` | `git -C $DEVBOOST_ROOT pull --ff-only` then re-validate; named error on failure |

### lib/devhygiene.sh
| function | responsibility |
|---|---|
| `dh_apphosts` | enumerate live AppHosts (project path, creator PID, age) from docker metadata |
| `dh_pid_alive <pid>` | `kill -0` / `/proc` check |
| `dh_status` | list AppHosts + ddev projects + per-container RAM + swap pressure; warn on duplicate live AppHost per project |
| `dh_gc` | remove containers where `persistent==false` AND creator PID dead; `docker container prune -f`; report duplicates; never touch persistent/live |
| `dh_down` | `ddev poweroff` + stop stale AppHosts + prune + `dh_gc` |

## bin/devboost — new verbs (dispatch only; existing verbs unchanged)
| verb | cmd_ fn | calls |
|---|---|---|
| `add <name> [--folder]` | `cmd_add` | `lc_add` |
| `export` | `cmd_export` | `lc_export` |
| `diff` | `cmd_diff` | `lc_diff` |
| `update [--profile X]` | `cmd_update` | `lc_update` |
| `self-update` | `cmd_self_update` | `lc_self_update` |
| `dev <status\|gc\|down>` | `cmd_dev` | `dh_status`/`dh_gc`/`dh_down` |

`main()` case gains: add/export/diff/update/self-update/dev; `usage()` updated. `install` also calls
`lc_lock_write` at the end (regenerate lock from resolved state).

## Artifacts / assets
| asset | shape |
|---|---|
| `devboost.lock` | sorted TSV `module<TAB>resolved-version`, committed, secret-free |
| `config/mise.toml` | runtime pins (seeded by `update` if absent) |
| `workstation-config/exports/<UTC-ts>/*.txt` | per-source actual-state snapshots (gitignored dir ok; exports are state, not source) |
| `templates/module-skeleton/module.toml` | canonical module manifest with `__NAME__` placeholder |
| `templates/module-skeleton/install.sh` | escape-hatch skeleton sourcing lib/log.sh+lib/pkg.sh |
| `modules/aspire-gc/{module.toml,install.sh,verify.sh}` | systemd --user hourly `dev gc` |

## aspire-gc module
- `category="dev-hygiene"`, `requires=["docker"]`, `profiles=["dev-hygiene"]` (opt-in; NOT in full by default? — design §8b implies it's part of the dev workstation; add to `dev-hygiene` profile and document). Fedora-only `[install]`.
- install.sh: write `~/.config/systemd/user/aspire-gc.{service,timer}` (oneshot `devboost dev gc`, `OnCalendar=hourly` `Persistent=true`), `systemctl --user enable --now aspire-gc.timer`, `loginctl enable-linger`. Idempotent.
- verify.sh: both unit files present (+ timer enabled best-effort).

## Requirement traceability
| data | FR |
|---|---|
| lc_add + template | FR-001 |
| lc_export + export layout | FR-002 |
| lc_diff + exit codes | FR-003 |
| lc_update + config/mise.toml, no commit | FR-004 |
| lc_lock_write + devboost.lock TSV | FR-005 |
| lc_self_update | FR-006 |
| bin dispatch, existing verbs unchanged | FR-007 |
| dh_status | FR-008 |
| dh_gc label+PID | FR-009 |
| dh_down | FR-010 |
| aspire-gc module | FR-011 |
| read verbs no mutation; unattended | FR-012 |
| test-first, stubs, suite green | FR-013 |

## Profile entry (profiles.toml)
```toml
dev-hygiene = ["aspire-gc"]
```
(opt-in; aspire-gc requires docker. The `dev` verbs themselves are engine built-ins, not modules.)
