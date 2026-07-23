# Remote Fleet — M3: `fleet` DX verbs + comprehensive operator docs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the `fleet` DX dispatcher (one-word cross-box verbs) and the comprehensive remote-fleet operator documentation — the capstone of the remote-fleet feature.

**Architecture:** A single executable shell dispatcher shipped as a chezmoi dotfile (`dot_local/bin/executable_fleet` → `~/.local/bin/fleet`), reading host targets from `~/.config/fleet/config`. Verbs (`dev`/`ship`/`expose`/`edge`/`status`) are thin wrappers over `mosh`/`ssh`/`tailscale`/`podman`. Plus a standalone `docs/remote-fleet.md` operator guide, a README "Remote fleet" section, and a `CLAUDE.md` pointer.

**Tech Stack:** POSIX/bash shell (chezmoi-managed dotfile), pytest+subprocess for the dispatcher's guard/dispatch tests, Markdown docs.

**Source spec:** `docs/superpowers/specs/2026-07-22-remote-fleet-workflow-design.md` (§5 fleet layer, §10 documentation).

## Global Constraints

- Merge gates from `engine/`: `uv run ruff check`, `uv run mypy` (`--strict`), `uv run pytest`. (Shell dotfile isn't linted by these, but the pytest that drives it must pass; keep `bash -n` clean.)
- `fleet` verbs: `dev`, `ship <img> [dir]`, `expose <port> [--pub]`, `edge`, `status`. Host targets from env (`DEVBOOST_BRAIN`, `DEVBOOST_BUILDER`, `DEVBOOST_EDGE`), sourced from `~/.config/fleet/config`. Each verb must error cleanly (non-zero, a clear message) when its required target env is unset — no silent failure.
- The dispatcher is a convenience wrapper: its remote subcommands (`herdr`, `tailscale serve/funnel`, `podman build`) are best-effort ergonomics, documented in the guide, not asserted for exact remote behavior.
- Commit messages: no Claude/Anthropic attribution.
- Chezmoi naming: `executable_` prefix → installed as an executable; `dot_` → leading dot.

---

## File Structure

- **Create** `dotfiles/dot_local/bin/executable_fleet` — the `fleet` dispatcher.
- **Create** `dotfiles/dot_config/fleet/config` — commented host-target defaults.
- **Create** `engine/tests/dotfiles/test_fleet.py` — subprocess tests (syntax, env-guard, dispatch).
- **Create** `engine/tests/dotfiles/__init__.py` — package marker (if the tests dir needs one; match sibling test dirs).
- **Create** `docs/remote-fleet.md` — the comprehensive operator guide.
- **Modify** `README.md` — add a "Remote fleet" section linking to the guide.
- **Modify** `CLAUDE.md` — a one-line pointer to the remote-fleet capability/guide.

---

## Task 1: the `fleet` dispatcher + config + tests

**Files:**
- Create: `dotfiles/dot_local/bin/executable_fleet`
- Create: `dotfiles/dot_config/fleet/config`
- Create: `engine/tests/dotfiles/test_fleet.py`
- Create: `engine/tests/dotfiles/__init__.py` (empty)

**Interfaces:**
- Produces: a `fleet` command with subcommands `dev|ship|expose|edge|status`, env-guarded.

- [ ] **Step 1: Write the failing test**

First check whether sibling test dirs carry an `__init__.py` (e.g. `ls engine/tests/modules/__init__.py`); if they do, create an empty `engine/tests/dotfiles/__init__.py` to match. Then create `engine/tests/dotfiles/test_fleet.py`:

```python
from __future__ import annotations

import subprocess
from pathlib import Path

FLEET = (
    Path(__file__).resolve().parents[3] / "dotfiles" / "dot_local" / "bin" / "executable_fleet"
)


def _run(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(FLEET), *args],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", **(env or {})},
    )


def test_fleet_script_is_valid_bash() -> None:
    # `bash -n` parses without executing — catches syntax errors in the dispatcher.
    result = subprocess.run(["bash", "-n", str(FLEET)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_fleet_no_args_prints_usage_nonzero() -> None:
    result = _run([])
    assert result.returncode != 0
    assert "usage" in (result.stdout + result.stderr).lower()


def test_fleet_unknown_verb_errors() -> None:
    result = _run(["frobnicate"])
    assert result.returncode != 0
    assert "frobnicate" in (result.stdout + result.stderr).lower() or "usage" in (
        result.stdout + result.stderr
    ).lower()


def test_fleet_dev_without_brain_env_errors_cleanly() -> None:
    # DEVBOOST_BRAIN unset -> clean non-zero with a message, not a silent/obscure failure.
    result = _run(["dev"])
    assert result.returncode != 0
    assert "DEVBOOST_BRAIN" in (result.stdout + result.stderr)


def test_fleet_edge_without_edge_env_errors_cleanly() -> None:
    result = _run(["edge"])
    assert result.returncode != 0
    assert "DEVBOOST_EDGE" in (result.stdout + result.stderr)
```

- [ ] **Step 2: Run to verify it fails**

Run (from `engine/`): `uv run pytest tests/dotfiles/test_fleet.py -q`
Expected: FAIL — the `executable_fleet` file does not exist (bash: No such file), so the subprocess returns non-zero and assertions on specific messages fail.

- [ ] **Step 3: Create the dispatcher**

Create `dotfiles/dot_local/bin/executable_fleet`:

```bash
#!/usr/bin/env bash
# fleet — one-word cross-box verbs for the dev-boost remote fleet.
# Host targets come from ~/.config/fleet/config (DEVBOOST_BRAIN / _BUILDER / _EDGE).
# These verbs are thin convenience wrappers over mosh/ssh/tailscale/podman — tune to taste.
set -euo pipefail

CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/fleet/config"
# shellcheck source=/dev/null
[ -f "$CONFIG" ] && . "$CONFIG"

usage() {
	cat >&2 <<'EOF'
usage: fleet <command> [args]

  dev                 mosh into the brain (devbrain@$DEVBOOST_BRAIN) and attach herdr
  ship <img> [dir]    build a multi-arch image on $DEVBOOST_BUILDER (rootless podman) and push
  expose <port> [--pub]   tailscale serve (tailnet) $port on the brain; --pub -> tailscale funnel
  edge                ssh into $DEVBOOST_EDGE (the public-facing / prod box)
  status              herdr agent snapshot on the brain (working / blocked / done)

hosts are read from ~/.config/fleet/config:
  DEVBOOST_BRAIN, DEVBOOST_BUILDER, DEVBOOST_EDGE
EOF
	exit 2
}

need() { # need VAR — fail cleanly if a required host target is unset
	local name="$1"
	if [ -z "${!name:-}" ]; then
		echo "fleet: $name is not set — add it to ~/.config/fleet/config" >&2
		exit 1
	fi
}

cmd="${1:-}"
[ -n "$cmd" ] || usage
shift || true

case "$cmd" in
dev)
	need DEVBOOST_BRAIN
	exec mosh "devbrain@${DEVBOOST_BRAIN}" -- herdr
	;;
ship)
	need DEVBOOST_BUILDER
	img="${1:-}"
	[ -n "$img" ] || { echo "fleet ship: usage: fleet ship <img> [dir]" >&2; exit 2; }
	dir="${2:-.}"
	exec ssh "devbrain@${DEVBOOST_BUILDER}" \
		"cd $(printf %q "$dir") && podman build --platform linux/amd64,linux/arm64 \
		 --manifest $(printf %q "$img") . && podman manifest push $(printf %q "$img")"
	;;
expose)
	need DEVBOOST_BRAIN
	port="${1:-}"
	[ -n "$port" ] || { echo "fleet expose: usage: fleet expose <port> [--pub]" >&2; exit 2; }
	if [ "${2:-}" = "--pub" ]; then
		exec ssh "${DEVBOOST_BRAIN}" tailscale funnel "$port"
	fi
	exec ssh "${DEVBOOST_BRAIN}" tailscale serve --https=443 "localhost:${port}"
	;;
edge)
	need DEVBOOST_EDGE
	exec ssh "${DEVBOOST_EDGE}"
	;;
status)
	need DEVBOOST_BRAIN
	exec ssh "devbrain@${DEVBOOST_BRAIN}" herdr status
	;;
*)
	echo "fleet: unknown command '$cmd'" >&2
	usage
	;;
esac
```

- [ ] **Step 4: Create the config dotfile**

Create `dotfiles/dot_config/fleet/config`:

```bash
# dev-boost fleet host targets — sourced by `fleet`. Set to your tailnet (MagicDNS) names.
# export DEVBOOST_BRAIN=my-dev        # the box hosting the sandboxed devbrain brain
# export DEVBOOST_BUILDER=mod-sol     # the box that runs multi-arch `fleet ship` builds
# export DEVBOOST_EDGE=my-dev         # the public-facing / production box for `fleet edge`
```

- [ ] **Step 5: Run the test to verify it passes**

Run (from `engine/`): `uv run pytest tests/dotfiles/test_fleet.py -q`
Expected: PASS (5 passed). The env-guard tests pass because `need`/`${VAR:?}` emit the var name to stderr and exit non-zero when unset.

- [ ] **Step 6: Run the full gates**

Run (from `engine/`): `uv run pytest -q`, `uv run mypy`, `uv run ruff check`. Expected: all green (the new test file is the only Python added; mypy/ruff cover it).

- [ ] **Step 7: Commit**

```bash
git add dotfiles/dot_local/bin/executable_fleet dotfiles/dot_config/fleet/config \
        engine/tests/dotfiles/test_fleet.py engine/tests/dotfiles/__init__.py
git commit -m "feat(fleet): fleet dispatcher (dev/ship/expose/edge/status) + config dotfile"
```

---

## Task 2: `docs/remote-fleet.md` operator guide

Write the comprehensive operator guide. This is a documentation task — the plan specifies the required structure and content; write clear, accurate prose (verify every command against what actually shipped in M1/M2).

**Files:**
- Create: `docs/remote-fleet.md`

- [ ] **Step 1: Write the guide**

Create `docs/remote-fleet.md` covering these sections (in order). Every command must match what actually shipped (`devboost install full`/`server`, `devboost brain`, `fleet <verb>`, `mosh`, `tailscale serve`, `podman build --platform …`). Do NOT document deferred tools as if built.

1. **Concept & topology** — the three-layer model (Tailscale reachability → Mosh transport → herdr session), and the "brain is a role, not a machine; the prod-sharing constraint is temporary" premise. Include the four-box reference table (laptops `full`; two Ubuntu production servers `server`; one hosts the brain).
2. **Per-role setup** — the exact one-liners: laptops `curl … | bash -s -- full`; servers `curl … | bash -s -- server`; then `devboost brain` on the chosen brain host. What each installs; the secrets each needs (`TAILSCALE_AUTHKEY`, restic B2, optional Telegram). Note laptops now join the tailnet + get Mosh via the `remote` profile.
3. **The `devbrain` sandbox** — what it is (a capped, `privilege=none` managed account created by `devboost brain`), how to review/tune caps (`devboost accounts edit devbrain`), and how it's reached (`fleet dev` / `mosh devbrain@brain`, keyed by `ssh_authorized_keys`). State plainly: passwordless sudo is never installed here.
4. **Daily DX flow** — develop from a laptop via VS Code Remote-SSH into the sandbox; orchestrate via `fleet dev` (herdr multiplayer — both laptops on one session); `fleet ship <img>` for capped rootless multi-arch builds on the x86 builder; `fleet edge` to the prod box; `fleet status` for the agent snapshot.
5. **Cross-arch builds** — the rootless-podman `--platform linux/amd64,linux/arm64 --manifest … && podman manifest push` flow runs as capped `devbrain`; the arm server only pulls. Why podman (rootless, capped) not host docker buildx (root-equivalent, uncapped).
6. **Domains** — MagicDNS short names (default, memorable — they're your hostnames); `tailscale serve` for HTTPS on a device; Caddy `*.localhost` + `tls internal` for multi-site sub-routing (the shipped starter Caddyfile).
7. **The mini-server migration** — a future dedicated box is a zero-architecture-change move: install `brain-host`, re-point `DEVBOOST_BRAIN`/`DEVBOOST_BUILDER`, optionally drop the sandbox (or keep it).
8. **Deferred / opt-in recipes** — clearly marked "not installed by default", copy-pasteable: Eternal Terminal, portless, cloudflared, vanity/public domains (Caddy DNS-01 ACME / `tailscale funnel`), and the future container-isolation tier.
9. **Troubleshooting** — mosh UDP rides `tailscale0` (no extra firewall rules); MagicDNS resolution needs the Tailscale app on the client; Tailscale SSH ACLs; rootless-podman subuid/subgid; tuning devbrain caps for prod headroom.

- [ ] **Step 2: Cross-check every command against the codebase**

Verify: profiles exist (`full`, `server`, `brain-host`, `brain-tools`); `devboost brain` flags match `cli/app.py`; `fleet` verbs match `executable_fleet`; the Caddyfile path matches `dotfiles/dot_config/caddy/Caddyfile`. Fix any mismatch.

- [ ] **Step 3: Verify docs-only change doesn't break tests**

Run (from `engine/`): `uv run pytest -q`. Expected: green (docs-only).

- [ ] **Step 4: Commit**

```bash
git add docs/remote-fleet.md
git commit -m "docs(fleet): comprehensive remote-fleet operator guide"
```

---

## Task 3: README "Remote fleet" section + `CLAUDE.md` pointer

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add the README section**

In `README.md`, add a concise **"Remote fleet"** section (near the profiles table / a sensible top-level spot) — the four-box story in ~5-8 lines + the `fleet` verbs, ending with a link to the full guide:

```markdown
## Remote fleet

Turn a laptop + always-on Linux servers into one machine for agentic dev: laptops join a
private Tailscale tailnet with resilient Mosh terminals (`full`), servers are hardened
(`server`), and `devboost brain` provisions a **sandboxed, sudo-less `devbrain`** brain on a
chosen server (herdr + capped rootless multi-arch builds) that shares a box with production
safely. Drive it with one-word `fleet` verbs — `fleet dev` (attach the brain), `fleet ship`
(multi-arch build), `fleet expose`, `fleet edge`, `fleet status`.

See **[docs/remote-fleet.md](docs/remote-fleet.md)** for the full operator guide.
```

If a "Remote fleet" prose note was added earlier (M2 pt2, near the profiles table), fold it into this section rather than duplicating; keep the profiles-table area clean.

- [ ] **Step 2: Add the CLAUDE.md pointer**

In `CLAUDE.md`, add a one-line pointer near the mission/active-plan section (do not disturb existing lines):

```markdown
The **remote-fleet** capability (tailnet + Mosh + a sandboxed `devbrain` brain + the `fleet`
DX verbs) is documented in `docs/remote-fleet.md`.
```

- [ ] **Step 3: Verify + commit**

Run (from `engine/`): `uv run pytest -q` (green, docs-only).

```bash
git add README.md CLAUDE.md
git commit -m "docs(fleet): README remote-fleet section + CLAUDE.md pointer"
```

---

## Self-Review (completed during authoring)

**Spec coverage:** §5 fleet dispatcher (dev/ship/expose/edge/status, env-guarded, config file) → Task 1. §10.1 operator guide (all 9 sections) → Task 2. §10.2 README section + §10.5 CLAUDE.md pointer → Task 3. §10.4 in-code docstrings were done per-module in M1/M2. Deferred-recipe docs (§10, part of the guide) → Task 2 §8.

**Placeholder scan:** none in Task 1/3 (complete shell + markdown). Task 2 is a doc-writing task specified by required sections + a mandatory codebase cross-check step (§2) — appropriate for prose, not a code placeholder.

**Type consistency:** the pytest drives the shell script by path (`parents[3]` from `engine/tests/dotfiles/` → repo root); env-guard tests assert the exact env var names the dispatcher checks (`DEVBOOST_BRAIN`/`DEVBOOST_EDGE`). Verb set is identical across the dispatcher, its tests, the guide, and the README.

**Note:** this is the final milestone; after merge the remote-fleet feature (M1→M3) is complete, with the documented deferrals (cloudflared, et, portless, vanity domains, container tier) remaining as opt-in recipes.
</content>
