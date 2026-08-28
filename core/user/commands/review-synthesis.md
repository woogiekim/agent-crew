# /review-synthesis — Parallel Review Synthesis

## Purpose

Run or collect multiple read-only review lenses in parallel and return one
combined operator-facing report.

This workflow is for receiving synthesis feedback after review-related
commands, skills, agents, and provider-native review capabilities inspect the
same scope from different angles. It does not fix code, post MR notes, update
MR descriptions, commit, push, merge, deploy, or mutate external systems.

## Feedback Triage Boundary

Apply `core/rules/contract-first-feedback-fidelity.md` to every synthesized
finding. In this workflow, review findings are candidate inputs for operator
triage, not accepted implementation requirements.

Do not treat a finding as an approved implementation task. Preserve the source
lens, reviewer or tool wording, affected contract, caller graph status, and
evidence limit before recommending follow-up. If a finding appears actionable,
assign a `candidate_disposition` of `ACCEPT`, `ACCEPT_WITH_ADAPTATION`,
`REJECT_METHOD_ONLY`, `DEFER`, `REJECT`, or `Unknown` and explain the evidence
needed to confirm it.

Only findings whose `candidate_disposition` is `ACCEPT` or
`ACCEPT_WITH_ADAPTATION` may be marked `implementation_prompt_eligible=true`.
`REJECT_METHOD_ONLY`, `DEFER`, and `REJECT` remain valid synthesis outcomes
when backed by contract, parity, scope, side-effect, ownership, or evidence
limits. A synthesis report may recommend a `review-followup` or `prompt` pass,
but it must not silently convert every finding into work.

`candidate_disposition` is the synthesis-time triage value. If the finding is
later promoted into `review-followup` implementation work, carry the same value
into `review-ledger.contract_disposition`; do not reuse
`review-ledger.disposition` for `ACCEPT`-family values. The ledger
`disposition` field remains the lifecycle result (`implemented`, `deferred`,
`rejected`, or `not-applicable`) and may also be displayed through existing
user-facing labels such as `IMPLEMENTED`, `LOCAL_DONE`, or `POLICY_WAITING`.

## Review Lens Discovery

Before selecting lenses, run review lens discovery using
`core/scripts/review-lens-discovery.py` or the installed equivalent. Discovery
uses the provider-neutral contract in `core/rules/review-lens-discovery.md`.

Discovery must separate installed capability from execution result:

- classify read-only, non-mutating, context-compatible lenses as `eligible`;
- promote an `eligible` lens to `completed` only after it actually runs and
  produces an artifact or inline result in the current synthesis pass;
- report MR-only lenses as `not-run` when MR context is unavailable;
- report parity lenses as `suggested` or `blocked` when the comparison
  contract, source/target repository, or mode is missing;
- report supervisor-only agents such as the system `reviewer` as `blocked`;
- report mutating review follow-up commands as `blocked`;
- report duplicate semantic lenses as `duplicate-suppressed`.

Do not directly invoke the system `reviewer` agent. It is supervisor-spawned.

## Default Lenses

The default lens set remains:

- generic review;
- post-audit;
- MR review-rate when MR context exists;
- parity when parity or producer/consumer contract scope exists;
- domain/user skills when capability dispatch selects them.

Provider-native lenses may participate only when their metadata declares a
read-only, non-mutating review-lens contract and the host adapter reports them
available.

## Output

The synthesis report must list every discovered or configured lens with one of:
`eligible`, `completed`, `not-run`, `suggested`, `blocked`, `degraded`, or
`duplicate-suppressed`. Every finding must preserve its source lens label, and
local implementation status must stay separate from remote MR completion.

When a lens reports caller graph coverage, preserve it in the synthesis instead
of flattening it into a generic finding. Surface BFS inventory, selective DFS
deep dive, `No references found`, partial graph, and unknown graph status with
the source lens. Missing graph coverage must narrow completion guidance rather
than becoming a stronger review or parity claim.

For each non-trivial finding, include `candidate_disposition` and
`implementation_prompt_eligible` in the human-readable report or clearly state
why those fields are `Unknown`. Keep this triage separate from local
implementation status and remote MR completion status.
