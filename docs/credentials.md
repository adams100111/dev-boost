# Credentials — how `secrets` gets git identity and GitHub access

Applies to **every OS**, not just Omarchy.

The `secrets` module configures `git config --global user.name/user.email` and gives
dev-boost a GitHub token, which `ssh-setup` (registers your SSH key), `chezmoi-repo`
(clones your personal dotfiles) and `obsidian-sync` (vault deploy key) then use.

## Where credentials come from

Four sources, in order of decreasing automation. The first that yields a complete set wins.

| # | Source | When it applies |
|---|---|---|
| 1 | The `age`-encrypted bundle | Provisioned on the USB — the zero-touch path |
| 2 | An authenticated `gh` | Offered as the default choice at a terminal; used directly when unattended |
| 3 | An interactive choice | Only when a real TTY is attached |
| 4 | An error naming the options | Nothing available, and nobody to ask |

### 1. The bundle — zero-touch

A Ventoy/Kickstart install has nobody at the keyboard, so `GIT_USER`, `GIT_EMAIL` and
`GITHUB_PAT` are pre-provisioned once as encrypted JSON and decrypted at firstboot.

```bash
scripts/make-secrets.sh --out DIR     # writes secrets.age + age-key.txt, both 0600
```

dev-boost looks for them in `$DEVBOOST_BOOTSTRAP_DIR`, else `/opt/dev-boost` (the path the
Kickstart `%post` copies to). `$DEVBOOST_SECRETS` / `$DEVBOOST_SECRETS_KEY` override the
individual files. This still takes precedence over everything below, so **zero-touch
behaviour is unchanged** — a provisioned box never reaches the fallbacks.

On a machine you installed yourself, keep the bundle under `$HOME`:

```bash
scripts/make-secrets.sh --out ~/.config/devboost/bootstrap
export DEVBOOST_BOOTSTRAP_DIR=~/.config/devboost/bootstrap
```

`/opt/dev-boost` is right for firstboot because that runs as root; you run `devboost` as
yourself, and a root-owned `0600` private key would be unreadable.

### 2 & 3. No bundle — the fallbacks

Requiring an encrypted bundle from somebody who installed the OS by hand and just wants to
run `devboost install` is friction with nothing to show for it: there is no USB, no
`/opt/dev-boost`, and no reason to encrypt anything to supply an email address. That case
used to be a hard `SecretsError` plus three blocked modules.

At a terminal with `gh` already signed in:

```
? GitHub CLI is already signed in as octocat. How should dev-boost set up git + GitHub?
❯ Use the signed-in GitHub account (octocat)
  Sign in as a different GitHub account
  Enter name, email and a personal access token myself
  Skip — configure git credentials later
```

Without a `gh` session the first row becomes *Sign in with GitHub CLI*, which installs
`gh` if needed and hands it the terminal.

The signed-in session is **offered, never assumed.** The `gh` account on a machine is
frequently not the one that box should commit as, and adopting it silently would write the
wrong name and email into every commit — invisible until somebody read the git log.
Choosing *Skip* is respected, not quietly overridden by the session just offered.

Signing in through this menu also runs `gh auth setup-git`, so git authenticates through
`gh` rather than a plaintext token in `~/.git-credentials`.

### 4. Nothing available

`secrets` fails with a message naming each option, and the three dependent modules are
reported as `blocked`. Every other module still installs — this is not a fatal run.

## Unattended runs never block

This is the property that keeps the zero-touch promise intact:

- Prompting requires **both** stdin and stdout to be a TTY.
- `DEVBOOST_NONINTERACTIVE=1` forces prompting off — use it in CI, or to reproduce an
  unattended run on a workstation.
- A firstboot service or `curl … | bash` therefore reaches step 4 and fails with an
  actionable message rather than hanging on a prompt nobody can answer. Where `gh` happens
  to be signed in, it is used directly, since that beats failing outright.

## What `verify()` accepts

Either credential source counts as configured:

- a `@github.com` line in `~/.git-credentials`, **or**
- an authenticated `gh`.

A box set up through `gh auth setup-git` deliberately has no plaintext token on disk.
Demanding the `.git-credentials` line would report that correctly configured machine as
broken and reinstall over it on every run.

## Token handling

- The PAT is never printed or logged; `make-secrets.sh` reads it silently and the
  interactive prompt masks it.
- When dev-boost holds a token it writes `~/.git-credentials` at `0600` — that is inherent
  to git's `credential.helper store`, and it is what `git clone` over HTTPS and the REST
  API calls in `ssh-setup` / `obsidian-sync` consume.
- Prefer a **fine-grained** PAT scoped to the repositories you need, not a classic token
  with blanket `repo` scope.
- `ssh-setup` exists so day-to-day pushes use your SSH key rather than the token.
