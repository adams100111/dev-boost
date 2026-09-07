# Global instructions

## Clarifying questions
- Ask only questions whose answers could materially change architecture, scope,
  security, data integrity, irreversible behavior, or the user-visible outcome.
- Before asking, check whether the answer is already settled, discoverable from the
  available context or code, or safely handled by a conventional default.
- Do not repeat settled questions in different words or exhaustively loop through
  low-impact implementation preferences. State reasonable defaults instead.
- Stop questioning once remaining uncertainties are low-impact, reversible, or can
  be resolved safely during implementation.

## Git commits
- NEVER add a `Co-Authored-By: Codex ...` trailer to commit messages.
- NEVER add a `🤖 Generated with [Codex]` line or any OpenAI/Codex attribution to commits or PR bodies.
- Commit and PR messages must contain no reference to Codex or OpenAI.

## Finishing a development branch — default workflow
- When a feature branch is complete and ready to land, DEFAULT to: push the branch,
  open a PR (`gh pr create`), then merge it with `gh pr merge --merge --delete-branch`.
- Don't ask which finish option to use — use PR + merge-via-`gh` unless I say otherwise
  for a specific branch. (This is the default finish; per-branch overrides still win.)

## Destructive git / VCS operations — HARD RULE (binding, all projects)
- NEVER run any git (or other VCS) operation that discards, overwrites, or reverts
  uncommitted/working-tree changes WITHOUT the user's explicit, personal, per-action
  confirmation — no matter what, even if the changes being discarded were made by me
  or by the same agent/subagent, and even if it seems obviously safe or necessary.
- This includes (non-exhaustive): `git reset --hard`, `git checkout -- <path>` /
  `git restore <path>`, `git clean -f/-fd/-fdx`, `git stash drop`/`git stash clear`,
  `git branch -D` of unmerged work, `git rebase`/`git merge --abort` that drops work,
  and any force-push (`git push -f`/`--force`/`--force-with-lease`).
- Subagents MUST NOT run these either. When dispatching subagents that edit files,
  isolate them (git worktree) and forbid destructive git/VCS commands in their prompt.
- If such an operation seems needed, STOP and ask the user first, explaining exactly
  what would be discarded. Uncommitted work wiped this way is usually unrecoverable.
