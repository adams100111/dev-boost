# Contract: `shell` environment modules

Escape-hatch modules sourcing `lib/log.sh`+`lib/pkg.sh`. `category="shell"`.

## starship
- `verify`: `command -v starship`. `requires=[]`.
- install: dnf (`sudo dnf install -y starship`) or the official installer fallback. Does
  NOT edit `~/.bashrc` — the init line lives in the chezmoi-managed rc (see dotfiles).

## ghostty
- `verify`: `command -v ghostty`. `requires=[]`.
- install: `sudo dnf copr enable -y scottames/ghostty` (add-if-absent) then `sudo dnf
  install -y ghostty`. Config applied via dotfiles. Ptyxis left as the GNOME fallback (not removed).

## nerd-fonts
- `verify`: `fc-list | grep -qi 'JetBrainsMono Nerd Font'` (and Meslo). `requires=[]`.
- install: download JetBrainsMono + Meslo Nerd Font Mono into `~/.local/share/fonts/`
  (idempotent: skip if present), then `fc-cache -f`. Document the Ptyxis `Mono` font gotcha
  in the ghostty/font config. Font URLs/versions pinned in the module.

## bash-config
- `requires=["dotfiles"]`. `verify`: the chezmoi-managed `~/.bashrc` is applied and
  contains the dev-boost sentinel + the init lines (single copy).
- Effectively a thin module asserting the rc landed (the actual apply is the `dotfiles`
  module). May be merged into `dotfiles` if cleaner — decide in tasks.

## Tests (`tests/shell.bats`, `tests/fonts.bats`) — stubbed dnf/copr/fc-list/fc-cache/curl
- starship: install + verify; idempotent.
- ghostty: copr enabled once (not re-added); install; verify; unsupported-OS reported.
- nerd-fonts: fonts downloaded+installed when absent; SKIPPED when `fc-list` already shows them; `fc-cache` run; verify maps to fc-list.
- bash-config: verify green only when rc applied with the init lines (single copy).
