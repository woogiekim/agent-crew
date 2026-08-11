---
name: review-followup
description: Use when the user invokes $review-followup or asks to coordinate repeated PR/MR review reflection, implementation prompts, crew:run execution, and review-synthesis verification loops.
---

# review-followup

This Codex skill delegates to the provider-neutral user command in
`~/.agent-crew/commands/review-followup.md`.

## Execution

1. Load `~/.agent-crew/commands/review-followup.md` in full before acting.
2. Treat text after `$review-followup` as the MR/PR id, branch, base ref,
   review source, scope, or loop option. Treat this wrapper as the target only
   when the user explicitly names the skill, wrapper, file, or `SKILL.md`.
3. Coordinate existing review commands instead of replacing them:
   `mr-review-rate`, `crew:agent`, `prompt`, `crew:run`, and
   `review-synthesis`.
4. Preserve approval checkpoints. Do not auto-execute `crew:run`, post MR/PR
   notes, update remote descriptions, commit, push, merge, deploy, or mutate
   external systems without a separate explicit user approval.
5. Preserve review intent and contract safety for every item. Keep
   `LOCAL_REFLECTION_RATE` separate from `MR_REFLECTION_RATE`.
6. Ask follow-up decisions with ordinary numbered choices such as `1.` / `2.`;
   do not use circled digit characters or mechanical approval labels in the
   default output.

This skill coordinates a loop; it is not a review lens for `review-synthesis`.
