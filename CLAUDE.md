# dev-boost — Mission (read first)

**Goal:** From a fresh laptop, with effectively zero config, reach a fully-configured
developer workstation in minutes — delivered by an unattended **Ventoy USB** (primary:
`curl … | bash`; bonus: zero-touch Kickstart). "Production ready" means the box can
**build, out of the box**: **Laravel** (ddev), **.NET + Aspire**, **Python** (uv),
**Next.js / React** (web), and **React Native + Expo** (Android) — plus editors
(VS Code + fresh), GUI apps (Obsidian w/ GitHub sync, Bruno, dbgate, Bitwarden, …),
and fully-configured terminal/shell/desktop (wezterm + starship + tmux + GNOME),
all restored from chezmoi-managed dotfiles.

**Zero-config caveats (by design):** secrets (GitHub PAT) are pre-provisioned once on
the USB (`age`-encrypted); **GPU vendor is auto-detected (`lspci`)** and the matching
driver/VA-API path is applied with no profile flag — the only possibly-interactive
moment is a one-time Secure-Boot MOK enrollment screen on NVIDIA when Secure Boot is on.

The roadmap of remaining specs is `docs/roadmap.md`; the canonical design is
`docs/superpowers/specs/2026-06-19-devboost-platform-design.md`; principles are in
`.specify/memory/constitution.md`. Every spec cycle must serve this mission.

The **remote-fleet** capability (tailnet + Mosh + a sandboxed `devbrain` brain + the `fleet`
DX verbs) is documented in `docs/remote-fleet.md`.

<!-- SPECKIT START -->
Active feature plan: `specs/014-python-engine-core/plan.md`
(spec `specs/014-python-engine-core/spec.md`; design `docs/superpowers/specs/2026-06-26-python-engine-migration-design.md`).
Spec 014 = the complete **bash → typed-Python rewrite** of the whole platform, shipped as one
greenfield deliverable (no intermediate release): Typer/Pydantic/uv src-layout engine under `engine/`,
pure-Python modules (one typed file each; `requires` as class refs), injected `Executor` seam (system
tools shell out, data via stdlib), opt-in per-OS `Installer` strategy; Fedora implemented for parity
with OS-dispatch seams for later OSes; frozen per-arch binary; only `get.sh` + Kickstart `%post` stay
bash. Built across internal milestones M0–M10 (M0 = foundation + tracer). Constitution v3.0.0 governs;
`mypy --strict` + ruff + pytest are merge gates. Specs 1–13 were the prior bash platform (now the
behavioral spec to port + delete, group-by-group).
<!-- SPECKIT END -->
