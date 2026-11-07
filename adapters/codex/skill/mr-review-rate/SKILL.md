---
name: mr-review-rate
description: Use when the user invokes $mr-review-rate or asks to read GitLab MR notes and report how much review feedback has been reflected in local diff, commits, scope guard, and remote MR description.
---

# mr-review-rate

This Codex skill delegates to the provider-neutral user workflow in
`~/.agent-crew/commands/mr-review-rate.md` and the specialist agent
`mr-review-rate-auditor`.

## Execution

1. Load `~/.agent-crew/commands/mr-review-rate.md` in full before acting.
2. Treat text after `$mr-review-rate` as command arguments such as MR id,
   branch, base ref, or scope. Treat this wrapper as the target only when the
   user explicitly names the skill, wrapper, file, or `SKILL.md`.
3. Read MR notes in the current run with `glab mr note list`; do not infer
   review completion from memory.
4. Compare every reviewer item against local git diff, local commits, remote MR
   description/metadata, and project scope guard.
5. Report both `LOCAL_REFLECTION_RATE` and `MR_REFLECTION_RATE`, rendered with
   human-readable labels in the default user-facing report.
6. For each non-trivial reviewer item, include a detailed explanation with:
   - the preserved reviewer request or faithful paraphrase;
   - the relevant file, symbol, route, query, config, or contract;
   - short code evidence when verified in the current run;
   - pseudocode for the verified behavior or clearly labeled missing follow-up;
   - why the code satisfies, partially satisfies, or misses the review intent.
7. Ask follow-up decisions with friendly ordinary numbered choices such as `1.` / `2.`;
   do not use circled digit characters or mechanical approval labels in the default output.
8. Keep the pass read-only. Do not run `glab mr update`, `git push`, `git
   commit`, `git commit --amend`, `git rebase`, or `git merge` unless the user
   explicitly approves a separate mutation.
9. Preserve the user's output language for narrative report prose. On this PC,
   Korean default rules mean report prose should be Korean. Keep structured
   tokens and file paths in their original language.
