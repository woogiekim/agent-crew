# Final Review Fix Wave Report

Date: 2026-09-20
Scope: `core/commands/run.md`, `core/agents/supervisor-bootstrap.md`,
`core/schemas/brainstorm-dialogue.schema.json`, and focused Brainstorm tests.

## Finding 1 — preliminary classification must precede requirements

- Root cause: `run.md` still described orchestrator-owned requirements collection
  before Supervisor startup, so Supervisor Phase 1a preliminary classification
  could not influence the real interview depth.
- RED: `test_success_case_run_delegates_preliminary_then_adaptive_requirements_to_supervisor`
  failed because the normal `crew:run` contract did not delegate the unchanged
  Root Input Snapshot directly to Supervisor Phase 1a.
- GREEN: normal Brainstorm tasks now proceed from task context preparation to the
  Supervisor. The Supervisor owns preliminary classification, adaptive requirements
  (`deep_interview` for Architectural, `single_round` for Bounded), and final
  classification. The old orchestrator requirements path is explicitly limited to
  legacy/injected compatibility callers.
- Refactor: the Step 5/Step 6 prose now has a single owner for new-task requirements
  and explicitly prohibits duplicate requirements questions.

## Finding 2 — legacy resume must fail closed

- Root cause: absence of `brainstorm-classification.json` unconditionally returned
  `legacy`, even for a new empty context or damaged partial state.
- RED: the empty-new-task regression returned `legacy`; three partial-legacy
  permutations also returned success instead of a blocker.
- GREEN: `legacy` now requires all four facts: `START_MODE=resume`,
  `register.current_phase=phase_1bc`, a non-placeholder pipeline with task/stages,
  and `context/approval.md=APPROVED`. Empty fresh state returns
  `phase_1a_preliminary`; partial evidence raises
  `legacy_resume_evidence_incomplete`.
- Refactor: `START_MODE` is passed into the Python gate as an explicit argument so
  correctness does not depend on shell export behavior.

## Finding 3 — exact Architectural section resume

- Root cause: section acknowledgements were not tied to a design revision and
  `design_review` always returned the general design-generation boundary.
- RED: current and stale acknowledgement scenarios both returned
  `phase_1b_design`; the schema accepted acknowledgements without a design hash.
- GREEN: acknowledgements require the canonical `design_hash`. The gate filters out
  stale hashes and returns `phase_1b_design_review` plus the first unacknowledged
  canonical section (`goals_and_scope`, `boundaries_and_interfaces`,
  `data_and_recovery`, `risks_tests_and_alternatives`). It reports
  `design_review_complete` only when all sections for the current hash are confirmed.
- Refactor: approval invalidation uses a distinct `design_revision_required` status,
  preserving the existing requirement to regenerate an invalidated design rather
  than confusing it with an interrupted section review.

## Verification

- RED run: 8 expected failures, 84 passes across the two modified Brainstorm test
  modules before production changes.
- Focused Brainstorm/schema/run/readme suite: 198 passed in 11.34s.
- Variant synthesis/lifecycle plus workflow replay/chaos/durability suite:
  47 passed in 94.71s.
- Fresh combined verification of all suites above: 245 passed in 109.97s.
- `git diff --check`: clean.

No push, merge, deployment, or other remote mutation was performed.
