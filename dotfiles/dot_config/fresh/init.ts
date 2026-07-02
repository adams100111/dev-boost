// ~/.config/fresh/init.ts — dev-boost managed (chezmoi: dotfiles/dot_config/fresh/init.ts).
//
// fresh startup script (TypeScript). Uses ONLY the documented init API
// (editor.getEnv / editor.setSetting / editor.on) — https://getfresh.dev/docs/configuration/init.
// Persistent editor settings + theme live in config.json; language servers are
// provisioned by dev-boost's *-lsp modules (merged into config.json). This script is
// for environment-dependent tweaks that shouldn't be baked into the persisted config.

// `editor` is injected by fresh at runtime; declare the (subset of the) API we use so
// standalone TypeScript checkers don't flag it. `declare` is type-only — no JS is emitted.
declare const editor: {
  getEnv(name: string): string | undefined;
  setSetting(key: string, value: unknown): void;
};

// Remote / headless (SSH): inline diagnostic text and terminal mouse reporting are
// noisy and often unreliable over SSH, so quiet them when connected remotely. On a
// local desktop session these stay at their defaults.
if (editor.getEnv("SSH_TTY") || editor.getEnv("SSH_CONNECTION")) {
  editor.setSetting("editor.diagnostics_inline_text", false);
  editor.setSetting("terminal.mouse", false);
}
