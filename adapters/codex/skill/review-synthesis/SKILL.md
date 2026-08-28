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
5. Preserve source labels for every finding and keep local review status
   separate from remote MR completion.
6. Treat findings as triage candidates, not approved implementation tasks.
   Include `candidate_disposition` and `implementation_prompt_eligible` when a
   finding is non-trivial, or explain why they are `Unknown`.
   `candidate_disposition` maps to `review-ledger.contract_disposition` when a
   finding enters follow-up; do not use `review-ledger.disposition` for
   `ACCEPT`-family triage values.
7. Ask follow-up decisions with ordinary numbered choices such as `1.` / `2.`;
   do not use circled digit characters.
