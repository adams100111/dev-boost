# Reuse a Docker registry login as a git HTTPS credential (Forgejo/Gitea/self-hosted)

**When to use:** you need `git push`/`pull` over **HTTPS** to a self-hosted forge that shares a host
with its container registry (Forgejo, Gitea, GitLab, Harbor-fronted, …), **SSH is not exposed** there
(all SSH ports refused — common when the forge sits behind a 443-only reverse proxy / Cloudflare), and
you've **already `docker login`ed** to that host. Forge **access tokens authenticate both** the
container registry (docker) **and** git-over-HTTPS — so the token already sitting in Docker's config
can drive git, no new secret needed.

## The move

1. **Confirm SSH really is closed** (don't assume): `for p in 22 222 2222 2200; do timeout 6 bash -c "echo >/dev/tcp/<host>/$p" 2>/dev/null && echo "$p open" || echo "$p refused"; done`. All refused → HTTPS is the only path.

2. **Extract the token from Docker** (base64 of `user:token`), without echoing it:
   ```bash
   B64=$(python3 -c "import json;print(json.load(open('$HOME/.docker/config.json'))['auths']['<host>']['auth'])")
   CRED=$(printf '%s' "$B64" | base64 -d); USER_="${CRED%%:*}"; TOKEN_="${CRED#*:}"
   ```

3. **Store it for git** via the `store` helper and `credential approve` (writes `~/.git-credentials`;
   never put the token in a remote URL or on a command line):
   ```bash
   git config --global credential.helper store
   printf 'protocol=https\nhost=<host>\nusername=%s\npassword=%s\n\n' "$USER_" "$TOKEN_" | git credential approve
   ```
   - If a broken global helper is set (e.g. `manager` printing `'credential-manager' is not a git command`),
     replacing it with `store` is fine — **github.com keeps working** if it has its own host-scoped helper
     (`!/usr/bin/gh auth git-credential`) or its own `~/.git-credentials` entry. Verify: `git ls-remote <github-url>`.

4. **Test read then write:** `git ls-remote --heads https://<host>/<org>/<repo>.git` (uses the stored cred).
   Then push. A **403 on push** means the token is **package/registry-scoped only** — mint a token with
   **repository write** scope; read may still succeed while write fails.

## Caveats
- Needs a **repo-write-scoped** token; the docker-registry token often has it, but not always.
- `~/.git-credentials` is plaintext (same trust level as `~/.docker/config.json`, which already holds it).
- Pairs well with a **push fan-out** (`git remote set-url --add --push origin <url>` twice) so one
  `git push origin` reaches GitHub + the self-hosted forge; the forge leg uses this stored credential.

*Learned 2026-08-05 on the Innovation self-hosted-Forgejo cutover: `registry.innovation-lab.co` exposes
only HTTPS; the `innolb` docker token had repo write, so it drove the git fan-out to inno.*
