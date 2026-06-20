#!/usr/bin/env bash
# modules/data-services/install.sh — Data dev-stack (containers-only).
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
#
# The data services (PostgreSQL, Valkey, dbgate) are persistent Docker containers
# described by templates/data/compose.yaml — there is NO host database service
# install (no dnf install of postgresql-server / redis). This module's only job is
# to ensure the compose assets are present so `docker compose up -d` can run.
#
# The compose assets ship in-repo, so "install" is a seed-if-absent guard that
# never clobbers an existing (possibly user-edited) compose.yaml. Idempotent;
# no prompts.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

data_dir="${DEVBOOST_ROOT}/templates/data"
compose="${data_dir}/compose.yaml"

# Seed-if-absent: the compose file ships in-repo, so normally this is a no-op.
# If it is somehow missing, recreate the canonical asset rather than failing.
if [[ -f "${compose}" ]]; then
  log_skip "data-services: compose assets already present (${compose})"
else
  log_info "data-services: seeding compose assets ${compose}"
  mkdir -p "${data_dir}"
  cat > "${compose}" <<'YAML'
services:
  postgres:
    image: postgres:18
    environment: { POSTGRES_PASSWORD: devboost }
    volumes: [pgdata:/var/lib/postgresql/18/docker]
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
YAML
fi

# Hard assertion: the compose asset must reference the pinned, verified images.
grep -q 'postgres:18'        "${compose}" || die "data-services: compose missing postgres:18"
grep -q 'valkey/valkey'      "${compose}" || die "data-services: compose missing valkey/valkey"
grep -q 'dbgate/dbgate'      "${compose}" || die "data-services: compose missing dbgate/dbgate"

log_ok "data-services: container compose assets ready (docker compose up -d)"
