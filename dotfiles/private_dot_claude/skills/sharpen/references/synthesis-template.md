# Synthesis — the enhanced-prompt template

Assemble settled answers + the context digest into ONE portable prompt. Every line must earn its place — cut before you add ([principle-subtract-before-you-add]). Drop any section that carries no load for *this* task (a bare-terminal script needs no "constraints"). The shape below is the ceiling, not a form to fill.

```
# <Task title — the outcome, not the mechanism>

## Goal
<One or two sentences: the outcome + what "done" looks like (success criteria).>

## Context
<Only load-bearing facts from the digest: the repo/module, exact paths, the
conventions to follow, and any constraints the user already stated. Names, not
narration. Use the repo's CONTEXT.md vocabulary. NO file dumps.>

## What to do
<The behavior/requirements. Decompose multi-step work into ordered steps.
Reference real seams (function/file names) the agent will touch.>

## Constraints & non-goals
<Scope fences: what must hold, and explicitly what NOT to do / build. This is
where over-engineering is prevented.>

## Acceptance / verification
<How the result is checked — the test seam, the command, the observable behavior.
Name it so the agent proves it works, not just compiles.>

## Out of scope / open facts to verify
<Deferred work, and any assumption logged past the grilling cap that the agent
should confirm rather than trust.>

## Output
<What the agent should produce: a diff, a plan, a file, an answer in a format.>
```

## Rules

- **Precision per token.** A shorter prompt that removes the agent's guesswork beats a longer one that pads. If a sentence doesn't change what the agent does, delete it.
- **Real handles over prose.** Exact paths, function names, and repo conventions from the digest — not "the relevant file."
- **State the fork you resolved,** don't re-open it. Settled decisions are constraints now, not questions.
- **Examples earn their place** for pattern-matchable tasks (a sample row, a target signature); skip them otherwise.
- **No invented specifics.** If you don't know a format/constraint, say "verify: …" in Out-of-scope — never fabricate one to sound thorough (false precision is worse than a rough ask).
- Match the register to the agent, in Simplified Technical English; keep reader load low ([principle-minimize-reader-load]).
