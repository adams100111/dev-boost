# lib/fresh.sh — fresh-editor LSP/formatter provisioning helper.
# Source-only; no side effects on source. Depends on lib/log.sh (die/log_*).
# All external commands (mise, jq) are PATH-stubbable in tests.
#
# Reused by the `fresh-lsp` module (always-on base set) and, later, by each
# dev-stacks per-stack module (Spec 7) — so adding a language server is one call.

# ---------------------------------------------------------------------------
# fresh_lsp_provision <lang> <fresh-command> <backend:tool@pin> [args…]
#   1. Install the server/formatter as a mise-managed, version-pinned tool
#      (`mise use -g <backend:tool@pin>`) — provisions the tool AND its runtime.
#   2. Resolve the binary to an ABSOLUTE path via `mise which <fresh-command>`
#      (PATH-independent — fresh need not have mise shims on PATH at launch).
#   3. jq-merge `{lsp:{<lang>:{command,args,enabled:true}}}` into
#      ~/.config/fresh/config.json, PRESERVING every other key (theme, editor,
#      formatter, other lsp.*). Idempotent: re-running yields an identical file.
#
#   `die`s (naming the tool) if mise cannot resolve the command, or if the
#   config file is missing.
# ---------------------------------------------------------------------------
fresh_lsp_provision() {
  local lang="$1" cmd="$2" spec="$3"; shift 3
  local -a extra_args=("$@")

  log_info "fresh-lsp: provisioning ${lang} → ${spec}"

  # 1. Install via mise (idempotent; the @pin makes it reproducible).
  mise use -g "${spec}" || die "fresh-lsp: 'mise use -g ${spec}' failed (${lang})"

  # 2. Resolve the absolute command path.
  local abs
  abs="$(mise which "${cmd}" 2>/dev/null)" \
    || die "fresh-lsp: could not resolve '${cmd}' via mise (tool ${spec})"
  [[ -n "${abs}" ]] || die "fresh-lsp: empty path resolving '${cmd}' (tool ${spec})"

  # 3. jq-merge the lsp entry, preserving all other config keys.
  local config="${HOME}/.config/fresh/config.json"
  [[ -f "${config}" ]] || die "fresh-lsp: config not found: ${config}"

  # Build a JSON array from the (possibly --dash-leading) argv slice without
  # relying on `jq --args` option parsing (which would mistake "--stdio" for a flag).
  local argsjson='[]'
  if [[ ${#extra_args[@]} -gt 0 ]]; then
    argsjson="$(printf '%s\n' "${extra_args[@]}" | jq -R . | jq -s .)"
  fi

  local tmp
  tmp="$(mktemp)" || die "fresh-lsp: mktemp failed"
  jq --arg lang "${lang}" --arg cmd "${abs}" --argjson args "${argsjson}" \
     '.lsp = (.lsp // {}) | .lsp[$lang] = {command: $cmd, args: $args, enabled: true}' \
     "${config}" > "${tmp}" \
    || { rm -f "${tmp}"; die "fresh-lsp: jq merge failed for ${lang}"; }
  mv "${tmp}" "${config}" \
    || { rm -f "${tmp}"; die "fresh-lsp: could not write ${config}"; }
}
