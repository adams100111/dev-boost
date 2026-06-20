# Contract: `data` stack (containers only)

`data-services` module: `category="dev-stacks"`, `requires=["docker"]`, only `[install].fedora`.
NO host database service is installed — databases are persistent containers.

## `install.sh`
- Seed `templates/data/compose.yaml` (the module ships it as data; "install" copies/ensures it
  into `templates/data/` — actually it lives in-repo already, so the module's job is to ensure the
  compose assets are present and dbgate reachable). Idempotent: seed-if-absent, never clobber.
- No `dnf`/host service install for postgres/redis.
- verify: `templates/data/compose.yaml` exists and references `postgres:18`, `valkey/valkey`, `dbgate/dbgate`.

## `templates/data/compose.yaml` (verified images, 2026-06)
```yaml
services:
  postgres:
    image: postgres:18
    environment: { POSTGRES_PASSWORD: devboost }
    volumes: [pgdata:/var/lib/postgresql/18/docker]   # PG18 version-specific PGDATA
    ports: ["5432:5432"]
  valkey:
    image: valkey/valkey:8.1
    command: ["valkey-server","--save","60","1","--appendonly","yes"]
    volumes: [valkeydata:/data]
    ports: ["6379:6379"]
  dbgate:
    image: dbgate/dbgate:7.2.0
    volumes: [dbgatedata:/root/.dbgate]
    ports: ["3000:3000"]
volumes: { pgdata: {}, valkeydata: {}, dbgatedata: {} }
```

## Tests (`data-stack.bats`)
- compose.yaml present with postgres:18 + valkey + dbgate + named volumes (persistence).
- NO host postgres/redis dnf install attempted (assert dnf log has no `install ... postgresql-server`/`redis`).
- idempotent (compose present → verify GREEN, no rewrite); unsupported-OS → engine failure.
- (No real `docker compose up` — assets-only validation, hermetic.)
