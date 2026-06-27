# dotfiles

Terminal developer environment — fully configured and ready to clone.

## Quick start

```bash
git clone <your-repo-url> ~/dotfiles
cd ~/dotfiles
chmod +x install.sh
./install.sh
source ~/.bashrc
```

Run `./install.sh --dry-run` first to preview all changes without touching anything.

---

## Tools

| Tool | What it is | Config |
|---|---|---|
| [starship](#starship) | Shell prompt | `starship/starship.toml` |
| [bash + fzf](#bash--fzf) | Shell + fuzzy finder | `bash/bashrc`, `bash/fzf.bash` |
| [eza](#eza) | Modern `ls` | aliases in `bash/bashrc` |
| [zoxide](#zoxide) | Smart `cd` | init in `bash/bashrc` |
| [bat](#bat) | Syntax-highlighted `cat` | `bat/config` |
| [fd](#fd) | Fast `find` | aliases in `bash/bashrc` |
| [ripgrep](#ripgrep) | Fast `grep` | `ripgrep/ripgreprc` |
| [tmux](#tmux) | Terminal multiplexer | `tmux/tmux.conf` |
| [delta](#delta) | Git diff pager | `git/gitconfig` |
| [lazygit](#lazygit) | TUI git client | `lazygit/config.yml` |
| [atuin](#atuin) | Shell history search | `atuin/config.toml` |
| [direnv](#direnv) | Per-directory env vars | init in `bash/bashrc` |
| [jq](#jq) | JSON processor | no config |
| [yq](#yq) | YAML/TOML processor | no config |
| [btop](#btop) | System monitor | `btop/btop.conf` |
| [tldr](#tldr) | Quick command reference | `tealdeer/config.toml` |
| [scp + rsync](#file-transfer-scp--rsync) | File transfer from/to VPS | no config |

---

## Starship

Fast, minimal shell prompt with git, language, and cloud context.

**Config:** `starship/starship.toml` → `~/.config/starship.toml`

**What shows in the prompt:**

```
~/projects/myapp  main !2 +1    node  python  aws  2.3s
[14:17] ❯
```

| Segment | Meaning |
|---|---|
| `~/path` | Current directory (truncated to 4 segments) |
| `main` | Git branch |
| `!2 +1` | 2 modified, 1 staged |
| Language icons | Auto-detected from project files |
| `2.3s` | Command duration (shown if >2s) |
| `[14:17]` | Current time |
| `❯` | Green = last command succeeded, red = failed |

**Theme:** Catppuccin Mocha

---

## Bash + fzf

**Config:** `bash/bashrc` → `~/.bashrc`, `bash/fzf.bash` → `~/.fzf.bash`

### fzf key bindings

| Key | Action |
|---|---|
| `Ctrl+T` | Fuzzy-find files, paste path at cursor (bat preview) |
| `Ctrl+R` | Fuzzy search command history |
| `Alt+C` | Fuzzy cd into a subdirectory (eza tree preview) |
| `Ctrl+/` | Toggle preview pane |
| `Ctrl+A` | Select all |

### fzf helper functions

| Function | Usage |
|---|---|
| `fcd [dir]` | Fuzzy cd into any subdirectory |
| `fe [query]` | Fuzzy-find and open file in `$EDITOR` |
| `fkill` | Fuzzy pick and kill a process |
| `fenv` | Fuzzy search environment variables |
| `fhistory` | Fuzzy history search and execute |

**Theme:** Catppuccin Mocha  
**Requires:** fd, bat, eza (for previews)

---

## eza

Modern replacement for `ls`. Icons, git status, tree views.

**Config:** aliases in `bash/bashrc`  
**Requires:** a Nerd Font in your terminal (JetBrains Mono Nerd Font recommended)

### Aliases

| Alias | Command |
|---|---|
| `ls` / `l` | Icons + directories first |
| `la` | Same + hidden files |
| `ll` | Long list with git status column |
| `lla` | Long list + hidden files |
| `lls` | Long list sorted by size |
| `llm` | Long list sorted by last modified |
| `lt` | Tree view, 2 levels |
| `lta` | Tree view + hidden files |
| `lt3` | Tree view, 3 levels |
| `lT` | Full tree |

---

## zoxide

Smart `cd` that learns your most-visited directories.

**Config:** `eval "$(zoxide init bash --cmd cd)"` in `bash/bashrc`

### Commands

| Command | Action |
|---|---|
| `cd foo` | Jump to best frecency match for `foo` |
| `cd foo bar` | Match path containing both `foo` and `bar` |
| `cdi` | Interactive fuzzy picker of known dirs |
| `builtin cd` | Bypass zoxide, use real `cd` |

> The more you use it, the smarter it gets. After a week it replaces nearly all manual path navigation.

---

## bat

Syntax-highlighted, line-numbered `cat` with git change markers.

**Config:** `bat/config` → `~/.config/bat/config`  
**Theme:** Dracula  
**Style:** full (filename header + line numbers + git change markers)

### Aliases

| Alias | Action |
|---|---|
| `cat <file>` | Drop-in replacement, no pager |
| `catp <file>` | With paging (`less`) |
| `batd <file>` | Show only changed lines |
| `bh <file>` | Plain output, no decorations (pipe-safe) |
| `man <cmd>` | Man pages with syntax highlighting |

### Key flags

```bash
bat --language python file.txt   # force language
bat --style=numbers file.txt     # line numbers only
bat --plain file.txt             # no decorations
bat -A file.txt                  # show non-printable chars
```

---

## fd

Fast, intuitive `find` replacement. Respects `.gitignore` by default.

**Config:** aliases in `bash/bashrc`  
**Ubuntu note:** installed as `fdfind`, symlinked to `~/.local/bin/fd`

### Aliases

| Alias | Action |
|---|---|
| `fd <pattern>` | Find files/dirs matching pattern |
| `fdf <pattern>` | Files only |
| `fdd <pattern>` | Directories only |
| `fdh <pattern>` | Include hidden files |
| `fdg <pattern>` | Include `.gitignore`d files |
| `fdx <pattern>` | Executables only |

### Useful patterns

```bash
fd -e py                         # by extension
fd --changed-within 1d           # modified in last day
fd -t f -x bat {}                # open all results in bat
fd -t f | fzf                    # pipe into fzf
```

---

## ripgrep

Fast grep with sane defaults. Respects `.gitignore`, skips binaries.

**Config:** `ripgrep/ripgreprc` → `~/.config/ripgrep/ripgreprc`

**Defaults applied by config:**
- Smart case (case-insensitive unless uppercase used)
- Line numbers + grouped headings
- Skips: `node_modules/`, `dist/`, `build/`, `target/`, lockfiles, sourcemaps

### Aliases

| Alias | Action |
|---|---|
| `rg <pattern>` | Search with all defaults |
| `rga <pattern>` | Search everything (ignored + hidden) |
| `rgl <pattern>` | List matching filenames only |
| `rgf <pattern>` | Literal search (no regex) |
| `rgc <pattern>` | Count matches per file |
| `rgt <type> <pat>` | Search by file type: `rgt py def` |
| `rgi <pattern>` | Force case-insensitive |
| `fzrg [pattern]` | Interactive: results in fzf with bat preview, `Enter` opens in `$EDITOR` |

### Useful patterns

```bash
rg 'def.*login'                  # regex search
rg -t py 'import'                # Python files only
rg -l 'TODO'                     # files with TODOs
rg --stats 'error'               # show match stats
rg -A 3 -B 3 'pattern'          # 3 lines context
rg -U 'start.*\n.*end'          # multiline match
```

---

## tmux

Terminal multiplexer — sessions, windows, panes. Persists across disconnects.

**Config:** `tmux/tmux.conf` → `~/.config/tmux/tmux.conf`  
**Prefix key:** `C-a` (Ctrl+A)  
**Theme:** Catppuccin Mocha (no plugins needed)

### Sessions

| Command/Key | Action |
|---|---|
| `ts [name]` | Attach to session or create it (default: `main`) |
| `tdev [name]` | 3-pane dev layout (editor + sidebar + terminal) |
| `ta <name>` | Attach to named session |
| `tl` | List all sessions |
| `tk <name>` | Kill named session |
| `td` | Detach |
| `C-a C-s` | Pick a session interactively |
| `C-a X` | Kill current session (with confirmation) |

### Windows

| Key | Action |
|---|---|
| `C-a c` | New window (inherits current dir) |
| `C-a ,` | Rename window |
| `C-a [` / `]` | Previous / next window |
| `C-a Tab` | Last window |
| `C-a <` / `>` | Move window left / right |

### Panes

| Key | Action |
|---|---|
| `C-a \|` | Split vertical |
| `C-a -` | Split horizontal |
| `C-a h/j/k/l` | Navigate panes (vim keys) |
| `C-a H/J/K/L` | Resize pane |
| `C-a z` | Zoom / unzoom pane |

### Copy mode (vi)

| Key | Action |
|---|---|
| `C-a Esc` | Enter copy mode |
| `v` | Begin selection |
| `V` | Select line |
| `y` | Yank to clipboard |
| `C-a p` | Paste |

### Other

| Key | Action |
|---|---|
| `C-a r` | Reload config |
| `F12` | Toggle prefix off (for nested tmux over SSH) |

---

## delta

Syntax-highlighted pager for `git diff`, `git log`, `git show`, `git blame`.

**Config:** `git/gitconfig` → `~/.gitconfig`  
**Theme:** Catppuccin Mocha + Dracula syntax  
Activated automatically — no extra commands needed.

### Key features

- Side-by-side diff available: set `side-by-side = true` in `git/gitconfig`
- Press `n` / `N` to jump between diff sections (`navigate = true`)
- Hyperlinks from file paths to your editor

### git aliases worth adding

```bash
git log --oneline --graph        # visual branch history
git diff HEAD~1                  # diff vs last commit
git show HEAD:path/to/file       # show file at commit
```

---

## lazygit

Full TUI git client. Branches, staging, rebasing, stashing — all keyboard-driven.

**Config:** `lazygit/config.yml` → `~/.config/lazygit/config.yml`  
**Launch:** `lg`  
**Theme:** Catppuccin Mocha

### Panel layout

```
┌─────────────┬──────────────────────────────────┐
│  Status     │                                  │
├─────────────┤         Diff / content           │
│  Files      │                                  │
├─────────────┤                                  │
│  Branches   ├──────────────────────────────────┤
├─────────────┤                                  │
│  Commits    │         Command log              │
├─────────────┤                                  │
│  Stash      │                                  │
└─────────────┴──────────────────────────────────┘
```

### Key bindings

| Key | Action |
|---|---|
| `Tab` | Switch panel |
| `space` | Stage / unstage file |
| `c` | Commit |
| `P` | Push |
| `p` | Pull |
| `b` | Branches panel |
| `s` | Squash commit |
| `r` | Reword commit |
| `R` | Rename commit (interactive rebase) |
| `g` | Reset options |
| `?` | Help / all keybindings |
| `q` | Quit |

---

## atuin

Replaces shell history with a searchable SQLite database. Tracks duration, exit code, directory, and host.

**Config:** `atuin/config.toml` → `~/.config/atuin/config.toml`

### Usage

| Key / Command | Action |
|---|---|
| `Ctrl+R` | Open atuin TUI search |
| `↑` arrow | Search history filtered to current directory |
| `atuin stats` | Show your most-used commands |
| `atuin history list` | List all history |
| `atuin search <query>` | Non-interactive search |

### Search TUI controls

| Key | Action |
|---|---|
| Type | Fuzzy filter |
| `↑` / `↓` | Navigate results |
| `Enter` | Execute selected command |
| `Tab` | Copy to prompt for editing |
| `Ctrl+R` | Cycle filter modes (global → host → session → directory) |
| `Esc` | Cancel |

### Config highlights

- **Search mode:** fuzzy
- **Up-arrow filter:** directory (only shows commands run here)
- **Secrets filter:** commands with `--password`, `--token`, `--secret`, `export *KEY=` are never stored
- **Sync:** disabled (offline-only; enable and create an account at atuin.sh to sync across machines)

---

## direnv

Automatically loads and unloads environment variables when you `cd` into a directory.

**Config:** `eval "$(direnv hook bash)"` in `bash/bashrc`

### Usage

```bash
# In any project directory:
echo 'export DATABASE_URL=postgres://localhost/mydb' > .envrc
direnv allow          # approve the .envrc (once)

# Now DATABASE_URL is set when you're in this dir
# and unset when you leave — automatically
```

### Useful `.envrc` patterns

```bash
# Load a .env file
dotenv

# Add local bin to PATH
PATH_add bin

# Set project-specific vars
export NODE_ENV=development
export API_BASE_URL=http://localhost:3000

# Use a specific Python virtualenv
source venv/bin/activate
```

---

## jq

JSON processor for the command line.

**Config:** none

### Common patterns

```bash
jq '.'                           # pretty-print
jq '.name'                       # extract key
jq '.users[0]'                   # array index
jq '.[] | .name'                 # iterate array
jq 'select(.active == true)'     # filter
jq '{name, email}'               # project fields
jq -r '.token'                   # raw string (no quotes)
jq -c '.'                        # compact (one line)
jq --arg val "foo" '.key=$val'   # pass shell var
jq -s '.[0] * .[1]'             # merge two JSON files

# With ripgrep
rg -l 'error' | xargs -I{} jq '.errors' {}
```

---

## yq

Like `jq` but for YAML, TOML, and JSON. Uses the same path syntax.

**Config:** none  
**Version:** v4 (incompatible with v3 — this install is v4)

### Common patterns

```bash
yq '.name' file.yaml             # extract key
yq '.services.web.image' docker-compose.yml
yq -i '.version = "2.0"' file.yaml   # in-place edit
yq -o json file.yaml             # convert YAML → JSON
yq -P file.json                  # convert JSON → YAML (pretty)
yq 'del(.debug)' file.yaml       # delete key
yq '.items[] | select(.enabled)' file.yaml
```

---

## btop

Resource monitor — CPU, memory, disk, network, processes.

**Config:** `btop/btop.conf` → `~/.config/btop/btop.conf`  
**Launch:** `btop`

### Config highlights

| Setting | Value | Why |
|---|---|---|
| `vim_keys` | `True` | h/j/k/l navigation in process list |
| `update_ms` | `1500` | Refresh every 1.5s (snappier than default 2s) |
| `graph_symbol` | `braille` | Highest resolution graphs (requires Nerd Font) |
| `rounded_corners` | `True` | Matches rest of the terminal theme |
| `proc_sorting` | `cpu lazy` | Stable top-process ordering |
| `truecolor` | `True` | 24-bit colour |

### Controls

| Key | Action |
|---|---|
| `h` / `?` | Help |
| `q` | Quit |
| `Esc` | Close menu / cancel |
| `j` / `k` | Navigate processes (vim keys enabled) |
| `f` | Filter processes |
| `K` | Kill selected process |
| `m` | Cycle memory display |
| `e` | Toggle disk tree |
| `F2` | Options menu |
| `1`–`4` | Toggle CPU / mem / net / proc boxes |
| `b` | Select network interface |

---

## tldr

Practical, community-maintained command examples. Faster than `man` for quick lookups.

**Config:** `tealdeer/config.toml` → `~/.config/tealdeer/config.toml`  
**Alias:** `help` → `tldr`

### Config highlights

| Setting | Value | Why |
|---|---|---|
| `auto_update` | `true` | Cache refreshes automatically every 30 days |
| `compact` | `false` | Blank lines between sections for readability |
| `use_pager` | `false` | Output directly to terminal, no less |

### Usage

```bash
help git              # git examples
help tar              # tar examples
help docker           # docker examples
help curl             # curl examples
tldr --update         # manually refresh cache
tldr --list           # list all available pages
tldr --render file    # render a local tldr page
```

---

## File transfer: scp + rsync

Both are installed by `install.sh` via `openssh-client` and `rsync` packages.  
Run all commands below **on your local machine**, not the server.

### Find your server details (run on server)

```bash
whoami && curl -s ifconfig.me
# → ubuntu   203.0.113.42
```

### scp — simple one-off transfer

```bash
# Download a file from server
scp user@server-ip:~/dotfiles.zip ~/Downloads/

# Download a whole directory
scp -r user@server-ip:~/dotfiles ~/Downloads/

# Upload a file to server
scp ~/file.txt user@server-ip:~/

# With a key file
scp -i ~/.ssh/id_rsa user@server-ip:~/dotfiles.zip ~/Downloads/
```

### rsync — preferred for directories and repeated syncs

```bash
# Download (server → local), show progress
rsync -avz --progress user@server-ip:~/dotfiles ~/Downloads/

# Upload (local → server)
rsync -avz --progress ~/dotfiles user@server-ip:~/

# With a key file
rsync -avz --progress -e "ssh -i ~/.ssh/id_rsa" user@server-ip:~/dotfiles ~/Downloads/

# Sync only changed files, delete files removed on source
rsync -avz --delete user@server-ip:~/project ~/local/project
```

### Flags reference

| Flag | Meaning |
|---|---|
| `-a` | Archive mode — preserves permissions, timestamps, symlinks |
| `-v` | Verbose output |
| `-z` | Compress during transfer |
| `--progress` | Show per-file progress |
| `--delete` | Delete destination files not in source |
| `-n` / `--dry-run` | Preview what would be transferred |
| `-e "ssh -p 2222"` | Use custom SSH port |

### Distro package names

| Distro | scp package | rsync package |
|---|---|---|
| Ubuntu / Debian | `openssh-client` | `rsync` |
| Fedora / RHEL | `openssh-clients` | `rsync` |
| Arch Linux | `openssh` | `rsync` |
| macOS | built-in | `brew install rsync` |

---

## Nerd Font

All icon glyphs (used by starship, eza, lazygit, tmux) require a Nerd Font in your **local terminal emulator**.

**Recommended:** JetBrains Mono Nerd Font

### Install on macOS

```bash
brew install --cask font-jetbrains-mono-nerd-font
```

### Install on Windows

Download from [nerdfonts.com](https://www.nerdfonts.com/font-downloads) → search JetBrainsMono → install the `.ttf` files.

### Install on Linux (desktop)

```bash
mkdir -p ~/.local/share/fonts
cd ~/.local/share/fonts
curl -sLO "https://github.com/ryanoasis/nerd-fonts/releases/latest/download/JetBrainsMono.tar.xz"
tar -xf JetBrainsMono.tar.xz
fc-cache -fv
```

After installing, set `JetBrainsMono Nerd Font Mono` as your terminal font.

---

## File map

```
dotfiles/
├── install.sh                    # bootstrap script
├── README.md                     # this file
├── bash/
│   ├── bashrc                    → ~/.bashrc
│   └── fzf.bash                  → ~/.fzf.bash
├── starship/
│   └── starship.toml             → ~/.config/starship.toml
├── bat/
│   └── config                    → ~/.config/bat/config
├── ripgrep/
│   └── ripgreprc                 → ~/.config/ripgrep/ripgreprc
├── tmux/
│   └── tmux.conf                 → ~/.config/tmux/tmux.conf
├── git/
│   ├── gitconfig                 → ~/.gitconfig
│   └── delta-themes.gitconfig    → ~/.config/delta/themes.gitconfig
├── lazygit/
│   └── config.yml                → ~/.config/lazygit/config.yml
├── atuin/
│   └── config.toml               → ~/.config/atuin/config.toml
├── btop/
│   └── btop.conf                 → ~/.config/btop/btop.conf
└── tealdeer/
    └── config.toml               → ~/.config/tealdeer/config.toml
```
