# Data dev-stack (containers-only)

Persistent local data services for development — PostgreSQL, Valkey (Redis-compatible),
and dbgate — run as Docker containers from `compose.yaml`. No host database service is
installed; all state lives in named Docker volumes so it survives container restarts.

## Bring it up

```sh
docker compose up -d
```

Tear it down (keeping data):

```sh
docker compose down
```

Wipe all data (removes the named volumes):

```sh
docker compose down -v
```

## Services

| Service  | Image                | Host port | Notes                              |
| -------- | -------------------- | --------- | ---------------------------------- |
| postgres | `postgres:18`        | 5432      | password `devboost`                |
| valkey   | `valkey/valkey:8.1`  | 6379      | append-only persistence enabled    |
| dbgate   | `dbgate/dbgate:7.2.0`| 3000      | web DB client, open http://localhost:3000 |

## Connection strings

- PostgreSQL: `postgres://postgres:devboost@localhost:5432/postgres`
- Valkey / Redis: `redis://localhost:6379`
- dbgate UI: open <http://localhost:3000> in a browser.

## Persistence

Data is stored in named volumes (`pgdata`, `valkeydata`, `dbgatedata`) and persists
across `docker compose down` / `up`. Use `docker compose down -v` to remove it.
