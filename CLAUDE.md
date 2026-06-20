# dev-boost — Mission (read first)

**Goal:** From a fresh laptop, with effectively zero config, reach a fully-configured
developer workstation in minutes — delivered by an unattended **Ventoy USB** (primary:
`curl … | bash`; bonus: zero-touch Kickstart). "Production ready" means the box can
**build, out of the box**: **Laravel** (ddev), **.NET + Aspire**, **Python** (uv),
**Next.js / React** (web), and **React Native + Expo** (Android) — plus editors
(VS Code + fresh), GUI apps (Obsidian w/ GitHub sync, Bruno, dbgate, Bitwarden, …),
and fully-configured terminal/shell/desktop (ghostty + starship + tmux + GNOME),
all restored from chezmoi-managed dotfiles.

**Zero-config caveats (by design):** secrets (GitHub PAT) are pre-provisioned once on
the USB (`age`-encrypted); **GPU vendor is auto-detected (`lspci`)** and the matching
driver/VA-API path is applied with no profile flag — the only possibly-interactive
moment is a one-time Secure-Boot MOK enrollment screen on NVIDIA when Secure Boot is on.

The roadmap of remaining specs is `docs/roadmap.md`; the canonical design is
`docs/superpowers/specs/2026-06-19-devboost-platform-design.md`; principles are in
`.specify/memory/constitution.md`. Every spec cycle must serve this mission.

<!-- SPECKIT START -->
Active feature plan: `specs/005-multimedia-codecs/plan.md`
(spec `specs/005-multimedia-codecs/spec.md`). Specs 1–4 (secrets-and-auth, base-profile,
cli-and-shell, gnome-desktop) merged to main (666 tests). For technologies, project
structure, shell commands, and other context, read that plan and the design doc / constitution.
<!-- SPECKIT END -->
