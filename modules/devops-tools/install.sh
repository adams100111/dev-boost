#!/usr/bin/env bash
# modules/devops-tools/install.sh — provision the DevOps stack's CLIs.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (`mise use -g` reconciles a pinned global set).
#
# Installs OpenTofu + kubectl + Helm + k9s as mise-managed, aqua-backed, version-
# pinned global tools in a single declaration. Pins ARE the in-repo source of
# truth (Principle III). OpenTofu is used over Terraform (research.md).
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"

have mise || die "devops-tools: mise is not installed — cannot provision DevOps CLIs"

# One combined, pinned declaration (idempotent; reconciles the global tool set).
mise use -g \
  aqua:opentofu/opentofu@1.11.6 \
  aqua:kubernetes/kubectl@1.35.2 \
  aqua:helm/helm@4.1.4 \
  aqua:derailed/k9s@0.51.0 \
  || die "devops-tools: 'mise use -g aqua:opentofu/opentofu@1.11.6 aqua:kubernetes/kubectl@1.35.2 aqua:helm/helm@4.1.4 aqua:derailed/k9s@0.51.0' failed"

log_ok "devops-tools: opentofu@1.11.6 kubectl@1.35.2 helm@4.1.4 k9s@0.51.0 provisioned"
