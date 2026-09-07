# Triage — decide whether (and how hard) to sharpen

The most important step. Sharpening scales with **ambiguity**, not applied uniformly. Grilling a 30-second ask is net-negative.

## Skip — hand the ask back untouched — when ALL hold

- The **goal** is unambiguous (one reading a capable agent would not have to guess).
- **Success is checkable** as stated (you can see what "done" means).
- Scope is **small** (≈ ≤1 file / one obvious change).
- No **codebase-specific unknowns** (paths, conventions, seams the agent must discover).
- No **conflicting or missing constraints**.

If it passes, say so in one line and stop. Do not add ceremony to a clear ask.

## Round budget — when it does NOT pass

Set the grilling cap from the ambiguity, then honor it:

| Ambiguity | Rounds | Questions | Signals |
|---|---|---|---|
| **Light** | 1 | ≤ 4 | one unclear decision, a missing constraint, an unnamed format |
| **Medium** | ≤ 2 | ≤ 4/round | multi-file work, a fork in approach, unclear acceptance |
| **Heavy** | ≤ 3 | ≤ 4/round | multiple subsystems, conflicting constraints, product direction unclear |

Rules:
- **Never exceed the cap.** Past it, log explicit assumptions and proceed to synthesis — do not keep interrogating ([principle-never-block-on-the-human]).
- A frontier that keeps growing from codebase exploration is a signal to **cap and assume**, not to loop.
- Prefer **facts over questions**: anything a subagent can find, find it — don't ask the user ([grilling]).
- Recommend an answer with every question so the user can confirm with a single token.
