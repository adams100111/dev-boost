#!/usr/bin/env bash
# modules/data-services/verify.sh — idempotency guard for the data-services module.
# GREEN iff templates/data/compose.yaml exists and references the pinned, verified
# container images (postgres:18, valkey/valkey, dbgate/dbgate). Read-only; no prompts.
set -Eeuo pipefail

compose="${DEVBOOST_ROOT}/templates/data/compose.yaml"

[[ -f "${compose}" ]]               || exit 1
grep -q 'postgres:18'   "${compose}" || exit 1
grep -q 'valkey/valkey' "${compose}" || exit 1
grep -q 'dbgate/dbgate' "${compose}" || exit 1

exit 0
