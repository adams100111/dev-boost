# lib/log.sh — logging + run summary. Source-only; no side effects.
if [[ -t 2 ]]; then
  _C_RED=$'\033[31m'; _C_GRN=$'\033[32m'; _C_YEL=$'\033[33m'
  _C_BLU=$'\033[34m'; _C_DIM=$'\033[2m'; _C_RST=$'\033[0m'
else
  _C_RED=; _C_GRN=; _C_YEL=; _C_BLU=; _C_DIM=; _C_RST=
fi

log_info()  { printf '%s[*]%s %s\n' "$_C_BLU" "$_C_RST" "$*" >&2; }
log_ok()    { printf '%s[+]%s %s\n' "$_C_GRN" "$_C_RST" "$*" >&2; }
log_warn()  { printf '%s[!]%s %s\n' "$_C_YEL" "$_C_RST" "$*" >&2; }
log_error() { printf '%s[x]%s %s\n' "$_C_RED" "$_C_RST" "$*" >&2; }
log_skip()  { printf '%s[=] %s%s\n' "$_C_DIM" "$*" "$_C_RST" >&2; }
die()       { log_error "$*"; exit 1; }

SUMMARY_STATUS=(); SUMMARY_NAME=(); SUMMARY_DETAIL=()
summary_reset() { SUMMARY_STATUS=(); SUMMARY_NAME=(); SUMMARY_DETAIL=(); }
summary_add() {
  SUMMARY_STATUS+=("$1"); SUMMARY_NAME+=("$2"); SUMMARY_DETAIL+=("${3:-}")
}
summary_print() {
  local i fails=0 sym
  printf '\n%s──── summary ────%s\n' "$_C_DIM" "$_C_RST" >&2
  for i in "${!SUMMARY_NAME[@]}"; do
    case "${SUMMARY_STATUS[$i]}" in
      ok)   sym="${_C_GRN}+${_C_RST}";;
      skip) sym="${_C_DIM}=${_C_RST}";;
      fail) sym="${_C_RED}x${_C_RST}"; fails=$((fails+1));;
      *)    sym="?";;
    esac
    printf '  [%s] %-22s %s\n' "$sym" "${SUMMARY_NAME[$i]}" "${SUMMARY_DETAIL[$i]}" >&2
  done
  [ "$fails" -eq 0 ]
}
