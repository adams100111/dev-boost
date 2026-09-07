# Headed browser on `mate-fedora` (drive from `hp` via SSH + Chrome CDP)

**Scope:** use this ONLY when the user wants a **VISIBLE browser they can watch / log into** on
the `mate-fedora` machine (its physical Wayland desktop) while you drive it from `hp`. For headless
automation just launch a local browser instead — this recipe exists specifically so the browser
appears on the user's screen and keeps its login/cookies between runs.

## The machines
- **`hp`** — this machine (Tailscale `100.121.150.49`). Where you run tools; where the CDP tunnel lands.
- **`mate-fedora`** — SSH alias for the remote desktop box. `ssh mate-fedora` reaches it:
  - HostName `100.79.147.36` (Tailscale) · User `dev` · IdentityFile `~/.ssh/id_rsa` · IdentitiesOnly `yes`.
  - Remote hostname `mate`, **Fedora**, **Wayland** desktop. `google-chrome` at `/usr/bin/google-chrome`.
  - Graphical session env: `XDG_RUNTIME_DIR=/run/user/1000`, `WAYLAND_DISPLAY=wayland-0`.
  - (Sibling alias `my-dev` → `130.110.127.90`, unrelated.)

## Gotchas (all painfully learned — read before running anything)

1. **Tailscale SSH interactive auth.** The first `ssh mate-fedora` may print
   `Tailscale SSH requires an additional check. To authenticate, visit: https://login.tailscale.com/a/…`
   and **hang** until a human opens that URL and approves. `BatchMode=yes` does NOT fix it — it is a
   Tailscale check, not a key problem. The box is reachable (TCP :22 open); if ssh "times out," this
   is almost always why. When the user is actively using the link, it's already approved.

2. **`pkill -f` self-match → SSH exit 255 with NO output.** `pkill -f "<pattern>"` matches the FULL
   command line of *every* process, **including the remote shell ssh is running**. If a single ssh
   command string contains both the launch `pkill "<pattern>"` AND a verify step that also mentions
   `<pattern>` (e.g. `pgrep -af "<pattern>"` or `curl …9222…`), the pkill kills its own parent shell
   → the whole ssh returns **255 and prints nothing**. FIX: (a) run the launch (which does the pkill)
   in its OWN ssh call whose argv does NOT contain the kill pattern; (b) do process/CDP verification
   in a SEPARATE later ssh call; (c) pick a kill token that does not appear in the launcher's own
   path/argv.

3. **CDP tunnel from `hp` needs the sandbox disabled.** The tunnel binds a LOCAL listener, which the
   Bash tool's sandbox blocks — a plain `ssh -fN -L …` dies with **exit 144 and no listener**. FIX:
   start the tunnel as a **tracked background** Bash process with `run_in_background: true` AND
   `dangerouslyDisableSandbox: true` (do NOT background it with a trailing `&`; let the tool track it).

4. Ignore the harmless `wayland_surface_factory … not compatible with Vulkan` stderr from Chrome.

## End-to-end sequence (copy-pasteable)

Pick a `<name>` (profile/log prefix) and a `<UNIQUE_PROFILE_TOKEN>` kill token that appears in the
Chrome argv (e.g. the `--user-data-dir` path) but NOT in the launcher script's own path.

**Step 1 — write a detached launcher on mate-fedora.** `setsid … & disown` + `</dev/null` keeps Chrome
alive after the SSH channel closes. Persistent `--user-data-dir` keeps login/cookies between runs.

```bash
# /home/dev/<name>-launch.sh  (on mate-fedora)
export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-0
pkill -f "<UNIQUE_PROFILE_TOKEN>"
sleep 1
setsid google-chrome --ozone-platform=wayland --remote-debugging-port=9222 \
  --user-data-dir=/home/dev/.<name>-chrome-profile \
  --no-first-run --no-default-browser-check "<url>" \
  </dev/null >/tmp/<name>-chrome.log 2>&1 & disown
```

**Step 2 — launch it (its OWN ssh call, argv must NOT contain the kill token):**
```bash
ssh mate-fedora 'nohup bash /home/dev/<name>-launch.sh >/tmp/launch.out 2>&1 </dev/null; echo launched'
```

**Step 3 — verify Chrome + CDP on mate-fedora (SEPARATE ssh call):**
```bash
ssh mate-fedora 'curl -s http://localhost:9222/json/version'
```

**Step 4 — open the CDP tunnel from `hp`** (Bash: `run_in_background: true`, `dangerouslyDisableSandbox: true`):
```bash
ssh -N -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes -L 9222:localhost:9222 mate-fedora
```

**Step 5 — confirm the tunnel on `hp`:**
```bash
curl -s http://localhost:9222/json/version
```

**Step 6 — drive the remote browser.** Two options:
- **(a) Node script:** `chromium.connectOverCDP('http://localhost:9222')`, grab the existing
  context/page, drive + screenshot. (Live endpoint is `ws://127.0.0.1:9222/devtools/browser/<id>`.)
- **(b) Playwright MCP:** configure it with `--cdp-endpoint http://localhost:9222` and reconnect so
  the normal Playwright MCP tools drive the remote browser.
  > NOTE: an older memory claimed the Playwright MCP "can't attach to remote CDP." The
  > `--cdp-endpoint` flag is the intended path — treat that old claim as **superseded / needs
  > re-verification**, and prefer (a) if the MCP path misbehaves.
