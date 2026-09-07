# Anti-patterns — when sharpening backfires

Enhancement is not free. Each failure mode below is evidence-backed; the mitigation is what keeps `sharpen` a net gain.

| Anti-pattern | Why it hurts | Mitigation |
|---|---|---|
| **Prompt bloat** | Excess context degrades output — the "lost in the middle" effect; irrelevant tokens measurably lower accuracy. | Digest-only context; cut any line that doesn't change agent behavior. Precision per token. |
| **Stale baked-in context** | Codebase/chat snapshots frozen into the prompt go wrong the moment the code changes underneath. | Prefer stable handles (paths, conventions, names) over volatile excerpts; note "verify against current state" for anything time-sensitive. |
| **Over-constraining a capable agent** | Heavy scaffolding on a simple/exploratory task removes the model's own (often correct) judgment. | Scale detail to ambiguity (triage). For simple asks, hand back untouched. |
| **False precision** | Inventing a format, constraint, or number to sound thorough dresses an error as authority — worse than the rough ask. | Never fabricate. Unknowns go to "Out of scope / verify", not into the spec. |
| **Grilling costs more than the task** | An interrogation on a 30-second fix is net-negative. | Triage gate + round cap. Skip is a valid, common outcome. |
| **Reinventing the interview** | Re-implementing question-loop logic duplicates `grilling` and drifts. | Compose the `grilling` skill; add only the synthesis/emit step it lacks. |

**The one-line test before emitting:** *Would a capable agent produce a better result from this prompt than from the user's raw ask — and is every added token pulling weight?* If not, sharpen less, or hand the ask back.
