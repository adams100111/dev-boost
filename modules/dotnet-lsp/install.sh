#!/usr/bin/env bash
# modules/dotnet-lsp/install.sh — provision fresh's C# language intelligence.
# Sourced env: DEVBOOST_ROOT, OS_DISTRO, OS_FAMILY, HOME.
# No prompts; idempotent (jq-merge reconciles, never clobbers); non-interactive.
#
# Unlike the mise-backed *-lsp modules, the C# servers are `dotnet tool`-installed
# (NOT mise-managed), so we wire csharp-ls into fresh's config via fresh_lsp_wire
# (the merge-only primitive) using its absolute ~/.dotnet/tools path. csharpier is the
# C# FORMATTER — wired per-project in templates/dotnet/.fresh/config.json, not globally.
set -Eeuo pipefail

source "${DEVBOOST_ROOT}/lib/log.sh"
source "${DEVBOOST_ROOT}/lib/pkg.sh"
source "${DEVBOOST_ROOT}/lib/fresh.sh"

# fresh must exist before we wire language intelligence into its config (FR-014).
have fresh || die "dotnet-lsp: the fresh editor is not installed — cannot provision LSP"

config="${HOME}/.config/fresh/config.json"
base_template="${DEVBOOST_ROOT}/modules/fresh-lsp/config.base.json"
csharp_ls="${HOME}/.dotnet/tools/csharp-ls"

# Seed the base config only if absent (editors/fresh-lsp or chezmoi may own it).
if [[ ! -f "${config}" ]]; then
  log_info "dotnet-lsp: seeding base config ${config}"
  mkdir -p "$(dirname "${config}")"
  cp "${base_template}" "${config}"
else
  log_skip "dotnet-lsp: base config already present (${config})"
fi

# Install the C# language server (csharp-ls) and formatter (csharpier) as global
# dotnet tools — each guarded by `command -v` for idempotency.
if have csharp-ls || [[ -x "${csharp_ls}" ]]; then
  log_skip "dotnet-lsp: csharp-ls already installed — skipping"
else
  log_info "dotnet-lsp: installing csharp-ls (dotnet tool install -g csharp-ls)"
  dotnet tool install -g csharp-ls
fi

if have csharpier; then
  log_skip "dotnet-lsp: csharpier already installed — skipping"
else
  log_info "dotnet-lsp: installing csharpier (dotnet tool install -g csharpier)"
  dotnet tool install -g csharpier
fi

# Wire csharp-ls into fresh's config using its absolute dotnet-tool path.
fresh_lsp_wire csharp "${csharp_ls}"

log_ok "dotnet-lsp: C# language intelligence provisioned"
