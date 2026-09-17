---
name: review-synthesis
description: Use when the user invokes $review-synthesis or asks to run multiple review-related commands, skills, or agents in parallel and receive one synthesized feedback report.
---

# review-synthesis

This Codex skill delegates to the provider-neutral workflow in
`~/.agent-crew/commands/review-synthesis.md`.

## Execution

1. Load `~/.agent-crew/commands/review-synthesis.md` in full before acting.
2. Treat text after `$review-synthesis` as the review scope, MR id, base ref,
   lens list, or free-text target.
3. Keep the pass read-only unless the user explicitly asks for a separate
   follow-up mutation workflow.
4. Discover eligible review lenses through the provider-neutral review-lens
   contract. Do not directly invoke the system `reviewer` agent.
   Include Codex-provided AI system review only when it is exposed as a
   read-only, non-mutating host-native lens such as `codex-system-review`.
5. When the discovered `codex-system-review` lens has
   `runner: codex-system-skill`, load `~/.codex/skills/.system/review-agent/SKILL.md`
   when that file is available; load it in full. Apply that skill to the same
   requested review scope as a read-only host-native lens, then label its
   findings with `source_lens=codex-system-review`.
6. Mark `codex-system-review` as `completed` only after the review-agent pass
   actually produces findings or a no-findings result for the current synthesis
   run. If the skill file is missing, unreadable, or cannot be applied in this
   Codex session, keep the lens `not-run` or `degraded` with the reason.
7. Preserve source labels for every finding and keep local review status
   separate from remote MR completion.
8. Treat findings as triage candidates, not approved implementation tasks.
   Include `candidate_disposition` and `implementation_prompt_eligible` when a
   finding is non-trivial, or explain why they are `Unknown`.
   `candidate_disposition` maps to `review-ledger.contract_disposition` when a
   finding enters follow-up; do not use `review-ledger.disposition` for
   `ACCEPT`-family triage values.
9. Ask follow-up decisions with ordinary numbered choices such as `1.` / `2.`;
   do not use circled digit characters.
