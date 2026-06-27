# fzf shell integration
# ──────────────────────────────────────────────────────────────────────────────

# PATH
[[ ":$PATH:" != *":/home/ubuntu/.fzf/bin:"* ]] && PATH="${PATH:+${PATH}:}/home/ubuntu/.fzf/bin"

# ── Theme (Catppuccin Mocha) ───────────────────────────────────────────────────
export FZF_DEFAULT_OPTS=" \
  --color=bg+:#313244,bg:#1e1e2e,spinner:#f5e0dc,hl:#f38ba8 \
  --color=fg:#cdd6f4,header:#f38ba8,info:#cba6f7,pointer:#f5e0dc \
  --color=marker:#b4befe,fg+:#cdd6f4,prompt:#cba6f7,hl+:#f38ba8 \
  --color=selected-bg:#45475a \
  --multi \
  --height=50% \
  --layout=reverse \
  --border=rounded \
  --border-label=' fzf ' \
  --preview-window=right:55%:wrap \
  --bind='ctrl-/:toggle-preview' \
  --bind='ctrl-y:execute-silent(echo -n {+} | xclip -selection clipboard 2>/dev/null || echo -n {+} | pbcopy 2>/dev/null)' \
  --bind='ctrl-a:select-all' \
  --bind='ctrl-d:deselect-all'"

# ── Default command (use fd if available) ─────────────────────────────────────
if command -v fd &>/dev/null; then
  export FZF_DEFAULT_COMMAND='fd --type f --hidden --follow --exclude .git --exclude node_modules --exclude .cache'
  export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"
  export FZF_ALT_C_COMMAND='fd --type d --hidden --follow --exclude .git --exclude node_modules --exclude .cache'
fi

# ── Preview with bat if available ─────────────────────────────────────────────
if command -v bat &>/dev/null; then
  export FZF_CTRL_T_OPTS="
    --preview 'bat --color=always --style=numbers,changes --line-range=:300 {}'
    --bind 'ctrl-/:change-preview-window(hidden|)'"
fi

export FZF_ALT_C_OPTS="
  --preview 'eza --icons --tree --level=2 --color=always {}'
  --bind 'ctrl-/:change-preview-window(hidden|)'"

export FZF_CTRL_R_OPTS="
  --preview 'echo {}' --preview-window=down:3:wrap
  --bind 'ctrl-/:toggle-preview'
  --bind 'ctrl-y:execute-silent(echo -n {2..} | xclip -selection clipboard 2>/dev/null)+abort'
  --color header:italic
  --header 'CTRL-Y: copy command'"

# ── Key bindings and completion ────────────────────────────────────────────────
eval "$(fzf --bash)"

# ── Helper functions ───────────────────────────────────────────────────────────

# fcd — fuzzy cd into any subdirectory
fcd() {
  local dir
  dir=$(fd --type d --hidden --follow --exclude .git --exclude node_modules . "${1:-.}" 2>/dev/null \
    | fzf --preview 'eza --icons --tree --level=2 --color=always {}') \
  && cd "$dir"
}

# fe — fuzzy open file in $EDITOR
fe() {
  local files
  IFS=$'\n' files=($(fzf --multi --preview 'bat --color=always --style=numbers {}' ${1:+--query="$1"})) \
  && "${EDITOR:-vim}" "${files[@]}"
}

# fkill — fuzzy kill process
fkill() {
  local pid
  pid=$(ps aux | tail -n +2 | fzf --multi | awk '{print $2}')
  [[ -n "$pid" ]] && echo "$pid" | xargs kill -"${1:-9}"
}

# fenv — fuzzy search env vars
fenv() {
  env | sort | fzf --preview 'echo {}' --preview-window=down:1
}

# fhistory — fuzzy history search (execute selected)
fhistory() {
  local cmd
  cmd=$(history | sort -rn | sed 's/^ *[0-9]* *//' | awk '!seen[$0]++' \
    | fzf --tac --no-sort --preview 'echo {}' --preview-window=down:3:wrap)
  [[ -n "$cmd" ]] && history -s "$cmd" && eval "$cmd"
}
