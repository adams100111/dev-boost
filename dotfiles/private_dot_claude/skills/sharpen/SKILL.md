---
name: sharpen
description: "Turn a rough, ambiguous, or codebase-grounded request into a precise, context-grounded, agent-ready prompt that gets better agent responses. The inverse of wait-what: wait-what re-pitches the AI's answer for a human; sharpen re-pitches the human's ask for the agent. It triages ambiguity (skips trivial/clear asks), gathers only load-bearing context via a subagent, grills proportionally, and synthesizes a sharper — not longer — prompt. Use when a request is underspecified, before dispatching a complex or multi-step agent task, or when the user says enhance/sharpen/improve/fix my prompt, make this a better prompt, or invokes /sharpen."
---

# Sharpen

**Concept — the inverse of `wait-what`.** `wait-what` re-pitches the *AI's* message so a *human* gets it. `sharpen` re-pitches the *human's* ask so the *agent* gets it: a rough, ambiguous, or codebase-grounded request becomes a precise, context-grounded, agent-ready prompt that yields better responses. Optimize for **precision-per-token, not length** — a sharper ask, never just a longer one.

## Triage first — sharpening the wrong thing hurts

Enhancing a well-specified or trivial ask wastes turns and can *degrade* the result (bloat, over-constraint, false precision). **Before anything, triage** — see [references/triage.md]. If the ask is already clear and small, **stop and hand it back untouched**, and say why. Grill **proportional to ambiguity**, never uniformly.

## The loop

1. **Triage** — [references/triage.md]. Pass (clear + small) → return the ask untouched. Otherwise set a round budget from the ambiguity.
2. **Gather load-bearing context — via a subagent, not inline.** Dispatch ONE Explore/general-purpose subagent to return a *digest* (relevant paths, conventions, prior stated constraints), never file dumps ([principle-guard-the-context-window]). Finding facts is your job, never the user's ([grilling]).
3. **Grill proportional to ambiguity.** Compose the **`grilling`** skill's frontier/rounds — one round at a time, numbered questions each with a recommended answer — but **capped** per triage. Stop at the cap or when the frontier is clear; log explicit assumptions for anything unresolved rather than blocking further ([principle-never-block-on-the-human]).
4. **Synthesize** against the fixed template — [references/synthesis-template.md]. Cut, don't pad ([principle-subtract-before-you-add]).
5. **Emit + prove.** Return the prompt as plain text (offer to dispatch it as an agent task). Then prove it's *better, not just longer* — [references/verify.md] ([principle-prove-it-works]).

## Compose, don't reinvent

- **Interview** → the `grilling` skill (frontier/rounds). Do not re-implement it.
- **Context** → an Explore / general-purpose subagent (digest only).
- **Output voice** → `writing-for-agents` (leading words, structure, prune no-ops) + `wait-what`'s ubiquitous-language + Simplified-Technical-English discipline — aimed at the *agent*. Use the repo's `CONTEXT.md` vocabulary when one exists.
- **Guardrails** → `principle-guard-the-context-window`, `principle-subtract-before-you-add`, `principle-minimize-reader-load`, `principle-prove-it-works`.

## Anti-patterns

Over-specifying a capable agent, stale baked-in context, false precision (inventing constraints), and grilling that costs more than the task. See [references/anti-patterns.md].
