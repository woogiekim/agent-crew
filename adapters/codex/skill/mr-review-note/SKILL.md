---
name: mr-review-note
description: Use when the user invokes $mr-review-note or asks to leave a GitLab MR note summarizing review feedback that has been reflected, verified, and any policy-waiting items after MR review follow-up.
---

# mr-review-note

This Codex skill delegates to the provider-neutral user workflow in
`~/.agent-crew/commands/mr-review-note.md`.

## Execution

1. Load `~/.agent-crew/commands/mr-review-note.md` in full before acting.
2. Treat text after `$mr-review-note` as command arguments such as MR id, branch, review
   scope, commit ref, policy-waiting items, publish intent, or draft output path.
3. Read MR metadata and notes in the current run with `glab mr view` and
   `glab mr note list`; do not infer review reflection from memory.
4. Compare reviewer requests against local diff, commits, verification evidence, and MR
   description state before drafting the note.
5. Draft the reviewer-facing note in Korean by default on this PC. Keep commands, paths,
   API names, status tokens, commit ids, ticket ids, and quoted source text in the original
   language.
6. Use the canonical command's human-readable default output. Ask posting decisions with
   friendly ordinary numbered choices such as `1.` / `2.`; do not use circled digit
   characters or mechanical approval labels in the default user-facing output.
7. When a review topic exposes an architecture or transaction-boundary decision, do not
   overstate a local mitigation as the final design. Separate current reflected changes from
   proposed follow-up direction, name the processing layer and ownership boundary, state
   known non-atomic or residual behavior explicitly, and phrase the direction as "will proceed
   if there are no objections" when reviewer agreement is still needed.
8. Do not run `glab mr note create` unless the user explicitly approves the remote write
   after seeing the exact note body.
9. When posting is approved, use `--resolvable=false --unique`, then re-read MR notes before
   reporting `STATUS: posted`.
10. Do not run `glab mr update`, `git push`, `git commit`, `git commit --amend`, `git rebase`,
   `git merge`, deploy, or release unless the user explicitly approves a separate mutation.
