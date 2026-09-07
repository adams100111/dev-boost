# Prove it's better — not just longer

A prompt-enhancer's whole value claim is "the sharpened prompt beats the raw ask." Do not ship on faith ([principle-prove-it-works]). Match the proof to the stakes.

## Always — the pre-emit self-critique (cheap, every run)

Before returning the prompt, run it against [anti-patterns.md] as a checklist:

- [ ] Every section carries load for *this* task (dropped the ones that don't).
- [ ] No invented specifics — unknowns are in "Out of scope / verify", not the spec.
- [ ] Real handles (paths/names/conventions), not "the relevant file".
- [ ] Shorter or as-short where possible; no token that doesn't change agent behavior.
- [ ] The resolved forks appear as constraints, not re-opened questions.

If a box fails, fix it or cut. If you cannot make the sharpened prompt clearly beat the raw ask, **say so and hand the ask back** — a rough-but-honest prompt beats a padded one.

## When it matters — the A/B check (higher stakes)

For a load-bearing prompt (a big task about to be dispatched, or a skill/spec), prove it empirically instead of by inspection:

1. **Baseline vs. enhanced.** Run the *raw ask* and the *sharpened prompt* on the same downstream task, same agent (dispatch two subagents), and diff the outputs. The sharpened one should need fewer clarifying questions, hit more acceptance criteria, and stay in scope.
2. **Script the check when it repeats** ([principle-build-the-lever]). If you sharpen prompts of a recurring shape, write a tiny harness that scores enhanced-vs-raw across a few fixture asks and keep it as the rerunnable proof — the artifact a reviewer runs instead of trusting your word.
3. **Keep the evidence visible** (the diff, the scores). Commit it only for large/auditable work (the `show-me-your-work` skill); otherwise just show it.

The bar is *demonstrated improvement on the real task*, not "reads more thorough."
