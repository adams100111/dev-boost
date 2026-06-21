# Contract: dev resource hygiene (bin/devboost dev + lib/devhygiene.sh)

## dev status  (FR-008, read-only)
- lists AppHosts (project path, PID, age), ddev projects, per-container RAM, swap pressure; WARN on
  >1 live AppHost for same project path. docker absent → graceful no-op. Tests: duplicate→warning.

## dev gc  (FR-009) — PRECISION GC
- remove container iff label com.microsoft.developer.usvc-dev.persistent==false AND creator PID dead;
  then `docker container prune -f`; report duplicate live AppHosts.
- NEVER remove: persistent==true containers; session containers whose creator PID is alive.
- Tests (stub docker ps/inspect + PID knobs): dead-PID session removed (`docker rm`); persistent NOT
  removed; live-PID session NOT removed; exited pruned; docker-absent → no-op success.

## dev down  (FR-010)
- `ddev poweroff` + stop stale AppHosts + `docker container prune -f` + dev gc. Tests: each step invoked (logs).
