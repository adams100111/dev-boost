# Configuration

dev-boost runs with no configuration at all. Everything here is opt-in, and it exists
because some things cannot have a sensible default: a personal repo, a device name, a
container runtime you prefer.

Two places hold it:

| | |
|---|---|
| `~/.config/devboost/config.toml` | choices you make once per account |
| `DEVBOOST_*` environment variables | per-run overrides, and everything a CI job needs |

**An environment variable always wins over the file.** `$XDG_CONFIG_HOME` moves the file
if it is set.

> Unknown keys in the file are ignored rather than rejected, so a typo silently falls back
> to the default. If something you set appears to have no effect, check the spelling
> against the table below first.

## `config.toml`

```toml
# ~/.config/devboost/config.toml

# Where your `pass` store lives. No default: see docs/pass.md.
pass_repo = "<owner>/<repo>"

# This machine's name in the pass store's device list. Default: the hostname.
device_name = "my-laptop"

# colima | orbstack | docker-desktop. Default: colima. See docs/docker-runtimes.md.
docker_runtime = "colima"

# Extra Claude/Codex plugin marketplaces, name -> "owner/repo".
# Private or personal marketplaces belong here, never in the shipped defaults.
extra_marketplaces = { my-market = "owner/repo" }

# Extra plugins to enable, each "plugin@marketplace".
extra_plugins = ["my-plugin@my-market"]
```

| Key | Default | Notes |
|---|---|---|
| `pass_repo` | *(none)* | Falls back to the `origin` of an existing `~/.password-store` clone; if that is absent too, `pass-store` reports **blocked** rather than guessing |
| `device_name` | hostname | Lower-cased, `[a-z0-9-]` only — it becomes a file name in the store |
| `docker_runtime` | `colima` | Switch later with `devboost docker use <runtime>` |
| `extra_marketplaces` | `{}` | Yours **wins a name clash** with a shipped marketplace, so you can point one at your own fork |
| `extra_plugins` | `[]` | Appended after the shipped list; duplicates are ignored |

`devboost docker use` rewrites this file wholesale, so comments you add by hand do not
survive a runtime switch.

## Environment variables

### Everyday

| Variable | Does |
|---|---|
| `DEVBOOST_PASS_REPO` | Beats `pass_repo` |
| `DEVBOOST_DOCKER_RUNTIME` | Beats `docker_runtime`; refused by `devboost docker use` when the two disagree, rather than switching a runtime later commands will not drive |
| `DEVBOOST_DOTFILES_REPO` | Your **personal** dotfiles repo for `chezmoi-repo`. Optional: dev-boost's own dotfiles do not need it. May also come from the secrets bundle as `DOTFILES_REPO` |
| `DEVBOOST_HARNESS_REPO`, `DEVBOOST_HARNESS_REF` | Source for `pi-harness`. No default; unset means the module reports **blocked**. A full git URL is used as given |
| `DEVBOOST_NONINTERACTIVE` | Force the unattended path — no prompts, and anything needing a human is reported `blocked` |
| `DEVBOOST_NO_UPDATE_CHECK` | Skip the release check on start-up |
| `DEVBOOST_SECRETS`, `DEVBOOST_SECRETS_KEY` | The secrets bundle and its key |

### Release and delivery

| Variable | Does |
|---|---|
| `DEVBOOST_RELEASE_BASE` | Fetch the binary from somewhere other than the official release. `get.sh` warns loudly when set: the binary **and** the checksums that vouch for it would both come from that same place |
| `DEVBOOST_RELEASE_EMERGENCY` | Lets `release.sh` publish while `release.yml` is the canonical path. Emergency only |

### Notifications

`DEVBOOST_NTFY_URL`, `DEVBOOST_HERDR_TELEGRAM_TOKEN`, `DEVBOOST_HERDR_TELEGRAM_CHAT_ID` —
unset means the notifier stays unconfigured, which is a warning, never a failure.

### Test seams

`DEVBOOST_BOOTSTRAP_DIR`, `DEVBOOST_DNF_CONF`, `DEVBOOST_DNF_AUTOMATIC_CONF`,
`DEVBOOST_DOCKER_DAEMON_JSON`, `DEVBOOST_EARLYOOM_CONF`, `DEVBOOST_FSTAB`,
`DEVBOOST_PASS_HOOK`, `DEVBOOST_SWAPFILE_PATH`, `DEVBOOST_SYSTEMD_SYSTEM_DIR`,
`DEVBOOST_ORCA_*` redirect a system path or pin a version so the tests never touch the
real machine. Not meant for everyday use.

## `~/.ssh/config` — the managed block

`ssh-setup` writes one delimited block into `~/.ssh/config`. Everything outside the
markers is yours and is never touched; the block itself is replaced wholesale on every
run, so a re-run upgrades a machine installed by an older dev-boost.

```
# BEGIN devboost-managed
Host *
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
  AddKeysToAgent yes
  HashKnownHosts yes
  ServerAliveInterval 30
  ServerAliveCountMax 10
  TCPKeepAlive yes
# END devboost-managed
```

| Setting | Why |
|---|---|
| `IdentityFile` / `IdentitiesOnly` | Offer the dev-boost key and only that key, so a full agent does not exhaust the server's auth-tries limit. |
| `AddKeysToAgent` | Unlock the key once per session instead of once per connection. |
| `HashKnownHosts` | `known_hosts` stops being a readable list of every host you reach. |
| `ServerAliveInterval` / `ServerAliveCountMax` / `TCPKeepAlive` | Keep a long, quiet session from being dropped by NAT or a stateful firewall. |

The keepalive matters more than it looks. `docker buildx` reaches a **remote builder** by
shelling out to `ssh … docker system dial-stdio`, and that stream sits idle for as long as
the compile takes. A 25-minute build survives without keepalive; an 80-minute one dies
with `client_loop: send disconnect: Broken pipe` *after* the work is finished, and the
build is lost. One packet every 30s removes the whole class of failure.

Since `Host *` supplies these as defaults, a per-host block in your own config still wins
— SSH takes the first value it sees for a keyword, and your entries come first.

## What dev-boost never assumes

It ships **no personal defaults**. Everything below is reachable by anyone who installs
it, and anything private is yours to configure:

- **no default `pass` repo** — it is discovered from an existing clone, or asked for
- **no default harness repo** — `pi-harness` is blocked until you name one
- **every shipped plugin marketplace is public** — private ones go in
  `extra_marketplaces`

A personal repo as a built-in fallback makes every other install try to clone something it
cannot read, and report a failed clone instead of an explanation.
